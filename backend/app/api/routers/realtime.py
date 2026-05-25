import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Any

from app.core.security import get_current_user
from app.realtime.manager import manager as connection_manager
from app.realtime.redis_client import pubsub_manager
from app.realtime.adaptation_loop import handle_realtime_message

logger = logging.getLogger(__name__)

router = APIRouter()

class TriggerEventRequest(BaseModel):
    user_id: str = Field(description="ID of the user who triggered the event")
    event_type: str = Field(description="Type of event (e.g. quiz_completed, resource_viewed)")
    topic_id: str | None = Field(default=None, description="Related topic ID")


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for a specific user to receive real-time updates.
    """
    await connection_manager.connect(user_id, websocket)
    
    # Subscribe this worker to the user's personal realtime channel
    # This ensures that if the adaptation loop runs on another worker, this worker still receives the payload.
    channel = f"growpath:realtime:{user_id}"
    subscription_ref = await pubsub_manager.subscribe(channel, handle_realtime_message)
    
    try:
        while True:
            # We don't expect much client->server data, but we keep the connection open
            data = await websocket.receive_text()
            # If client sends a ping or heartbeat, we could respond here
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"User {user_id} disconnected from WebSocket.")
        connection_manager.disconnect(user_id, websocket)
    finally:
        # Unsubscribe when the websocket closes
        await pubsub_manager.unsubscribe(channel, subscription_ref)


@router.post("/trigger")
async def trigger_adaptation(
    request: TriggerEventRequest,
    # In a real app, this endpoint might be protected by a service-to-service API key
    # or require the current user to match request.user_id
    current_user: Any = Depends(get_current_user),
):
    """
    Publish a progress event to trigger the adaptation loop for a user.
    """
    if current_user.id != request.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only trigger events for your own user ID."
        )

    payload = {
        "user_id": request.user_id,
        "event_type": request.event_type,
        "topic_id": request.topic_id
    }
    
    # Publish to the global events channel
    await pubsub_manager.publish("growpath:events:global", payload)
    
    return {"message": "Event published successfully", "event": payload}
