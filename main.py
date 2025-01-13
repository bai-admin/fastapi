from fastapi import FastAPI, Request, Depends, HTTPException, Response, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from services.o365_service import O365Service, O365Config
from config import Settings, get_settings
from typing import Annotated, Optional
from functools import lru_cache
import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Background task state
subscription_check_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application."""
    # Start background tasks
    global subscription_check_task
    subscription_check_task = asyncio.create_task(periodic_subscription_check())
    
    yield
    
    # Cleanup on shutdown
    if subscription_check_task:
        subscription_check_task.cancel()
        try:
            await subscription_check_task
        except asyncio.CancelledError:
            pass

    # Delete subscription on local dev server shutdown
    try:
        settings = get_settings()
        # Only cleanup subscription if we're running locally
        if settings.app_base_url.startswith(('http://localhost', 'https://localhost')):
            logger.info("Local dev server shutting down, cleaning up subscription...")
            o365_service = get_o365_service(settings)
            if o365_service.is_authenticated():
                success = o365_service.delete_subscription()
                if success:
                    logger.info("Successfully deleted subscription on shutdown")
                else:
                    logger.warning("Failed to delete subscription on shutdown")
    except Exception as e:
        logger.error(f"Error cleaning up subscription on shutdown: {str(e)}")

app = FastAPI(lifespan=lifespan)

# Create logs directory if it doesn't exist
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

async def periodic_subscription_check():
    """Background task that periodically checks and renews subscriptions."""
    while True:
        try:
            # Get a new service instance
            settings = get_settings()
            o365_service = get_o365_service(settings)
            
            if o365_service.is_authenticated():
                if o365_service.should_renew_subscription():
                    logger.info("Periodic check: Subscription needs renewal")
                    subscription = o365_service.ensure_subscription(
                        notification_url=o365_service.config.webhook_uri
                    )
                    logger.info(f"Subscription renewed, new expiration: {subscription['expirationDateTime']}")
                else:
                    logger.debug("Periodic check: Subscription is valid")
            
        except Exception as e:
            logger.error(f"Error in periodic subscription check: {str(e)}")
            
        # Check every hour
        await asyncio.sleep(3600)  # 1 hour

def save_notification_to_file(notification: dict):
    """Save a webhook notification to a file with timestamp and message details."""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    notification_file = LOGS_DIR / f"notification_{timestamp}.json"
    
    # Add metadata to the notification
    notification_data = {
        "received_at": datetime.utcnow().isoformat(),
        "notification": notification
    }
    
    try:
        with open(notification_file, 'w') as f:
            json.dump(notification_data, f, indent=2)
        logger.info(f"Saved notification to {notification_file}")
    except Exception as e:
        logger.error(f"Failed to save notification to file: {str(e)}")

async def check_and_renew_subscription(o365_service: O365Service):
    """Background task to check subscription status and renew if needed."""
    try:
        if o365_service.should_renew_subscription():
            logger.info("Subscription needs renewal, attempting to renew...")
            subscription = o365_service.ensure_subscription()
            logger.info(f"Subscription renewed, new expiration: {subscription['expirationDateTime']}")
    except Exception as e:
        logger.error(f"Failed to renew subscription: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Run when the FastAPI app starts up."""
    logger.info("Starting up FastAPI application")
    LOGS_DIR.mkdir(exist_ok=True)

@lru_cache()
def get_o365_service(settings: Annotated[Settings, Depends(get_settings)]) -> O365Service:
    """Dependency injection for O365Service"""
    config = O365Config(
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        tenant_id=settings.azure_tenant_id,
        base_url=settings.app_base_url
    )
    return O365Service(config)

