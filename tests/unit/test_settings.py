"""Tests for settings and configuration validation.

Tests for weak password detection and settings validation.
"""

import pytest
import os
from unittest.mock import patch

from agentManager.config.settings import validate_settings, WEAK_PASSWORDS


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
