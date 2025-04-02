"""
Security settings for Langflow.
"""
import os
from pydantic import BaseModel


class SecuritySettings(BaseModel):
    """Security settings for the application."""
    
    # Rate limiting settings
    RATE_LIMITING_ENABLED: bool = os.getenv("RATE_LIMITING_ENABLED", "True").lower() in ("true", "1", "t")
    
    # Redis settings for rate limiting
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    
    # IP Ban settings
    IP_BAN_ENABLED: bool = os.getenv("IP_BAN_ENABLED", "False").lower() in ("true", "1", "t")
    IP_BAN_THRESHOLD: int = int(os.getenv("IP_BAN_THRESHOLD", "10"))  # Number of failed attempts before ban
    IP_BAN_DURATION: int = int(os.getenv("IP_BAN_DURATION", "3600"))  # Ban duration in seconds (1 hour) 