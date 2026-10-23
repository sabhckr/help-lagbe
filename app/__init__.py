"""Help Lagbe? application factory."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from app import permissions as P
from app.extensions import bcrypt, csrf, db, limiter, login_manager, migrate
from app.i18n import get_locale, init_i18n, translate
from config import get_config, is_local_database

# Re-exported for backwards compatibility with the original package layout.
__all__ = ["create_app", "db", "bcrypt", "login_manager"]


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    load_dotenv()
    instance_path = os.environ.get("INSTANCE_PATH") or ("/tmp/help_lagbe_instance" if os.environ.get("VERCEL") else None)  # noqa: S108  # nosec B108
    app = Flask(__name__, instance_relative_config=True, static_url_path="/static", instance_path=instance_path)
    cfg = get_config(config_name)
    app.config.from_object(cfg)
    if overrides:
        app.config.update(overrides)
    if app.config.get("ENV_NAME") == "production":
        cfg.validate()  # type: ignore[attr-defined]
    if app.config.get("ENV_NAME") == "migrate" and not os.environ.get("DATABASE_URL"):
        raise RuntimeError("APP_ENV=migrate needs DATABASE_URL set explicitly, so the target database is never a default.")
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        # Read-only filesystem (serverless). Nothing in production writes here; evidence lives in the database.
        logging.getLogger(__name__).info("instance folder not writable; continuing")
    _configure_logging(app)

    proxies = int(app.config.get("TRUSTED_PROXY_COUNT") or 0)
    if proxies > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)  # type: ignore[method-assign]

    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(app.root_path), "migrations"))
    csrf.init_app(app)
    limiter.init_app(app)
    init_i18n(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.session_protection = "strong"
    login_manager.login_message = None

    from app import models  # noqa: F401  (registers tables)
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None
        if user is None or not user.active:
            return None
        return user

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"error": "unauthorized"}), 401
        return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))

    _register_blueprints(app)
    _register_errors(app)
    _register_context(app)
    _register_security_headers(app)
    _register_cli(app)

    env = app.config.get("ENV_NAME")
    if env == "testing":
        with app.app_context():
            db.create_all()
    elif env == "development" and app.config.get("AUTO_UPGRADE_DB", True):
        if not is_local_database(app.config["SQLALCHEMY_DATABASE_URI"]):
            # Never migrate or seed demo accounts into a remote database from a development run.
            logging.getLogger(__name__).warning("development start-up skipped migrations and demo data: database is not local")
            return app
        with app.app_context():
            migrations_dir = os.path.join(os.path.dirname(app.root_path), "migrations")
            if os.path.isdir(migrations_dir):
                from flask_migrate import upgrade

                upgrade(directory=migrations_dir)
            else:
                db.create_all()
            if app.config.get("SEED_DEMO_DATA") and User.query.count() == 0:
                from app.seed import seed_demo

                seed_demo()
    return app


def _configure_logging(app: Flask) -> None:
    level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING if not app.debug else logging.INFO)


def _register_blueprints(app: Flask) -> None:
    from app.routes.auth import auth_bp
    from app.routes.legacy import legacy_bp
    from app.routes.public import public_bp
    from app.routes.report import report_bp
    from app.routes.support import support_bp
    from app.routes.track import track_bp
    from app.routes.workspace import workspace_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(report_bp, url_prefix="/report")
    app.register_blueprint(track_bp, url_prefix="/track")
    app.register_blueprint(support_bp, url_prefix="/support")
    app.register_blueprint(workspace_bp, url_prefix="/workspace")
    app.register_blueprint(legacy_bp)


def _register_errors(app: Flask) -> None:
    def _render(template: str, code: int):
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"error": code}), code
        return render_template(template, code=code), code

    @app.errorhandler(403)
    def forbidden(_e):
        return _render("errors/403.html", 403)

    @app.errorhandler(404)
    def not_found(_e):
        return _render("errors/404.html", 404)

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return _render("errors/404.html", 405)

    @app.errorhandler(413)
    def too_large(_e):
        return _render("errors/413.html", 413)

    @app.errorhandler(429)
    def too_many(_e):
        return _render("errors/429.html", 429)

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return _render("errors/csrf.html", 400)

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return _render("errors/500.html", 500)


def _register_context(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        from app.helplines import CHECKED_ON, NATIONAL

        return {
            "P": P,
            "national_helplines": NATIONAL,
            "checked_on": CHECKED_ON,
            "config": app.config,
            "site_name": app.config.get("SITE_NAME", "Help Lagbe?"),
            "now": datetime.utcnow(),
            "is_staff": bool(getattr(current_user, "is_authenticated", False) and getattr(current_user, "is_staff", False)),
        }

    from app.helplines import CHECKED_ON

    # Globals are visible inside imported macros, unlike context-processor values.
    app.jinja_env.globals["current_lang"] = get_locale
    app.jinja_env.globals["checked_on"] = CHECKED_ON

    @app.template_filter("dt")
    def format_dt(value, fmt: str = "%d %b %Y, %H:%M"):
        if not value:
            return ""
        return value.strftime(fmt) + " UTC"

    @app.template_filter("d")
    def format_d(value):
        if not value:
            return ""
        return value.strftime("%d %b %Y")

    @app.template_filter("tkey")
    def translate_key(value, prefix: str = ""):
        return translate(f"{prefix}{value}") if value else ""

    @app.template_filter("bn_digits")
    def bn_digits(value):
        if get_locale() != "bn":
            return value
        table = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
        return str(value).translate(table)

    @app.before_request
    def _touch_locale():
        get_locale()


def _register_security_headers(app: Flask) -> None:
    csp = (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; connect-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; manifest-src 'self'; "
        "worker-src 'self'"
    )
    private_prefixes = ("/workspace", "/track", "/support/chat", "/auth", "/report")

    @app.after_request
    def set_headers(response):
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if app.config.get("ENV_NAME") == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.path.startswith(private_prefixes):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response


def _register_cli(app: Flask) -> None:
    import click

    @app.cli.command("seed-demo")
    def seed_demo_cmd():
        """Insert fictional demo data (refuses in production)."""
        if app.config.get("ENV_NAME") == "production":
            raise click.ClickException("Demo data is never seeded in production.")
        from app.seed import seed_demo

        seed_demo()
        click.echo("Demo data seeded.")

    @app.cli.command("create-staff")
    @click.option("--email", required=True)
    @click.option("--name", required=True)
    @click.option("--role", required=True, type=click.Choice(list(P.STAFF_ROLES)))
    @click.password_option()
    def create_staff(email, name, role, password):
        """Create a staff account (MFA enrolment is forced at first login)."""
        from app.models.user import User
        from app.services.security import password_problems

        problems = password_problems(password, email=email, name=name)
        if problems:
            raise click.ClickException("Weak password: " + ", ".join(problems))
        if User.query.filter_by(email=email.lower()).first():
            raise click.ClickException("Email already exists")
        user = User(email=email.lower(), name=name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {role} account {user.id}")

    @app.cli.command("check-config")
    def check_config():
        """Validate production settings without starting the server."""
        from config import ProductionConfig

        ProductionConfig.validate()
        click.echo("Production configuration OK")

    @app.cli.command("housekeeping")
    def housekeeping():
        """Close abandoned support conversations and list cases due for retention review."""
        from datetime import date

        from app.models.case import Case
        from app.services.support import expire_abandoned

        n = expire_abandoned()
        from app.services.drafts import purge_expired

        click.echo(f"removed {purge_expired()} expired report drafts")
        due = Case.query.filter(Case.retention_review_at.isnot(None), Case.retention_review_at <= date.today()).count()
        click.echo(f"closed {n} abandoned conversations; {due} cases due for retention review")
