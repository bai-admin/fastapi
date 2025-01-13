#!/usr/bin/env python3
import os
import sys
import json
import logging
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

def get_railway_variables() -> Dict[str, str]:
    """Get variables from Railway environment."""
    url = 'https://backboard.railway.app/graphql/v2'
    query = '''
    query ($serviceId: String!) {
      variables(serviceId: $serviceId) {
        edges {
          node {
            name
            value
          }
        }
      }
    }
    '''
    
    try:
        api_token = os.getenv('RAILWAY_API_TOKEN')
        service_id = os.getenv('RAILWAY_SERVICE_ID')
        
        if not api_token or not service_id:
            logger.error("Missing required Railway environment variables")
            return {}
            
        response = requests.post(
            url,
            headers={
                'Authorization': f'Bearer {api_token}',
                'Content-Type': 'application/json'
            },
            json={
                'query': query,
                'variables': {
                    'serviceId': service_id
                }
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            variables = data.get('data', {}).get('variables', {}).get('edges', [])
            return {
                edge['node']['name']: edge['node']['value']
                for edge in variables
            }
        else:
            logger.error(f"Failed to get Railway variables: {response.text}")
            return {}
            
    except Exception as e:
        logger.error(f"Error getting Railway variables: {str(e)}")
        return {}

def cleanup_subscriptions() -> None:
    """Clean up any existing subscriptions."""
    try:
        from main import get_settings, get_o365_service
        
        settings = get_settings()
        o365_service = get_o365_service(settings)
        
        if o365_service.is_authenticated():
            subscription = o365_service.get_subscription()
            if subscription:
                logger.info("Found existing subscription, deleting...")
                o365_service.delete_subscription()
                logger.info("Successfully deleted subscription")
            else:
                logger.info("No existing subscription found")
        else:
            logger.warning("Not authenticated, skipping subscription cleanup")
            
    except Exception as e:
        logger.error(f"Error cleaning up subscriptions: {str(e)}")

def run_server() -> None:
    """Run the development server."""
    try:
        import uvicorn
        
        # Get Railway variables
        railway_vars = get_railway_variables()
        
        # Set environment variables
        for key, value in railway_vars.items():
            os.environ[key] = value
            
        # Clean up any existing subscriptions
        cleanup_subscriptions()
        
        # Run the server
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True
        )
        
    except Exception as e:
        logger.error(f"Error running server: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    run_server() 