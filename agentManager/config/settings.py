"""Settings and configuration management for agentManager.

This module handles application settings validation, including weak password
detection for production environments.
"""

import logging
import os
from typing import Set

logger = logging.getLogger(__name__)

# Common weak passwords to detect
WEAK_PASSWORDS = {
    'password',
    'admin',
    'minioadmin',
    'test',
    'demo',
    '123456',
    'password123',
    'admin123',
}


def validate_settings(settings: dict[str, str] | None = None) -> None:
    """Validate application settings for security issues.

    Checks for weak passwords in critical environment variables or provided settings.
    Raises RuntimeError if weak passwords are detected.

    Args:
        settings: Optional dict of settings to validate.
                 If None, reads from environment variables.

    Raises:
        RuntimeError: If weak passwords are detected in settings
    """
    if settings is None:
        # Read from environment variables
        settings = {
            'POSTGRES_PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'REDIS_PASSWORD': os.getenv('REDIS_PASSWORD', ''),
            'MINIO_SECRET_KEY': os.getenv('MINIO_SECRET_KEY', ''),
            'SECRET_KEY': os.getenv('SECRET_KEY', ''),
            'QDRANT_API_KEY': os.getenv('QDRANT_API_KEY', ''),
        }

    weak_found: Set[str] = set()

    for key, value in settings.items():
        if value and value.lower() in WEAK_PASSWORDS:
            weak_found.add(key)
            logger.error(f"Weak password detected for {key}")

    if weak_found:
        raise RuntimeError(
            f"Weak passwords detected in: {', '.join(weak_found)}. "
            f"Please set strong passwords in .env file."
        )

    logger.info("Settings validation passed")


def get_setting(key: str, default: str = '') -> str:
    """Get a setting from environment variables.

    Args:
        key: Setting key
        default: Default value if not found

    Returns:
        Setting value or default
    """
    return os.getenv(key, default)
