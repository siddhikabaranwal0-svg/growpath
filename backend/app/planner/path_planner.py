"""
Path Planner: Generates personalized, dependency-respecting learning roadmaps.

Uses the knowledge graph (DAG) + gap analysis to compute an ordered sequence of
topics a student should study. Applies filtered topological sorting with priority
weighting to produce actionable paths.
"""

import json
from dataclasses import dataclass, asdict
from supabase import Client

from app.planner.graph_builder import KnowledgeGraph
from app.planner.gap_analyzer import analyze_gaps, GapAnalysisResult, DEFAULT_MASTERY_THRESHOLD


DEFAULT_MAX_STEPS = 20


@dataclass
class PathNode:
    """A single step in a learning path."""
    topic_id: str
    topic_name: str
    current_proficiency: float
    target_proficiency: float  # mastery_threshold
    status: str                # "not_started" | "in_progress" | "mastered"
    prerequisites_met: bool
    step_number: int


@dataclass
class LearningPath:
    """A complete generated learning roadmap."""
    nodes: list[PathNode]
    target_topics: list[str]
    total_steps: int
    estimated_effort: str  # "light" | "moderate" | "intensive"


def _estimate_effort(total_steps: int) -> str:
    """Estimate effort level based on path length."""
    if total_steps <= 5:
        return "light"
    elif total_steps <= 12:
        return "moderate"
    else:
        return "intensive"


def generate_learning_path(
    supabase: Client,
    user_id: str,
    knowledge_graph: KnowledgeGraph,
    target_topic_ids: list[str] | None = None,
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> LearningPath:
    """
    Generate a personalized learning path for a user.

    Algorithm:
        1. Run gap analysis to identify weak/unstarted topics.
        2. Determine target topics (explicit goals or auto-detected leaf gaps).
        3. Walk backward from targets collecting unmastered prerequisites.
        4. Topologically sort the unmastered subgraph.
        5. Prioritize "quick wins" (topics closest to mastery) within topological constraints.
        6. Cap at max_steps.

    Args:
        supabase: Supabase client for database access.
        user_id: The student's user ID.
        knowledge_graph: The pre-built KnowledgeGraph DAG.
        target_topic_ids: Optional list of goal topic IDs. If None, auto-detects.
        mastery_threshold: Proficiency score at which a topic is considered mastered.
        max_steps: Maximum number of steps in the generated path.

    Returns:
        A LearningPath with ordered PathNodes.
    """
    # Step 1: Gap analysis
    gaps = analyze_gaps(supabase, user_id, knowledge_graph, mastery_threshold)

    # Build a set of mastered topics for quick lookup
    mastered_ids = {g.topic_id for g in gaps.mastered}

    # Build proficiency lookup
    proficiency_map = {}
    for g in gaps.mastered + gaps.in_progress + gaps.not_started:
        proficiency_map[g.topic_id] = {
            "proficiency": g.current_proficiency,
            "status": g.status,
            "gap_severity": g.gap_severity,
        }

    # Step 2: Determine targets
    if target_topic_ids:
        # Validate that targets exist in the graph
        targets = [t for t in target_topic_ids if t in knowledge_graph.graph]
    else:
        # Auto-detect: use leaf topics that are NOT mastered
        leaf_topics = knowledge_graph.get_leaf_topics()
        targets = [t for t in leaf_topics if t not in mastered_ids]

        # If all leaves are mastered, fall back to any unmastered topic
        if not targets:
            targets = [g.topic_id for g in gaps.all_gaps[:max_steps]]

    if not targets:
        # Nothing to learn — student has mastered everything (or graph is empty)
        return LearningPath(
            nodes=[],
            target_topics=[],
            total_steps=0,
            estimated_effort="light",
        )

    # Step 3: Collect all unmastered prerequisites for each target
    topics_needed: set[str] = set()
    for target_id in targets:
        # Add the target itself if not mastered
        if target_id not in mastered_ids:
            topics_needed.add(target_id)

        # Walk backward through prerequisites
        all_prereqs = knowledge_graph.get_prerequisites(target_id)
        for prereq_id in all_prereqs:
            if prereq_id not in mastered_ids:
                topics_needed.add(prereq_id)

    if not topics_needed:
        return LearningPath(
            nodes=[],
            target_topics=targets,
            total_steps=0,
            estimated_effort="light",
        )

    # Step 4: Topological sort of the needed subgraph
    topo_order = knowledge_graph.get_subgraph_topological_order(topics_needed)

    # Step 5: Priority weighting within topological constraints
    # We sort by: (topological_layer, -gap_severity) so that within each
    # dependency layer, topics closest to mastery ("quick wins") come first.
    # Compute topological layers (longest path from roots)
    subgraph = knowledge_graph.graph.subgraph(topics_needed)
    layers: dict[str, int] = {}
    for node in topo_order:
        preds_in_subgraph = [p for p in subgraph.predecessors(node) if p in layers]
        if preds_in_subgraph:
            layers[node] = max(layers[p] for p in preds_in_subgraph) + 1
        else:
            layers[node] = 0

    # Sort: primary by layer (dependency order), secondary by gap severity descending
    # but inverted: small gap = "quick win" = sorted first within same layer
    sorted_topics = sorted(
        topo_order,
        key=lambda tid: (
            layers.get(tid, 0),
            -proficiency_map.get(tid, {}).get("gap_severity", mastery_threshold),
        ),
    )

    # Step 6: Cap at max_steps
    sorted_topics = sorted_topics[:max_steps]

    # Build PathNodes
    nodes = []
    for i, topic_id in enumerate(sorted_topics):
        topic = knowledge_graph.get_topic(topic_id)
        prof_info = proficiency_map.get(topic_id, {"proficiency": 0.0, "status": "not_started"})

        # Check if direct prerequisites are met (mastered or not in the remaining path)
        direct_prereqs = knowledge_graph.get_direct_prerequisites(topic_id)
        prereqs_met = all(
            p in mastered_ids or (p in sorted_topics and sorted_topics.index(p) < i)
            for p in direct_prereqs
        )

        nodes.append(PathNode(
            topic_id=topic_id,
            topic_name=topic.name if topic else topic_id,
            current_proficiency=prof_info["proficiency"],
            target_proficiency=mastery_threshold,
            status=prof_info["status"],
            prerequisites_met=prereqs_met,
            step_number=i + 1,
        ))

    path = LearningPath(
        nodes=nodes,
        target_topics=targets,
        total_steps=len(nodes),
        estimated_effort=_estimate_effort(len(nodes)),
    )

    return path


def persist_learning_path(
    supabase: Client,
    user_id: str,
    path: LearningPath,
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
) -> dict:
    """
    Persist a generated learning path to the database.
    Returns the inserted row.
    """
    path_data = [asdict(node) for node in path.nodes]

    row = {
        "user_id": user_id,
        "path_data": json.dumps(path_data),
        "target_topics": path.target_topics,
        "mastery_threshold": int(mastery_threshold),
        "total_steps": path.total_steps,
        "completed_steps": 0,
    }

    res = supabase.table("learning_paths").insert(row).execute()
    return res.data[0] if res.data else {}


def get_latest_learning_path(supabase: Client, user_id: str) -> dict | None:
    """
    Retrieve the user's most recently generated learning path.
    """
    res = (
        supabase.table("learning_paths")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        row = res.data[0]
        # Parse path_data from JSON string if needed
        if isinstance(row.get("path_data"), str):
            row["path_data"] = json.loads(row["path_data"])
        return row
    return None
