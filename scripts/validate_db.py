import os
import sys
from dotenv import load_dotenv
import psycopg2

def check_table_exists(cur, table_name):
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s);",
        (table_name,)
    )
    return cur.fetchone()[0]

def check_rls_enabled(cur, table_name):
    cur.execute(
        "SELECT rowsecurity FROM pg_tables WHERE schemaname = 'public' AND tablename = %s;",
        (table_name,)
    )
    res = cur.fetchone()
    return res[0] if res else False

def check_trigger_exists(cur, trigger_name):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = 'auth' AND t.tgname = %s
        );
        """,
        (trigger_name,)
    )
    return cur.fetchone()[0]

def check_index_exists(cur, index_name):
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = %s);",
        (index_name,)
    )
    return cur.fetchone()[0]

def main():
    # Load environment variables
    load_dotenv()
    
    # Also load from root if script is inside scripts/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(base_dir, ".env"))

    # Retrieve connection details
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "postgres")
        user = os.getenv("DB_USER", "postgres")
        pw = os.getenv("DB_PASSWORD", "")
        db_url = f"postgresql://{user}:{pw}@{host}:{port}/{name}"

    print("=" * 60)
    print("GrowPath Database Integrity & RLS Validation Utility")
    print("=" * 60)

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
    except Exception as e:
        print(f"[ERROR] Could not connect to the database. Details:")
        print(f"  {e}")
        sys.exit(1)

    print("[SUCCESS] Connected to database. Running checks...")
    print("-" * 60)

    # 1. Check tables
    required_tables = ["profiles", "quizzes", "questions", "options", "quiz_attempts", "user_responses"]
    all_tables_ok = True

    print("Checking Table Existence & Row-Level Security (RLS):")
    with conn.cursor() as cur:
        for tbl in required_tables:
            exists = check_table_exists(cur, tbl)
            if exists:
                rls = check_rls_enabled(cur, tbl)
                rls_status = "ENABLED" if rls else "DISABLED"
                print(f"  - Table 'public.{tbl}': EXISTS | RLS: {rls_status}")
                if not rls:
                    print(f"    [WARNING] RLS should be enabled on 'public.{tbl}' for maximum security.")
            else:
                print(f"  - Table 'public.{tbl}': MISSING [ERROR]")
                all_tables_ok = False
        
        print("-" * 60)
        
        # 2. Check Triggers
        print("Checking Profile Sync Trigger:")
        trigger_ok = check_trigger_exists(cur, "on_auth_user_created")
        if trigger_ok:
            print("  - Trigger 'on_auth_user_created' on 'auth.users': ACTIVE [SUCCESS]")
        else:
            print("  - Trigger 'on_auth_user_created' on 'auth.users': MISSING [ERROR]")
            
        print("-" * 60)

        # 3. Check Indexes
        print("Checking Database Indexes:")
        required_indexes = [
            "quizzes_creator_id_idx",
            "questions_quiz_id_idx",
            "options_question_id_idx",
            "quiz_attempts_user_id_idx",
            "quiz_attempts_quiz_id_idx",
            "user_responses_attempt_id_idx",
            "user_responses_question_id_idx"
        ]
        all_indexes_ok = True
        for idx in required_indexes:
            idx_exists = check_index_exists(cur, idx)
            status = "FOUND [SUCCESS]" if idx_exists else "MISSING [WARNING]"
            print(f"  - Index 'public.{idx}': {status}")
            if not idx_exists:
                all_indexes_ok = False

    conn.close()

    print("=" * 60)
    print("Validation Summary:")
    if all_tables_ok and trigger_ok:
        print("[SUCCESS] All core tables and security triggers are properly configured!")
    else:
        print("[FAILED] Some database structure errors were detected. Review logs above.")
        sys.exit(1)
        
    if not all_indexes_ok:
        print("[INFO] Note: Some performance indexes were not found. This is fine for initial MVP but recommended for production.")
    print("=" * 60)

if __name__ == "__main__":
    main()
