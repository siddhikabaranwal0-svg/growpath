"""
Seed Learning Resources: Populates the learning_resources and resource_topics tables
with realistic content for testing the Content Recommendation System.

Creates 40+ resources across 6 topics (Variables, Control Flow, Functions,
Data Structures, Recursion, Algorithms) with varied types and difficulty levels.

Usage:
    python scripts/seed_learning_resources.py
"""

import os
import sys
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, ".env"))


# ── Resource Catalog ──────────────────────────────────────────────────────────
# Each entry: (title, description, resource_type, url, difficulty, minutes, quality, topic_slug)

RESOURCES = [
    # ── Variables & Data Types ─────────────────────────────────
    ("Python Variables Explained", "A beginner-friendly guide to variables, naming conventions, and basic data types in Python.", "article", "https://realpython.com/python-variables/", 1, 15, 0.90, "variables"),
    ("Data Types Deep Dive", "Video tutorial covering int, float, str, bool and type conversion.", "video", "https://www.youtube.com/watch?v=example_vars1", 1, 25, 0.85, "variables"),
    ("Variable Practice Exercises", "10 hands-on exercises to practice variable assignment and type casting.", "exercise", None, 1, 20, 0.80, "variables"),
    ("Type Annotations in Python 3.10+", "Advanced guide to type hints, generics, and static type checking.", "article", "https://docs.python.org/3/library/typing.html", 3, 30, 0.88, "variables"),
    ("Python Data Model Reference", "Official Python docs on the data model and built-in types.", "external_link", "https://docs.python.org/3/reference/datamodel.html", 4, 45, 0.92, "variables"),
    ("Variables & Types Quick Quiz", "A 10-question quiz to test your understanding of Python data types.", "quiz", None, 2, 10, 0.75, "variables"),
    ("Immutability and Memory in Python", "Understanding mutable vs immutable types and memory allocation.", "article", "https://realpython.com/python-memory-management/", 3, 20, 0.87, "variables"),

    # ── Control Flow ───────────────────────────────────────────
    ("If/Else Mastery Guide", "Complete guide to conditional logic: if, elif, else, and ternary expressions.", "article", "https://realpython.com/python-conditional-statements/", 1, 20, 0.88, "control-flow"),
    ("Python Loops Tutorial", "Video covering for loops, while loops, break, continue, and else clauses.", "video", "https://www.youtube.com/watch?v=example_cf1", 1, 30, 0.82, "control-flow"),
    ("Control Flow Challenges", "15 progressively difficult exercises on branching and looping.", "exercise", None, 2, 35, 0.90, "control-flow"),
    ("Pattern Matching (match/case)", "Python 3.10 structural pattern matching explained with examples.", "article", "https://peps.python.org/pep-0634/", 4, 25, 0.85, "control-flow"),
    ("Iterators and Generators Deep Dive", "Advanced iteration patterns: iterators, generators, and yield.", "video", "https://www.youtube.com/watch?v=example_cf2", 4, 40, 0.91, "control-flow"),
    ("Loop Optimization Techniques", "Performance tips for writing efficient loops in Python.", "article", "https://wiki.python.org/moin/PythonSpeed/PerformanceTips", 3, 15, 0.78, "control-flow"),
    ("Control Flow Quiz", "Test your branching and loop knowledge.", "quiz", None, 2, 10, 0.74, "control-flow"),

    # ── Functions ──────────────────────────────────────────────
    ("Functions 101", "Defining functions, parameters, return values, and docstrings.", "article", "https://realpython.com/defining-your-own-python-function/", 1, 20, 0.92, "functions"),
    ("Lambda and Higher-Order Functions", "Video on lambda expressions, map, filter, and reduce.", "video", "https://www.youtube.com/watch?v=example_fn1", 2, 25, 0.84, "functions"),
    ("Function Practice Set", "20 exercises from basic function definition to closures.", "exercise", None, 2, 40, 0.88, "functions"),
    ("Decorators Demystified", "Understanding Python decorators from first principles.", "article", "https://realpython.com/primer-on-python-decorators/", 3, 30, 0.93, "functions"),
    ("Closures and Scope Rules", "Deep dive into LEGB scope, closures, and nonlocal.", "video", "https://www.youtube.com/watch?v=example_fn2", 3, 35, 0.86, "functions"),
    ("Advanced Function Patterns", "Partial application, currying, and function factories.", "article", "https://docs.python.org/3/library/functools.html", 5, 40, 0.89, "functions"),
    ("Functions Mastery Quiz", "Challenging quiz covering all function concepts.", "quiz", None, 3, 15, 0.80, "functions"),

    # ── Data Structures ────────────────────────────────────────
    ("Lists and Tuples Guide", "Comprehensive guide to Python sequences: lists, tuples, and slicing.", "article", "https://realpython.com/python-lists-tuples/", 1, 20, 0.90, "data-structures"),
    ("Dictionaries and Sets", "Video tutorial on dict operations, set theory, and comprehensions.", "video", "https://www.youtube.com/watch?v=example_ds1", 2, 30, 0.86, "data-structures"),
    ("Data Structure Drills", "25 exercises covering lists, dicts, sets, tuples, and deques.", "exercise", None, 2, 45, 0.91, "data-structures"),
    ("Collections Module Deep Dive", "Counter, defaultdict, OrderedDict, namedtuple, and deque.", "article", "https://docs.python.org/3/library/collections.html", 3, 25, 0.87, "data-structures"),
    ("Implementing Custom Data Structures", "Building stacks, queues, and linked lists from scratch.", "video", "https://www.youtube.com/watch?v=example_ds2", 4, 50, 0.93, "data-structures"),
    ("Python Data Structures Cheat Sheet", "Quick reference card for all built-in data structures.", "external_link", "https://www.pythoncheatsheet.org/cheatsheet/data-structures", 1, 5, 0.75, "data-structures"),
    ("Data Structures Quiz", "Test your knowledge of Python collections.", "quiz", None, 2, 12, 0.77, "data-structures"),

    # ── Recursion ──────────────────────────────────────────────
    ("Introduction to Recursion", "Understanding recursive thinking, base cases, and call stacks.", "article", "https://realpython.com/python-thinking-recursively/", 2, 25, 0.89, "recursion"),
    ("Recursion Visualized", "Video walkthrough of recursive calls with stack frame animations.", "video", "https://www.youtube.com/watch?v=example_rec1", 2, 20, 0.91, "recursion"),
    ("Recursive Problem Set", "12 classic recursion problems: factorial, fibonacci, towers of Hanoi.", "exercise", None, 3, 50, 0.92, "recursion"),
    ("Memoization and Dynamic Programming Intro", "Using functools.lru_cache and manual memoization.", "article", "https://realpython.com/python-memoization/", 3, 30, 0.88, "recursion"),
    ("Tail Recursion and Optimization", "Why Python doesn't optimize tail calls and workaround patterns.", "article", "https://stackoverflow.com/questions/13591970/", 4, 20, 0.80, "recursion"),
    ("Recursive Backtracking Algorithms", "Video on backtracking: N-Queens, maze solving, Sudoku.", "video", "https://www.youtube.com/watch?v=example_rec2", 5, 45, 0.94, "recursion"),
    ("Recursion Quiz", "Test your recursive thinking skills.", "quiz", None, 3, 15, 0.79, "recursion"),

    # ── Algorithms ─────────────────────────────────────────────
    ("Big O Notation Explained", "Understanding time and space complexity with examples.", "article", "https://realpython.com/python-big-o-notation/", 2, 25, 0.90, "algorithms"),
    ("Sorting Algorithms Visualized", "Video comparing bubble, insertion, merge, and quick sort.", "video", "https://www.youtube.com/watch?v=example_alg1", 2, 35, 0.92, "algorithms"),
    ("Sorting & Searching Exercises", "15 exercises implementing and analyzing classic algorithms.", "exercise", None, 3, 60, 0.93, "algorithms"),
    ("Graph Algorithms in Python", "BFS, DFS, Dijkstra, and topological sort with NetworkX.", "article", "https://realpython.com/python-graph-algorithms/", 4, 40, 0.91, "algorithms"),
    ("Dynamic Programming Masterclass", "Video series on DP techniques: knapsack, LCS, coin change.", "video", "https://www.youtube.com/watch?v=example_alg2", 5, 60, 0.95, "algorithms"),
    ("Algorithm Complexity Cheat Sheet", "Quick reference for common algorithm complexities.", "external_link", "https://www.bigocheatsheet.com/", 2, 5, 0.82, "algorithms"),
    ("Algorithms Challenge Quiz", "Advanced quiz on algorithmic complexity and optimization.", "quiz", None, 4, 20, 0.83, "algorithms"),
]


