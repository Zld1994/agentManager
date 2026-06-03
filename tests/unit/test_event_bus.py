"""Unit tests for Event Bus."""

from agentManager.domain.models import Event, EventType
from agentManager.engine.event_bus import EventBus


class TestEventBus:
    """Test EventBus class."""

    def test_subscribe_and_publish(self):
        """Test subscribing and publishing events."""
        bus = EventBus()
        received_events = []

        def callback(event):
            received_events.append(event)

        bus.subscribe(EventType.TASK_COMPLETED, callback)

        event = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )
        bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].event_id == "evt_1"

    def test_publish_correlation_id_does_not_mutate_original_payload(self):
        """Request correlation injection should not mutate caller-owned payload."""
        from agentManager.observability.logging import (
            clear_correlation_id,
            set_correlation_id,
        )

        bus = EventBus()
        payload = {"task_id": "task_1"}
        event = Event(
            event_type=EventType.TASK_CREATED,
            workflow_id="wf_1",
            payload=payload,
        )

        set_correlation_id("req-1")
        try:
            bus.publish(event)
        finally:
            clear_correlation_id()

        assert payload == {"task_id": "task_1"}
        assert event.payload["correlation_id"] == "req-1"

    def test_wildcard_subscription(self):
        """Test wildcard subscription receives all workflows."""
        bus = EventBus()
        received_events = []

        def callback(event):
            received_events.append(event)

        # Subscribe to all workflows
        bus.subscribe(EventType.TASK_COMPLETED, callback, workflow_id=None)

        # Publish event for specific workflow
        event = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )
        bus.publish(event)

        assert len(received_events) == 1

    def test_specific_workflow_subscription(self):
        """Test subscription for specific workflow."""
        bus = EventBus()
        received_events = []

        def callback(event):
            received_events.append(event)

        # Subscribe to specific workflow
        bus.subscribe(EventType.TASK_COMPLETED, callback, workflow_id="wf_1")

        # Publish event for same workflow
        event1 = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )
        bus.publish(event1)

        # Publish event for different workflow
        event2 = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_2",
            event_id="evt_2",
        )
        bus.publish(event2)

        # Should only receive event for wf_1
        assert len(received_events) == 1
        assert received_events[0].event_id == "evt_1"

    def test_both_exact_and_wildcard_triggered(self):
        """Test that both exact and wildcard subscriptions are triggered."""
        bus = EventBus()
        exact_events = []
        wildcard_events = []

        def exact_callback(event):
            exact_events.append(event)

        def wildcard_callback(event):
            wildcard_events.append(event)

        # Subscribe to specific workflow
        bus.subscribe(EventType.TASK_COMPLETED, exact_callback, workflow_id="wf_1")
        # Subscribe to all workflows
        bus.subscribe(EventType.TASK_COMPLETED, wildcard_callback, workflow_id=None)

        event = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )
        bus.publish(event)

        # Both should receive the event
        assert len(exact_events) == 1
        assert len(wildcard_events) == 1

    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        bus = EventBus()
        received_events = []

        def callback(event):
            received_events.append(event)

        bus.subscribe(EventType.TASK_COMPLETED, callback)
        bus.unsubscribe(EventType.TASK_COMPLETED, callback)

        event = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )
        bus.publish(event)

        assert len(received_events) == 0

    def test_get_events_by_type(self):
        """Test filtering events by type."""
        bus = EventBus()

        event1 = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )
        event2 = Event(
            event_type=EventType.TASK_FAILED,
            workflow_id="wf_1",
            event_id="evt_2",
        )

        bus.publish(event1)
        bus.publish(event2)

        completed_events = bus.get_events(event_type=EventType.TASK_COMPLETED)
        assert len(completed_events) == 1
        assert completed_events[0].event_id == "evt_1"

    def test_get_events_by_workflow(self):
        """Test filtering events by workflow."""
        bus = EventBus()

        event1 = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )
        event2 = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_2",
            event_id="evt_2",
        )

        bus.publish(event1)
        bus.publish(event2)

        wf1_events = bus.get_events(workflow_id="wf_1")
        assert len(wf1_events) == 1
        assert wf1_events[0].event_id == "evt_1"

    def test_clear_events(self):
        """Test clearing events and subscribers."""
        bus = EventBus()

        def callback(event):
            pass

        bus.subscribe(EventType.TASK_COMPLETED, callback)

        event = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )
        bus.publish(event)

        assert len(bus.events) == 1
        assert len(bus.subscribers) > 0

        bus.clear()

        assert len(bus.events) == 0
        assert len(bus.subscribers) == 0

    def test_callback_exception_handling(self):
        """Test that callback exceptions don't break event bus."""
        bus = EventBus()
        received_events = []

        def failing_callback(event):
            raise Exception("Callback failed")

        def good_callback(event):
            received_events.append(event)

        bus.subscribe(EventType.TASK_COMPLETED, failing_callback)
        bus.subscribe(EventType.TASK_COMPLETED, good_callback)

        event = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            event_id="evt_1",
        )

        # Should not raise, despite failing callback
        bus.publish(event)

        # Good callback should still be called
        assert len(received_events) == 1

    def test_event_retention_limit(self):
        """Test that the event bus only keeps the configured number of events."""
        bus = EventBus(max_events=2)

        bus.publish(Event(EventType.TASK_CREATED, workflow_id="wf_1", event_id="evt_1"))
        bus.publish(Event(EventType.TASK_STARTED, workflow_id="wf_1", event_id="evt_2"))
        bus.publish(Event(EventType.TASK_COMPLETED, workflow_id="wf_1", event_id="evt_3"))

        assert [event.event_id for event in bus.events] == ["evt_2", "evt_3"]
