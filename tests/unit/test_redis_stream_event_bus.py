"""Comprehensive tests for Redis Streams EventBus implementation.

Tests cover:
- Connection management
- Event publishing and consumption
- Consumer groups and ACK mechanism
- Event replay (xrange)
- Dead letter queue (DLQ) handling
- Callback triggering
- Error handling
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from agentManager.engine.event_bus.base import Event, EventType
from agentManager.engine.event_bus.redis_stream import RedisStreamEventBus


def utc_now():
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@pytest.fixture
async def redis_event_bus():
    """Create a Redis event bus instance for testing."""
    bus = RedisStreamEventBus(
        redis_url="redis://localhost:6379",
        stream_key="test_stream",
        consumer_group="test_group",
        dlq_key="test_dlq",
    )
    yield bus
    # Cleanup
    try:
        await bus.disconnect()
    except Exception:
        pass


@pytest.fixture
def sample_event():
    """Create a sample event for testing."""
    return Event(
        event_type=EventType.TASK_CREATED,
        workflow_id="workflow_123",
        payload={"task_id": "task_456", "status": "pending"},
        event_id="event_789",
        timestamp=utc_now(),
    )


class TestRedisStreamEventBusConnection:
    """Test connection management."""

    @pytest.mark.asyncio
    async def test_connect_success(self, redis_event_bus):
        """Test successful connection to Redis."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            # Make from_url return an awaitable that resolves to mock_client
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()

            assert redis_event_bus.redis_client is not None
            mock_redis.assert_called_once()
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_creates_consumer_group(self, redis_event_bus):
        """Test that connect creates consumer group."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()

            mock_client.xgroup_create.assert_called_once_with(
                "test_stream",
                "test_group",
                id="0",
                mkstream=True,
            )

    @pytest.mark.asyncio
    async def test_connect_handles_existing_group(self, redis_event_bus):
        """Test that connect handles existing consumer group."""
        from redis.exceptions import ResponseError

        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock(
                side_effect=ResponseError("BUSYGROUP Consumer Group name already exists")
            )
            mock_redis.return_value = mock_client

            # Should not raise
            await redis_event_bus.connect()
            assert redis_event_bus.redis_client is not None

    @pytest.mark.asyncio
    async def test_disconnect_closes_connection(self, redis_event_bus):
        """Test that disconnect closes Redis connection."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.close = AsyncMock()
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            await redis_event_bus.disconnect()

            mock_client.close.assert_called_once()


class TestRedisStreamEventBusPublish:
    """Test event publishing."""

    @pytest.mark.asyncio
    async def test_publish_event_success(self, redis_event_bus, sample_event):
        """Test successful event publishing."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xadd = AsyncMock(return_value="1234567890-0")
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            await redis_event_bus.publish(sample_event)

            mock_client.xadd.assert_called_once()
            call_args = mock_client.xadd.call_args
            assert call_args[0][0] == "test_stream"
            assert call_args[0][1]["event_type"] == "task_created"
            assert call_args[0][1]["workflow_id"] == "workflow_123"

    @pytest.mark.asyncio
    async def test_publish_without_connection_raises(self, redis_event_bus, sample_event):
        """Test that publishing without connection raises error."""
        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await redis_event_bus.publish(sample_event)

    @pytest.mark.asyncio
    async def test_publish_serializes_payload(self, redis_event_bus, sample_event):
        """Test that payload is properly serialized."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xadd = AsyncMock(return_value="1234567890-0")
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            await redis_event_bus.publish(sample_event)

            call_args = mock_client.xadd.call_args
            payload_str = call_args[0][1]["payload"]
            payload = json.loads(payload_str)
            assert payload == sample_event.payload


class TestRedisStreamEventBusSubscribe:
    """Test subscription management."""

    @pytest.mark.asyncio
    async def test_subscribe_to_event_type(self, redis_event_bus):
        """Test subscribing to an event type."""
        callback = Mock()
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback)

        assert "task_created:*" in redis_event_bus.subscribers
        assert callback in redis_event_bus.subscribers["task_created:*"]

    @pytest.mark.asyncio
    async def test_subscribe_to_specific_workflow(self, redis_event_bus):
        """Test subscribing to specific workflow."""
        callback = Mock()
        await redis_event_bus.subscribe(
            EventType.TASK_CREATED,
            callback,
            workflow_id="workflow_123",
        )

        assert "task_created:workflow_123" in redis_event_bus.subscribers
        assert callback in redis_event_bus.subscribers["task_created:workflow_123"]

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_callback(self, redis_event_bus):
        """Test unsubscribing removes callback."""
        callback = Mock()
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback)
        await redis_event_bus.unsubscribe(EventType.TASK_CREATED, callback)

        assert callback not in redis_event_bus.subscribers.get("task_created:*", [])

    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self, redis_event_bus):
        """Test multiple subscriptions to same event."""
        callback1 = Mock()
        callback2 = Mock()
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback1)
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback2)

        assert len(redis_event_bus.subscribers["task_created:*"]) == 2


