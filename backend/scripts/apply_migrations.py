"""
Apply infra/sql/001..007 to the PostgreSQL database named in DATABASE_URL (psql).

RankPilot SEO data layer is PostgreSQL only — same physical model as the product brief
(suburb grid, ranks, content queue, jobs, citations). Not SQLite/MySQL.

Run from the backend folder (so .env is found):
  cd backend
  python scripts/apply_migrations.py

Requires PostgreSQL client `psql` (add .../PostgreSQL/<ver>/bin to PATH, or we try common Windows paths).
DATABASE_URL must use postgresql+asyncpg://... (SQLAlchemy URL; this script connects with psql).
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url


def _find_psql() -> str | None:
    p = shutil.which("psql")
    if p:
        return p
    bases = [
        r"C:\Program Files\PostgreSQL",
        r"C:\Program Files (x86)\PostgreSQL",
    ]
    for base in bases:
        if not os.path.isdir(base):
            continue
        matches = sorted(
            glob.glob(os.path.join(base, "*", "bin", "psql.exe")),
            key=lambda x: x,
            reverse=True,
        )
        if matches:
            return matches[0]
    return None


def main() -> int:
    os.chdir(Path(__file__).resolve().parent.parent)
    sys.path.insert(0, str(Path.cwd()))
    from app.core.config import get_settings  # noqa: PLC0415 — after chdir

    settings = get_settings()
    psql = _find_psql()
    if not psql:
        print(
            "ERROR: psql not found. Install PostgreSQL client tools and add bin to PATH,\n"
            "or run the SQL files manually in pgAdmin (infra/sql 001→005).",
            file=sys.stderr,
        )
        return 1

    url = make_url(settings.database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    user = url.username or "postgres"
    database = url.database
    if not database:
        print("ERROR: DATABASE_URL has no database name.", file=sys.stderr)
        return 1

    backend_root = Path(__file__).resolve().parent.parent
    # Monorepo: ../infra/sql  |  Standalone backend repo: ./infra/sql (copy migrations there when splitting)
    sql_dir = backend_root / "infra" / "sql"
    if not sql_dir.is_dir():
        sql_dir = backend_root.parent / "infra" / "sql"
    files = [
        "001_init_seo.sql",
        "002_extensions.sql",
        "003_seed_demo.sql",
        "004_client_password.sql",
        "005_login_username.sql",
        "006_drop_legacy_ai_overview.sql",
        "007_clear_placeholder_content_queue.sql",
        "008_integrations.sql",
        "009_search_radius.sql",
        "010_perf_indexes.sql",
        "011_business_nap.sql",
        "012_citation_scraped_nap.sql",
    ]

    env = os.environ.copy()
    if url.password is not None:
        env["PGPASSWORD"] = str(url.password)

    print(f"Using psql: {psql}")
    print(f"Target: {user}@{host}:{port}/{database}\n")

    for name in files:
        path = sql_dir / name
        if not path.is_file():
            print(f"ERROR: missing {path}", file=sys.stderr)
            return 1
        print(f"Applying {name} ...")
        r = subprocess.run(
            [
                psql,
                "-h",
                host,
                "-p",
                str(port),
                "-U",
                user,
                "-d",
                database,
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(path),
            ],
            env=env,
        )
        if r.returncode != 0:
            print(f"FAILED: {name} (exit {r.returncode})", file=sys.stderr)
            return r.returncode

    print("\nDone. Restart uvicorn and sign in as admin / admin123.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
