import json
import logging
import asyncio
from typing import Callable, Any, Awaitable
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class InMemoryPubSub:
    """
    Graceful fallback for local development or testing when Redis is not available.
    Implements a simple async in-memory pub/sub broker.
    """
    def __init__(self):
        self.subscribers: dict[str, set[Callable[[dict], Awaitable[None]]]] = {}
        self.lock = asyncio.Lock()

    async def publish(self, channel: str, message: str):
        async with self.lock:
            subs = self.subscribers.get(channel, set()).copy()
        
        if not subs:
            return
            
        try:
            data = json.loads(message)
        except Exception:
            data = message
            
        for callback in subs:
            try:
                # Fire and forget callback execution
                asyncio.create_task(callback(data))
            except Exception as e:
                logger.error(f"Error executing in-memory subscriber callback: {e}")

    async def subscribe(self, channel: str, callback: Callable[[dict], Awaitable[None]]):
        async with self.lock:
            if channel not in self.subscribers:
                self.subscribers[channel] = set()
            self.subscribers[channel].add(callback)

    async def unsubscribe(self, channel: str, callback: Callable[[dict], Awaitable[None]]):
        async with self.lock:
            if channel in self.subscribers:
                self.subscribers[channel].discard(callback)
                if not self.subscribers[channel]:
                    del self.subscribers[channel]


class RedisPubSubManager:
    """
    Manager for Redis connections and Pub/Sub functionality.
    Falls back to InMemoryPubSub if Redis is unavailable or disabled.
    """
    def __init__(self):
        self.redis_client = None
        self.fallback_broker = None
        self.pubsub_tasks = set()

    async def init_pool(self):
        """Initialize Redis connection pool or fallback broker."""
        if not settings.USE_REDIS or redis is None:
            logger.info("Redis is disabled or not installed. Using InMemoryPubSub fallback.")
            self.fallback_broker = InMemoryPubSub()
            return

        try:
            pool = redis.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True
            )
            self.redis_client = redis.Redis(connection_pool=pool)
            # Test connection
            await self.redis_client.ping()
            logger.info("Successfully connected to Redis for real-time pub/sub.")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Falling back to InMemoryPubSub.")
            self.redis_client = None
            self.fallback_broker = InMemoryPubSub()

    async def close(self):
        """Close connections and cancel listening tasks."""
        if self.redis_client:
            await self.redis_client.close()
            
        for task in self.pubsub_tasks:
            task.cancel()
        self.pubsub_tasks.clear()

    async def publish(self, channel: str, message: dict):
        """Publish a message to a channel."""
        message_str = json.dumps(message)
        if self.redis_client:
            try:
                await self.redis_client.publish(channel, message_str)
            except Exception as e:
                logger.error(f"Failed to publish to Redis channel {channel}: {e}")
        elif self.fallback_broker:
            await self.fallback_broker.publish(channel, message_str)

    async def subscribe(self, channel: str, callback: Callable[[dict], Awaitable[None]]):
        """
        Subscribe to a channel and execute callback for each message.
        Returns a task or subscription object that can be cancelled/unsubscribed.
        """
        if self.redis_client:
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(channel)
            
            async def _listen():
                try:
                    async for message in pubsub.listen():
                        if message["type"] == "message":
                            try:
                                data = json.loads(message["data"])
                                await callback(data)
                            except Exception as e:
                                logger.error(f"Error processing Redis message: {e}")
                except asyncio.CancelledError:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                    
            task = asyncio.create_task(_listen())
            self.pubsub_tasks.add(task)
            # Remove from task set when done
            task.add_done_callback(self.pubsub_tasks.discard)
            return task
        elif self.fallback_broker:
            await self.fallback_broker.subscribe(channel, callback)
            return callback

    async def unsubscribe(self, channel: str, subscription_ref: Any):
        """Unsubscribe from a channel using the reference returned by subscribe."""
        if self.redis_client and isinstance(subscription_ref, asyncio.Task):
            subscription_ref.cancel()
        elif self.fallback_broker and callable(subscription_ref):
            await self.fallback_broker.unsubscribe(channel, subscription_ref)


pubsub_manager = RedisPubSubManager()