class TestRedisStreamEventBusCallbacks:
    """Test callback triggering."""

    @pytest.mark.asyncio
    async def test_trigger_callbacks_sync(self, redis_event_bus, sample_event):
        """Test triggering synchronous callbacks."""
        callback = Mock()
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback)
        await redis_event_bus._trigger_callbacks(sample_event)

        callback.assert_called_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_trigger_callbacks_async(self, redis_event_bus, sample_event):
        """Test triggering asynchronous callbacks."""
        callback = AsyncMock()
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback)
        await redis_event_bus._trigger_callbacks(sample_event)

        callback.assert_called_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_trigger_callbacks_wildcard_match(self, redis_event_bus, sample_event):
        """Test wildcard subscription matching."""
        callback_wildcard = Mock()
        callback_specific = Mock()
        
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback_wildcard)
        await redis_event_bus.subscribe(
            EventType.TASK_CREATED,
            callback_specific,
            workflow_id="workflow_123",
        )
        
        await redis_event_bus._trigger_callbacks(sample_event)

        callback_wildcard.assert_called_once()
        callback_specific.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_callbacks_error_handling(self, redis_event_bus, sample_event):
        """Test error handling in callbacks."""
        callback_error = Mock(side_effect=Exception("Test error"))
        callback_ok = Mock()
        
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback_error)
        await redis_event_bus.subscribe(EventType.TASK_CREATED, callback_ok)
        
        # Should not raise despite callback error
        await redis_event_bus._trigger_callbacks(sample_event)
        
        callback_error.assert_called_once()
        callback_ok.assert_called_once()


class TestRedisStreamEventBusEventReplay:
    """Test event replay functionality."""

    @pytest.mark.asyncio
    async def test_get_events_all(self, redis_event_bus):
        """Test retrieving all events."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xrange = AsyncMock(
                return_value=[
                    (
                        "1234567890-0",
                        {
                            "event_type": "task_created",
                            "workflow_id": "workflow_123",
                            "event_id": "event_1",
                            "timestamp": utc_now().isoformat(),
                            "payload": "{}",
                        },
                    ),
                ]
            )
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            events = await redis_event_bus.get_events()

            assert len(events) == 1
            assert events[0].event_type == EventType.TASK_CREATED

    @pytest.mark.asyncio
    async def test_get_events_with_event_type_filter(self, redis_event_bus):
        """Test retrieving events with event type filter."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xrange = AsyncMock(
                return_value=[
                    (
                        "1234567890-0",
                        {
                            "event_type": "task_created",
                            "workflow_id": "workflow_123",
                            "event_id": "event_1",
                            "timestamp": utc_now().isoformat(),
                            "payload": "{}",
                        },
                    ),
                    (
                        "1234567891-0",
                        {
                            "event_type": "task_completed",
                            "workflow_id": "workflow_123",
                            "event_id": "event_2",
                            "timestamp": utc_now().isoformat(),
                            "payload": "{}",
                        },
                    ),
                ]
            )
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            events = await redis_event_bus.get_events(event_type=EventType.TASK_CREATED)

            assert len(events) == 1
            assert events[0].event_type == EventType.TASK_CREATED

    @pytest.mark.asyncio
    async def test_get_events_with_workflow_filter(self, redis_event_bus):
        """Test retrieving events with workflow ID filter."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xrange = AsyncMock(
                return_value=[
                    (
                        "1234567890-0",
                        {
                            "event_type": "task_created",
                            "workflow_id": "workflow_123",
                            "event_id": "event_1",
                            "timestamp": utc_now().isoformat(),
                            "payload": "{}",
                        },
                    ),
                    (
                        "1234567891-0",
                        {
                            "event_type": "task_created",
                            "workflow_id": "workflow_456",
                            "event_id": "event_2",
                            "timestamp": utc_now().isoformat(),
                            "payload": "{}",
                        },
                    ),
                ]
            )
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            events = await redis_event_bus.get_events(workflow_id="workflow_123")

            assert len(events) == 1
            assert events[0].workflow_id == "workflow_123"


class TestRedisStreamEventBusDLQ:
    """Test dead letter queue functionality."""

    @pytest.mark.asyncio
    async def test_move_to_dlq(self, redis_event_bus):
        """Test moving message to DLQ."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xadd = AsyncMock(return_value="dlq_id")
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            await redis_event_bus._move_to_dlq(
                "msg_123",
                {"event_type": "task_created"},
                "Test error",
            )

            mock_client.xadd.assert_called_once()
            call_args = mock_client.xadd.call_args
            assert call_args[0][0] == "test_dlq"
            assert call_args[0][1]["original_message_id"] == "msg_123"
            assert call_args[0][1]["error"] == "Test error"

    @pytest.mark.asyncio
    async def test_get_dlq_events(self, redis_event_bus):
        """Test retrieving DLQ events."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xrange = AsyncMock(
                return_value=[
                    (
                        "dlq_1",
                        {
                            "event_type": "task_created",
                            "error": "Processing failed",
                        },
                    ),
                ]
            )
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            dlq_events = await redis_event_bus.get_dlq_events()

            assert len(dlq_events) == 1
            assert dlq_events[0]["error"] == "Processing failed"


class TestRedisStreamEventBusClear:
    """Test clear functionality."""

    @pytest.mark.asyncio
    async def test_clear_events_and_subscribers(self, redis_event_bus):
        """Test clearing events and subscribers."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.delete = AsyncMock()
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            callback = Mock()
            await redis_event_bus.subscribe(EventType.TASK_CREATED, callback)
            
            await redis_event_bus.clear()

            mock_client.delete.assert_any_call("test_stream")
            mock_client.delete.assert_any_call("test_dlq")
            assert len(redis_event_bus.subscribers) == 0

    @pytest.mark.asyncio
    async def test_clear_without_connection_raises(self, redis_event_bus):
        """Test that clear without connection raises error."""
        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await redis_event_bus.clear()


