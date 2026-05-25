from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client
from typing import Any
from dataclasses import asdict

from app.core.security import get_supabase_client, get_current_user
from app.planner.graph_builder import KnowledgeGraph
from app.planner.path_planner import (
    generate_learning_path,
    persist_learning_path,
    get_latest_learning_path,
    DEFAULT_MASTERY_THRESHOLD,
    DEFAULT_MAX_STEPS,
)

router = APIRouter()


class GeneratePathRequest(BaseModel):
    target_topics: list[str] | None = None
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD
    max_steps: int = DEFAULT_MAX_STEPS


class ValidateEdgeRequest(BaseModel):
    prerequisite_topic_id: str
    topic_id: str


@router.get("/me")
async def get_my_learning_path(
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Returns the user's most recently generated learning path.
    """
    try:
        path = get_latest_learning_path(supabase, current_user.id)
        if not path:
            return {
                "message": "No learning path found. Use POST /api/paths/me/generate to create one.",
                "path": None,
            }
        return {"path": path}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch learning path: {str(e)}"
        )


@router.post("/me/generate")
async def generate_my_learning_path(
    request: GeneratePathRequest = GeneratePathRequest(),
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Triggers path generation based on the user's current skill gaps.
    
    Accepts optional target_topics (goal topic IDs), mastery_threshold, and max_steps.
    If no targets are provided, automatically identifies unmastered leaf topics.
    """
    try:
        # Build the knowledge graph from the database
        knowledge_graph = KnowledgeGraph.from_database(supabase)

        if knowledge_graph.node_count == 0:
            return {
                "message": "No topics found in the knowledge graph. Please add topics and prerequisites first.",
                "path": None,
            }

        # Generate the personalized path
        path = generate_learning_path(
            supabase=supabase,
            user_id=current_user.id,
            knowledge_graph=knowledge_graph,
            target_topic_ids=request.target_topics,
            mastery_threshold=request.mastery_threshold,
            max_steps=request.max_steps,
        )

        # Persist to database
        if path.nodes:
            persisted = persist_learning_path(
                supabase, current_user.id, path, request.mastery_threshold
            )
        else:
            persisted = None

        return {
            "message": "Learning path generated successfully" if path.nodes else "All topics mastered — no path needed!",
            "total_steps": path.total_steps,
            "estimated_effort": path.estimated_effort,
            "target_topics": path.target_topics,
            "path": [asdict(node) for node in path.nodes],
            "persisted_id": persisted.get("id") if persisted else None,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Path generation failed: {str(e)}"
        )


@router.get("/graph")
async def get_topic_graph(
    supabase: Client = Depends(get_supabase_client),
):
    """
    Returns the full topic prerequisite graph as a JSON adjacency list.
    Publicly accessible for frontend visualization.
    """
    try:
        knowledge_graph = KnowledgeGraph.from_database(supabase)
        adj = knowledge_graph.to_adjacency_dict()
        return {
            "node_count": knowledge_graph.node_count,
            "edge_count": knowledge_graph.edge_count,
            "root_topics": knowledge_graph.get_root_topics(),
            "leaf_topics": knowledge_graph.get_leaf_topics(),
            "graph": adj,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build topic graph: {str(e)}"
        )


@router.post("/graph/validate")
async def validate_prerequisite_edge(
    request: ValidateEdgeRequest,
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Checks if adding a proposed prerequisite edge would create a cycle.
    Returns {valid: true} if safe, {valid: false} if it would break the DAG.
    """
    try:
        knowledge_graph = KnowledgeGraph.from_database(supabase)

        would_cycle = knowledge_graph.would_create_cycle(
            prerequisite_id=request.prerequisite_topic_id,
            topic_id=request.topic_id,
        )

        return {
            "valid": not would_cycle,
            "would_create_cycle": would_cycle,
            "prerequisite_topic_id": request.prerequisite_topic_id,
            "topic_id": request.topic_id,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}"
        )