@app.get("/search/messages")
async def search_messages_endpoint(
    o365_service: Annotated[O365Service, Depends(get_o365_service)]
):
    """
    Search for recent messages in O365 mailbox.
    If not authenticated, redirects to Microsoft login.
    """
    try:
        if not o365_service.account.is_authenticated:
            auth_url, state = o365_service.get_auth_url()
            if auth_url:
                return RedirectResponse(auth_url)
            raise HTTPException(
                status_code=500,
                detail="Failed to get authentication URL"
            )
        
        messages = o365_service.search_recent_messages()
        return JSONResponse({
            "status": "success",
            "data": messages
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.get("/auth/callback")
async def auth_callback(
    request: Request,
    o365_service: Annotated[O365Service, Depends(get_o365_service)]
):
    """
    OAuth callback endpoint that Microsoft redirects to after user login.
    The URL will contain an authorization code that we exchange for an access token.
    """
    try:
        # Get the full URL including all query parameters
        auth_response_url = str(request.url)
        
        # Exchange the authorization code for an access token
        result = o365_service.handle_auth_callback(auth_response_url)
        
        if result:
            # Redirect back to the messages endpoint now that we're authenticated
            return RedirectResponse(
                url="/search/messages",
                status_code=303  # See Other - for changing from GET to GET
            )
        else:
            raise HTTPException(
                status_code=401,
                detail="Authentication failed"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error in callback: {str(e)}"
        )

@app.post("/webhooks/messages")
async def handle_webhook(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    o365_service: Annotated[O365Service, Depends(get_o365_service)]
):
    """Handle incoming webhook notifications from Microsoft Graph."""
    try:
        # Get the raw request body
        body = await request.body()
        data = json.loads(body)
        
        # Save the raw webhook data first
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
        raw_file = LOGS_DIR / f"webhook_raw_{timestamp}.json"
        with open(raw_file, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved raw webhook data to {raw_file}")
        
        # Handle validation request first (doesn't require subscription check)
        validation_token = request.query_params.get('validationToken')
        if validation_token:
            logger.info("Responding to subscription validation request")
            response.headers['Content-Type'] = 'text/plain'
            return validation_token
            
        # Get stored subscription to verify clientState
        subscription = o365_service.get_subscription()
        if not subscription:
            logger.error("No subscription found for webhook validation")
            raise HTTPException(status_code=404, detail="Subscription not found")
            
        # Check for lifecycle notifications
        if data.get('lifecycleEvent'):
            logger.info(f"Received lifecycle event: {data['lifecycleEvent']}")
            o365_service.handle_lifecycle_event(data)
            return {"status": "success"}
            
        # Validate the clientState for regular notifications
        if data.get('clientState') != subscription.get('clientState'):
            logger.error("Invalid clientState in webhook notification")
            raise HTTPException(status_code=401, detail="Invalid clientState")
            
        # Process notifications
        notifications = data.get('value', [])
        for notification in notifications:
            # Save each notification separately
            save_notification_to_file(notification)
            
            # Log basic info
            logger.info(f"Received notification type: {notification.get('changeType')}")
            
            # Get message details if available
            resource_data = notification.get('resourceData', {})
            message_id = resource_data.get('id')
            if message_id:
                try:
                    # Get the full message details
                    message = o365_service.get_message_details(message_id)
                    if message:
                        # Save full message details
                        message_file = LOGS_DIR / f"message_{message_id}_{timestamp}.json"
                        with open(message_file, 'w') as f:
                            json.dump(message, f, indent=2)
                        logger.info(f"Saved full message details to {message_file}")
                except Exception as e:
                    logger.error(f"Failed to get message details for {message_id}: {str(e)}")
        
        # Schedule subscription check/renewal
        background_tasks.add_task(check_and_renew_subscription, o365_service)
                
        return {"status": "success"}
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/subscriptions/create")
async def create_subscription(
    o365_service: Annotated[O365Service, Depends(get_o365_service)]
):
    """Create a new subscription for inbox messages."""
    try:
        if not o365_service.is_authenticated():
            raise HTTPException(status_code=401, detail="Authentication required")
            
        subscription = o365_service.create_subscription()
        return subscription
    except Exception as e:
        logger.error(f"Error creating subscription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/subscriptions/renew")
async def renew_subscription(
    o365_service: Annotated[O365Service, Depends(get_o365_service)]
):
    """Renew the current subscription."""
    try:
        if not o365_service.is_authenticated():
            raise HTTPException(status_code=401, detail="Authentication required")
            
        subscription = o365_service.renew_subscription()
        return subscription
    except Exception as e:
        logger.error(f"Error renewing subscription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/subscriptions/delete")
async def delete_subscription(
    o365_service: Annotated[O365Service, Depends(get_o365_service)]
):
    """Delete the current subscription."""
    try:
        if not o365_service.is_authenticated():
            raise HTTPException(status_code=401, detail="Authentication required")
            
        success = o365_service.delete_subscription()
        return {"success": success}
    except Exception as e:
        logger.error(f"Error deleting subscription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/subscriptions/current")
async def get_subscription(
    o365_service: Annotated[O365Service, Depends(get_o365_service)]
):
    """Get the current subscription if it exists."""
    try:
        if not o365_service.is_authenticated():
            raise HTTPException(status_code=401, detail="Authentication required")
            
        subscription = o365_service.get_subscription()
        if not subscription:
            raise HTTPException(status_code=404, detail="No active subscription")
        return subscription
    except Exception as e:
        logger.error(f"Error getting subscription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))