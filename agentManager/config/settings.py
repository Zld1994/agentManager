"""Settings and configuration management for agentManager.

This module handles application settings validation, including weak password
detection for production environments.
"""

import logging
import os
from typing import Any
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


def get_durable_backend_settings() -> dict[str, str]:
    """Get opt-in durable backend settings from environment variables."""
    return {
        "database_url": os.getenv("DATABASE_URL", ""),
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        "object_store_endpoint": os.getenv("OBJECT_STORE_ENDPOINT", ""),
        "object_store_bucket": os.getenv("OBJECT_STORE_BUCKET", ""),
        "object_store_access_key": os.getenv("OBJECT_STORE_ACCESS_KEY", ""),
        "object_store_secret_key": os.getenv("OBJECT_STORE_SECRET_KEY", ""),
        "vector_backend": os.getenv("VECTOR_BACKEND", "sqlite").lower(),
    }


def _parse_csv_setting(value: str) -> tuple[str, ...]:
    """Parse a comma-separated environment setting into a tuple."""
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_bool_setting(value: str) -> bool:
    """Parse common boolean environment values."""
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_sandbox_policy_settings() -> dict[str, Any]:
    """Get production WorkerSandbox policy settings from environment variables."""
    return {
        "allowed_images": _parse_csv_setting(
            os.getenv("SANDBOX_ALLOWED_IMAGES", "python:3.10-slim")
        ),
        "denied_mounts": _parse_csv_setting(
            os.getenv("SANDBOX_DENIED_MOUNTS", "/var/run/docker.sock")
        ),
        "network_mode": os.getenv("SANDBOX_NETWORK_MODE", "none"),
        "cpu_limit": float(os.getenv("SANDBOX_CPU_LIMIT", "1.0")),
        "memory_limit": os.getenv("SANDBOX_MEMORY_LIMIT", "512m"),
        "read_only_rootfs": _parse_bool_setting(
            os.getenv("SANDBOX_READ_ONLY_ROOTFS", "true")
        ),
    }


def get_observability_settings() -> dict[str, Any]:
    """Get observability configuration from environment variables."""
    return {
        "log_level": os.getenv("LOG_LEVEL", "INFO").upper(),
        "log_json": _parse_bool_setting(os.getenv("LOG_JSON", "true")),
        "otel_enabled": _parse_bool_setting(os.getenv("OTEL_ENABLED", "false")),
        "otel_service_name": os.getenv("OTEL_SERVICE_NAME", "agentManager"),
        "otel_endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        "audit_enabled": _parse_bool_setting(os.getenv("AUDIT_ENABLED", "true")),
    }