def seed():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        print("[ERROR] SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
        sys.exit(1)

    supabase = create_client(url, key)

    print("=" * 60)
    print("GrowPath Learning Resources Seeder")
    print("=" * 60)

    # Fetch existing topics by slug
    topics_res = supabase.table("topics").select("id, slug").execute()
    if not topics_res.data:
        print("[ERROR] No topics found in the database. Run generate_synthetic_data.py first.")
        sys.exit(1)

    slug_to_id = {t["slug"]: t["id"] for t in topics_res.data}
    print(f"Found {len(slug_to_id)} topics: {list(slug_to_id.keys())}")

    # Check which slugs we need
    needed_slugs = set(r[7] for r in RESOURCES)
    missing = needed_slugs - set(slug_to_id.keys())
    if missing:
        print(f"[WARN] Missing topics for slugs: {missing}. Resources for these will be skipped.")

    resources_created = 0
    links_created = 0

    for title, description, rtype, url_val, difficulty, minutes, quality, topic_slug in RESOURCES:
        if topic_slug not in slug_to_id:
            continue

        topic_id = slug_to_id[topic_slug]
        resource_id = str(uuid.uuid4())

        resource_row = {
            "id": resource_id,
            "title": title,
            "description": description,
            "resource_type": rtype,
            "url": url_val,
            "difficulty_level": difficulty,
            "estimated_minutes": minutes,
            "quality_score": quality,
            "metadata": "{}",
        }

        try:
            supabase.table("learning_resources").upsert(
                resource_row, on_conflict="id"
            ).execute()
            resources_created += 1
        except Exception as e:
            print(f"  [WARN] Resource '{title}': {e}")
            continue

        # Link to topic
        link_row = {
            "resource_id": resource_id,
            "topic_id": topic_id,
        }
        try:
            supabase.table("resource_topics").upsert(
                link_row, on_conflict="resource_id,topic_id"
            ).execute()
            links_created += 1
        except Exception as e:
            print(f"  [WARN] Link for '{title}': {e}")

    print(f"\n[OK] Created {resources_created} learning resources with {links_created} topic links.")
    print("=" * 60)
    print("Seeding complete!")
    print(f"  Resources: {resources_created}")
    print(f"  Topic links: {links_created}")
    print("=" * 60)


if __name__ == "__main__":
    seed()
