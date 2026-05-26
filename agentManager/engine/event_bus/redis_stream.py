"""Redis Streams based event bus implementation.

Provides persistent event storage, consumer groups, ACK mechanism, and event replay.
"""

import json
import logging
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime, timezone
import asyncio

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class RedisStreamEventBus(BaseEventBus):
    """Redis Streams based event bus with persistence and consumer groups."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        stream_key: str = "event_stream",
        consumer_group: str = "event_consumers",
        dlq_key: str = "event_dlq",
        max_retries: int = 3,
    ):
        """Initialize Redis Streams event bus.

        Args:
            redis_url: Redis connection URL
            stream_key: Redis stream key name
            consumer_group: Consumer group name
            dlq_key: Dead letter queue key name
            max_retries: Maximum retries before moving to DLQ
        """
        self.redis_url = redis_url
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self.dlq_key = dlq_key
        self.max_retries = max_retries
        self.redis_client: Optional[Redis] = None
        self.subscribers: Dict[str, List[Callable]] = {}
        self._consumer_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")

            # Create consumer group if it doesn't exist
            try:
                await self.redis_client.xgroup_create(
                    self.stream_key,
                    self.consumer_group,
                    id="0",
                    mkstream=True,
                )
                logger.info(f"Created consumer group {self.consumer_group}")
            except ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
                logger.info(f"Consumer group {self.consumer_group} already exists")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        # Cancel all consumer tasks
        for task in self._consumer_tasks.values():
            task.cancel()

        if self.redis_client:
            await self.redis_client.close()
            logger.info("Disconnected from Redis")

    async def publish(self, event: Event) -> None:
        """Publish an event to the stream.

        Args:
            event: Event to publish
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        try:
            event_data = {
                "event_type": event.event_type.value,
                "workflow_id": event.workflow_id,
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "payload": json.dumps(event.payload),
            }

            message_id = await self.redis_client.xadd(self.stream_key, event_data)
            logger.info(
                f"Published event {event.event_id} (type: {event.event_type.value}) "
                f"to stream with ID {message_id}"
            )
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            raise

    async def subscribe(
        self,
        event_type: EventType,
        callback: Callable,
        workflow_id: Optional[str] = None,
    ) -> None:
        """Subscribe to events.

        Args:
            event_type: Type of event to subscribe to
            callback: Callback function to invoke
            workflow_id: Optional workflow ID for filtering
        """
        key = f"{event_type.value}:{workflow_id or '*'}"

        if key not in self.subscribers:
            self.subscribers[key] = []

        self.subscribers[key].append(callback)
        logger.info(f"Subscribed to {key}")

    async def unsubscribe(
        self,
        event_type: EventType,
        callback: Callable,
        workflow_id: Optional[str] = None,
    ) -> None:
        """Unsubscribe from events.

        Args:
            event_type: Type of event
            callback: Callback to remove
            workflow_id: Optional workflow ID
        """
        key = f"{event_type.value}:{workflow_id or '*'}"

        if key in self.subscribers and callback in self.subscribers[key]:
            self.subscribers[key].remove(callback)
            logger.info(f"Unsubscribed from {key}")

    async def _trigger_callbacks(self, event: Event) -> None:
        """Trigger all matching callbacks for an event.

        Args:
            event: Event to process
        """
        keys = [
            f"{event.event_type.value}:{event.workflow_id}",
            f"{event.event_type.value}:*",
        ]

        for key in keys:
            for callback in self.subscribers.get(key, []):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Error in subscriber callback for {key}: {e}")

    async def start_consumer(self, consumer_name: str = "default") -> None:
        """Start consuming events from the stream.

        Args:
            consumer_name: Name of the consumer
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        async def consume_loop():
            last_id = ">"  # Start from new messages

            while True:
                try:
                    # Read from consumer group
                    messages = await self.redis_client.xreadgroup(
                        {self.stream_key: last_id},
                        self.consumer_group,
                        consumer_name,
                        count=10,
                        block=1000,
                    )

                    if messages:
                        for stream_key, stream_messages in messages:
                            for message_id, data in stream_messages:
                                try:
                                    event = self._deserialize_event(data)
                                    await self._trigger_callbacks(event)

                                    # ACK the message
                                    await self.redis_client.xack(
                                        self.stream_key,
                                        self.consumer_group,
                                        message_id,
                                    )
                                    logger.debug(f"ACKed message {message_id}")
                                except Exception as e:
                                    logger.error(f"Error processing message {message_id}: {e}")
                                    # Move to DLQ on error
                                    await self._move_to_dlq(message_id, data, str(e))
                except asyncio.CancelledError:
                    logger.info(f"Consumer {consumer_name} stopped")
                    break
                except Exception as e:
                    logger.error(f"Error in consumer loop: {e}")
                    await asyncio.sleep(1)

        task = asyncio.create_task(consume_loop())
        self._consumer_tasks[consumer_name] = task
        logger.info(f"Started consumer {consumer_name}")

    def _deserialize_event(self, data: Dict[str, str]) -> Event:
        """Deserialize event from Redis data.

        Args:
            data: Raw data from Redis

        Returns:
            Deserialized Event object
        """
        return Event(
            event_type=EventType(data["event_type"]),
            workflow_id=data["workflow_id"],
            event_id=data["event_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            payload=json.loads(data.get("payload", "{}")),
        )

    async def _move_to_dlq(
        self,
        message_id: str,
        data: Dict[str, str],
        error: str,
    ) -> None:
        """Move a failed message to the dead letter queue.

        Args:
            message_id: Original message ID
            data: Message data
            error: Error message
        """
        if not self.redis_client:
            return

        try:
            dlq_data = {
                **data,
                "original_message_id": message_id,
                "error": error,
                "moved_at": utc_now().isoformat(),
            }
            await self.redis_client.xadd(self.dlq_key, dlq_data)
            logger.warning(f"Moved message {message_id} to DLQ: {error}")
        except Exception as e:
            logger.error(f"Failed to move message to DLQ: {e}")

    async def get_events(
        self,
        event_type: Optional[EventType] = None,
        workflow_id: Optional[str] = None,
        start_id: str = "-",
        end_id: str = "+",
    ) -> List[Event]:
        """Get events from the stream (event replay).

        Args:
            event_type: Optional event type filter
            workflow_id: Optional workflow ID filter
            start_id: Start message ID (default: "-" for beginning)
            end_id: End message ID (default: "+" for end)

        Returns:
            List of matching events
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        try:
            messages = await self.redis_client.xrange(
                self.stream_key,
                min=start_id,
                max=end_id,
            )

            events = []
            for message_id, data in messages:
                try:
                    event = self._deserialize_event(data)

                    # Apply filters
                    if event_type and event.event_type != event_type:
                        continue
                    if workflow_id and event.workflow_id != workflow_id:
                        continue

                    events.append(event)
                except Exception as e:
                    logger.error(f"Error deserializing event from {message_id}: {e}")

            logger.info(f"Retrieved {len(events)} events from stream")
            return events
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            raise

    async def get_dlq_events(self) -> List[Dict[str, Any]]:
        """Get all events from the dead letter queue.

        Returns:
            List of DLQ events
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        try:
            messages = await self.redis_client.xrange(self.dlq_key)
            dlq_events = [data for _, data in messages]
            logger.info(f"Retrieved {len(dlq_events)} events from DLQ")
            return dlq_events
        except Exception as e:
            logger.error(f"Failed to get DLQ events: {e}")
            raise

    async def clear(self) -> None:
        """Clear all events and subscribers."""
        if not self.redis_client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        try:
            await self.redis_client.delete(self.stream_key)
            await self.redis_client.delete(self.dlq_key)
            self.subscribers.clear()
            logger.info("Event bus cleared")
        except Exception as e:
            logger.error(f"Failed to clear event bus: {e}")
            raise

    async def get_stream_info(self) -> Dict[str, Any]:
        """Get information about the stream.

        Returns:
            Stream information
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        try:
            info = await self.redis_client.xinfo_stream(self.stream_key)
            return info
        except Exception as e:
            logger.error(f"Failed to get stream info: {e}")
            raise

    async def get_consumer_group_info(self) -> Dict[str, Any]:
        """Get information about the consumer group.

        Returns:
            Consumer group information
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        try:
            info = await self.redis_client.xinfo_groups(self.stream_key)
            return info
        except Exception as e:
            logger.error(f"Failed to get consumer group info: {e}")
            raise
