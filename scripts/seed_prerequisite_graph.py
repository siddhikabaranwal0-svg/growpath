"""
Seed Prerequisite Graph: Populates the topic_prerequisites table with a realistic
Python Programming curriculum DAG.

Graph structure:
    Variables ──→ Control Flow ──→ Functions ──→ Recursion
                       │                           ↑
                       └──→ Data Structures ───────┘
                                 │
                                 └──→ Algorithms

This script reads existing topics from the database (by slug), then inserts
prerequisite edges. It validates the final graph is a valid DAG using NetworkX.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, ".env"))

try:
    import networkx as nx
except ImportError:
    print("[ERROR] networkx is required. Run: pip install networkx>=3.1")
    sys.exit(1)


# Define the prerequisite relationships by topic slug.
# Format: (prerequisite_slug, dependent_slug)
PREREQUISITE_EDGES = [
    ("variables", "control-flow"),           # Variables → Control Flow
    ("control-flow", "functions"),           # Control Flow → Functions
    ("control-flow", "data-structures"),     # Control Flow → Data Structures
    ("functions", "recursion"),              # Functions → Recursion
    ("data-structures", "recursion"),        # Data Structures → Recursion
    ("data-structures", "algorithms"),       # Data Structures → Algorithms
]


def seed():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        print("[ERROR] SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
        sys.exit(1)

    supabase = create_client(url, key)

    print("=" * 60)
    print("GrowPath Prerequisite Graph Seeder")
    print("=" * 60)

    # Fetch all topics by slug
    topics_res = supabase.table("topics").select("id, slug, name").execute()
    if not topics_res.data:
        print("[ERROR] No topics found in the database. Run generate_synthetic_data.py first.")
        sys.exit(1)

    slug_to_id = {t["slug"]: t["id"] for t in topics_res.data}
    slug_to_name = {t["slug"]: t["name"] for t in topics_res.data}

    print(f"Found {len(slug_to_id)} topics:")
    for slug, name in slug_to_name.items():
        print(f"  • {name} ({slug})")

    # Insert prerequisite edges
    print(f"\nInserting {len(PREREQUISITE_EDGES)} prerequisite edges...")
    inserted = 0
    for prereq_slug, dependent_slug in PREREQUISITE_EDGES:
        prereq_id = slug_to_id.get(prereq_slug)
        dependent_id = slug_to_id.get(dependent_slug)

        if not prereq_id:
            print(f"  [SKIP] Prerequisite topic '{prereq_slug}' not found.")
            continue
        if not dependent_id:
            print(f"  [SKIP] Dependent topic '{dependent_slug}' not found.")
            continue

        try:
            supabase.table("topic_prerequisites").upsert({
                "topic_id": dependent_id,
                "prerequisite_topic_id": prereq_id,
            }, on_conflict="topic_id,prerequisite_topic_id").execute()
            print(f"  [OK] {slug_to_name[prereq_slug]} → {slug_to_name[dependent_slug]}")
            inserted += 1
        except Exception as e:
            print(f"  [ERROR] {prereq_slug} → {dependent_slug}: {e}")

    # Validate the DAG using NetworkX
    print(f"\nValidating DAG integrity...")
    prereqs_res = supabase.table("topic_prerequisites").select("topic_id, prerequisite_topic_id").execute()

    G = nx.DiGraph()
    for t in topics_res.data:
        G.add_node(t["id"], name=t["name"])

    if prereqs_res.data:
        for edge in prereqs_res.data:
            G.add_edge(edge["prerequisite_topic_id"], edge["topic_id"])

    is_dag = nx.is_directed_acyclic_graph(G)
    topo_order = list(nx.topological_sort(G)) if is_dag else []

    if is_dag:
        print("[SUCCESS] Graph is a valid DAG!")
        print(f"\nTopological order (learning sequence):")
        for i, node_id in enumerate(topo_order):
            name = G.nodes[node_id].get("name", node_id)
            in_deg = G.in_degree(node_id)
            out_deg = G.out_degree(node_id)
            label = ""
            if in_deg == 0:
                label = " ← ROOT (entry point)"
            elif out_deg == 0:
                label = " ← LEAF (goal)"
            print(f"  {i + 1}. {name}{label}")
    else:
        cycles = list(nx.simple_cycles(G))
        print(f"[ERROR] Graph contains {len(cycles)} cycle(s)!")
        for cycle in cycles[:5]:
            cycle_names = [G.nodes[n].get("name", n) for n in cycle]
            print(f"  Cycle: {' → '.join(cycle_names)}")

    print("=" * 60)
    print(f"Seeding complete! Edges inserted: {inserted}/{len(PREREQUISITE_EDGES)}")
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, DAG={is_dag}")
    print("=" * 60)


if __name__ == "__main__":
    seed()
