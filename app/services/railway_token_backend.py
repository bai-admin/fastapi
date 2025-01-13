from typing import Dict, Any, Optional, cast
import os
import json
import logging
import requests
from O365.utils.token import BaseTokenBackend  # type: ignore

logger = logging.getLogger(__name__)

class RailwayTokenBackend(BaseTokenBackend):
    """Token backend that stores tokens in Railway variables."""

    def __init__(self, token_path: Optional[str] = None) -> None:
        """Initialize the token backend.
        
        Args:
            token_path: Ignored, included for compatibility with base class.
        """
        super().__init__(token_path=token_path or '')
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
            
    def load_token(self) -> Dict[str, Any]:
        """Load the token from Railway variables."""
        token_str = self._get_variable('O365_TOKEN')
        if token_str:
            try:
                return cast(Dict[str, Any], json.loads(token_str))
            except json.JSONDecodeError:
                logger.error("Failed to decode token JSON from Railway variable")
        return {}
        
    def save_token(self, token: Dict[str, Any]) -> bool:
        """Save the token to Railway variables."""
        try:
            token_str = json.dumps(token)
            return self._set_variable('O365_TOKEN', token_str)
        except Exception as e:
            logger.error(f"Error saving token to Railway: {str(e)}")
            return False
            
    def delete_token(self) -> None:
        """Delete the token from Railway variables."""
        # Set to empty string since Railway doesn't have a delete API
        self._set_variable('O365_TOKEN', '') 