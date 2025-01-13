import json
import os
from typing import Optional
import requests
from O365.utils.token import BaseTokenBackend, Token

class RailwayTokenBackend(BaseTokenBackend):
    """Token backend that stores tokens in Railway environment variables via GraphQL API."""
    
    def __init__(self, token_path: str = None):
        """Initialize the backend.
        
        Args:
            token_path: Ignored, kept for compatibility with BaseTokenBackend
        """
        super().__init__()
        self.api_token = os.getenv('RAILWAY_API_TOKEN')
        if not self.api_token:
            raise ValueError('RAILWAY_API_TOKEN environment variable is required')
            
        self.project_id = os.getenv('RAILWAY_PROJECT_ID')
        self.environment_id = os.getenv('RAILWAY_ENVIRONMENT_ID')
        self.service_id = os.getenv('RAILWAY_SERVICE_ID')
        
        if not all([self.project_id, self.environment_id, self.service_id]):
            raise ValueError('Missing required Railway environment variables')
            
        self.api_url = 'https://backboard.railway.app/graphql/v2'
        
    def _get_headers(self) -> dict:
        """Get headers for Railway API requests."""
        return {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
        }
        
    def _variable_upsert(self, key: str, value: str):
        """Upsert a variable in Railway."""
        mutation = """
        mutation variableUpsert($input: VariableUpsertInput!) {
            variableUpsert(input: $input)
        }
        """
        
        variables = {
            "input": {
                "name": key,
                "value": value,
                "environmentId": self.environment_id,
                "projectId": self.project_id,
                "serviceId": self.service_id
            }
        }
        
        response = requests.post(
            self.api_url,
            headers=self._get_headers(),
            json={"query": mutation, "variables": variables}
        )
        response.raise_for_status()
        
    def _get_variables(self) -> dict:
        """Get variables from Railway."""
        query = """
        query variables($environmentId: String!, $projectId: String!, $serviceId: String!) {
            variables(
                environmentId: $environmentId
                projectId: $projectId
                serviceId: $serviceId
            )
        }
        """
        
        variables = {
            "environmentId": self.environment_id,
            "projectId": self.project_id,
            "serviceId": self.service_id
        }
        
        response = requests.post(
            self.api_url,
            headers=self._get_headers(),
            json={"query": query, "variables": variables}
        )
        response.raise_for_status()
        return response.json().get('data', {}).get('variables', {})

    def load_token(self) -> Optional[Token]:
        """Load token from Railway environment variables."""
        variables = self._get_variables()
        token_data = variables.get('O365_TOKEN')
        
        if not token_data:
            return None
            
        try:
            token_dict = json.loads(token_data)
            return Token(token_dict)
        except (json.JSONDecodeError, KeyError):
            return None
            
    def save_token(self, token: Token):
        """Save token to Railway environment variables."""
        if not isinstance(token, Token):
            raise ValueError('token must be an instance of Token')
            
        token_data = json.dumps(dict(token))
        self._variable_upsert('O365_TOKEN', token_data)
        
    def delete_token(self):
        """Delete token from Railway environment variables."""
        self._variable_upsert('O365_TOKEN', '')  # Railway API doesn't support deletion, so we set to empty
        
    def check_token(self) -> bool:
        """Check if token exists in Railway environment variables."""
        variables = self._get_variables()
        return 'O365_TOKEN' in variables 