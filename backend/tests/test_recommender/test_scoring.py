"""
Unit tests for the Content Recommendation scoring engine.

Tests each scoring signal function in isolation and the composite
score_and_rank pipeline with various edge cases.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.recommender.scoring import (
    ScoringWeights,
    ScoredResource,
    compute_relevance_scores,
    compute_difficulty_fit_scores,
    compute_trend_boost_scores,
    compute_freshness_scores,
    compute_diversity_scores,
    score_and_rank,
    _proficiency_to_ideal_difficulty,
    PATH_RELEVANCE_MULTIPLIER,
    DIFFICULTY_FIT_SIGMA,
    FRESHNESS_HALF_LIFE_DAYS,
)
from app.planner.gap_analyzer import GapAnalysisResult, TopicGap
from app.ml.trend_detector import TopicTrend


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_candidates():
    """A small DataFrame of candidate resources."""
    return pd.DataFrame({
        "resource_id": ["r1", "r2", "r3", "r4", "r5"],
        "title": ["Res A", "Res B", "Res C", "Res D", "Res E"],
        "resource_type": ["article", "video", "exercise", "article", "video"],
        "difficulty_level": [1, 2, 3, 4, 5],
        "estimated_minutes": [10, 20, 30, 40, 50],
        "quality_score": [0.9, 0.8, 0.7, 0.6, 0.95],
        "url": ["http://a", "http://b", None, "http://d", "http://e"],
        "topic_id": ["t1", "t1", "t2", "t2", "t3"],
    })


@pytest.fixture
def sample_gap_analysis():
    """A GapAnalysisResult with known gaps."""
    mastered = [
        TopicGap("t3", "Topic 3", 85.0, "mastered", 0.0, "high"),
    ]
    in_progress = [
        TopicGap("t1", "Topic 1", 40.0, "in_progress", 30.0, "medium"),
    ]
    not_started = [
        TopicGap("t2", "Topic 2", 0.0, "not_started", 70.0, "low"),
    ]
    all_gaps = sorted(in_progress + not_started, key=lambda g: g.gap_severity, reverse=True)

    return GapAnalysisResult(
        user_id="user1",
        mastery_threshold=70.0,
        mastered=mastered,
        in_progress=in_progress,
        not_started=not_started,
        all_gaps=all_gaps,
    )


@pytest.fixture
def sample_interactions():
    """A DataFrame of past user interactions."""
    now = datetime.now(timezone.utc)
    return pd.DataFrame({
        "resource_id": ["r1", "r2", "r1"],
        "interaction_type": ["viewed", "completed", "viewed"],
        "rating": [None, 4, None],
        "interacted_at": [
            now - timedelta(days=7),
            now - timedelta(days=1),
            now - timedelta(days=30),
        ],
    })


@pytest.fixture
def empty_interactions():
    """An empty interactions DataFrame."""
    return pd.DataFrame(columns=["resource_id", "interaction_type", "rating", "interacted_at"])


# ── Test: Proficiency → Difficulty Mapping ────────────────────────────────────

class TestProficiencyToIdealDifficulty:
    def test_zero_proficiency_maps_to_1(self):
        assert _proficiency_to_ideal_difficulty(0.0) == pytest.approx(1.0)

    def test_fifty_proficiency_maps_to_3(self):
        assert _proficiency_to_ideal_difficulty(50.0) == pytest.approx(3.0)

    def test_hundred_proficiency_maps_to_5(self):
        assert _proficiency_to_ideal_difficulty(100.0) == pytest.approx(5.0)

    def test_twenty_five_proficiency_maps_to_2(self):
        assert _proficiency_to_ideal_difficulty(25.0) == pytest.approx(2.0)


# ── Test: Relevance Scoring ───────────────────────────────────────────────────

class TestRelevanceScores:
    def test_higher_gap_severity_gets_higher_relevance(self, sample_candidates, sample_gap_analysis):
        scores = compute_relevance_scores(sample_candidates, sample_gap_analysis, set())
        # t2 has gap_severity=70, t1 has gap_severity=30 → t2 resources should score higher
        t2_scores = scores[sample_candidates["topic_id"] == "t2"]
        t1_scores = scores[sample_candidates["topic_id"] == "t1"]
        assert t2_scores.mean() > t1_scores.mean()

    def test_mastered_topics_get_zero_relevance(self, sample_candidates, sample_gap_analysis):
        scores = compute_relevance_scores(sample_candidates, sample_gap_analysis, set())
        t3_scores = scores[sample_candidates["topic_id"] == "t3"]
        assert (t3_scores == 0.0).all()

    def test_path_topics_get_boosted(self, sample_candidates, sample_gap_analysis):
        path_topics = {"t1"}
        scores_with_path = compute_relevance_scores(sample_candidates, sample_gap_analysis, path_topics)
        scores_without_path = compute_relevance_scores(sample_candidates, sample_gap_analysis, set())
        # t1 resources should be higher with path boost
        t1_with = scores_with_path[sample_candidates["topic_id"] == "t1"]
        t1_without = scores_without_path[sample_candidates["topic_id"] == "t1"]
        assert t1_with.mean() > t1_without.mean()

    def test_scores_are_in_range(self, sample_candidates, sample_gap_analysis):
        scores = compute_relevance_scores(sample_candidates, sample_gap_analysis, {"t1"})
        assert (scores >= 0.0).all()
        assert (scores <= 1.0).all()

    def test_empty_candidates_returns_empty(self, sample_gap_analysis):
        empty = pd.DataFrame()
        scores = compute_relevance_scores(empty, sample_gap_analysis, set())
        assert len(scores) == 0


# ── Test: Difficulty Fit Scoring ──────────────────────────────────────────────

class TestDifficultyFitScores:
    def test_perfect_match_gets_max_score(self, sample_candidates):
        # Student at proficiency 50 → ideal difficulty 3.0
        proficiency_map = {"t2": 50.0}
        scores = compute_difficulty_fit_scores(sample_candidates, proficiency_map)
        # r3 (difficulty=3, topic=t2) should be the best fit
        r3_idx = sample_candidates[sample_candidates["resource_id"] == "r3"].index[0]
        assert scores[r3_idx] == pytest.approx(1.0, abs=0.01)

    def test_mismatch_gets_lower_score(self, sample_candidates):
        proficiency_map = {"t1": 0.0, "t2": 0.0, "t3": 0.0}
        scores = compute_difficulty_fit_scores(sample_candidates, proficiency_map)
        # Ideal = 1.0 for all; difficulty=5 should be worst fit
        r5_idx = sample_candidates[sample_candidates["resource_id"] == "r5"].index[0]
        r1_idx = sample_candidates[sample_candidates["resource_id"] == "r1"].index[0]
        assert scores[r1_idx] > scores[r5_idx]

    def test_scores_are_in_range(self, sample_candidates):
        proficiency_map = {"t1": 50.0, "t2": 30.0, "t3": 80.0}
        scores = compute_difficulty_fit_scores(sample_candidates, proficiency_map)
        assert (scores >= 0.0).all()
        assert (scores <= 1.0).all()

    def test_unknown_topic_defaults_to_beginner(self, sample_candidates):
        # Missing topic → proficiency 0 → ideal difficulty 1
        scores = compute_difficulty_fit_scores(sample_candidates, {})
        assert (scores >= 0.0).all()
        assert (scores <= 1.0).all()


# ── Test: Trend Boost Scoring ─────────────────────────────────────────────────

class TestTrendBoostScores:
    def test_declining_gets_highest_boost(self, sample_candidates):
        trend_map = {
            "t1": TopicTrend("t1", "declining", -0.05, 5),
            "t2": TopicTrend("t2", "stable", 0.0, 5),
            "t3": TopicTrend("t3", "improving", 0.05, 5),
        }
        scores = compute_trend_boost_scores(sample_candidates, trend_map)
        t1_scores = scores[sample_candidates["topic_id"] == "t1"]
        t3_scores = scores[sample_candidates["topic_id"] == "t3"]
        assert t1_scores.mean() > t3_scores.mean()

    def test_declining_is_1_0(self, sample_candidates):
        trend_map = {
            "t1": TopicTrend("t1", "declining", -0.05, 5),
            "t2": TopicTrend("t2", "declining", -0.03, 4),
            "t3": TopicTrend("t3", "declining", -0.04, 3),
        }
        scores = compute_trend_boost_scores(sample_candidates, trend_map)
        assert (scores == 1.0).all()

    def test_improving_is_0_2(self, sample_candidates):
        trend_map = {
            "t1": TopicTrend("t1", "improving", 0.05, 5),
            "t2": TopicTrend("t2", "improving", 0.03, 4),
            "t3": TopicTrend("t3", "improving", 0.04, 3),
        }
        scores = compute_trend_boost_scores(sample_candidates, trend_map)
        assert (scores == 0.2).all()

    def test_unknown_topic_gets_neutral(self, sample_candidates):
        scores = compute_trend_boost_scores(sample_candidates, {})
        assert (scores == 0.5).all()


# ── Test: Freshness Scoring ───────────────────────────────────────────────────

class TestFreshnessScores:
    def test_no_interactions_all_fresh(self, sample_candidates, empty_interactions):
        scores = compute_freshness_scores(sample_candidates, empty_interactions)
        assert (scores == 1.0).all()

    def test_recent_interaction_reduces_freshness(self, sample_candidates, sample_interactions):
        scores = compute_freshness_scores(sample_candidates, sample_interactions)
        # r2 was interacted with 1 day ago → should have lower freshness
        r2_idx = sample_candidates[sample_candidates["resource_id"] == "r2"].index[0]
        r3_idx = sample_candidates[sample_candidates["resource_id"] == "r3"].index[0]
        # r3 never interacted → freshness 1.0
        assert scores[r3_idx] > scores[r2_idx]

    def test_old_interaction_recovers_freshness(self):
        candidates = pd.DataFrame({
            "resource_id": ["r_old"],
            "topic_id": ["t1"],
        })
        now = datetime.now(timezone.utc)
        interactions = pd.DataFrame({
            "resource_id": ["r_old"],
            "interaction_type": ["viewed"],
            "rating": [None],
            "interacted_at": [now - timedelta(days=90)],
        })
        scores = compute_freshness_scores(candidates, interactions)
        # 90 days is well past the 14-day half-life → should be close to 1.0
        assert scores.iloc[0] > 0.95

    def test_scores_are_in_range(self, sample_candidates, sample_interactions):
        scores = compute_freshness_scores(sample_candidates, sample_interactions)
        assert (scores >= 0.0).all()
        assert (scores <= 1.0).all()


# ── Test: Diversity Scoring ───────────────────────────────────────────────────

class TestDiversityScores:
    def test_no_interactions_max_diversity(self, sample_candidates, empty_interactions):
        scores = compute_diversity_scores(sample_candidates, empty_interactions)
        assert (scores == 1.0).all()

    def test_overrepresented_type_gets_lower_score(self, sample_candidates, sample_interactions):
        # r1 and r2 were interacted with (article, video)
        scores = compute_diversity_scores(sample_candidates, sample_interactions)
        # exercise type (r3) should have high diversity (not in interactions)
        r3_idx = sample_candidates[sample_candidates["resource_id"] == "r3"].index[0]
        assert scores[r3_idx] >= 0.5

    def test_scores_are_in_range(self, sample_candidates, sample_interactions):
        scores = compute_diversity_scores(sample_candidates, sample_interactions)
        assert (scores >= 0.0).all()
        assert (scores <= 1.0).all()


# ── Test: Composite score_and_rank ────────────────────────────────────────────

class TestScoreAndRank:
    def test_returns_top_k_results(self, sample_candidates, sample_gap_analysis, empty_interactions):
        results = score_and_rank(
            candidates=sample_candidates,
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={"t1": 40.0, "t2": 0.0, "t3": 85.0},
            trend_map={},
            interactions=empty_interactions,
            top_k=3,
        )
        assert len(results) <= 3

    def test_results_sorted_by_score_descending(self, sample_candidates, sample_gap_analysis, empty_interactions):
        results = score_and_rank(
            candidates=sample_candidates,
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={"t1": 40.0, "t2": 0.0, "t3": 85.0},
            trend_map={},
            interactions=empty_interactions,
            top_k=10,
        )
        scores = [r.final_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_completed_resources_excluded(self, sample_candidates, sample_gap_analysis, sample_interactions):
        results = score_and_rank(
            candidates=sample_candidates,
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={},
            trend_map={},
            interactions=sample_interactions,
            exclude_completed=True,
        )
        # r2 was completed → should be excluded
        result_ids = {r.resource_id for r in results}
        assert "r2" not in result_ids

    def test_completed_resources_kept_when_not_excluded(self, sample_candidates, sample_gap_analysis, sample_interactions):
        results = score_and_rank(
            candidates=sample_candidates,
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={},
            trend_map={},
            interactions=sample_interactions,
            exclude_completed=False,
        )
        result_ids = {r.resource_id for r in results}
        assert "r2" in result_ids

    def test_score_breakdown_present(self, sample_candidates, sample_gap_analysis, empty_interactions):
        results = score_and_rank(
            candidates=sample_candidates,
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={},
            trend_map={},
            interactions=empty_interactions,
        )
        for r in results:
            assert "relevance" in r.score_breakdown
            assert "difficulty_fit" in r.score_breakdown
            assert "trend_boost" in r.score_breakdown
            assert "freshness" in r.score_breakdown
            assert "diversity" in r.score_breakdown
            assert "quality" in r.score_breakdown

    def test_all_breakdown_values_in_range(self, sample_candidates, sample_gap_analysis, empty_interactions):
        results = score_and_rank(
            candidates=sample_candidates,
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={"t1": 40.0, "t2": 0.0, "t3": 85.0},
            trend_map={
                "t1": TopicTrend("t1", "declining", -0.05, 5),
                "t2": TopicTrend("t2", "stable", 0.0, 3),
                "t3": TopicTrend("t3", "improving", 0.03, 4),
            },
            interactions=empty_interactions,
        )
        for r in results:
            for signal, value in r.score_breakdown.items():
                assert 0.0 <= value <= 1.0, f"{signal} = {value} out of range"

    def test_empty_candidates_returns_empty(self, sample_gap_analysis, empty_interactions):
        results = score_and_rank(
            candidates=pd.DataFrame(),
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={},
            trend_map={},
            interactions=empty_interactions,
        )
        assert results == []

    def test_custom_weights_affect_ranking(self, sample_candidates, sample_gap_analysis, empty_interactions):
        # With quality weight = 1.0, everything else = 0 → should rank by quality
        quality_only = ScoringWeights(
            relevance=0.0, difficulty_fit=0.0, trend_boost=0.0,
            freshness=0.0, diversity=0.0, quality=1.0,
        )
        results = score_and_rank(
            candidates=sample_candidates,
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={},
            trend_map={},
            interactions=empty_interactions,
            weights=quality_only,
        )
        # r5 has quality 0.95, r1 has 0.9 → r5 should be first
        if len(results) >= 2:
            assert results[0].resource_id == "r5"

    def test_scored_resource_has_all_fields(self, sample_candidates, sample_gap_analysis, empty_interactions):
        results = score_and_rank(
            candidates=sample_candidates,
            gap_analysis=sample_gap_analysis,
            path_topic_ids=set(),
            proficiency_map={},
            trend_map={},
            interactions=empty_interactions,
        )
        for r in results:
            assert isinstance(r, ScoredResource)
            assert isinstance(r.resource_id, str)
            assert isinstance(r.title, str)
            assert isinstance(r.resource_type, str)
            assert isinstance(r.final_score, float)
            assert isinstance(r.score_breakdown, dict)
            assert isinstance(r.difficulty_level, int)


# ── Test: ScoringWeights ──────────────────────────────────────────────────────

class TestScoringWeights:
    def test_default_weights_sum_to_1(self):
        w = ScoringWeights()
        total = sum(w.as_dict().values())
        assert total == pytest.approx(1.0)

    def test_as_dict_has_all_keys(self):
        w = ScoringWeights()
        d = w.as_dict()
        expected_keys = {"relevance", "difficulty_fit", "trend_boost", "freshness", "diversity", "quality"}
        assert set(d.keys()) == expected_keys
