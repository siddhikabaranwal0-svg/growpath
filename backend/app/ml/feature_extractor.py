"""
Feature Extractor: Builds per-user, per-topic feature matrices from raw quiz responses.

Queries user_responses joined with question_topics, applies exponential time-decay
weighting, and produces aggregated feature DataFrames for the proficiency model.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from supabase import Client


# Half-life in days for exponential time-decay weighting.
# A response from DECAY_HALF_LIFE_DAYS ago has half the weight of one from today.
DECAY_HALF_LIFE_DAYS = 30.0


def _compute_time_decay_weight(responded_at: datetime, now: datetime, half_life_days: float = DECAY_HALF_LIFE_DAYS) -> float:
    """
    Compute an exponential decay weight based on how old a response is.
    Weight = 0.5 ^ (age_in_days / half_life_days)
    """
    if responded_at.tzinfo is None:
        responded_at = responded_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_days = (now - responded_at).total_seconds() / 86400.0
    age_days = max(age_days, 0.0)  # guard against future timestamps
    return 0.5 ** (age_days / half_life_days)


def fetch_user_responses_with_topics(supabase: Client, user_id: str) -> pd.DataFrame:
    """
    Fetch all quiz responses for a given user, joined with question-topic mappings.

    Returns a DataFrame with columns:
        - response_id, question_id, is_correct, points, responded_at, topic_id
    """
    # Fetch user responses via their quiz attempts
    attempts_res = supabase.table("quiz_attempts").select("id, quiz_id").eq("user_id", user_id).execute()
    if not attempts_res.data:
        return pd.DataFrame()

    attempt_ids = [a["id"] for a in attempts_res.data]

    # Fetch all responses for these attempts
    responses_res = (
        supabase.table("user_responses")
        .select("id, attempt_id, question_id, is_correct, created_at")
        .in_("attempt_id", attempt_ids)
        .execute()
    )
    if not responses_res.data:
        return pd.DataFrame()

    responses_df = pd.DataFrame(responses_res.data)
    responses_df.rename(columns={"id": "response_id", "created_at": "responded_at"}, inplace=True)

    # Fetch question points
    question_ids = responses_df["question_id"].unique().tolist()
    questions_res = (
        supabase.table("questions")
        .select("id, points")
        .in_("id", question_ids)
        .execute()
    )
    questions_df = pd.DataFrame(questions_res.data)
    questions_df.rename(columns={"id": "question_id"}, inplace=True)

    # Fetch question-topic mappings
    qt_res = (
        supabase.table("question_topics")
        .select("question_id, topic_id")
        .in_("question_id", question_ids)
        .execute()
    )
    if not qt_res.data:
        return pd.DataFrame()

    qt_df = pd.DataFrame(qt_res.data)

    # Join responses with questions (for points) and question_topics (for topic mapping)
    merged = responses_df.merge(questions_df, on="question_id", how="left")
    merged = merged.merge(qt_df, on="question_id", how="inner")  # inner: drop responses without topics

    # Parse timestamps
    merged["responded_at"] = pd.to_datetime(merged["responded_at"], utc=True)

    return merged[["response_id", "question_id", "is_correct", "points", "responded_at", "topic_id"]]


def extract_topic_features(responses_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-topic features from raw response data.

    Returns a DataFrame indexed by topic_id with columns:
        - total_responses: total number of responses in this topic
        - correct_count: number of correct responses
        - raw_accuracy: simple correct/total ratio
        - weighted_accuracy: time-decay-weighted accuracy
        - avg_points_earned: average points from correct answers
        - time_span_days: days between first and last response
        - latest_response: most recent response timestamp
    """
    if responses_df.empty:
        return pd.DataFrame()

    now = datetime.now(timezone.utc)

    # Compute decay weights
    responses_df = responses_df.copy()
    responses_df["decay_weight"] = responses_df["responded_at"].apply(
        lambda t: _compute_time_decay_weight(t, now)
    )

    # Per-topic aggregation
    grouped = responses_df.groupby("topic_id")

    features = pd.DataFrame({
        "total_responses": grouped.size(),
        "correct_count": grouped["is_correct"].sum(),
        "raw_accuracy": grouped["is_correct"].mean(),
        "weighted_correct_sum": grouped.apply(
            lambda g: (g["is_correct"].astype(float) * g["decay_weight"]).sum()
        ),
        "weight_sum": grouped["decay_weight"].sum(),
        "avg_points_earned": grouped.apply(
            lambda g: (g["is_correct"].astype(float) * g["points"].fillna(1)).mean()
        ),
        "time_span_days": grouped["responded_at"].apply(
            lambda dates: (dates.max() - dates.min()).total_seconds() / 86400.0
        ),
        "latest_response": grouped["responded_at"].max(),
    })

    # Weighted accuracy = weighted_correct_sum / weight_sum
    features["weighted_accuracy"] = features["weighted_correct_sum"] / features["weight_sum"].replace(0, 1)

    # Clean up helper columns
    features.drop(columns=["weighted_correct_sum", "weight_sum"], inplace=True)

    return features
