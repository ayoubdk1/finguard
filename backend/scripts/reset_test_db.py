import os, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import psycopg

target_url = os.getenv("DATABASE_URL", "postgresql+psycopg://finguard:finguard_dev_password@127.0.0.1:5433/finguard_test")
parsed = urlparse(target_url.replace("postgresql+psycopg://", "postgresql://"))
db_name = parsed.path.lstrip("/") or "finguard_test"
admin_url = urlunparse(parsed._replace(path="/postgres"))
with psycopg.connect(admin_url, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (db_name,))
        cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        cur.execute(f'CREATE DATABASE "{db_name}"')
backend_dir = Path(__file__).resolve().parents[1]
env = {**os.environ, "DATABASE_URL": target_url, "PYTHONPATH": str(backend_dir)}
subprocess.run([sys.executable, "-m", "alembic", "-c", str(backend_dir / "alembic.ini"), "upgrade", "head"], check=True, env=env)
print(f"Recreated {db_name} cleanly!")
