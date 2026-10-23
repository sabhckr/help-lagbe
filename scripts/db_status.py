"""Read-only database status: schema revision, tables and row counts. Never writes, never prints the URL.

Usage (the URL comes from the environment, never from the command line):
    DATABASE_URL=... python scripts/db_status.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from config import normalise_database_url  # noqa: E402

EXPECTED_HEAD = "c3cee4c88fb2"
NEW_TABLES = ("report_drafts", "report_draft_files")
COUNT_SQL = {
    "users": "SELECT COUNT(*) FROM users",
    "cases": "SELECT COUNT(*) FROM cases",
    "evidence": "SELECT COUNT(*) FROM evidence",
    "publications": "SELECT COUNT(*) FROM publications",
}


def main() -> int:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("DATABASE_URL is not set.")
        return 2
    url = normalise_database_url(raw)
    engine = create_engine(url, connect_args={"prepare_threshold": None} if url.startswith("postgresql+psycopg://") else {})
    print(f"driver: {engine.dialect.name}+{engine.dialect.driver}")
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
        tables = set(inspect(conn).get_table_names())
        revision = None
        if "alembic_version" in tables:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(f"alembic revision: {revision or 'none (no alembic_version table)'}")
        print(f"application tables: {len(tables - {'alembic_version'})}")
        for table, sql in COUNT_SQL.items():
            if table in tables:
                print(f"rows in {table}: {conn.execute(text(sql)).scalar()}")
        print("new tables already present:", [t for t in NEW_TABLES if t in tables] or "none")
        conn.rollback()
    if revision == EXPECTED_HEAD:
        print("verdict: already at the latest revision")
    elif revision:
        print("verdict: needs `flask db upgrade` (back up first)")
    elif tables:
        print("verdict: tables exist without Alembic history; compare the schema before stamping")
    else:
        print("verdict: empty database; `flask db upgrade` creates everything")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
