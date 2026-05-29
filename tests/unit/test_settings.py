"""Tests for settings and configuration validation.

Tests for weak password detection and settings validation.
"""

import pytest
import os
from unittest.mock import patch

from agentManager.config.settings import (
    WEAK_PASSWORDS,
    get_durable_backend_settings,
    get_sandbox_policy_settings,
    validate_settings,
)


class TestWeakPasswordDetection:
    """Test suite for weak password detection."""

    def test_weak_passwords_set_contains_common_weak_passwords(self):
        """Test that WEAK_PASSWORDS set contains expected weak passwords."""
        assert 'password' in WEAK_PASSWORDS
        assert 'admin' in WEAK_PASSWORDS
        assert 'minioadmin' in WEAK_PASSWORDS
        assert 'test' in WEAK_PASSWORDS
        assert 'demo' in WEAK_PASSWORDS

    def test_validate_settings_no_weak_passwords(self):
        """Test validation passes with strong passwords."""
        env_vars = {
            'POSTGRES_PASSWORD': 'StrongP@ssw0rd123!',
            'REDIS_PASSWORD': 'AnotherStr0ng!Pass',
            'MINIO_SECRET_KEY': 'MinioSecureKey123!',
            'SECRET_KEY': 'AppSecretKey123!',
            'QDRANT_API_KEY': 'QdrantKey123!',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            # Should not raise
            validate_settings()

    def test_validate_settings_detects_weak_postgres_password(self):
        """Test detection of weak PostgreSQL password."""
        env_vars = {
            'POSTGRES_PASSWORD': 'password',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError, match='Weak passwords detected'):
                validate_settings()

    def test_validate_settings_detects_weak_minio_secret(self):
        """Test detection of weak MinIO secret key."""
        env_vars = {
            'MINIO_SECRET_KEY': 'minioadmin',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError, match='Weak passwords detected'):
                validate_settings()

    def test_validate_settings_detects_weak_redis_password(self):
        """Test detection of weak Redis password."""
        env_vars = {
            'REDIS_PASSWORD': 'admin',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError, match='Weak passwords detected'):
                validate_settings()

    def test_validate_settings_detects_weak_secret_key(self):
        """Test detection of weak application secret key."""
        env_vars = {
            'SECRET_KEY': 'test',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError, match='Weak passwords detected'):
                validate_settings()

    def test_validate_settings_detects_weak_qdrant_api_key(self):
        """Test detection of weak Qdrant API key."""
        env_vars = {
            'QDRANT_API_KEY': 'demo',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError, match='Weak passwords detected'):
                validate_settings()

    def test_validate_settings_multiple_weak_passwords(self):
        """Test detection of multiple weak passwords."""
        env_vars = {
            'POSTGRES_PASSWORD': 'password',
            'REDIS_PASSWORD': 'admin',
            'MINIO_SECRET_KEY': 'minioadmin',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError, match='Weak passwords detected'):
                validate_settings()

    def test_validate_settings_case_insensitive(self):
        """Test that weak password detection is case-insensitive."""
        env_vars = {
            'POSTGRES_PASSWORD': 'PASSWORD',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError, match='Weak passwords detected'):
                validate_settings()

    def test_validate_settings_ignores_empty_values(self):
        """Test that empty environment variables are ignored."""
        env_vars = {
            'POSTGRES_PASSWORD': '',
            'REDIS_PASSWORD': '',
        }

        with patch.dict(os.environ, env_vars, clear=True):
            # Should not raise
            validate_settings()

    def test_validate_settings_ignores_unset_variables(self):
        """Test that unset environment variables are ignored."""
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise
            validate_settings()


class TestSandboxPolicySettings:
    """Test sandbox production policy settings parsing."""

    def test_get_sandbox_policy_settings_defaults(self):
        """Test secure sandbox policy defaults."""
        with patch.dict(os.environ, {}, clear=True):
            policy = get_sandbox_policy_settings()

        assert policy["allowed_images"] == ("python:3.10-slim",)
        assert policy["denied_mounts"] == ("/var/run/docker.sock",)
        assert policy["network_mode"] == "none"
        assert policy["cpu_limit"] == 1.0
        assert policy["memory_limit"] == "512m"
        assert policy["read_only_rootfs"] is True

    def test_get_sandbox_policy_settings_from_environment(self):
        """Test sandbox policy can be configured through environment."""
        env_vars = {
            "SANDBOX_ALLOWED_IMAGES": "python:3.10-slim,python:3.12-slim",
            "SANDBOX_DENIED_MOUNTS": "/,/var/run/docker.sock",
            "SANDBOX_NETWORK_MODE": "bridge",
            "SANDBOX_CPU_LIMIT": "2.5",
            "SANDBOX_MEMORY_LIMIT": "1g",
            "SANDBOX_READ_ONLY_ROOTFS": "false",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            policy = get_sandbox_policy_settings()

        assert policy["allowed_images"] == ("python:3.10-slim", "python:3.12-slim")
        assert policy["denied_mounts"] == ("/", "/var/run/docker.sock")
        assert policy["network_mode"] == "bridge"
        assert policy["cpu_limit"] == 2.5
        assert policy["memory_limit"] == "1g"
        assert policy["read_only_rootfs"] is False


class TestDurableBackendSettings:
    """Test durable backend environment settings parsing."""

    def test_get_durable_backend_settings_defaults_to_local_fallbacks(self):
        """Durable backends should be opt-in with local-safe defaults."""
        with patch.dict(os.environ, {}, clear=True):
            settings = get_durable_backend_settings()

        assert settings["database_url"] == ""
        assert settings["redis_url"] == "redis://localhost:6379/0"
        assert settings["object_store_endpoint"] == ""
        assert settings["object_store_bucket"] == ""
        assert settings["object_store_access_key"] == ""
        assert settings["object_store_secret_key"] == ""
        assert settings["vector_backend"] == "sqlite"

    def test_get_durable_backend_settings_reads_environment(self):
        """Durable backend settings should come from production env vars."""
        env_vars = {
            "DATABASE_URL": "postgresql://agent:secret@db:5432/agentmanager",
            "REDIS_URL": "redis://redis:6379/1",
            "OBJECT_STORE_ENDPOINT": "http://minio:9000",
            "OBJECT_STORE_BUCKET": "agentmanager-checkpoints",
            "OBJECT_STORE_ACCESS_KEY": "access",
            "OBJECT_STORE_SECRET_KEY": "secret",
            "VECTOR_BACKEND": "qdrant",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = get_durable_backend_settings()

        assert settings == {
            "database_url": "postgresql://agent:secret@db:5432/agentmanager",
            "redis_url": "redis://redis:6379/1",
            "object_store_endpoint": "http://minio:9000",
            "object_store_bucket": "agentmanager-checkpoints",
            "object_store_access_key": "access",
            "object_store_secret_key": "secret",
            "vector_backend": "qdrant",
        }
