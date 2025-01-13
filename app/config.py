from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path
import os
import logging
from typing import Any, Dict, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application settings"""
    azure_client_id: str
    azure_client_secret: str
    azure_tenant_id: str
    
    # Base URL configuration with Railway support
    app_base_url: str = "http://localhost:8000"  # Default to local development URL
    
    # Other settings
    log_file: str = "search_results.log"
    token_path: str = str(Path("tokens").absolute())  # Absolute path to token directory
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs: Any) -> None:
        """Initialize settings with environment variables and Railway configuration."""
        super().__init__(**kwargs)
        
        # Set base URL based on environment
        if os.getenv('RAILWAY_ENVIRONMENT_NAME'):
            # We're in Railway
            env_name = os.getenv('RAILWAY_ENVIRONMENT_NAME')
            public_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
            
            if not public_domain:
                error_msg = f"RAILWAY_PUBLIC_DOMAIN not set in Railway environment: {env_name}"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
            self.app_base_url = f"https://{public_domain}"
            logger.info(f"Using Railway domain for {env_name} environment: {self.app_base_url}")
        else:
            # Local development
            logger.info("Using local development URL: http://localhost:8000")
            
        # Log environment info
        logger.info(f"Current environment: {os.getenv('RAILWAY_ENVIRONMENT_NAME', 'local')}")
        logger.info(f"Project name: {os.getenv('RAILWAY_PROJECT_NAME', 'local')}")
        logger.info(f"Service name: {os.getenv('RAILWAY_SERVICE_NAME', 'local')}")

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings() 