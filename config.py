"""Application configuration.

Three profiles: development, testing, production. Production refuses to start with
placeholder secrets. Every secret comes from the environment (see .env.example).
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

_PLACEHOLDER_SECRETS = {"", "dev-secret-change-in-prod", "change-me", "changeme", "secret"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def normalise_database_url(url: str) -> str:
    """Route every PostgreSQL URL to the bundled psycopg (version 3) driver.

    Hosting dashboards and integrations usually hand out `postgres://` or `postgresql://`, which
    SQLAlchemy maps to psycopg2. Only psycopg 3 is installed, so the scheme is rewritten. Query
    parameters such as `sslmode=require` are kept as they are.
    """
    for prefix in ("postgres://", "postgresql://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def engine_options(url: str) -> dict[str, Any]:
    options: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("postgresql+psycopg://"):
        options["pool_recycle"] = 300
        # Transaction-mode poolers (PgBouncer, Neon, Supabase) reject server-side prepared statements.
        options["connect_args"] = {"prepare_threshold": None}
        if os.environ.get("VERCEL"):
            # Many short-lived function instances: keep each one's pool small.
            options.update(pool_size=2, max_overflow=3)
    return options


def is_local_database(url: str) -> bool:
    """True for SQLite and for servers on this machine. Development conveniences only run against these."""
    if url.startswith("sqlite:"):
        return True
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower()
    return host in ("", "localhost", "127.0.0.1", "::1")


ON_VERCEL = bool(os.environ.get("VERCEL"))


class BaseConfig:
    ENV_NAME = "base"
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    # Fernet key (base64, 32 bytes) used for the separate identity store. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    IDENTITY_ENCRYPTION_KEY = os.environ.get("IDENTITY_ENCRYPTION_KEY", "")

    SQLALCHEMY_DATABASE_URI = normalise_database_url(os.environ.get("DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'help_lagbe.db'}"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = engine_options(SQLALCHEMY_DATABASE_URI)

    # Sessions / cookies
    SESSION_COOKIE_NAME = "hl_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_env_int("SESSION_HOURS", 8))
    REMEMBER_COOKIE_DURATION = timedelta(days=1)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_SAMESITE = "Lax"

    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 6
    WTF_CSRF_SSL_STRICT = False  # Referer checks break behind some proxies; origin is enforced by SameSite + token.

    # Uploads (evidence). Stored outside the static folder, never served directly.
    EVIDENCE_DIR = os.environ.get("EVIDENCE_DIR", "/tmp/help_lagbe_evidence" if ON_VERCEL else str(INSTANCE_DIR / "evidence"))  # noqa: S108  # nosec B108
    # Vercel Functions accept at most 4.5 MB per request body, so the default there is 4 MB.
    MAX_CONTENT_LENGTH = _env_int("MAX_UPLOAD_MB", 4 if ON_VERCEL else 25) * 1024 * 1024
    EVIDENCE_MAX_FILES_PER_REPORT = 5
    EVIDENCE_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "pdf", "mp3", "m4a", "mp4", "txt"}
    CLAMD_SOCKET = os.environ.get("CLAMD_SOCKET", "")  # e.g. /var/run/clamav/clamd.ctl ; empty = scanner unavailable

    # Rate limiting
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = False
    RATELIMIT_DEFAULT = "300 per hour"

    # Reverse proxy. Number of trusted proxies in front of the app (0 = none).
    TRUSTED_PROXY_COUNT = _env_int("TRUSTED_PROXY_COUNT", 0)

    # Policy knobs (overridable in the admin console; these are the defaults).
    MFA_REQUIRED_FOR_STAFF = _env_bool("MFA_REQUIRED_FOR_STAFF", True)
    LOGIN_MAX_FAILURES = 6
    LOGIN_LOCKOUT_MINUTES = 15
    PASSWORD_MIN_LENGTH = 12
    SUPPORT_PRESENCE_TIMEOUT_SECONDS = 120
    DATA_RETENTION_DAYS_CLOSED_CASES = _env_int("DATA_RETENTION_DAYS_CLOSED_CASES", 365)

    LANGUAGES = ("en", "bn")
    DEFAULT_LANGUAGE = "bn"  # Bangla first; English is a full second language
    SITE_NAME = "Help Lagbe?"
    PREFERRED_URL_SCHEME = "http"

    # Email / outbound notifications: not configured. The app never sends mail unless this is set
    # and the feature is enabled by an admin. Kept here so the blocker is visible.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    OUTBOUND_NOTIFICATIONS_ENABLED = False

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    SEED_DEMO_DATA = _env_bool("SEED_DEMO_DATA", False)
    AUTO_UPGRADE_DB = _env_bool("AUTO_UPGRADE_DB", True)


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    DEBUG = True
    SEED_DEMO_DATA = _env_bool("SEED_DEMO_DATA", True)
    TEMPLATES_AUTO_RELOAD = True


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production-0123456789"  # nosec B105  # test profile only
    IDENTITY_ENCRYPTION_KEY = "u0kG8s7Q4N4x5cQ1yq1vF1n0q3M5s7f9r2t4y6u8i0o="  # test-only Fernet key
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # in-memory, isolated per app instance
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": False,
        "connect_args": {"check_same_thread": False},
    }
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    BCRYPT_LOG_ROUNDS = 4  # fast hashing in tests only; production uses the library default (12)
    MFA_REQUIRED_FOR_STAFF = True
    SEED_DEMO_DATA = False
    DEFAULT_LANGUAGE = "en"  # tests read English strings
    EVIDENCE_DIR = ""  # set per test to a temporary directory
    SERVER_NAME = "localhost.test"
    PREFERRED_URL_SCHEME = "http"


class MigrateConfig(BaseConfig):
    """Schema work only: `APP_ENV=migrate DATABASE_URL=... flask --app wsgi.py db current|upgrade`.

    Never seeds, never auto-migrates on start-up, and needs no application secrets.
    """

    ENV_NAME = "migrate"
    DEBUG = False
    SEED_DEMO_DATA = False
    AUTO_UPGRADE_DB = False


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    SEED_DEMO_DATA = False

    @classmethod
    def validate(cls) -> None:
        problems = []
        if cls.SECRET_KEY in _PLACEHOLDER_SECRETS or len(cls.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be set to a random value of at least 32 characters.")
        if not cls.IDENTITY_ENCRYPTION_KEY:
            problems.append("IDENTITY_ENCRYPTION_KEY must be set (Fernet key).")
        if cls.SQLALCHEMY_DATABASE_URI.startswith("sqlite://") and "DATABASE_URL" not in os.environ:
            problems.append("DATABASE_URL must be set explicitly in production.")
        if cls.RATELIMIT_STORAGE_URI == "memory://" and not _env_bool("ALLOW_MEMORY_RATELIMIT", False):
            problems.append("RATELIMIT_STORAGE_URI should point at a shared store (e.g. redis://) in production.")
        if problems:
            raise RuntimeError("Refusing to start in production:\n - " + "\n - ".join(problems))


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "migrate": MigrateConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    name = (name or os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "development").lower()
    return CONFIGS.get(name, DevelopmentConfig)