class TestRedisStreamEventBusStreamInfo:
    """Test stream information retrieval."""

    @pytest.mark.asyncio
    async def test_get_stream_info(self, redis_event_bus):
        """Test retrieving stream information."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xinfo_stream = AsyncMock(
                return_value={"length": 10, "radix-tree-keys": 1}
            )
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            info = await redis_event_bus.get_stream_info()

            assert info["length"] == 10
            mock_client.xinfo_stream.assert_called_once_with("test_stream")

    @pytest.mark.asyncio
    async def test_get_consumer_group_info(self, redis_event_bus):
        """Test retrieving consumer group information."""
        with patch("agentManager.engine.event_bus.redis_stream.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.xgroup_create = AsyncMock()
            mock_client.xinfo_groups = AsyncMock(
                return_value=[{"name": "test_group", "consumers": 1}]
            )
            mock_redis.return_value = mock_client

            await redis_event_bus.connect()
            info = await redis_event_bus.get_consumer_group_info()

            assert len(info) == 1
            assert info[0]["name"] == "test_group"
            mock_client.xinfo_groups.assert_called_once_with("test_stream")


class TestRedisStreamEventBusEventDeserialization:
    """Test event serialization and deserialization."""

    @pytest.mark.asyncio
    async def test_deserialize_event(self, redis_event_bus):
        """Test deserializing event from Redis data."""
        now = utc_now()
        data = {
            "event_type": "task_created",
            "workflow_id": "workflow_123",
            "event_id": "event_789",
            "timestamp": now.isoformat(),
            "payload": '{"task_id": "task_456"}',
        }

        event = redis_event_bus._deserialize_event(data)

        assert event.event_type == EventType.TASK_CREATED
        assert event.workflow_id == "workflow_123"
        assert event.event_id == "event_789"
        assert event.payload == {"task_id": "task_456"}

    @pytest.mark.asyncio
    async def test_event_to_dict_and_back(self, sample_event):
        """Test event serialization round-trip."""
        event_dict = sample_event.to_dict()
        restored_event = Event.from_dict(event_dict)

        assert restored_event.event_type == sample_event.event_type
        assert restored_event.workflow_id == sample_event.workflow_id
        assert restored_event.event_id == sample_event.event_id
        assert restored_event.payload == sample_event.payload
