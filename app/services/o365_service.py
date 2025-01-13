from typing import Optional, Dict, Any, Tuple, List, Union, cast
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from urllib.parse import urljoin
import secrets
import hashlib
import base64
from pathlib import Path
import logging
from O365 import Account  # type: ignore
from O365.utils.token import FileSystemTokenBackend  # type: ignore
from .railway_token_backend import RailwayTokenBackend
from .subscription_backend import BaseSubscriptionBackend, FileSystemSubscriptionBackend, RailwaySubscriptionBackend

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class O365Config:
    """Configuration for O365 service with environment-specific settings."""
    client_id: str
    client_secret: str
    tenant_id: str
    base_url: str
    scopes: List[str] = None  # type: ignore
    auth_flow_type: str = 'authorization'
    environment: str = 'local'

    @classmethod
    def from_env(cls) -> 'O365Config':
        """Create configuration from environment variables."""
        environment = os.getenv('RAILWAY_ENVIRONMENT_NAME', 'local')
        
        # Get base URL from Railway if available, otherwise use local
        if environment != 'local':
            base_url = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', '')}"
            logger.info(f"Using Railway domain for {environment} environment: {base_url}")
        else:
            base_url = os.getenv('APP_BASE_URL', 'http://localhost:8000')
            logger.info(f"Using local development URL: {base_url}")

        # Include Mail.ReadWrite for subscriptions
        scopes = ['offline_access', 'Mail.Read', 'Mail.ReadWrite']

        config = cls(
            client_id=os.getenv('AZURE_CLIENT_ID', ''),
            client_secret=os.getenv('AZURE_CLIENT_SECRET', ''),
            tenant_id=os.getenv('AZURE_TENANT_ID', ''),
            base_url=base_url,
            scopes=scopes,
            environment=environment
        )
        
        logger.info(f"Initialized O365Config for {environment} environment")
        logger.info(f"Using redirect URI: {config.redirect_uri}")
        
        return config

    @property
    def redirect_uri(self) -> str:
        """Get the full callback URL for OAuth."""
        return urljoin(self.base_url, '/auth/callback')

    @property
    def webhook_uri(self) -> str:
        """Get the full webhook URL for subscriptions."""
        return urljoin(self.base_url, '/webhooks/messages')

