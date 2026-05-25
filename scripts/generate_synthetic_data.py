"""
Synthetic Data Generator: Produces realistic quiz response data for testing the ML pipeline.

Generates 10+ students across 6 topics with varying ability levels, response
patterns, and temporal distributions. Designed to test all aspects of the
Skill Mapping Engine including time-decay, trend detection, and edge cases.
"""

import os
import sys
import random
import uuid
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, ".env"))


def generate():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        print("[ERROR] SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
        sys.exit(1)

    supabase = create_client(url, key)

    print("=" * 60)
    print("GrowPath Synthetic Data Generator")
    print("=" * 60)

    # ── 1. Define Topics ──────────────────────────────────────
    topics = [
        {"id": str(uuid.uuid4()), "name": "Variables & Data Types", "slug": "variables", "description": "Fundamental programming variables and data types"},
        {"id": str(uuid.uuid4()), "name": "Control Flow", "slug": "control-flow", "description": "If/else statements, loops, and branching logic"},
        {"id": str(uuid.uuid4()), "name": "Functions", "slug": "functions", "description": "Function definitions, parameters, return values, and scope"},
        {"id": str(uuid.uuid4()), "name": "Data Structures", "slug": "data-structures", "description": "Lists, dictionaries, sets, and tuples"},
        {"id": str(uuid.uuid4()), "name": "Recursion", "slug": "recursion", "description": "Recursive algorithms and base cases"},
        {"id": str(uuid.uuid4()), "name": "Algorithms", "slug": "algorithms", "description": "Sorting, searching, and algorithmic complexity"},
    ]

    print(f"Creating {len(topics)} topics...")
    for t in topics:
        try:
            supabase.table("topics").upsert(t, on_conflict="slug").execute()
        except Exception as e:
            print(f"  [WARN] Topic '{t['name']}': {e}")
    print("[OK] Topics created.")

    # ── 2. Create a Quiz with Questions ────────────────────────
    # Use an existing profile or create mock auth users
    quiz_id = str(uuid.uuid4())
    creator_id = None

    # Try to find an existing profile
    profiles_res = supabase.table("profiles").select("id").limit(1).execute()
    if profiles_res.data:
        creator_id = profiles_res.data[0]["id"]
    else:
        print("[WARN] No profiles found. Creating quiz without a creator.")

    quiz = {
        "id": quiz_id,
        "title": "Python Programming Comprehensive Quiz",
        "description": "A comprehensive quiz covering all Python fundamentals.",
        "creator_id": creator_id,
        "is_published": True,
    }
    print("Creating quiz...")
    try:
        supabase.table("quizzes").upsert(quiz, on_conflict="id").execute()
    except Exception as e:
        print(f"  [WARN] Quiz: {e}")

    # Create questions (5 per topic = 30 total)
    questions = []
    question_topic_links = []
    all_options = []

    for topic in topics:
        for q_num in range(1, 6):
            q_id = str(uuid.uuid4())
            questions.append({
                "id": q_id,
                "quiz_id": quiz_id,
                "question_text": f"{topic['name']} - Question {q_num}",
                "question_type": "multiple_choice",
                "points": random.choice([1, 2, 3]),
                "order_no": len(questions) + 1,
            })
            question_topic_links.append({
                "question_id": q_id,
                "topic_id": topic["id"],
            })
            # Create 4 options, 1 correct
            correct_idx = random.randint(0, 3)
            for opt_num in range(4):
                all_options.append({
                    "id": str(uuid.uuid4()),
                    "question_id": q_id,
                    "option_text": f"Option {opt_num + 1} for Q{len(questions)}",
                    "is_correct": opt_num == correct_idx,
                })

    print(f"Creating {len(questions)} questions with {len(all_options)} options...")
    for q in questions:
        try:
            supabase.table("questions").upsert(q, on_conflict="id").execute()
        except Exception as e:
            print(f"  [WARN] Question: {e}")

    for opt in all_options:
        try:
            supabase.table("options").upsert(opt, on_conflict="id").execute()
        except Exception as e:
            pass  # silent for bulk

    for link in question_topic_links:
        try:
            supabase.table("question_topics").upsert(
                link, on_conflict="question_id,topic_id"
            ).execute()
        except Exception as e:
            pass

    print("[OK] Questions, options, and topic links created.")

    # ── 3. Generate Student Profiles & Responses ──────────────
    # Define student archetypes with different ability levels
    student_archetypes = [
        {"name": "Alice Expert", "username": "alice_expert", "accuracy_by_topic": [0.95, 0.90, 0.85, 0.88, 0.80, 0.75], "trend": "stable"},
        {"name": "Bob Beginner", "username": "bob_beginner", "accuracy_by_topic": [0.60, 0.40, 0.30, 0.35, 0.15, 0.10], "trend": "improving"},
        {"name": "Carol Improving", "username": "carol_improving", "accuracy_by_topic": [0.70, 0.55, 0.50, 0.45, 0.40, 0.30], "trend": "improving"},
        {"name": "Dave Declining", "username": "dave_declining", "accuracy_by_topic": [0.80, 0.75, 0.65, 0.50, 0.40, 0.30], "trend": "declining"},
        {"name": "Eve Mixed", "username": "eve_mixed", "accuracy_by_topic": [0.90, 0.30, 0.85, 0.20, 0.75, 0.15], "trend": "mixed"},
        {"name": "Frank Newbie", "username": "frank_newbie", "accuracy_by_topic": [0.50, 0.45, 0.0, 0.0, 0.0, 0.0], "trend": "stable"},
        {"name": "Grace Steady", "username": "grace_steady", "accuracy_by_topic": [0.70, 0.70, 0.70, 0.70, 0.70, 0.70], "trend": "stable"},
        {"name": "Hank Focused", "username": "hank_focused", "accuracy_by_topic": [0.95, 0.95, 0.10, 0.10, 0.10, 0.10], "trend": "stable"},
        {"name": "Ivy Fast", "username": "ivy_fast", "accuracy_by_topic": [0.80, 0.75, 0.70, 0.65, 0.60, 0.55], "trend": "improving"},
        {"name": "Jack Minimal", "username": "jack_minimal", "accuracy_by_topic": [0.60, 0.0, 0.0, 0.0, 0.0, 0.0], "trend": "stable"},
    ]

    print(f"\nGenerating responses for {len(student_archetypes)} synthetic students...")

    now = datetime.now(timezone.utc)

    for student in student_archetypes:
        # Create auth user and profile
        user_id = str(uuid.uuid4())
        try:
            supabase.table("auth.users" if False else "profiles").upsert({
                "id": user_id,
                "username": student["username"],
                "full_name": student["name"],
                "avatar_url": f"https://api.dicebear.com/7.x/adventurer/svg?seed={student['username']}",
            }, on_conflict="username").execute()
        except Exception as e:
            print(f"  [WARN] Profile '{student['name']}': {e}")
            continue

        # Generate quiz attempts and responses
        for topic_idx, topic in enumerate(topics):
            accuracy = student["accuracy_by_topic"][topic_idx]
            if accuracy == 0.0:
                continue  # Skip topics with 0 accuracy (not attempted)

            # Determine number of attempts (1–3 spread over weeks)
            num_attempts = random.randint(1, 3)
            topic_questions = [q for q in questions if any(
                l["question_id"] == q["id"] and l["topic_id"] == topic["id"]
                for l in question_topic_links
            )]

            for attempt_num in range(num_attempts):
                attempt_id = str(uuid.uuid4())
                # Space attempts over the past 60 days
                days_ago = random.randint(0, 60) - (attempt_num * 20)
                days_ago = max(0, days_ago)
                attempt_time = now - timedelta(days=days_ago, hours=random.randint(0, 23))

                # Adjust accuracy for trend
                if student["trend"] == "improving":
                    trend_factor = 1.0 + (attempt_num * 0.1)
                elif student["trend"] == "declining":
                    trend_factor = 1.0 - (attempt_num * 0.1)
                else:
                    trend_factor = 1.0

                adjusted_accuracy = min(max(accuracy * trend_factor, 0.0), 1.0)

                correct_count = 0
                total_points = 0
                responses = []

                for q in topic_questions:
                    is_correct = random.random() < adjusted_accuracy
                    if is_correct:
                        correct_count += 1
                        total_points += q["points"]

                    # Find the correct option
                    q_options = [o for o in all_options if o["question_id"] == q["id"]]
                    if is_correct:
                        selected = [o for o in q_options if o["is_correct"]][0]
                    else:
                        wrong_opts = [o for o in q_options if not o["is_correct"]]
                        selected = random.choice(wrong_opts) if wrong_opts else q_options[0]

                    responses.append({
                        "id": str(uuid.uuid4()),
                        "attempt_id": attempt_id,
                        "question_id": q["id"],
                        "selected_option_id": selected["id"],
                        "is_correct": is_correct,
                        "created_at": (attempt_time + timedelta(minutes=random.randint(1, 30))).isoformat(),
                    })

                # Insert attempt
                try:
                    supabase.table("quiz_attempts").upsert({
                        "id": attempt_id,
                        "user_id": user_id,
                        "quiz_id": quiz_id,
                        "score": total_points,
                        "started_at": attempt_time.isoformat(),
                        "completed_at": (attempt_time + timedelta(minutes=35)).isoformat(),
                    }, on_conflict="id").execute()
                except Exception as e:
                    print(f"  [WARN] Attempt: {e}")
                    continue

                # Insert responses
                for r in responses:
                    try:
                        supabase.table("user_responses").upsert(r, on_conflict="id").execute()
                    except Exception:
                        pass

        print(f"  [OK] {student['name']}: responses generated.")

    print("=" * 60)
    print("Synthetic data generation complete!")
    print(f"  Topics: {len(topics)}")
    print(f"  Questions: {len(questions)}")
    print(f"  Students: {len(student_archetypes)}")
    print("=" * 60)


if __name__ == "__main__":
    generate()
