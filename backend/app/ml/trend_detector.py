"""
Trend Detector: Analyzes time-windowed accuracy data to detect whether a student
is improving, declining, or stable in each topic.

Uses linear regression on weekly accuracy buckets to compute a slope, then
classifies the trend based on configurable thresholds.
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta


# Slope thresholds for trend classification
IMPROVING_THRESHOLD = 0.02   # slope > +0.02 → improving
DECLINING_THRESHOLD = -0.02  # slope < −0.02 → declining
# Between these thresholds → stable

# Minimum number of weekly data points required to detect a trend
MIN_WEEKS_FOR_TREND = 2


@dataclass
class TopicTrend:
    """Trend detection result for a single topic."""
    topic_id: str
    trend: str         # "improving", "declining", "stable"
    slope: float       # raw regression slope
    data_points: int   # number of weekly buckets used


def _bucket_by_week(responses_df: pd.DataFrame, topic_id: str) -> pd.DataFrame:
    """
    Group responses for a specific topic into weekly accuracy buckets.

    Returns a DataFrame with columns:
        - week_number: integer index (0 = oldest week)
        - accuracy: fraction correct in that week
        - count: number of responses in that week
    """
    topic_responses = responses_df[responses_df["topic_id"] == topic_id].copy()

    if topic_responses.empty:
        return pd.DataFrame()

    # Ensure datetime
    topic_responses["responded_at"] = pd.to_datetime(topic_responses["responded_at"], utc=True)

    # Create weekly period
    topic_responses["week"] = topic_responses["responded_at"].dt.isocalendar().week + \
        (topic_responses["responded_at"].dt.isocalendar().year * 52)

    weekly = topic_responses.groupby("week").agg(
        accuracy=("is_correct", "mean"),
        count=("is_correct", "size")
    ).reset_index()

    # Normalize week to sequential index
    weekly = weekly.sort_values("week").reset_index(drop=True)
    weekly["week_number"] = range(len(weekly))

    return weekly[["week_number", "accuracy", "count"]]


def detect_trend_for_topic(responses_df: pd.DataFrame, topic_id: str) -> TopicTrend:
    """
    Detect the learning trend for a single topic using linear regression on weekly accuracy.
    """
    weekly = _bucket_by_week(responses_df, topic_id)

    if weekly.empty or len(weekly) < MIN_WEEKS_FOR_TREND:
        return TopicTrend(
            topic_id=str(topic_id),
            trend="stable",
            slope=0.0,
            data_points=len(weekly) if not weekly.empty else 0,
        )

    # Fit linear regression: accuracy ~ week_number
    X = weekly["week_number"].values.reshape(-1, 1)
    y = weekly["accuracy"].values

    model = LinearRegression()
    model.fit(X, y)
    slope = float(model.coef_[0])

    # Classify
    if slope > IMPROVING_THRESHOLD:
        trend = "improving"
    elif slope < DECLINING_THRESHOLD:
        trend = "declining"
    else:
        trend = "stable"

    return TopicTrend(
        topic_id=str(topic_id),
        trend=trend,
        slope=round(slope, 6),
        data_points=len(weekly),
    )


def detect_trends(responses_df: pd.DataFrame, topic_ids: list[str]) -> dict[str, TopicTrend]:
    """
    Detect trends for multiple topics.

    Returns a dict mapping topic_id → TopicTrend.
    """
    trends = {}
    for topic_id in topic_ids:
        trends[topic_id] = detect_trend_for_topic(responses_df, topic_id)
    return trends
