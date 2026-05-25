"""
Gap Analyzer: Identifies skill gaps by comparing a student's proficiency scores
against the full topic graph.

Classifies each topic as mastered, in_progress, or not_started, and computes
a gap severity score for priority ranking.
"""

from dataclasses import dataclass
from supabase import Client

from app.planner.graph_builder import KnowledgeGraph


DEFAULT_MASTERY_THRESHOLD = 70


@dataclass
class TopicGap:
    """Represents a skill gap for a single topic."""
    topic_id: str
    topic_name: str
    current_proficiency: float
    status: str              # "mastered", "in_progress", "not_started"
    gap_severity: float      # mastery_threshold - current_proficiency (higher = more urgent)
    confidence: str          # from skill_profiles


@dataclass
class GapAnalysisResult:
    """Full gap analysis for a user."""
    user_id: str
    mastery_threshold: float
    mastered: list[TopicGap]
    in_progress: list[TopicGap]
    not_started: list[TopicGap]
    all_gaps: list[TopicGap]  # in_progress + not_started, sorted by severity descending

    @property
    def total_topics(self) -> int:
        return len(self.mastered) + len(self.in_progress) + len(self.not_started)

    @property
    def mastery_percentage(self) -> float:
        if self.total_topics == 0:
            return 0.0
        return (len(self.mastered) / self.total_topics) * 100.0


def analyze_gaps(
    supabase: Client,
    user_id: str,
    knowledge_graph: KnowledgeGraph,
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
) -> GapAnalysisResult:
    """
    Analyze skill gaps for a user against the full knowledge graph.

    Steps:
        1. Fetch all skill_profiles for the user
        2. Cross-reference with all topics in the graph
        3. Classify each topic and compute gap severity
    """
    # Fetch user's skill profiles
    profiles_res = (
        supabase.table("skill_profiles")
        .select("topic_id, proficiency_score, confidence")
        .eq("user_id", user_id)
        .execute()
    )

    # Build a lookup: topic_id → {proficiency_score, confidence}
    proficiency_map: dict[str, dict] = {}
    if profiles_res.data:
        for p in profiles_res.data:
            proficiency_map[p["topic_id"]] = {
                "proficiency_score": p["proficiency_score"],
                "confidence": p["confidence"],
            }

    # Classify each topic in the graph
    mastered = []
    in_progress = []
    not_started = []

    for topic_id in knowledge_graph.graph.nodes():
        topic = knowledge_graph.get_topic(topic_id)
        topic_name = topic.name if topic else topic_id

        if topic_id in proficiency_map:
            score = proficiency_map[topic_id]["proficiency_score"]
            confidence = proficiency_map[topic_id]["confidence"]

            if score >= mastery_threshold:
                status = "mastered"
                gap = TopicGap(
                    topic_id=topic_id,
                    topic_name=topic_name,
                    current_proficiency=score,
                    status=status,
                    gap_severity=0.0,
                    confidence=confidence,
                )
                mastered.append(gap)
            else:
                status = "in_progress"
                gap = TopicGap(
                    topic_id=topic_id,
                    topic_name=topic_name,
                    current_proficiency=score,
                    status=status,
                    gap_severity=mastery_threshold - score,
                    confidence=confidence,
                )
                in_progress.append(gap)
        else:
            # No proficiency data — never attempted
            gap = TopicGap(
                topic_id=topic_id,
                topic_name=topic_name,
                current_proficiency=0.0,
                status="not_started",
                gap_severity=mastery_threshold,
                confidence="low",
            )
            not_started.append(gap)

    # Combine gaps and sort by severity (most urgent first)
    all_gaps = sorted(
        in_progress + not_started,
        key=lambda g: g.gap_severity,
        reverse=True,
    )

    return GapAnalysisResult(
        user_id=user_id,
        mastery_threshold=mastery_threshold,
        mastered=mastered,
        in_progress=in_progress,
        not_started=not_started,
        all_gaps=all_gaps,
    )
