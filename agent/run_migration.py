"""Run database migration 003 via direct PostgreSQL connection."""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

sb_url = os.getenv("SUPABASE_URL", "")
ref = sb_url.split("//")[1].split(".")[0] if "//" in sb_url else ""
db_password = os.getenv("SUPABASE_DB_PASSWORD", "")

if not db_password:
    print("SUPABASE_DB_PASSWORD not set in .env")
    print("You can find it in Supabase Dashboard > Settings > Database")
    print()
    print("Alternative: run this SQL manually in Supabase SQL Editor:")
    print(f"  https://supabase.com/dashboard/project/{ref}/sql/new")
    print()
    with open("src/migrations/003_add_project_columns.sql", "r", encoding="utf-8") as f:
        print(f.read())
    exit(1)

host = f"db.{ref}.supabase.co"
conn_str = f"postgresql://postgres.{ref}:{db_password}@{host}:5432/postgres"
print(f"Connecting to: postgresql://postgres.{ref}:***@{host}:5432/postgres")

try:
    conn = psycopg2.connect(conn_str, connect_timeout=10)
    print("Connected!")
    cur = conn.cursor()

    with open("src/migrations/003_add_project_columns.sql", "r", encoding="utf-8") as f:
        sql = f.read()

    cur.execute(sql)
    conn.commit()
    print("Migration 003 executed successfully!")

    # Verify columns
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'autoviralvid_jobs' "
        "ORDER BY ordinal_position"
    )
    cols = [r[0] for r in cur.fetchall()]
    print(f"Columns now ({len(cols)}): {cols}")

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
