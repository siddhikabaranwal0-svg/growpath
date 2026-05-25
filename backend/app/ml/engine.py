"""
Skill Mapping Engine: Orchestrates the full ML pipeline.

1. Calls the feature extractor for a given user.
2. Pipes features through the proficiency model.
3. Runs trend detection.
4. Writes/upserts results into public.skill_profiles via Supabase.
5. Returns a structured SkillProfileResult.
"""

from dataclasses import dataclass, asdict
from supabase import Client

from app.ml.feature_extractor import fetch_user_responses_with_topics, extract_topic_features
from app.ml.proficiency_model import compute_proficiency_scores, TopicProficiency
from app.ml.trend_detector import detect_trends, TopicTrend


@dataclass
class SkillProfileEntry:
    """Combined proficiency + trend result for a single topic."""
    topic_id: str
    proficiency_score: float
    confidence: str
    trend: str
    slope: float
    raw_accuracy: float
    weighted_accuracy: float
    responses_count: int


@dataclass
class SkillProfileResult:
    """Full skill profile computation result for a user."""
    user_id: str
    profiles: list[SkillProfileEntry]
    topics_analyzed: int
    has_data: bool


def compute_skill_profile(supabase: Client, user_id: str) -> SkillProfileResult:
    """
    Run the complete skill mapping pipeline for a user.

    Steps:
        1. Fetch raw response data with topic mappings
        2. Extract per-topic features
        3. Compute proficiency scores
        4. Detect trends
        5. Merge and persist results
    """
    # Step 1: Fetch data
    responses_df = fetch_user_responses_with_topics(supabase, user_id)

    if responses_df.empty:
        return SkillProfileResult(
            user_id=user_id,
            profiles=[],
            topics_analyzed=0,
            has_data=False,
        )

    # Step 2: Extract features
    topic_features = extract_topic_features(responses_df)

    if topic_features.empty:
        return SkillProfileResult(
            user_id=user_id,
            profiles=[],
            topics_analyzed=0,
            has_data=False,
        )

    # Step 3: Compute proficiency scores
    proficiency_results = compute_proficiency_scores(topic_features)

    # Step 4: Detect trends
    topic_ids = [p.topic_id for p in proficiency_results]
    trend_results = detect_trends(responses_df, topic_ids)

    # Step 5: Merge proficiency + trend into unified entries
    entries = []
    for prof in proficiency_results:
        trend = trend_results.get(prof.topic_id)
        entry = SkillProfileEntry(
            topic_id=prof.topic_id,
            proficiency_score=prof.proficiency_score,
            confidence=prof.confidence,
            trend=trend.trend if trend else "stable",
            slope=trend.slope if trend else 0.0,
            raw_accuracy=prof.raw_accuracy,
            weighted_accuracy=prof.weighted_accuracy,
            responses_count=prof.responses_count,
        )
        entries.append(entry)

    # Step 6: Persist to database (upsert into skill_profiles)
    _persist_skill_profiles(supabase, user_id, entries)

    return SkillProfileResult(
        user_id=user_id,
        profiles=entries,
        topics_analyzed=len(entries),
        has_data=True,
    )


def _persist_skill_profiles(supabase: Client, user_id: str, entries: list[SkillProfileEntry]):
    """
    Upsert skill profile entries into the database.
    Uses Supabase's upsert with the unique (user_id, topic_id) constraint.
    """
    for entry in entries:
        row = {
            "user_id": user_id,
            "topic_id": entry.topic_id,
            "proficiency_score": entry.proficiency_score,
            "confidence": entry.confidence,
            "trend": entry.trend,
            "responses_count": entry.responses_count,
        }

        try:
            supabase.table("skill_profiles").upsert(
                row,
                on_conflict="user_id,topic_id"
            ).execute()
        except Exception as e:
            # Log but don't crash the pipeline for a single topic
            print(f"[WARN] Failed to persist skill profile for topic {entry.topic_id}: {e}")


def get_cached_skill_profile(supabase: Client, user_id: str) -> list[dict]:
    """
    Retrieve the most recently computed skill profiles from the database.
    """
    res = (
        supabase.table("skill_profiles")
        .select("*, topics(name, slug)")
        .eq("user_id", user_id)
        .order("proficiency_score", desc=True)
        .execute()
    )
    return res.data if res.data else []


def get_cached_topic_profile(supabase: Client, user_id: str, topic_id: str) -> dict | None:
    """
    Retrieve a single cached skill profile for a specific topic.
    """
    res = (
        supabase.table("skill_profiles")
        .select("*, topics(name, slug)")
        .eq("user_id", user_id)
        .eq("topic_id", topic_id)
        .single()
        .execute()
    )
    return res.data if res.data else None
