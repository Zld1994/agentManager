"""Tests for the RuntimeFactory module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from agentManager.runtime.factory import (
    Runtime,
    configure_runtime_audit_sinks,
    _create_checkpoint_manager,
    _create_event_bus,
    _create_memory_system,
    _create_state_machine,
    _mask_url,
    create_runtime,
)


class TestMaskUrl:
    def test_no_credentials(self):
        assert _mask_url("http://localhost:5432") == "http://localhost:5432"

    def test_with_credentials(self):
        assert _mask_url("postgres://user:pass@host:5432/db") == "postgres://***@host:5432/db"

    def test_no_scheme(self):
        assert _mask_url("just-a-string") == "just-a-string"


class TestCreateStateMachine:
    def test_in_memory_when_no_database_url(self):
        sm = _create_state_machine({"database_url": ""})
        assert sm.repository is None

    def test_postgres_when_database_url(self):
        mock_repo = MagicMock()
        mock_module = MagicMock()
        mock_module.PostgresStateRepository.from_database_url.return_value = mock_repo

        with patch.dict("sys.modules", {"agentManager.storage.postgres": mock_module}):
            sm = _create_state_machine({"database_url": "postgresql://user:pass@host/db"})
            mock_module.PostgresStateRepository.from_database_url.assert_called_once_with(
                "postgresql://user:pass@host/db"
            )
            mock_repo.initialize_schema.assert_called_once()
            assert sm.repository is mock_repo

    def test_fallback_on_connection_error(self):
        sm = _create_state_machine({"database_url": "postgres://invalid:5432/nodb"})
        assert sm.repository is None


class TestCreateEventBus:
    def test_in_memory_when_no_redis_url(self):
        settings = {"redis_url": ""}
        bus = _create_event_bus(settings)
        from agentManager.engine.event_bus.in_memory import InMemoryEventBus

        assert isinstance(bus, InMemoryEventBus)

    def test_redis_when_url_configured(self):
        settings = {"redis_url": "redis://localhost:6379"}
        bus = _create_event_bus(settings)
        from agentManager.engine.event_bus.redis_stream import RedisStreamEventBus

        assert isinstance(bus, RedisStreamEventBus)
        assert bus.redis_url == "redis://localhost:6379"

    def test_in_memory_fallback_on_import_error(self):
        settings = {"redis_url": "redis://localhost:6379"}
        mock_module = MagicMock()
        mock_module.RedisStreamEventBus.side_effect = ImportError("redis not available")

        with patch.dict("sys.modules", {"agentManager.engine.event_bus.redis_stream": mock_module}):
            bus = _create_event_bus(settings)
            from agentManager.engine.event_bus.in_memory import InMemoryEventBus

            assert isinstance(bus, InMemoryEventBus)


class TestCreateCheckpointManager:
    def test_in_memory_when_no_object_store(self):
        settings = {
            "object_store_endpoint": "",
            "object_store_bucket": "",
            "object_store_access_key": "",
            "object_store_secret_key": "",
        }
        mgr = _create_checkpoint_manager(settings)
        from agentManager.engine.checkpoint import InMemoryCheckpointManager

        assert isinstance(mgr, InMemoryCheckpointManager)

    def test_in_memory_when_missing_bucket(self):
        settings = {
            "object_store_endpoint": "http://minio:9000",
            "object_store_bucket": "",
            "object_store_access_key": "key",
            "object_store_secret_key": "secret",
        }
        mgr = _create_checkpoint_manager(settings)
        from agentManager.engine.checkpoint import InMemoryCheckpointManager

        assert isinstance(mgr, InMemoryCheckpointManager)

    def test_object_store_when_configured(self):
        mock_store = MagicMock()
        mock_s3_module = MagicMock()
        mock_s3_module.S3ObjectStore.from_settings.return_value = mock_store

        settings = {
            "object_store_endpoint": "http://minio:9000",
            "object_store_bucket": "checkpoints",
            "object_store_access_key": "minioadmin",
            "object_store_secret_key": "minioadmin",
        }
        with patch.dict("sys.modules", {"agentManager.storage.object_store": mock_s3_module}):
            mgr = _create_checkpoint_manager(settings)
            from agentManager.engine.checkpoint import InMemoryCheckpointManager

            assert not isinstance(mgr, InMemoryCheckpointManager)


class TestCreateMemorySystem:
    def test_sqlite_by_default(self):
        settings = {"vector_backend": "sqlite"}
        mem = _create_memory_system(settings)
        from agentManager.memory.memory_system import MemorySystem

        assert isinstance(mem, MemorySystem)
        assert mem.backend == "sqlite"
        mem.close()

    def test_qdrant_falls_back_on_missing_client(self):
        settings = {"vector_backend": "qdrant"}
        mem = _create_memory_system(settings)
        from agentManager.memory.memory_system import MemorySystem

        assert isinstance(mem, MemorySystem)
        assert mem.backend == "sqlite"
        mem.close()


class TestConfigureRuntimeAuditSinks:
    def test_no_durable_sinks_when_only_log_is_configured(self):
        settings = {
            "database_url": "",
            "object_store_endpoint": "",
            "object_store_bucket": "",
            "object_store_access_key": "",
            "object_store_secret_key": "",
        }

        with patch("agentManager.runtime.factory.configure_audit_sinks") as configure:
            configure_runtime_audit_sinks(settings, audit_sink="log")

        configure.assert_called_once_with("log", repository=None, object_store=None)

    def test_database_url_injects_postgres_audit_repository(self):
        repository = MagicMock()
        mock_module = MagicMock()
        mock_module.PostgresStateRepository.from_database_url.return_value = repository
        settings = {
            "database_url": "postgresql://user:pass@host/db",
            "object_store_endpoint": "",
            "object_store_bucket": "",
            "object_store_access_key": "",
            "object_store_secret_key": "",
        }

        with patch.dict("sys.modules", {"agentManager.storage.postgres": mock_module}):
            with patch("agentManager.runtime.factory.configure_audit_sinks") as configure:
                configure_runtime_audit_sinks(settings, audit_sink="log,db")

        repository.initialize_schema.assert_called_once()
        configure.assert_called_once_with("log,db", repository=repository, object_store=None)

    def test_object_store_env_injects_object_storage_audit_sink(self):
        store = MagicMock()
        mock_module = MagicMock()
        mock_module.S3ObjectStore.from_settings.return_value = store
        settings = {
            "database_url": "",
            "object_store_endpoint": "http://minio:9000",
            "object_store_bucket": "agentmanager",
            "object_store_access_key": "key",
            "object_store_secret_key": "secret",
        }

        with patch.dict("sys.modules", {"agentManager.storage.object_store": mock_module}):
            with patch("agentManager.runtime.factory.configure_audit_sinks") as configure:
                configure_runtime_audit_sinks(settings, audit_sink="log,object_storage")

        mock_module.S3ObjectStore.from_settings.assert_called_once_with(
            endpoint_url="http://minio:9000",
            bucket="agentmanager",
            access_key="key",
            secret_key="secret",
        )
        configure.assert_called_once_with(
            "log,object_storage",
            repository=None,
            object_store=store,
        )

    def test_durable_sink_initialization_failure_falls_back_to_log(self):
        mock_module = MagicMock()
        mock_module.PostgresStateRepository.from_database_url.side_effect = RuntimeError("db down")
        settings = {
            "database_url": "postgresql://user:pass@host/db",
            "object_store_endpoint": "",
            "object_store_bucket": "",
            "object_store_access_key": "",
            "object_store_secret_key": "",
        }

        with patch.dict("sys.modules", {"agentManager.storage.postgres": mock_module}):
            with patch("agentManager.runtime.factory.configure_audit_sinks") as configure:
                configure_runtime_audit_sinks(settings, audit_sink="log,db")

        configure.assert_called_once_with("log", repository=None, object_store=None)


class TestCreateRuntime:
    def test_default_creates_in_memory(self):
        runtime = create_runtime(
            settings={
                "database_url": "",
                "redis_url": "",
                "object_store_endpoint": "",
                "object_store_bucket": "",
                "object_store_access_key": "",
                "object_store_secret_key": "",
                "vector_backend": "sqlite",
            }
        )
        assert isinstance(runtime, Runtime)
        assert runtime.dag_engine is not None
        assert runtime.state_machine is not None
        assert runtime.event_bus is not None
        assert runtime.scheduler is not None
        assert runtime.checkpoint_manager is not None
        assert runtime.state_machine.repository is None
        if runtime.memory_system is not None:
            runtime.memory_system.close()

    def test_custom_max_concurrent_tasks(self):
        runtime = create_runtime(
            settings={
                "database_url": "",
                "redis_url": "",
                "object_store_endpoint": "",
                "object_store_bucket": "",
                "object_store_access_key": "",
                "object_store_secret_key": "",
                "vector_backend": "sqlite",
            },
            max_concurrent_tasks=5,
        )
        assert runtime.scheduler.max_concurrent_tasks == 5
        if runtime.memory_system is not None:
            runtime.memory_system.close()

    def test_reads_env_when_no_settings(self):
        with patch.dict(os.environ, {}, clear=False):
            runtime = create_runtime()
            assert isinstance(runtime, Runtime)
            if runtime.memory_system is not None:
                runtime.memory_system.close()
