import json
import os
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class BaseSubscriptionBackend(ABC):
    """Base class for subscription storage backends."""
    
    @abstractmethod
    def save_subscription(self, subscription_data: Dict[str, Any]) -> None:
        """Save subscription data."""
        pass
        
    @abstractmethod
    def get_subscription(self) -> Optional[Dict[str, Any]]:
        """Get subscription data."""
        pass
        
    @abstractmethod
    def delete_subscription(self) -> None:
        """Delete subscription data."""
        pass

class FileSystemSubscriptionBackend(BaseSubscriptionBackend):
    """Stores subscription data in a JSON file."""
    
    def __init__(self, subscription_path: Optional[str] = None):
        """Initialize with optional path."""
        if subscription_path:
            self.subscription_file = Path(subscription_path)
        else:
            self.subscription_file = Path.home() / '.o365' / 'subscription.json'
            
        self.subscription_file.parent.mkdir(exist_ok=True)
        
    def save_subscription(self, subscription_data: Dict[str, Any]) -> None:
        """Save subscription data to file."""
        subscription_data['stored_at'] = datetime.utcnow().isoformat()
        
        with open(self.subscription_file, 'w') as f:
            json.dump(subscription_data, f)
            logger.info(f"Saved subscription data to {self.subscription_file}")
            
    def get_subscription(self) -> Optional[Dict[str, Any]]:
        """Get subscription data from file."""
        if not self.subscription_file.exists():
            return None
            
        try:
            with open(self.subscription_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode subscription data from {self.subscription_file}")
            return None
            
    def delete_subscription(self) -> None:
        """Delete subscription file."""
        if self.subscription_file.exists():
            self.subscription_file.unlink()
            logger.info(f"Deleted subscription file {self.subscription_file}")

class RailwaySubscriptionBackend(BaseSubscriptionBackend):
    """Stores subscription data in Railway environment variables."""
    
    def __init__(self):
        """Initialize the backend."""
        from .railway_token_backend import RailwayTokenBackend
        self.railway_backend = RailwayTokenBackend()
        self.subscription_key = 'O365_SUBSCRIPTION'
        
    def save_subscription(self, subscription_data: Dict[str, Any]) -> None:
        """Save subscription data to Railway environment."""
        subscription_data['stored_at'] = datetime.utcnow().isoformat()
        self.railway_backend._variable_upsert(
            self.subscription_key,
            json.dumps(subscription_data)
        )
        logger.info("Saved subscription data to Railway environment")
        
    def get_subscription(self) -> Optional[Dict[str, Any]]:
        """Get subscription data from Railway environment."""
        variables = self.railway_backend._get_variables()
        subscription_json = variables.get(self.subscription_key)
        
        if not subscription_json:
            return None
            
        try:
            return json.loads(subscription_json)
        except json.JSONDecodeError:
            logger.error("Failed to decode subscription data from Railway environment")
            return None
            
    def delete_subscription(self) -> None:
        """Delete subscription from Railway environment."""
        self.railway_backend._variable_upsert(self.subscription_key, '')
        logger.info("Deleted subscription data from Railway environment") 