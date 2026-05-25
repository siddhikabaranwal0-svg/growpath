import os
import sys
import argparse
from dotenv import load_dotenv
import psycopg2

def main():
    parser = argparse.ArgumentParser(description="GrowPath Database Setup and Migrations Utility")
    parser.add_argument("--seed", action="store_true", help="Apply sample mock data from seeds.sql")
    args = parser.parse_args()

    # Load environment variables from current directory or parent directory
    load_dotenv()
    
    # Also attempt loading from the root of the project if script is executed from inside scripts/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(base_dir, ".env"))

    # Retrieve connection details
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Construct from components
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "postgres")
        user = os.getenv("DB_USER", "postgres")
        pw = os.getenv("DB_PASSWORD", "")
        db_url = f"postgresql://{user}:{pw}@{host}:{port}/{name}"

    print("=" * 60)
    print("GrowPath PostgreSQL Schema Setup Utility")
    print("=" * 60)

    schema_path = os.path.join(base_dir, "db", "schema.sql")
    seeds_path = os.path.join(base_dir, "db", "seeds.sql")

    if not os.path.exists(schema_path):
        print(f"[ERROR] schema.sql not found at: {schema_path}")
        sys.exit(1)

    print("Connecting to database...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
    except Exception as e:
        print(f"[ERROR] Could not connect to the database. Details:")
        print(f"  {e}")
        print("\nTroubleshooting recommendations:")
        print("  1. Ensure your PostgreSQL server is running.")
        print("  2. Double check credentials in your .env file or environment.")
        print("  3. If connecting to Supabase, check network connectivity and transaction pooler settings.")
        sys.exit(1)

    print("[SUCCESS] Connected to PostgreSQL!")

    # Read schema.sql
    print(f"Applying schema definition from: {schema_path} ...")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        print("[SUCCESS] Database schema successfully applied.")
    except Exception as e:
        print(f"[ERROR] Failed to apply database migration:")
        print(f"  {e}")
        sys.exit(1)

    # Seed optionally
    if args.seed:
        if not os.path.exists(seeds_path):
            print(f"[WARNING] seeds.sql not found at: {seeds_path}. Skipping seeding.")
        else:
            print(f"Applying seed data from: {seeds_path} ...")
            try:
                with open(seeds_path, "r", encoding="utf-8") as f:
                    seeds_sql = f.read()
                
                with conn.cursor() as cur:
                    cur.execute(seeds_sql)
                print("[SUCCESS] Seed data successfully populated.")
            except Exception as e:
                print(f"[ERROR] Failed to apply seed data:")
                print(f"  {e}")
                sys.exit(1)

    conn.close()
    print("=" * 60)
    print("Setup Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
