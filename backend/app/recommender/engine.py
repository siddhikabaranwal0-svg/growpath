"""
Recommendation Engine: Orchestrates the full content recommendation pipeline.

1. Builds the KnowledgeGraph and runs Gap Analysis.
2. Fetches the user's latest Learning Path (or relevant topics).
3. Fetches candidate resources from the catalog.
4. Loads user interaction history and skill profiles.
5. Scores & ranks candidates via the multi-signal scoring engine.
6. Logs served recommendations for audit.
7. Returns a structured RecommendationResult.

Mirrors the orchestration pattern of app.ml.engine.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from supabase import Client

from app.planner.graph_builder import KnowledgeGraph
from app.planner.gap_analyzer import analyze_gaps, GapAnalysisResult, DEFAULT_MASTERY_THRESHOLD
from app.planner.path_planner import get_latest_learning_path
from app.ml.engine import get_cached_skill_profile
from app.ml.trend_detector import TopicTrend
from app.recommender.resource_fetcher import (
    fetch_candidate_resources,
    fetch_user_interactions,
    fetch_resource_topic_names,
)
from app.recommender.scoring import (
    ScoringWeights,
    ScoredResource,
    score_and_rank,
)


DEFAULT_TOP_K = 10


@dataclass
class RecommendationResult:
    """Complete recommendation output for a user."""
    user_id: str
    recommendations: list[ScoredResource]
    total_candidates: int
    path_context: dict | None
    generated_at: str


def generate_recommendations(
    supabase: Client,
    user_id: str,
    top_k: int = DEFAULT_TOP_K,
    resource_types: list[str] | None = None,
    target_topic_ids: list[str] | None = None,
    weights: ScoringWeights | None = None,
    exclude_completed: bool = True,
) -> RecommendationResult:
    """
    Run the complete recommendation pipeline for a user.

    Steps:
        1. Build KnowledgeGraph from DB
        2. Run Gap Analysis for the user
        3. Fetch the user's latest Learning Path
        4. Determine relevant topic IDs (from path + gaps)
        5. Fetch candidate resources
        6. Fetch user interaction history
        7. Build proficiency and trend maps from skill profiles
        8. Score & rank candidates
        9. Log recommendations
        10. Return RecommendationResult

    Args:
        supabase: Supabase client for database access.
        user_id: The student's user ID.
        top_k: Maximum number of recommendations to return.
        resource_types: Optional filter for resource types.
        target_topic_ids: Optional scope to specific topics. If None,
                          uses all topics from the learning path + gaps.
        weights: Custom scoring weights. If None, uses defaults.
        exclude_completed: If True, exclude resources the user completed.

    Returns:
        RecommendationResult with ranked recommendations.
    """
    weights = weights or ScoringWeights()
    now = datetime.now(timezone.utc)

    # Step 1: Build knowledge graph
    knowledge_graph = KnowledgeGraph.from_database(supabase)

    if knowledge_graph.node_count == 0:
        return RecommendationResult(
            user_id=user_id,
            recommendations=[],
            total_candidates=0,
            path_context=None,
            generated_at=now.isoformat(),
        )

    # Step 2: Gap analysis
    gap_analysis = analyze_gaps(
        supabase, user_id, knowledge_graph, DEFAULT_MASTERY_THRESHOLD
    )

    # Step 3: Fetch latest learning path
    path_data = get_latest_learning_path(supabase, user_id)
    path_context = None
    path_topic_ids: set[str] = set()

    if path_data and path_data.get("path_data"):
        path_nodes = path_data["path_data"]
        if isinstance(path_nodes, str):
            path_nodes = json.loads(path_nodes)
        path_topic_ids = {node["topic_id"] for node in path_nodes}
        path_context = {
            "path_id": path_data.get("id"),
            "total_steps": path_data.get("total_steps", 0),
            "completed_steps": path_data.get("completed_steps", 0),
            "target_topics": path_data.get("target_topics", []),
        }

    # Step 4: Determine relevant topic IDs
    if target_topic_ids:
        relevant_topics = target_topic_ids
    else:
        # Use all topics from gaps + path
        gap_topic_ids = {g.topic_id for g in gap_analysis.all_gaps}
        relevant_topics = list(gap_topic_ids | path_topic_ids)

        # If no gaps, fall back to all graph topics (new user exploration)
        if not relevant_topics:
            relevant_topics = list(knowledge_graph.graph.nodes())

    # Step 5: Fetch candidate resources
    candidates = fetch_candidate_resources(
        supabase, relevant_topics, resource_types
    )

    if candidates.empty:
        return RecommendationResult(
            user_id=user_id,
            recommendations=[],
            total_candidates=0,
            path_context=path_context,
            generated_at=now.isoformat(),
        )

    total_candidates = len(candidates)

    # Step 6: Fetch user interaction history
    interactions = fetch_user_interactions(supabase, user_id)

    # Step 7: Build proficiency and trend maps from cached skill profiles
    proficiency_map: dict[str, float] = {}
    trend_map: dict[str, TopicTrend] = {}

    cached_profiles = get_cached_skill_profile(supabase, user_id)
    for profile in cached_profiles:
        topic_id = profile.get("topic_id", "")
        proficiency_map[topic_id] = profile.get("proficiency_score", 0.0)
        trend_map[topic_id] = TopicTrend(
            topic_id=topic_id,
            trend=profile.get("trend", "stable"),
            slope=0.0,  # slope not stored in cached profile
            data_points=0,
        )

    # Fetch topic names for display
    candidate_topic_ids = candidates["topic_id"].unique().tolist()
    topic_names = fetch_resource_topic_names(supabase, candidate_topic_ids)

    # Step 8: Score & rank
    scored = score_and_rank(
        candidates=candidates,
        gap_analysis=gap_analysis,
        path_topic_ids=path_topic_ids,
        proficiency_map=proficiency_map,
        trend_map=trend_map,
        interactions=interactions,
        topic_names=topic_names,
        weights=weights,
        top_k=top_k,
        exclude_completed=exclude_completed,
    )

    # Step 9: Log recommendations
    if scored:
        log_recommendations(supabase, user_id, scored, path_context)

    # Step 10: Return result
    return RecommendationResult(
        user_id=user_id,
        recommendations=scored,
        total_candidates=total_candidates,
        path_context=path_context,
        generated_at=now.isoformat(),
    )


def log_recommendations(
    supabase: Client,
    user_id: str,
    scored_resources: list[ScoredResource],
    context: dict | None = None,
) -> None:
    """
    Persist recommendation results to recommendation_logs for audit
    and future A/B testing evaluation.

    Args:
        supabase: Supabase client for database access.
        user_id: The student's user ID.
        scored_resources: List of scored recommendations.
        context: Optional context snapshot (path info, etc.).
    """
    for rank, sr in enumerate(scored_resources, start=1):
        row = {
            "user_id": user_id,
            "resource_id": sr.resource_id,
            "score": sr.final_score,
            "rank": rank,
            "score_breakdown": json.dumps(sr.score_breakdown),
            "context": json.dumps(context or {}),
        }
        try:
            supabase.table("recommendation_logs").insert(row).execute()
        except Exception as e:
            # Log but don't crash the pipeline for a single log entry
            print(f"[WARN] Failed to log recommendation for resource {sr.resource_id}: {e}")


def record_interaction(
    supabase: Client,
    user_id: str,
    resource_id: str,
    interaction_type: str,
    rating: int | None = None,
) -> dict:
    """
    Record a user interaction with a learning resource.

    Args:
        supabase: Supabase client for database access.
        user_id: The student's user ID.
        resource_id: The learning resource ID.
        interaction_type: One of 'viewed', 'completed', 'skipped', 'bookmarked'.
        rating: Optional 1–5 rating.

    Returns:
        The inserted interaction row.

    Raises:
        ValueError: If interaction_type is invalid.
    """
    valid_types = {"viewed", "completed", "skipped", "bookmarked"}
    if interaction_type not in valid_types:
        raise ValueError(
            f"Invalid interaction_type '{interaction_type}'. "
            f"Must be one of: {valid_types}"
        )

    if rating is not None and not (1 <= rating <= 5):
        raise ValueError(f"Rating must be between 1 and 5, got {rating}")

    row: dict = {
        "user_id": user_id,
        "resource_id": resource_id,
        "interaction_type": interaction_type,
    }
    if rating is not None:
        row["rating"] = rating

    res = supabase.table("user_resource_interactions").insert(row).execute()
    return res.data[0] if res.data else {}


def get_recommendation_history(
    supabase: Client,
    user_id: str,
    limit: int = 50,
) -> list[dict]:
    """
    Retrieve the user's recommendation history (past served recommendations).

    Args:
        supabase: Supabase client for database access.
        user_id: The student's user ID.
        limit: Maximum number of log entries to return.

    Returns:
        List of recommendation log entries with resource details.
    """
    res = (
        supabase.table("recommendation_logs")
        .select("*, learning_resources(title, resource_type, url)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data if res.data else []
