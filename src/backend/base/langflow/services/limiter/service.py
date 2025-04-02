"""
Rate limiter service for Langflow.
Provides rate limiting functionality for API endpoints using fastapi-limiter.
"""
import asyncio
from typing import Optional, Any

import redis.asyncio as redis
from fastapi import Request, Response
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from loguru import logger

from langflow.services.deps import get_settings_service

# Cache for initialized limiter
_limiter_initialized = False


async def init_limiter():
    """Initialize the FastAPILimiter with Redis connection."""
    global _limiter_initialized
    
    # Skip if already initialized
    if _limiter_initialized:
        return
    
    settings = get_settings_service()
    
    # If rate limiting is disabled, skip initialization
    if not settings.security_settings.RATE_LIMITING_ENABLED:
        logger.info("Rate limiting is disabled")
        return
    
    # Configure Redis connection
    redis_host = settings.security_settings.REDIS_HOST
    redis_port = settings.security_settings.REDIS_PORT
    
    try:
        # Connect to Redis
        redis_connection = redis.Redis(
            host=redis_host,
            port=redis_port,
            encoding="utf-8",
            decode_responses=True
        )
        
        # Test connection
        await redis_connection.ping()
        
        # Initialize FastAPILimiter
        await FastAPILimiter.init(redis_connection)
        
        _limiter_initialized = True
        logger.info(f"Rate limiter initialized with Redis at {redis_host}:{redis_port}")
        
    except Exception as e:
        logger.error(f"Failed to initialize rate limiter: {str(e)}")
        logger.warning("Rate limiting will be disabled")


# Helper function to create custom rate limiters
def create_rate_limiter(
    times: int = 5, 
    seconds: int = 60
) -> Any:
    """
    Create a rate limiter with custom limits.
    
    Args:
        times: Maximum number of requests allowed within the time window
        seconds: Time window in seconds
    
    Returns:
        RateLimiter dependency or a pass-through function if rate limiting is disabled
    """
    settings = get_settings_service()
    
    # If rate limiting is disabled, return a pass-through function
    if not settings.security_settings.RATE_LIMITING_ENABLED:
        async def no_limiter(request: Request, response: Response) -> None:
            return None
        return no_limiter
    
    # Return the actual rate limiter
    return RateLimiter(
        times=times,
        seconds=seconds
    )


# Commonly used rate limiters
# Login rate limiter: 5 attempts per minute
login_limiter = create_rate_limiter(times=5, seconds=60)

# Password reset request limiter: 3 attempts per 10 minutes
password_reset_limiter = create_rate_limiter(times=3, seconds=600)

# Email verification limiter: 5 attempts per 10 minutes
email_verification_limiter = create_rate_limiter(times=5, seconds=600)

# Registration limiter: 3 attempts per hour per IP
registration_limiter = create_rate_limiter(times=3, seconds=3600) 