# utils.py
import secrets
import logging
import redis
from django.conf import settings

logger = logging.getLogger(__name__)

def generate_otp(length=6):
    """
    Generates a cryptographically secure random numeric OTP.
    """
    return ''.join(secrets.choice('0123456789') for _ in range(length))

def get_redis_connection():
    """
    Establishes and returns a connection to Redis.
    """
    try:
        redis_connection = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        redis_connection.ping()  # Test the connection
        return redis_connection
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Could not connect to Redis: {e}")
        return None