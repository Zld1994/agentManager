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


def validate_settings() -> None:
    """Validate application settings for security issues.

    Checks for weak passwords in critical environment variables.
    Raises RuntimeError if weak passwords are detected.

    Raises:
        RuntimeError: If weak passwords are detected in settings
    """
    weak_found: Set[str] = set()

    # Environment variables to check
    settings_to_check = {
        'POSTGRES_PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
        'REDIS_PASSWORD': os.getenv('REDIS_PASSWORD', ''),
        'MINIO_SECRET_KEY': os.getenv('MINIO_SECRET_KEY', ''),
        'SECRET_KEY': os.getenv('SECRET_KEY', ''),
        'QDRANT_API_KEY': os.getenv('QDRANT_API_KEY', ''),
    }

    for key, value in settings_to_check.items():
        if value and value.lower() in WEAK_PASSWORDS:
            weak_found.add(key)
            logger.error(f"Weak password detected for {key}")

    if weak_found:
        raise RuntimeError(
            f"Weak passwords detected in: {', '.join(sorted(weak_found))}. "
            f"Please use strong passwords for production environments."
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
