"""
Scoring Engine: Multi-signal content recommendation scoring.

Computes a composite recommendation score for each candidate learning resource
using six weighted signals:
  1. Relevance      — gap severity alignment with learning path
  2. Difficulty Fit — Gaussian alignment between resource difficulty and student level
  3. Trend Boost    — urgency boost for declining topics
  4. Freshness      — spaced repetition: rewards topics not recently studied
  5. Diversity      — penalizes over-represented resource types
  6. Quality        — direct passthrough of curated quality score

All signal functions operate on Pandas DataFrames/Series for vectorized performance.
No external ML models required — pure algorithmic scoring with NumPy.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from dataclasses import dataclass, field

from app.planner.gap_analyzer import GapAnalysisResult
from app.ml.trend_detector import TopicTrend


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class ScoringWeights:
    """Configurable weights for the recommendation signals.

    Weights should sum to 1.0 for interpretable final scores in [0, 1].
    """
    relevance: float = 0.35
    difficulty_fit: float = 0.20
    trend_boost: float = 0.15
    freshness: float = 0.10
    diversity: float = 0.10
    quality: float = 0.10

    def as_dict(self) -> dict[str, float]:
        return {
            "relevance": self.relevance,
            "difficulty_fit": self.difficulty_fit,
            "trend_boost": self.trend_boost,
            "freshness": self.freshness,
            "diversity": self.diversity,
            "quality": self.quality,
        }


@dataclass
class ScoredResource:
    """A resource with its computed recommendation score and breakdown."""
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


# ── Signal Functions ──────────────────────────────────────────────────────────

# Path multiplier: resources for topics on the active learning path get boosted
PATH_RELEVANCE_MULTIPLIER = 1.5

# Gaussian width parameter for difficulty fit
DIFFICULTY_FIT_SIGMA = 1.0

# Freshness half-life in days: how fast the freshness score recovers
FRESHNESS_HALF_LIFE_DAYS = 14.0


def _proficiency_to_ideal_difficulty(proficiency: float) -> float:
    """
    Map a proficiency score (0–100) to an ideal resource difficulty level (1–5).

    The mapping is linear:
        0   → 1.0 (beginner)
        50  → 3.0 (intermediate)
        100 → 5.0 (expert)
    """
    return 1.0 + (proficiency / 100.0) * 4.0


def compute_relevance_scores(
    candidates: pd.DataFrame,
    gap_analysis: GapAnalysisResult,
    path_topic_ids: set[str],
) -> pd.Series:
    """
    Compute the relevance signal for all candidate resources.

    Higher gap_severity → higher relevance. Resources for topics on the active
    learning path receive a multiplier boost.

    Args:
        candidates: DataFrame with 'topic_id' column.
        gap_analysis: GapAnalysisResult containing per-topic gaps.
        path_topic_ids: Set of topic IDs on the active learning path.

    Returns:
        pd.Series of relevance scores in [0, 1], indexed like candidates.
    """
    if candidates.empty:
        return pd.Series(dtype=float)

    # Build gap severity lookup: topic_id → gap_severity
    severity_map: dict[str, float] = {}
    max_severity = gap_analysis.mastery_threshold  # theoretical max

    for gap in gap_analysis.all_gaps:
        severity_map[gap.topic_id] = gap.gap_severity
    for gap in gap_analysis.mastered:
        severity_map[gap.topic_id] = 0.0

    # Normalize to [0, 1]
    raw_relevance = candidates["topic_id"].map(
        lambda tid: severity_map.get(tid, max_severity)
    )
    # Normalize by max possible severity
    normalized = raw_relevance / max(max_severity, 1.0)

    # Apply path multiplier (capped at 1.0)
    on_path = candidates["topic_id"].isin(path_topic_ids).astype(float)
    boosted = normalized * (1.0 + on_path * (PATH_RELEVANCE_MULTIPLIER - 1.0))

    return boosted.clip(0.0, 1.0)


def compute_difficulty_fit_scores(
    candidates: pd.DataFrame,
    proficiency_map: dict[str, float],
) -> pd.Series:
    """
    Gaussian alignment between resource difficulty and student proficiency.

    Perfect alignment (resource difficulty == ideal for student) → 1.0.
    Mismatch decays as exp(-0.5 × ((diff - ideal) / σ)²).

    Args:
        candidates: DataFrame with 'topic_id' and 'difficulty_level' columns.
        proficiency_map: Dict mapping topic_id → proficiency score (0–100).

    Returns:
        pd.Series of difficulty fit scores in [0, 1].
    """
    if candidates.empty:
        return pd.Series(dtype=float)

    ideal_difficulty = candidates["topic_id"].map(
        lambda tid: _proficiency_to_ideal_difficulty(
            proficiency_map.get(tid, 0.0)
        )
    )

    resource_difficulty = candidates["difficulty_level"].astype(float)
    diff = resource_difficulty - ideal_difficulty

    # Gaussian fit: perfect match = 1.0
    fit = np.exp(-0.5 * (diff / DIFFICULTY_FIT_SIGMA) ** 2)

    return pd.Series(fit, index=candidates.index).clip(0.0, 1.0)


def compute_trend_boost_scores(
    candidates: pd.DataFrame,
    trend_map: dict[str, TopicTrend],
) -> pd.Series:
    """
    Boost resources for topics where the student is declining.

    - declining → 1.0 (high urgency)
    - stable    → 0.5 (neutral)
    - improving → 0.2 (low urgency, already getting better)
    - unknown   → 0.5 (neutral)

    Args:
        candidates: DataFrame with 'topic_id' column.
        trend_map: Dict mapping topic_id → TopicTrend.

    Returns:
        pd.Series of trend boost scores in [0, 1].
    """
    if candidates.empty:
        return pd.Series(dtype=float)

    trend_score_map = {
        "declining": 1.0,
        "stable": 0.5,
        "improving": 0.2,
    }

    scores = candidates["topic_id"].map(
        lambda tid: trend_score_map.get(
            trend_map[tid].trend if tid in trend_map else "stable",
            0.5,
        )
    )

    return pd.Series(scores, index=candidates.index).clip(0.0, 1.0)


def compute_freshness_scores(
    candidates: pd.DataFrame,
    interactions: pd.DataFrame,
) -> pd.Series:
    """
    Spaced repetition freshness based on last interaction time per topic.

    Longer time since last interaction → higher freshness.
    Uses exponential recovery: freshness = 1 - exp(-age_days / half_life).

    Resources never interacted with get freshness = 1.0 (fully fresh).
    Recently interacted resources are penalized.

    Args:
        candidates: DataFrame with 'topic_id' column.
        interactions: User's interaction history with 'resource_id' and
                      'interacted_at' columns.

    Returns:
        pd.Series of freshness scores in [0, 1].
    """
    if candidates.empty:
        return pd.Series(dtype=float)

    if interactions.empty:
        # No interactions → everything is maximally fresh
        return pd.Series(1.0, index=candidates.index)

    now = datetime.now(timezone.utc)

    # Find last interaction time per resource
    last_interaction = (
        interactions
        .groupby("resource_id")["interacted_at"]
        .max()
        .to_dict()
    )

    def _freshness_for_resource(resource_id: str) -> float:
        last_time = last_interaction.get(resource_id)
        if last_time is None:
            return 1.0  # never interacted → fully fresh
        age_days = (now - last_time).total_seconds() / 86400.0
        age_days = max(age_days, 0.0)
        # Exponential recovery toward 1.0
        return 1.0 - np.exp(-age_days / FRESHNESS_HALF_LIFE_DAYS)

    scores = candidates["resource_id"].map(_freshness_for_resource)

    return pd.Series(scores, index=candidates.index).clip(0.0, 1.0)


def compute_diversity_scores(
    candidates: pd.DataFrame,
    interactions: pd.DataFrame,
) -> pd.Series:
    """
    Penalize resource types that are over-represented in the user's history.

    Computes the distribution of resource_type in recent interactions, then
    scores each candidate inversely to how common its type is in that history.

    Users with no interaction history get uniform diversity (1.0).

    Args:
        candidates: DataFrame with 'resource_type' column.
        interactions: User's interaction history (we join with resources
                      externally, but here we use the type distribution
                      from candidates' types).

    Returns:
        pd.Series of diversity scores in [0, 1].
    """
    if candidates.empty:
        return pd.Series(dtype=float)

    if interactions.empty:
        # No history → no bias → max diversity
        return pd.Series(1.0, index=candidates.index)

    # Count interactions per resource_id, then we need to know the resource_type
    # of interacted resources. Since we don't have that directly, we use the
    # interaction count per resource and cross-reference with candidates.
    # Alternative: compute type distribution from interactions joined with
    # candidate metadata. For simplicity, we use a uniform penalty based on
    # how many times the user has interacted with resources of each type
    # among the current candidates.

    # Get resource types from candidates that user has interacted with
    interacted_ids = set(interactions["resource_id"].unique())
    interacted_candidates = candidates[
        candidates["resource_id"].isin(interacted_ids)
    ]

    if interacted_candidates.empty:
        return pd.Series(1.0, index=candidates.index)

    # Type frequency in user's past interactions (from candidates we know about)
    type_counts = interacted_candidates["resource_type"].value_counts(normalize=True)

    # Diversity = 1 - frequency of this type (rare types get higher diversity)
    scores = candidates["resource_type"].map(
        lambda rt: 1.0 - type_counts.get(rt, 0.0)
    )

    return pd.Series(scores, index=candidates.index).clip(0.0, 1.0)


# ── Composite Scoring Pipeline ────────────────────────────────────────────────

def score_and_rank(
    candidates: pd.DataFrame,
    gap_analysis: GapAnalysisResult,
    path_topic_ids: set[str],
    proficiency_map: dict[str, float],
    trend_map: dict[str, TopicTrend],
    interactions: pd.DataFrame,
    topic_names: dict[str, str] | None = None,
    weights: ScoringWeights = ScoringWeights(),
    top_k: int = 10,
    exclude_completed: bool = True,
) -> list[ScoredResource]:
    """
    Full scoring pipeline: compute all signals, combine with weights, rank,
    and return top-K resources.

    Args:
        candidates: DataFrame of candidate resources (from resource_fetcher).
        gap_analysis: User's gap analysis result.
        path_topic_ids: Set of topic IDs on the active learning path.
        proficiency_map: Dict mapping topic_id → proficiency (0–100).
        trend_map: Dict mapping topic_id → TopicTrend.
        interactions: User's interaction history DataFrame.
        topic_names: Optional dict mapping topic_id → topic name.
        weights: Signal weights (default ScoringWeights).
        top_k: Number of top results to return.
        exclude_completed: If True, remove resources the user has completed.

    Returns:
        List of ScoredResource, sorted by final_score descending.
    """
    if candidates.empty:
        return []

    topic_names = topic_names or {}

    # Optionally exclude completed resources
    working = candidates.copy()
    if exclude_completed and not interactions.empty:
        completed_ids = set(
            interactions[interactions["interaction_type"] == "completed"]["resource_id"]
        )
        working = working[~working["resource_id"].isin(completed_ids)]

    if working.empty:
        return []

    # Compute all signals
    relevance = compute_relevance_scores(working, gap_analysis, path_topic_ids)
    difficulty_fit = compute_difficulty_fit_scores(working, proficiency_map)
    trend_boost = compute_trend_boost_scores(working, trend_map)
    freshness = compute_freshness_scores(working, interactions)
    diversity = compute_diversity_scores(working, interactions)
    quality = working["quality_score"].clip(0.0, 1.0)

    # Weighted composite score
    final_score = (
        weights.relevance * relevance
        + weights.difficulty_fit * difficulty_fit
        + weights.trend_boost * trend_boost
        + weights.freshness * freshness
        + weights.diversity * diversity
        + weights.quality * quality
    )

    # Attach scores to working DataFrame
    working = working.copy()
    working["_relevance"] = relevance
    working["_difficulty_fit"] = difficulty_fit
    working["_trend_boost"] = trend_boost
    working["_freshness"] = freshness
    working["_diversity"] = diversity
    working["_quality"] = quality
    working["_final_score"] = final_score

    # Sort by final score descending and take top-K
    working = working.sort_values("_final_score", ascending=False).head(top_k)

    # De-duplicate by resource_id (a resource may appear multiple times
    # if tagged to multiple requested topics — keep the highest-scored row)
    working = working.drop_duplicates(subset=["resource_id"], keep="first")

    # Build ScoredResource list
    results: list[ScoredResource] = []
    for _, row in working.iterrows():
        results.append(ScoredResource(
            resource_id=str(row["resource_id"]),
            title=str(row["title"]),
            resource_type=str(row["resource_type"]),
            topic_id=str(row["topic_id"]),
            topic_name=topic_names.get(str(row["topic_id"]), str(row["topic_id"])),
            final_score=round(float(row["_final_score"]), 4),
            score_breakdown={
                "relevance": round(float(row["_relevance"]), 4),
                "difficulty_fit": round(float(row["_difficulty_fit"]), 4),
                "trend_boost": round(float(row["_trend_boost"]), 4),
                "freshness": round(float(row["_freshness"]), 4),
                "diversity": round(float(row["_diversity"]), 4),
                "quality": round(float(row["_quality"]), 4),
            },
            difficulty_level=int(row["difficulty_level"]),
            estimated_minutes=int(row["estimated_minutes"]) if pd.notna(row.get("estimated_minutes")) else None,
            url=str(row["url"]) if pd.notna(row.get("url")) else None,
        ))

    return results
