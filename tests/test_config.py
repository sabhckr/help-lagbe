"""Database URL handling, serverless pool settings and the guards that keep development runs
from touching a remote database."""

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from config import engine_options, is_local_database, normalise_database_url

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "given",
    [
        "postgres://u:p@db.example.com:5432/app?sslmode=require",
        "postgresql://u:p@db.example.com:5432/app?sslmode=require",
        "postgresql+psycopg2://u:p@db.example.com:5432/app?sslmode=require",
        "postgresql+psycopg://u:p@db.example.com:5432/app?sslmode=require",
    ],
)
def test_every_postgres_url_uses_the_installed_psycopg_driver(given):
    assert normalise_database_url(given) == "postgresql+psycopg://u:p@db.example.com:5432/app?sslmode=require"


def test_non_postgres_urls_are_unchanged():
    assert normalise_database_url("sqlite:///instance/x.db") == "sqlite:///instance/x.db"


def test_postgres_engine_options_suit_poolers_and_serverless(monkeypatch):
    options = engine_options("postgresql+psycopg://u@db.example.com/app")
    assert options["connect_args"] == {"prepare_threshold": None} and options["pool_pre_ping"] is True
    monkeypatch.setenv("VERCEL", "1")
    assert engine_options("postgresql+psycopg://u@db.example.com/app")["pool_size"] == 2
    assert engine_options("sqlite:///x.db") == {"pool_pre_ping": True}


def test_local_database_detection():
    assert is_local_database("sqlite:///x.db") and is_local_database("postgresql+psycopg://localhost/x")
    assert not is_local_database("postgresql+psycopg://u@ep-calm-db.example.com/app")


def test_development_start_never_migrates_or_seeds_a_remote_database(tmp_path, caplog):
    from app import create_app

    caplog.set_level(logging.WARNING)
    # No server exists at this address: if start-up tried to migrate or seed, it would fail to connect.
    create_app("development", {"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://u@db.example.invalid/app", "EVIDENCE_DIR": str(tmp_path)})
    assert "database is not local" in caplog.text


def test_migrate_profile_requires_an_explicit_database_url(monkeypatch):
    from app import create_app

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app("migrate")


def test_migrate_profile_creates_nothing_on_start(monkeypatch, tmp_path):
    from sqlalchemy import create_engine, inspect

    from app import create_app

    target = tmp_path / "m.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target}")
    create_app("migrate", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{target}"})
    assert not target.exists() or inspect(create_engine(f"sqlite:///{target}")).get_table_names() == []


def test_status_script_needs_a_url_and_never_echoes_it():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/db_status.py")], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"}, cwd=ROOT
    )
    assert result.returncode == 2 and "DATABASE_URL is not set" in result.stdout
