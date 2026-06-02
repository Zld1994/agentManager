"""Runtime factory for backend selection based on configuration.

Creates runtime components (state machine, event bus, checkpoint manager,
memory system, DAG engine, scheduler) according to environment settings.
When durable backend URLs are configured, the factory wires in PostgreSQL,
Redis, S3-compatible object storage, and Qdrant as appropriate. Otherwise
it falls back to in-memory / SQLite defaults suitable for local development.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from agentManager.config.settings import get_durable_backend_settings
from agentManager.engine.dag import DAGEngine
from agentManager.engine.scheduler import SchedulerEngine
from agentManager.engine.state_manager import StateMachine
from agentManager.memory.engineering_memory import EngineeringMemory
from agentManager.observability.audit import configure_audit_sinks

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    """Assembled runtime components produced by the factory."""

    dag_engine: DAGEngine
    state_machine: StateMachine
    event_bus: Any
    scheduler: SchedulerEngine
    checkpoint_manager: Any
    memory_system: Any = None
    engineering_memory: Optional[EngineeringMemory] = None


def _create_state_machine(settings: dict[str, str]) -> StateMachine:
    """Create a StateMachine, optionally backed by PostgreSQL."""
    database_url = settings.get("database_url", "")
    if not database_url:
        return StateMachine()

    try:
        from agentManager.storage.postgres import PostgresStateRepository

        repo = PostgresStateRepository.from_database_url(database_url)
        repo.initialize_schema()
        logger.info("StateMachine backed by PostgreSQL at %s", _mask_url(database_url))
        return StateMachine(repository=repo)
    except Exception as exc:
        logger.warning(
            "Failed to initialise PostgreSQL state repository, " "falling back to in-memory: %s",
            exc,
        )
        return StateMachine()


def _create_event_bus(settings: dict[str, str]) -> Any:
    """Create an event bus, optionally backed by Redis Streams.

    Returns an InMemoryEventBus when Redis is not configured. When a Redis
    URL is provided, a RedisStreamEventBus is created but **not** connected
    yet — the caller should invoke ``await bus.connect()`` during
    application startup.

    Note: InMemoryEventBus.publish is synchronous while
    RedisStreamEventBus.publish is async; callers should use the adapter
    pattern if they need a uniform async interface.
    """
    redis_url = settings.get("redis_url", "")
    if not redis_url:
        from agentManager.engine.event_bus.in_memory import InMemoryEventBus

        return InMemoryEventBus()

    try:
        from agentManager.engine.event_bus.redis_stream import RedisStreamEventBus

        bus = RedisStreamEventBus(redis_url=redis_url)
        logger.info("EventBus backed by Redis at %s (connect on startup)", _mask_url(redis_url))
        return bus
    except Exception as exc:
        logger.warning(
            "Failed to initialise Redis event bus, falling back to in-memory: %s",
            exc,
        )
        from agentManager.engine.event_bus.in_memory import InMemoryEventBus

        return InMemoryEventBus()


def _create_checkpoint_manager(settings: dict[str, str]) -> Any:
    """Create a checkpoint manager, optionally backed by object storage."""
    endpoint = settings.get("object_store_endpoint", "")
    bucket = settings.get("object_store_bucket", "")
    access_key = settings.get("object_store_access_key", "")
    secret_key = settings.get("object_store_secret_key", "")

    if not endpoint or not bucket:
        from agentManager.engine.checkpoint import InMemoryCheckpointManager

        return InMemoryCheckpointManager()

    try:
        from agentManager.engine.checkpoint import ObjectStoreCheckpointManager
        from agentManager.storage.object_store import S3ObjectStore

        store = S3ObjectStore.from_settings(
            endpoint_url=endpoint,
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
        )
        logger.info(
            "CheckpointManager backed by object store at %s/%s",
            _mask_url(endpoint),
            bucket,
        )
        return ObjectStoreCheckpointManager(object_store=store)
    except Exception as exc:
        logger.warning(
            "Failed to initialise object store checkpoint manager, "
            "falling back to in-memory: %s",
            exc,
        )
        from agentManager.engine.checkpoint import InMemoryCheckpointManager

        return InMemoryCheckpointManager()


def _create_memory_system(settings: dict[str, str]) -> Any:
    """Create a memory system with pluggable backend.

    Supports "sqlite" (default) and "qdrant" backends. When the backend
    is "qdrant", the MemorySystem delegates vector search to Qdrant while
    still using SQLite for structured storage.
    """
    vector_backend = settings.get("vector_backend", "sqlite").lower()

    if vector_backend == "qdrant":
        try:
            from agentManager.memory.memory_system import MemorySystem
            from agentManager.memory.vector_backend import QdrantVectorSearchBackend

            qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
            qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
            vector = QdrantVectorSearchBackend(
                url=qdrant_url,
                api_key=qdrant_api_key or None,
            )
            mem = MemorySystem(storage_backend="sqlite", vector_backend=vector)
            logger.info("MemorySystem with Qdrant vector backend at %s", _mask_url(qdrant_url))
            return mem
        except Exception as exc:
            logger.warning(
                "Failed to initialise Qdrant vector backend, " "falling back to SQLite: %s",
                exc,
            )

    from agentManager.memory.memory_system import MemorySystem

    return MemorySystem(storage_backend="sqlite")


def _create_engineering_memory(settings: dict[str, str]) -> Optional[EngineeringMemory]:
    """Create an EngineeringMemory backend for workflow write-back.

    Uses the same vector_backend setting as MemorySystem. When Qdrant is
    configured, the engineering memory delegates vector search to it.
    Otherwise falls back to the default SQLite-backed vector search.

    Note: Unlike other _create_* functions that read from *settings*,
    EngineeringMemory.from_settings() reads environment variables directly
    via get_durable_backend_settings(). This means a custom *settings*
    dict will not override the vector backend selection for engineering
    memory. This is intentional: engineering memory is a write-back side
    channel and follows the deployment-level configuration.
    """
    try:
        return EngineeringMemory.from_settings()
    except Exception as exc:
        logger.warning(
            "Failed to initialise EngineeringMemory, " "memory write-back will be disabled: %s",
            exc,
        )
        return None


def configure_runtime_audit_sinks(
    settings: dict[str, str],
    audit_sink: Optional[str] = None,
) -> None:
    """Wire process audit sinks from durable backend settings.

    Durable audit outputs are opt-in. If a requested durable sink cannot be
    created, it is dropped and the process keeps the log sink enabled.
    """
    raw_sinks = audit_sink if audit_sink is not None else os.getenv("AUDIT_SINK", "log")
    requested = [sink.strip().lower() for sink in raw_sinks.split(",") if sink.strip()]
    if not requested:
        requested = ["log"]

    configured: list[str] = []
    repository = None
    object_store = None

    if "log" in requested:
        configured.append("log")

    if "db" in requested:
        database_url = settings.get("database_url", "")
        if database_url:
            try:
                from agentManager.storage.postgres import PostgresStateRepository

                repository = PostgresStateRepository.from_database_url(database_url)
                repository.initialize_schema()
                configured.append("db")
                logger.info("Audit db sink backed by PostgreSQL at %s", _mask_url(database_url))
            except Exception as exc:
                logger.warning("Failed to initialise audit db sink, using log sink only: %s", exc)
        else:
            logger.warning("AUDIT_SINK requested db but DATABASE_URL is not configured")

    if "object_storage" in requested:
        endpoint = settings.get("object_store_endpoint", "")
        bucket = settings.get("object_store_bucket", "")
        if endpoint and bucket:
            try:
                from agentManager.storage.object_store import S3ObjectStore

                object_store = S3ObjectStore.from_settings(
                    endpoint_url=endpoint,
                    bucket=bucket,
                    access_key=settings.get("object_store_access_key", ""),
                    secret_key=settings.get("object_store_secret_key", ""),
                )
                configured.append("object_storage")
                logger.info(
                    "Audit object sink backed by object store at %s/%s",
                    _mask_url(endpoint),
                    bucket,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to initialise audit object storage sink, using remaining sinks: %s",
                    exc,
                )
        else:
            logger.warning(
                "AUDIT_SINK requested object_storage but OBJECT_STORE_ENDPOINT "
                "or OBJECT_STORE_BUCKET is not configured"
            )

    if not configured:
        configured = ["log"]

    configure_audit_sinks(",".join(configured), repository=repository, object_store=object_store)


def create_runtime(
    settings: Optional[dict[str, str]] = None,
    max_concurrent_tasks: int = 10,
) -> Runtime:
    """Create a fully wired Runtime from environment or explicit settings.

    Args:
        settings: Override durable backend settings. When None, reads from
            environment variables via ``get_durable_backend_settings()``.
        max_concurrent_tasks: Concurrency limit for the scheduler.

    Returns:
        A ``Runtime`` dataclass holding all assembled components.
    """
    if settings is None:
        settings = get_durable_backend_settings()

    state_machine = _create_state_machine(settings)
    event_bus = _create_event_bus(settings)
    checkpoint_manager = _create_checkpoint_manager(settings)
    memory_system = _create_memory_system(settings)
    engineering_memory = _create_engineering_memory(settings)

    return Runtime(
        dag_engine=DAGEngine(),
        state_machine=state_machine,
        event_bus=event_bus,
        scheduler=SchedulerEngine(max_concurrent_tasks=max_concurrent_tasks),
        checkpoint_manager=checkpoint_manager,
        memory_system=memory_system,
        engineering_memory=engineering_memory,
    )


def _mask_url(url: str) -> str:
    """Hide credentials in a URL for safe logging."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        credentials, host_part = rest.rsplit("@", 1)
        return f"{scheme}://***@{host_part}"
    return url
