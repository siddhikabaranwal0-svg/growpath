"""
Recommendations API Router: Endpoints for personalized content recommendations.

Provides endpoints for:
- Getting personalized recommendations (overall and per-topic)
- Recording user interactions with resources
- Viewing recommendation history

Follows the existing router patterns in paths.py and skills.py.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from supabase import Client
from typing import Any
from dataclasses import asdict

from app.core.security import get_supabase_client, get_current_user
from app.recommender.engine import (
    generate_recommendations,
    record_interaction,
    get_recommendation_history,
    DEFAULT_TOP_K,
)
from app.recommender.scoring import ScoringWeights

router = APIRouter()


# ── Request / Response Models ─────────────────────────────────────────────────

class RecommendationRequest(BaseModel):
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=50, description="Number of recommendations to return")
    resource_types: list[str] | None = Field(default=None, description="Filter by resource types: article, video, exercise, external_link, quiz")
    target_topics: list[str] | None = Field(default=None, description="Scope recommendations to specific topic IDs")
    exclude_completed: bool = Field(default=True, description="Exclude resources the user has completed")


class InteractionRequest(BaseModel):
    resource_id: str = Field(description="ID of the learning resource")
    interaction_type: str = Field(description="One of: viewed, completed, skipped, bookmarked")
    rating: int | None = Field(default=None, ge=1, le=5, description="Optional 1-5 rating")


class ScoredResourceResponse(BaseModel):
    resource_id: str
    title: str
    resource_type: str
    topic_id: str
    topic_name: str
    final_score: float
    score_breakdown: dict
    difficulty_level: int
    estimated_minutes: int | None
    url: str | None


class RecommendationResponse(BaseModel):
    user_id: str
    recommendations: list[ScoredResourceResponse]
    total_candidates: int
    path_context: dict | None
    generated_at: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/me")
async def get_my_recommendations(
    top_k: int = Query(default=DEFAULT_TOP_K, ge=1, le=50),
    resource_type: str | None = Query(default=None, description="Filter by resource type"),
    exclude_completed: bool = Query(default=True),
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Get personalized learning resource recommendations for the current user.

    Returns the top-K resources ranked by a multi-signal scoring algorithm
    that considers skill gaps, difficulty alignment, learning trends,
    content freshness, diversity, and quality.
    """
    try:
        resource_types = [resource_type] if resource_type else None

        result = generate_recommendations(
            supabase=supabase,
            user_id=current_user.id,
            top_k=top_k,
            resource_types=resource_types,
            exclude_completed=exclude_completed,
        )

        return {
            "user_id": result.user_id,
            "recommendations": [asdict(r) for r in result.recommendations],
            "total_candidates": result.total_candidates,
            "path_context": result.path_context,
            "generated_at": result.generated_at,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recommendation generation failed: {str(e)}"
        )


@router.post("/me")
async def generate_my_recommendations(
    request: RecommendationRequest = RecommendationRequest(),
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Generate personalized recommendations with advanced filtering options.

    Accepts optional target_topics, resource_types, and top_k parameters
    for fine-grained control over the recommendation output.
    """
    try:
        result = generate_recommendations(
            supabase=supabase,
            user_id=current_user.id,
            top_k=request.top_k,
            resource_types=request.resource_types,
            target_topic_ids=request.target_topics,
            exclude_completed=request.exclude_completed,
        )

        return {
            "user_id": result.user_id,
            "recommendations": [asdict(r) for r in result.recommendations],
            "total_candidates": result.total_candidates,
            "path_context": result.path_context,
            "generated_at": result.generated_at,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recommendation generation failed: {str(e)}"
        )


@router.get("/me/topic/{topic_id}")
async def get_topic_recommendations(
    topic_id: str,
    top_k: int = Query(default=DEFAULT_TOP_K, ge=1, le=50),
    exclude_completed: bool = Query(default=True),
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Get recommendations scoped to a specific topic.

    Useful when a student is focused on a particular area and wants
    targeted resource suggestions.
    """
    try:
        result = generate_recommendations(
            supabase=supabase,
            user_id=current_user.id,
            top_k=top_k,
            target_topic_ids=[topic_id],
            exclude_completed=exclude_completed,
        )

        return {
            "user_id": result.user_id,
            "topic_id": topic_id,
            "recommendations": [asdict(r) for r in result.recommendations],
            "total_candidates": result.total_candidates,
            "path_context": result.path_context,
            "generated_at": result.generated_at,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Topic recommendation failed: {str(e)}"
        )


@router.post("/me/interact")
async def record_resource_interaction(
    request: InteractionRequest,
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Record a user interaction with a learning resource.

    Interaction types: viewed, completed, skipped, bookmarked.
    Optionally include a 1-5 rating.

    This data feeds back into the recommendation scoring engine
    for freshness and diversity signals.
    """
    try:
        interaction = record_interaction(
            supabase=supabase,
            user_id=current_user.id,
            resource_id=request.resource_id,
            interaction_type=request.interaction_type,
            rating=request.rating,
        )

        return {
            "message": f"Interaction '{request.interaction_type}' recorded successfully.",
            "interaction": interaction,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record interaction: {str(e)}"
        )


@router.get("/me/history")
async def get_my_recommendation_history(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    View the user's recommendation history — past recommendations that
    were served, including scores and ranking context.

    Useful for transparency and debugging recommendation quality.
    """
    try:
        history = get_recommendation_history(
            supabase=supabase,
            user_id=current_user.id,
            limit=limit,
        )

        return {
            "user_id": current_user.id,
            "history": history,
            "count": len(history),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch recommendation history: {str(e)}"
        )
