"""
Integration tests for the Content Recommendation engine.

Tests the full generate_recommendations pipeline, interaction recording,
and recommendation logging with mocked Supabase responses.
"""

import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import asdict

from app.recommender.engine import (
    generate_recommendations,
    record_interaction,
    get_recommendation_history,
    log_recommendations,
    RecommendationResult,
)
from app.recommender.scoring import ScoredResource


# ── Mock Helpers ──────────────────────────────────────────────────────────────

def _mock_execute(data):
    """Create a mock Supabase execute() result."""
    mock = MagicMock()
    mock.data = data
    return mock


def _build_mock_supabase(
    topics=None,
    prerequisites=None,
    skill_profiles=None,
    learning_path=None,
    resources=None,
    resource_topics=None,
    interactions=None,
):
    """
    Build a mock Supabase client with configurable table responses.
    """
    supabase = MagicMock()

    # Table routing
    def mock_table(name):
        table = MagicMock()

        if name == "topics":
            table.select.return_value.execute.return_value = _mock_execute(topics or [])
            table.select.return_value.in_.return_value.execute.return_value = _mock_execute(topics or [])
        elif name == "topic_prerequisites":
            table.select.return_value.execute.return_value = _mock_execute(prerequisites or [])
        elif name == "skill_profiles":
            table.select.return_value.eq.return_value.order.return_value.execute.return_value = _mock_execute(skill_profiles or [])
            table.select.return_value.eq.return_value.execute.return_value = _mock_execute(skill_profiles or [])
        elif name == "learning_paths":
            table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = _mock_execute([learning_path] if learning_path else [])
        elif name == "learning_resources":
            table.select.return_value.in_.return_value.execute.return_value = _mock_execute(resources or [])
            table.select.return_value.in_.return_value.in_.return_value.execute.return_value = _mock_execute(resources or [])
        elif name == "resource_topics":
            table.select.return_value.in_.return_value.execute.return_value = _mock_execute(resource_topics or [])
        elif name == "user_resource_interactions":
            table.select.return_value.eq.return_value.order.return_value.execute.return_value = _mock_execute(interactions or [])
            table.insert.return_value.execute.return_value = _mock_execute([{"id": "int-1"}])
        elif name == "recommendation_logs":
            table.insert.return_value.execute.return_value = _mock_execute([{}])
            table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = _mock_execute([])

        return table

    supabase.table = mock_table
    return supabase


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_topics():
    return [
        {"id": "t1", "name": "Variables", "slug": "variables", "description": "Vars"},
        {"id": "t2", "name": "Control Flow", "slug": "control-flow", "description": "CF"},
        {"id": "t3", "name": "Functions", "slug": "functions", "description": "Funcs"},
    ]


@pytest.fixture
def sample_prerequisites():
    return [
        {"prerequisite_topic_id": "t1", "topic_id": "t2"},
        {"prerequisite_topic_id": "t2", "topic_id": "t3"},
    ]


@pytest.fixture
def sample_skill_profiles():
    return [
        {"topic_id": "t1", "proficiency_score": 80.0, "confidence": "high", "trend": "stable"},
        {"topic_id": "t2", "proficiency_score": 40.0, "confidence": "medium", "trend": "declining"},
    ]


@pytest.fixture
def sample_resources():
    return [
        {"id": "r1", "title": "Vars 101", "description": "Intro", "resource_type": "article",
         "url": "http://a", "difficulty_level": 1, "estimated_minutes": 15, "quality_score": 0.9, "metadata": "{}"},
        {"id": "r2", "title": "CF Guide", "description": "Flow", "resource_type": "video",
         "url": "http://b", "difficulty_level": 2, "estimated_minutes": 25, "quality_score": 0.85, "metadata": "{}"},
        {"id": "r3", "title": "Func Practice", "description": "Exercises", "resource_type": "exercise",
         "url": None, "difficulty_level": 3, "estimated_minutes": 30, "quality_score": 0.88, "metadata": "{}"},
    ]


@pytest.fixture
def sample_resource_topics():
    return [
        {"resource_id": "r1", "topic_id": "t1"},
        {"resource_id": "r2", "topic_id": "t2"},
        {"resource_id": "r3", "topic_id": "t3"},
    ]


@pytest.fixture
def sample_learning_path():
    return {
        "id": "path-1",
        "path_data": json.dumps([
            {"topic_id": "t2", "topic_name": "Control Flow", "step_number": 1,
             "current_proficiency": 40.0, "target_proficiency": 70.0,
             "status": "in_progress", "prerequisites_met": True},
            {"topic_id": "t3", "topic_name": "Functions", "step_number": 2,
             "current_proficiency": 0.0, "target_proficiency": 70.0,
             "status": "not_started", "prerequisites_met": False},
        ]),
        "total_steps": 2,
        "completed_steps": 0,
        "target_topics": ["t3"],
    }


# ── Test: generate_recommendations ────────────────────────────────────────────

