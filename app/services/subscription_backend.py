from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, cast
import os
import json
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

class BaseSubscriptionBackend(ABC):
    """Base class for subscription storage backends."""
    
    @abstractmethod
    def get_subscription(self) -> Optional[Dict[str, Any]]:
        """Get the current subscription if it exists."""
        pass
        
    @abstractmethod
    def save_subscription(self, subscription: Dict[str, Any]) -> bool:
        """Save a subscription."""
        pass
        
    @abstractmethod
    def delete_subscription(self) -> None:
        """Delete the current subscription."""
        pass

class FileSystemSubscriptionBackend(BaseSubscriptionBackend):
    """Subscription backend that stores data in local files."""
    
    def __init__(self, subscription_path: Optional[str] = None) -> None:
        """Initialize the backend.
        
        Args:
            subscription_path: Path to subscription file. Defaults to ~/.o365/subscription.json
        """
        if subscription_path:
            self.subscription_path = Path(subscription_path)
        else:
            self.subscription_path = Path.home() / '.o365' / 'subscription.json'
            
        # Create directory if it doesn't exist
        self.subscription_path.parent.mkdir(parents=True, exist_ok=True)
        
    def get_subscription(self) -> Optional[Dict[str, Any]]:
        """Get the current subscription if it exists."""
        try:
            if self.subscription_path.exists():
                with open(self.subscription_path) as f:
                    return cast(Dict[str, Any], json.load(f))
            return None
        except Exception as e:
            logger.error(f"Error loading subscription: {str(e)}")
            return None
            
    def save_subscription(self, subscription: Dict[str, Any]) -> bool:
        """Save a subscription."""
        try:
            with open(self.subscription_path, 'w') as f:
                json.dump(subscription, f)
            return True
        except Exception as e:
            logger.error(f"Error saving subscription: {str(e)}")
            return False
            
    def delete_subscription(self) -> None:
        """Delete the current subscription."""
        try:
            if self.subscription_path.exists():
                self.subscription_path.unlink()
        except Exception as e:
            logger.error(f"Error deleting subscription: {str(e)}")

class RailwaySubscriptionBackend(BaseSubscriptionBackend):
    """Subscription backend that stores data in Railway variables."""
    
    def __init__(self) -> None:
        """Initialize the backend."""
        self.service_id = os.getenv('RAILWAY_SERVICE_ID')
        self.project_id = os.getenv('RAILWAY_PROJECT_ID')
        self.environment = os.getenv('RAILWAY_ENVIRONMENT_NAME')
        self.api_token = os.getenv('RAILWAY_API_TOKEN')
        
        if not all([self.service_id, self.project_id, self.environment, self.api_token]):
            raise ValueError("Missing required Railway environment variables")
            
        self.headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }
        
    def _get_variable(self, name: str) -> Optional[str]:
        """Get a Railway variable value."""
        url = 'https://backboard.railway.app/graphql/v2'
        query = '''
        query ($serviceId: String!, $name: String!) {
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
            response = requests.post(
                url,
                headers=self.headers,
                json={
                    'query': query,
                    'variables': {
                        'serviceId': self.service_id,
                        'name': name
                    }
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                variables = data.get('data', {}).get('variables', {}).get('edges', [])
                for edge in variables:
                    node = edge.get('node', {})
                    if node.get('name') == name:
                        return node.get('value')
            return None
            
        except Exception as e:
            logger.error(f"Error getting Railway variable {name}: {str(e)}")
            return None
            
    def _set_variable(self, name: str, value: str) -> bool:
        """Set a Railway variable value."""
        url = 'https://backboard.railway.app/graphql/v2'
        mutation = '''
        mutation ($serviceId: String!, $name: String!, $value: String!) {
          variableCreate(
            input: {
              serviceId: $serviceId
              name: $name
              value: $value
            }
          ) {
            id
          }
        }
        '''
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json={
                    'query': mutation,
                    'variables': {
                        'serviceId': self.service_id,
                        'name': name,
                        'value': value
                    }
                }
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error setting Railway variable {name}: {str(e)}")
            return False
            
    def get_subscription(self) -> Optional[Dict[str, Any]]:
        """Get the current subscription if it exists."""
        subscription_str = self._get_variable('O365_SUBSCRIPTION')
        if subscription_str:
            try:
                return cast(Dict[str, Any], json.loads(subscription_str))
            except json.JSONDecodeError:
                logger.error("Failed to decode subscription JSON from Railway variable")
        return None
        
    def save_subscription(self, subscription: Dict[str, Any]) -> bool:
        """Save a subscription."""
        try:
            subscription_str = json.dumps(subscription)
            return self._set_variable('O365_SUBSCRIPTION', subscription_str)
        except Exception as e:
            logger.error(f"Error saving subscription to Railway: {str(e)}")
            return False
            
    def delete_subscription(self) -> None:
        """Delete the current subscription."""
        # Set to empty string since Railway doesn't have a delete API
        self._set_variable('O365_SUBSCRIPTION', '') 