class O365Service:
    """Service for interacting with Office 365."""

    def __init__(self, config: Optional[O365Config] = None) -> None:
        """Initialize the service with optional config."""
        self.config = config or O365Config.from_env()
        
        # Set up token backend based on environment
        if self.config.environment != 'local':
            self.token_backend = RailwayTokenBackend()
            self.subscription_backend: BaseSubscriptionBackend = RailwaySubscriptionBackend()
        else:
            token_path = Path.home() / '.o365' / 'token.txt'
            self.token_backend = FileSystemTokenBackend(token_path=str(token_path))
            self.subscription_backend = FileSystemSubscriptionBackend()
            
        self._account: Optional[Account] = None
        self._code_verifier: Optional[str] = None

    def _generate_code_verifier(self) -> str:
        """Generate a code verifier for PKCE."""
        token = secrets.token_urlsafe(32)
        return token
        
    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate a code challenge for PKCE."""
        sha256_hash = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(sha256_hash).decode().rstrip('=')
        return code_challenge

    @property
    def account(self) -> Account:
        """Get or create the O365 Account instance."""
        if not self._account:
            self._account = Account(
                credentials=(self.config.client_id, self.config.client_secret),
                auth_flow_type=self.config.auth_flow_type,
                tenant_id=self.config.tenant_id,
                scopes=self.config.scopes,
                token_backend=self.token_backend
            )
        return self._account

    def get_auth_url(self) -> Tuple[Optional[str], Optional[str]]:
        """Get the authorization URL for OAuth flow with PKCE."""
        try:
            # Generate and store code verifier for PKCE
            self._code_verifier = self._generate_code_verifier()
            code_challenge = self._generate_code_challenge(self._code_verifier)
            
            auth_url, state = self.account.connection.get_authorization_url(
                requested_scopes=self.config.scopes,
                redirect_uri=self.config.redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method='S256'
            )
            
            logger.info(f"Generated auth URL for {self.config.environment} environment")
            logger.debug(f"Auth URL: {auth_url}")
            
            return auth_url, state
        except Exception as e:
            self._log_error("Error getting auth URL", e)
            return None, None

    def handle_auth_callback(self, auth_response_url: str) -> bool:
        """Handle the OAuth callback with PKCE verification."""
        try:
            if not self._code_verifier:
                self._log_error("Missing code verifier", ValueError("Code verifier not found"))
                return False
                
            result = self.account.connection.request_token(
                authorization_url=auth_response_url,
                redirect_uri=self.config.redirect_uri,
                code_verifier=self._code_verifier
            )
            
            # Clear the code verifier after use
            self._code_verifier = None
            
            if result:
                logger.info(f"Successfully authenticated in {self.config.environment} environment")
            else:
                logger.error(f"Authentication failed in {self.config.environment} environment")
                
            return bool(result)
        except Exception as e:
            self._log_error("Error handling auth callback", e)
            return False

    def is_authenticated(self) -> bool:
        """Check if the service is authenticated."""
        return bool(self.token_backend.check_token())
        
    def get_token(self) -> Optional[Dict[str, Any]]:
        """Get the current token if it exists."""
        token = self.token_backend.load_token()
        return dict(token) if token else None

    def search_recent_messages(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for recent messages."""
        try:
            if not self.account.is_authenticated:
                logger.warning(f"Account not authenticated in {self.config.environment} environment")
                return []

            mailbox = self.account.mailbox()
            query = mailbox.new_query()
            query.received_date_time.greater_equal(datetime.now() - timedelta(days=days))

            logger.info(f"Searching messages from last {days} days in {self.config.environment} environment")
            messages = []
            for msg in mailbox.get_messages(query=query, limit=limit):
                messages.append({
                    "subject": msg.subject,
                    "from": msg.sender.address,
                    "received": msg.received.strftime('%Y-%m-%d %H:%M:%S')
                })
            
            logger.info(f"Found {len(messages)} messages")
            return messages

        except Exception as e:
            self._log_error("Error searching messages", e)
            return []

    def _log_error(self, message: str, error: Exception) -> None:
        """Log errors with timestamp and environment context."""
        logger.error(f"[{self.config.environment}] {message}: {str(error)}")
        
        # Also log to file for persistence
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_file = f'search_results_{self.config.environment}.log'
        
        try:
            with open(log_file, 'a') as f:
                f.write(f'[{timestamp}] {message}: {str(error)}\n')
        except Exception as e:
            logger.error(f"Failed to write to log file {log_file}: {str(e)}")

    def create_subscription(self, expiration_days: int = 7) -> Dict[str, Any]:
        """Create a new subscription for inbox messages."""
        if not self.is_authenticated():
            raise ValueError("Authentication required before creating subscription")
            
        # Delete any existing subscription
        existing = self.subscription_backend.get_subscription()
        if existing and 'id' in existing:
            try:
                self.delete_subscription(existing['id'])
            except Exception as e:
                self._log_error("Failed to delete existing subscription", e)
                
        # Create new subscription
        expiration_days = min(expiration_days, 7)
        expiration_date = (datetime.utcnow() + timedelta(days=expiration_days)).isoformat() + 'Z'
        
        subscription_data = {
            "changeType": "created,updated",
            "notificationUrl": self.config.webhook_uri,
            "resource": "me/mailFolders('Inbox')/messages",
            "expirationDateTime": expiration_date,
            "clientState": secrets.token_urlsafe(32),
            "latestSupportedTlsVersion": "v1_2",
            "includeResourceData": True
        }
        
        try:
            response = self.account.connection.post(
                url='/subscriptions',
                data=subscription_data,
                headers={'Prefer': 'outlook.body-content-type="text"'}
            )
            
            if response.status_code == 201:
                subscription = cast(Dict[str, Any], response.json())
                self.subscription_backend.save_subscription(subscription)
                logger.info("Successfully created and stored new subscription")
                return subscription
            else:
                raise ValueError(f"Failed to create subscription: {response.text}")
                
        except Exception as e:
            self._log_error("Error creating subscription", e)
            raise
            
    def get_subscription(self) -> Optional[Dict[str, Any]]:
        """Get the current subscription if it exists."""
        return self.subscription_backend.get_subscription()
        
    def renew_subscription(self, subscription_id: Optional[str] = None, 
                         expiration_days: int = 7) -> Dict[str, Any]:
        """Renew an existing subscription."""
        if subscription_id is None:
            stored = self.subscription_backend.get_subscription()
            if not stored or 'id' not in stored:
                raise ValueError("No subscription ID provided or stored")
            subscription_id = stored['id']
            
        expiration_days = min(expiration_days, 7)
        expiration_date = (datetime.utcnow() + timedelta(days=expiration_days)).isoformat() + 'Z'
        
        update_data = {
            "expirationDateTime": expiration_date
        }
        
        try:
            response = self.account.connection.patch(
                url=f'/subscriptions/{subscription_id}',
                data=update_data
            )
            
            if response.status_code == 200:
                subscription = cast(Dict[str, Any], response.json())
                self.subscription_backend.save_subscription(subscription)
                logger.info(f"Successfully renewed subscription {subscription_id}")
                return subscription
            else:
                raise ValueError(f"Failed to renew subscription: {response.text}")
                
        except Exception as e:
            self._log_error("Error renewing subscription", e)
            raise
            
    def delete_subscription(self, subscription_id: Optional[str] = None) -> bool:
        """Delete a subscription."""
        if subscription_id is None:
            stored = self.subscription_backend.get_subscription()
            if not stored or 'id' not in stored:
                raise ValueError("No subscription ID provided or stored")
            subscription_id = stored['id']
            
        try:
            response = self.account.connection.delete(
                url=f'/subscriptions/{subscription_id}'
            )
            
            if response.status_code == 204:
                self.subscription_backend.delete_subscription()
                logger.info(f"Successfully deleted subscription {subscription_id}")
                return True
            else:
                raise ValueError(f"Failed to delete subscription: {response.text}")
                
        except Exception as e:
            self._log_error("Error deleting subscription", e)
            raise

    def get_message_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get full details of a message by its ID."""
        try:
            # Get the message with all properties including body and attachments
            response = self.account.connection.get(
                url=f'/messages/{message_id}',
                params={
                    '$select': 'id,subject,body,from,toRecipients,ccRecipients,bccRecipients,' +
                              'receivedDateTime,hasAttachments,attachments,importance,categories'
                }
            )
            
            if response.status_code == 200:
                message_data = cast(Dict[str, Any], response.json())
                logger.info(f"Retrieved details for message {message_id}")
                return message_data
            else:
                logger.error(f"Failed to get message {message_id}: {response.text}")
                return None
                
        except Exception as e:
            self._log_error(f"Error getting message details for {message_id}", e)
            return None

    def check_subscription_expiration(self) -> Optional[timedelta]:
        """Check how long until the current subscription expires."""
        subscription = self.subscription_backend.get_subscription()
        if not subscription or 'expirationDateTime' not in subscription:
            return None
            
        try:
            expiration = datetime.fromisoformat(subscription['expirationDateTime'].rstrip('Z'))
            now = datetime.utcnow()
            
            if expiration > now:
                return expiration - now
            return None
            
        except Exception as e:
            self._log_error("Error checking subscription expiration", e)
            return None
            
    def should_renew_subscription(self, renewal_threshold: timedelta = timedelta(days=1)) -> bool:
        """Check if subscription should be renewed based on expiration time."""
        time_remaining = self.check_subscription_expiration()
        if not time_remaining:
            return False
            
        return time_remaining <= renewal_threshold
        
    def ensure_subscription(self, notification_url: Optional[str] = None) -> Dict[str, Any]:
        """Ensure a valid subscription exists, creating or renewing as needed."""
        current = self.subscription_backend.get_subscription()
        
        # If no subscription exists, create new one
        if not current:
            if not notification_url:
                raise ValueError("notification_url required to create new subscription")
            return self.create_subscription()
            
        # If subscription exists but is expired or near expiration, renew it
        if self.should_renew_subscription():
            try:
                return self.renew_subscription(current['id'])
            except Exception as e:
                # If renewal fails, try creating a new subscription
                self._log_error("Failed to renew subscription, creating new one", e)
                if not notification_url:
                    raise ValueError("notification_url required to create new subscription")
                return self.create_subscription()
                
        return current
        
    def handle_lifecycle_event(self, lifecycle_event: Dict[str, Any]) -> None:
        """Handle subscription lifecycle events from Microsoft Graph."""
        event_type = lifecycle_event.get('lifecycleEvent')
        subscription_id = lifecycle_event.get('subscriptionId')
        
        logger.info(f"Handling lifecycle event: {event_type} for subscription {subscription_id}")
        
        if event_type == 'subscriptionRemoved':
            # Clean up the stored subscription if it matches
            stored = self.subscription_backend.get_subscription()
            if stored and stored.get('id') == subscription_id:
                self.subscription_backend.delete_subscription()
                
        elif event_type == 'reauthorizationRequired':
            # Force token refresh
            try:
                self.account.connection.refresh_token()
                # Try to renew the subscription
                if subscription_id:
                    self.renew_subscription(subscription_id)
            except Exception as e:
                self._log_error("Failed to reauthorize subscription", e)
                # Clean up the invalid subscription
                self.subscription_backend.delete_subscription() 