class TestGenerateRecommendations:
    def test_returns_recommendation_result(
        self, sample_topics, sample_prerequisites, sample_skill_profiles,
        sample_resources, sample_resource_topics, sample_learning_path,
    ):
        supabase = _build_mock_supabase(
            topics=sample_topics,
            prerequisites=sample_prerequisites,
            skill_profiles=sample_skill_profiles,
            learning_path=sample_learning_path,
            resources=sample_resources,
            resource_topics=sample_resource_topics,
        )

        result = generate_recommendations(supabase, "user1", top_k=5)

        assert isinstance(result, RecommendationResult)
        assert result.user_id == "user1"
        assert isinstance(result.recommendations, list)
        assert isinstance(result.generated_at, str)

    def test_empty_graph_returns_empty(self):
        supabase = _build_mock_supabase(topics=[], prerequisites=[])
        result = generate_recommendations(supabase, "user1")

        assert result.recommendations == []
        assert result.total_candidates == 0

    def test_no_resources_returns_empty(
        self, sample_topics, sample_prerequisites, sample_skill_profiles,
    ):
        supabase = _build_mock_supabase(
            topics=sample_topics,
            prerequisites=sample_prerequisites,
            skill_profiles=sample_skill_profiles,
            resources=[],
            resource_topics=[],
        )
        result = generate_recommendations(supabase, "user1")

        assert result.recommendations == []
        assert result.total_candidates == 0

    def test_path_context_present_when_path_exists(
        self, sample_topics, sample_prerequisites, sample_skill_profiles,
        sample_resources, sample_resource_topics, sample_learning_path,
    ):
        supabase = _build_mock_supabase(
            topics=sample_topics,
            prerequisites=sample_prerequisites,
            skill_profiles=sample_skill_profiles,
            learning_path=sample_learning_path,
            resources=sample_resources,
            resource_topics=sample_resource_topics,
        )

        result = generate_recommendations(supabase, "user1")

        assert result.path_context is not None
        assert "path_id" in result.path_context
        assert "total_steps" in result.path_context

    def test_respects_top_k_limit(
        self, sample_topics, sample_prerequisites, sample_skill_profiles,
        sample_resources, sample_resource_topics,
    ):
        supabase = _build_mock_supabase(
            topics=sample_topics,
            prerequisites=sample_prerequisites,
            skill_profiles=sample_skill_profiles,
            resources=sample_resources,
            resource_topics=sample_resource_topics,
        )

        result = generate_recommendations(supabase, "user1", top_k=1)
        assert len(result.recommendations) <= 1

    def test_recommendations_have_score_breakdown(
        self, sample_topics, sample_prerequisites, sample_skill_profiles,
        sample_resources, sample_resource_topics,
    ):
        supabase = _build_mock_supabase(
            topics=sample_topics,
            prerequisites=sample_prerequisites,
            skill_profiles=sample_skill_profiles,
            resources=sample_resources,
            resource_topics=sample_resource_topics,
        )

        result = generate_recommendations(supabase, "user1")
        for rec in result.recommendations:
            assert isinstance(rec.score_breakdown, dict)
            assert "relevance" in rec.score_breakdown


# ── Test: record_interaction ──────────────────────────────────────────────────

class TestRecordInteraction:
    def test_valid_interaction(self):
        supabase = MagicMock()
        supabase.table.return_value.insert.return_value.execute.return_value = _mock_execute([
            {"id": "int-1", "user_id": "u1", "resource_id": "r1",
             "interaction_type": "viewed", "rating": None}
        ])

        result = record_interaction(supabase, "u1", "r1", "viewed")
        assert result["interaction_type"] == "viewed"

    def test_invalid_interaction_type_raises(self):
        supabase = MagicMock()
        with pytest.raises(ValueError, match="Invalid interaction_type"):
            record_interaction(supabase, "u1", "r1", "invalid_type")

    def test_invalid_rating_raises(self):
        supabase = MagicMock()
        with pytest.raises(ValueError, match="Rating must be between"):
            record_interaction(supabase, "u1", "r1", "viewed", rating=0)

    def test_valid_rating_accepted(self):
        supabase = MagicMock()
        supabase.table.return_value.insert.return_value.execute.return_value = _mock_execute([
            {"id": "int-1", "rating": 5}
        ])

        result = record_interaction(supabase, "u1", "r1", "completed", rating=5)
        assert result["rating"] == 5

    def test_all_valid_interaction_types(self):
        for itype in ["viewed", "completed", "skipped", "bookmarked"]:
            supabase = MagicMock()
            supabase.table.return_value.insert.return_value.execute.return_value = _mock_execute([
                {"id": "x", "interaction_type": itype}
            ])
            result = record_interaction(supabase, "u1", "r1", itype)
            assert result["interaction_type"] == itype


# ── Test: get_recommendation_history ──────────────────────────────────────────

class TestGetRecommendationHistory:
    def test_returns_list(self):
        supabase = MagicMock()
        supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = _mock_execute([
            {"id": "log-1", "score": 0.85, "rank": 1}
        ])

        history = get_recommendation_history(supabase, "u1", limit=10)
        assert isinstance(history, list)
        assert len(history) == 1

    def test_empty_history(self):
        supabase = MagicMock()
        supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = _mock_execute([])

        history = get_recommendation_history(supabase, "u1")
        assert history == []


# ── Test: log_recommendations ─────────────────────────────────────────────────

class TestLogRecommendations:
    def test_logs_each_recommendation(self):
        supabase = MagicMock()
        supabase.table.return_value.insert.return_value.execute.return_value = _mock_execute([{}])

        scored = [
            ScoredResource("r1", "Res 1", "article", "t1", "Topic 1", 0.9,
                          {"relevance": 0.8}, 2, 15, "http://a"),
            ScoredResource("r2", "Res 2", "video", "t2", "Topic 2", 0.7,
                          {"relevance": 0.6}, 3, 25, "http://b"),
        ]

        # Should not raise
        log_recommendations(supabase, "u1", scored)

        # Verify insert was called for each recommendation
        assert supabase.table.return_value.insert.call_count == 2

    def test_log_failure_does_not_raise(self):
        supabase = MagicMock()
        supabase.table.return_value.insert.return_value.execute.side_effect = Exception("DB error")

        scored = [
            ScoredResource("r1", "Res 1", "article", "t1", "Topic 1", 0.9,
                          {"relevance": 0.8}, 2, 15, "http://a"),
        ]

        # Should not raise despite DB error
        log_recommendations(supabase, "u1", scored)
