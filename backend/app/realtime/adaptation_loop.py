import logging
import asyncio
from typing import Any
from supabase import Client
from dataclasses import asdict

from app.core.security import get_supabase_client
from app.realtime.redis_client import pubsub_manager
from app.realtime.manager import manager as connection_manager
from app.ml.engine import compute_skill_profile
from app.planner.path_planner import generate_learning_path, persist_learning_path, get_latest_learning_path
from app.planner.graph_builder import KnowledgeGraph
from app.recommender.engine import generate_recommendations

logger = logging.getLogger(__name__)

# Constants for pubsub channels
EVENT_CHANNEL_PREFIX = "growpath:events:"
REALTIME_CHANNEL_PREFIX = "growpath:realtime:"

# In-memory debounce tracking: user_id -> Task
_debounce_tasks: dict[str, asyncio.Task] = {}
DEBOUNCE_DELAY_SECONDS = 3.0


async def _run_adaptation_pipeline(user_id: str):
    """
    Core adaptation pipeline executed in the background.
    1. Recompute skill profiles.
    2. Re-generate learning path based on new skills.
    3. Generate updated recommendations.
    4. Publish the payload to the user's real-time channel.
    """
    logger.info(f"Running adaptation pipeline for user {user_id}")
    try:
        # Create a fresh supabase client for the background task
        # Ideally we'd use a service role key if we don't have the user's token context,
        # but for this MVP, we simulate with get_supabase_client directly if environment permits,
        # or we assume RLS allows this service worker to read/write.
        from app.core.security import get_supabase_client
        # In a real background worker without FastAPI context, get_supabase_client needs a way to auth.
        # For this prototype we'll get a raw client (which defaults to anon or service_role depending on ENV)
        import os
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_ANON_KEY") 
        # For backend tasks modifying user data without their token, SERVICE_ROLE key should be used.
        # Here we'll use ANON_KEY which will respect public RLS policies or bypass if configured so.
        # Alternatively, we just use create_client(url, key)
        supabase = create_client(url, key)

        # 1. Recompute skill profile
        skill_result = compute_skill_profile(supabase, user_id)
        
        # 2. Update learning path
        knowledge_graph = KnowledgeGraph.from_database(supabase)
        path = None
        if knowledge_graph.node_count > 0:
            # We don't have specific target topics, we re-evaluate their latest path goals
            old_path = get_latest_learning_path(supabase, user_id)
            target_topics = old_path.get("target_topics") if old_path else None
            
            new_path_obj = generate_learning_path(
                supabase=supabase,
                user_id=user_id,
                knowledge_graph=knowledge_graph,
                target_topic_ids=target_topics,
            )
            if new_path_obj.nodes:
                persist_learning_path(supabase, user_id, new_path_obj)
                path = [asdict(node) for node in new_path_obj.nodes]

        # 3. Regenerate recommendations
        rec_result = generate_recommendations(
            supabase=supabase,
            user_id=user_id,
            top_k=10
        )
        
        # Build payload
        payload = {
            "type": "adaptation_update",
            "user_id": user_id,
            "skills": [asdict(p) for p in skill_result.profiles],
            "path": path,
            "recommendations": [asdict(r) for r in rec_result.recommendations],
            "generated_at": rec_result.generated_at
        }
        
        # 4. Publish to realtime channel
        await pubsub_manager.publish(f"{REALTIME_CHANNEL_PREFIX}{user_id}", payload)
        
    except Exception as e:
        logger.error(f"Error in adaptation pipeline for user {user_id}: {e}")
    finally:
        if user_id in _debounce_tasks:
            del _debounce_tasks[user_id]


def trigger_adaptation_loop(user_id: str):
    """
    Triggers the adaptation loop for a user.
    Uses debouncing to prevent excessive re-computations if multiple events fire rapidly.
    """
    if user_id in _debounce_tasks:
        _debounce_tasks[user_id].cancel()
        
    async def _debounced():
        await asyncio.sleep(DEBOUNCE_DELAY_SECONDS)
        await _run_adaptation_pipeline(user_id)
        
    _debounce_tasks[user_id] = asyncio.create_task(_debounced())


async def handle_realtime_message(message: dict):
    """Callback for messages received on a user's realtime channel. Forwards to their WebSockets."""
    user_id = message.get("user_id")
    if user_id:
        await connection_manager.send_personal_message(message, user_id)


async def handle_progress_event(message: dict):
    """Callback for messages received on the events channel."""
    user_id = message.get("user_id")
    if user_id:
        logger.info(f"Received progress event for user {user_id}: {message.get('event_type')}")
        trigger_adaptation_loop(user_id)


# Global subscription references for cleanup
_subscriptions = []

async def startup_realtime_subscriptions():
    """Called on FastAPI startup to establish pub/sub connections."""
    await pubsub_manager.init_pool()
    # We could subscribe to a global events channel or pattern if Redis supports it,
    # but with InMemoryPubSub, we might need a generic event channel.
    # We'll use a global "growpath:events:global" channel for any server to publish to.
    sub_ref = await pubsub_manager.subscribe("growpath:events:global", handle_progress_event)
    if sub_ref:
        _subscriptions.append(("growpath:events:global", sub_ref))


async def shutdown_realtime_subscriptions():
    """Called on FastAPI shutdown."""
    for channel, sub_ref in _subscriptions:
        await pubsub_manager.unsubscribe(channel, sub_ref)
    _subscriptions.clear()
    await pubsub_manager.close()
