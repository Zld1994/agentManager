"""Tests for M4 tracing span attributes."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from agentManager.engine.checkpoint import ObjectStoreCheckpointManager
from agentManager.observability.tracing import create_span


class RecordingSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


def test_create_span_preserves_dot_separated_attribute_names(monkeypatch):
    started = {}

    class FakeTracer:
        def start_as_current_span(self, name):
            started["name"] = name
            span = RecordingSpan()
            started["span"] = span

            class SpanContext:
                def __enter__(self):
                    return span

                def __exit__(self, *args):
                    return None

            return SpanContext()

    monkeypatch.setattr("agentManager.observability.tracing._tracer", FakeTracer())

    with create_span("task.execute", {"task.id": "task-1", "workflow.id": "wf-1"}):
        pass

    assert started["name"] == "task.execute"
    assert started["span"].attributes == {"task.id": "task-1", "workflow.id": "wf-1"}


def test_object_store_checkpoint_save_sets_size_attribute(monkeypatch):
    spans = []

    class SpanContext:
        def __init__(self, name, attributes=None):
            self.span = RecordingSpan()
            self.span.attributes.update(attributes or {})
            spans.append(self.span)

        def __enter__(self):
            return self.span

        def __exit__(self, *args):
            return None

    monkeypatch.setattr("agentManager.engine.checkpoint.create_span", SpanContext)
    object_store = MagicMock()
    manager = ObjectStoreCheckpointManager(object_store)

    asyncio.run(manager.save_checkpoint("task-1", {"answer": 42}))

    assert spans[0].attributes["task.id"] == "task-1"
    assert spans[0].attributes["checkpoint.size_bytes"] == len(b'{"answer": 42}')
