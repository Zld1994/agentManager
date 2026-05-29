"""Tests for explicit memory layers and pluggable vector backends."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from unittest.mock import patch
from pathlib import Path

from agentManager.memory import EngineeringMemory, ProfileMemory, SessionMemory
from agentManager.memory.vector_backend import (
    InMemoryVectorSearchBackend,
    QdrantVectorSearchBackend,
    SQLiteVectorSearchBackend,
    create_vector_backend,
)


def run(coro):
    """Run async test operations without pytest-asyncio dependency."""
    return asyncio.run(coro)


def _workspace_temp_db(name: str) -> Path:
    """Create a writable temporary sqlite path."""
    with tempfile.NamedTemporaryFile(
        prefix=f"{name}-{uuid.uuid4().hex}-",
        suffix=".db",
        delete=False,
    ) as db_file:
        return Path(db_file.name)


def test_profile_memory_and_session_memory_compatibility():
    """SessionMemory remains a compatible alias over ProfileMemory behavior."""
    profile_memory = ProfileMemory(default_ttl=60)
    session_memory = SessionMemory(default_ttl=60)

    run(profile_memory.put("profile", "user", {"id": "u-1"}))
    run(session_memory.put("session", "state", "active"))

    assert run(profile_memory.get("profile", "user")) == {"id": "u-1"}
    assert run(session_memory.get("session", "state")) == "active"


def test_in_memory_vector_backend_ranks_semantic_matches():
    """In-memory vector backend should rank closer text higher."""
    backend = InMemoryVectorSearchBackend()

    run(backend.upsert("eng", "a", "database timeout on write"))
    run(backend.upsert("eng", "b", "cache miss warning"))
    run(backend.upsert("eng", "c", "timeout in database connection"))

    results = run(backend.query("eng", "database timeout", limit=3))

    assert [result.key for result in results[:2]] == ["a", "c"]
    assert all(result.score > 0 for result in results)


def test_sqlite_vector_backend_fallback_behavior():
    """SQLite vector backend should persist vectors and support search fallback."""
    db_path = _workspace_temp_db("vector")
    try:
        backend = SQLiteVectorSearchBackend(db_path=str(db_path))
        run(backend.upsert("eng", "err-1", "database timeout error"))
        run(backend.upsert("eng", "err-2", "validation failed on payload"))

        results = run(backend.query("eng", "timeout database", limit=5))
        assert results
        assert results[0].key == "err-1"

        removed = run(backend.remove("eng", "err-1"))
        assert removed is True
        cleared = run(backend.clear("eng"))
        assert cleared >= 1
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def test_engineering_memory_accepts_custom_vector_backend():
    """EngineeringMemory should delegate similarity search to injected backend."""
    db_path = _workspace_temp_db("engineering")
    try:
        vector_backend = InMemoryVectorSearchBackend()
        memory = EngineeringMemory(
            db_path=str(db_path),
            vector_backend=vector_backend,
        )

        run(memory.put("knowledge", "k1", {"content": "retry on timeout", "type": "fix"}))
        run(memory.put("knowledge", "k2", {"content": "linter warning", "type": "note"}))

        results = run(memory.search("knowledge", "timeout retry", limit=5))
        assert results
        assert results[0]["key"] == "k1"
        assert results[0]["similarity"] > 0
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def test_engineering_memory_defaults_to_sqlite_vector_backend():
    """EngineeringMemory should use the persistent SQLite vector fallback by default."""
    db_path = _workspace_temp_db("engineering-default")
    try:
        memory = EngineeringMemory(db_path=str(db_path))

        assert isinstance(memory.vector_backend, SQLiteVectorSearchBackend)
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def test_create_vector_backend_selects_sqlite_fallback():
    """Factory should default production vector selection to SQLite fallback."""
    backend = create_vector_backend("sqlite", db_path=":memory:")

    assert isinstance(backend, SQLiteVectorSearchBackend)


def test_create_vector_backend_selects_qdrant_backend():
    """Factory should expose an opt-in Qdrant backend for production config."""
    backend = create_vector_backend(
        "qdrant",
        url="http://qdrant:6333",
        collection_name="agentmanager",
        api_key="secret",
    )

    assert isinstance(backend, QdrantVectorSearchBackend)
    assert backend.url == "http://qdrant:6333"
    assert backend.collection_name == "agentmanager"


def test_engineering_memory_from_settings_uses_vector_backend_env():
    """EngineeringMemory factory should honor VECTOR_BACKEND configuration."""
    db_path = _workspace_temp_db("engineering-settings")
    env_vars = {
        "VECTOR_BACKEND": "qdrant",
        "QDRANT_URL": "http://qdrant:6333",
        "QDRANT_API_KEY": "secret",
    }

    try:
        with patch.dict("os.environ", env_vars, clear=True):
            memory = EngineeringMemory.from_settings(db_path=str(db_path))

        assert isinstance(memory.vector_backend, QdrantVectorSearchBackend)
        assert memory.vector_backend.url == "http://qdrant:6333"
        assert memory.vector_backend.api_key == "secret"
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
