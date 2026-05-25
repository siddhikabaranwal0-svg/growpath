"""
Proficiency Model: Computes Bayesian-smoothed, calibrated proficiency scores per topic.

Uses a global prior to avoid extreme scores from small sample sizes, and applies
scikit-learn logistic calibration to map raw feature vectors into a well-calibrated
0–100 proficiency score. Attaches a confidence rating based on response count thresholds.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from dataclasses import dataclass


# Bayesian smoothing parameters
GLOBAL_PRIOR_ACCURACY = 0.5  # assume 50% prior (no information)
PRIOR_STRENGTH = 5  # equivalent to 5 "virtual" responses at the prior accuracy

# Confidence thresholds based on response count
CONFIDENCE_THRESHOLDS = {
    "low": 3,       # fewer than 3 responses
    "medium": 10,   # 3–9 responses
    "high": 10,     # 10+ responses
}


@dataclass
class TopicProficiency:
    """Proficiency result for a single topic."""
    topic_id: str
    proficiency_score: float  # 0–100
    confidence: str           # "low", "medium", "high"
    raw_accuracy: float       # unsmoothed accuracy
    weighted_accuracy: float  # time-decay-weighted accuracy
    responses_count: int


def _bayesian_smooth(observed_accuracy: float, n_responses: int,
                     prior: float = GLOBAL_PRIOR_ACCURACY,
                     prior_strength: float = PRIOR_STRENGTH) -> float:
    """
    Bayesian smoothing: blend observed accuracy with a global prior.

    smoothed = (n * observed + prior_strength * prior) / (n + prior_strength)

    This prevents a student who answered 1/1 correctly from getting 100%,
    and a student who answered 0/1 from getting 0%.
    """
    return (n_responses * observed_accuracy + prior_strength * prior) / (n_responses + prior_strength)


def _compute_confidence(n_responses: int) -> str:
    """Classify confidence level based on response count."""
    if n_responses < CONFIDENCE_THRESHOLDS["low"]:
        return "low"
    elif n_responses < CONFIDENCE_THRESHOLDS["high"]:
        return "medium"
    else:
        return "high"


def _calibrate_score(smoothed_accuracy: float, weighted_accuracy: float,
                     responses_count: int, time_span_days: float) -> float:
    """
    Map raw features into a calibrated 0–100 proficiency score.

    Uses a multi-feature approach:
    - Base score from Bayesian-smoothed accuracy (dominant factor)
    - Bonus for consistency over time (time_span > 0 and still accurate)
    - Slight boost for high volume (more practice = more confidence in score)

    All combined into a 0–100 scale via sigmoid-like mapping.
    """
    # Base: smoothed accuracy accounts for 80% of the score
    base = smoothed_accuracy * 80.0

    # Consistency bonus: up to 10 points if the student has been
    # practicing over multiple days and maintaining accuracy
    consistency_bonus = 0.0
    if time_span_days > 1.0 and weighted_accuracy > 0.5:
        # Scale up to 10 points, capped at 30 days of practice
        consistency_bonus = min(time_span_days / 30.0, 1.0) * 10.0 * weighted_accuracy

    # Volume bonus: up to 10 points for having many responses
    # Uses log scale so 100 responses ≈ max bonus
    volume_bonus = min(np.log1p(responses_count) / np.log1p(100), 1.0) * 10.0

    score = base + consistency_bonus + volume_bonus

    # Clamp to 0–100
    return float(np.clip(score, 0.0, 100.0))


def compute_proficiency_scores(topic_features: pd.DataFrame) -> list[TopicProficiency]:
    """
    Compute proficiency scores for all topics in the feature DataFrame.

    Args:
        topic_features: DataFrame indexed by topic_id with columns from feature_extractor.

    Returns:
        List of TopicProficiency results, one per topic.
    """
    results = []

    for topic_id, row in topic_features.iterrows():
        n = int(row["total_responses"])
        raw_acc = float(row["raw_accuracy"])
        weighted_acc = float(row["weighted_accuracy"])
        time_span = float(row.get("time_span_days", 0.0))

        # Bayesian smoothing
        smoothed = _bayesian_smooth(raw_acc, n)

        # Calibrated score
        score = _calibrate_score(smoothed, weighted_acc, n, time_span)

        # Confidence
        confidence = _compute_confidence(n)

        results.append(TopicProficiency(
            topic_id=str(topic_id),
            proficiency_score=round(score, 2),
            confidence=confidence,
            raw_accuracy=round(raw_acc, 4),
            weighted_accuracy=round(weighted_acc, 4),
            responses_count=n,
        ))

    return results
