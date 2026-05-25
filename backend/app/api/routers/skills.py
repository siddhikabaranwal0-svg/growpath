from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from typing import Any
from dataclasses import asdict

from app.core.security import get_supabase_client, get_current_user
from app.ml.engine import compute_skill_profile, get_cached_skill_profile, get_cached_topic_profile

router = APIRouter()


@router.get("/me")
async def get_my_skill_profile(
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Returns the current user's cached skill profile across all topics.
    Returns the most recently computed proficiency scores.
    """
    try:
        profiles = get_cached_skill_profile(supabase, current_user.id)
        return {
            "user_id": current_user.id,
            "profiles": profiles,
            "topics_count": len(profiles),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch skill profile: {str(e)}"
        )


@router.post("/me/compute")
async def compute_my_skill_profile(
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Triggers a fresh recomputation of the current user's skill profile.
    Runs the full ML pipeline: feature extraction → proficiency scoring → trend detection.
    """
    try:
        result = compute_skill_profile(supabase, current_user.id)
        return {
            "user_id": result.user_id,
            "has_data": result.has_data,
            "topics_analyzed": result.topics_analyzed,
            "profiles": [asdict(p) for p in result.profiles],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill profile computation failed: {str(e)}"
        )


@router.get("/me/{topic_id}")
async def get_my_topic_profile(
    topic_id: str,
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Returns the detailed proficiency breakdown for a single topic.
    """
    try:
        profile = get_cached_topic_profile(supabase, current_user.id, topic_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No skill profile found for topic {topic_id}. Run POST /api/skills/me/compute first."
            )
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch topic profile: {str(e)}"
        )
