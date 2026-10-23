"""Staff workspaces. One blueprint, one module per area. Every view is behind login + a
permission check; case views additionally go through services.access."""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, abort, redirect, request, url_for
from flask_login import current_user

from app.services.security import mfa_required_for

workspace_bp = Blueprint("workspace", __name__)


def staff_required(*perms: str):
    """Require an authenticated, active staff member with every listed permission."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.path))
            if not current_user.is_staff:
                abort(403)
            if mfa_required_for(current_user) and not current_user.mfa_enabled:
                return redirect(url_for("auth.mfa_setup"))
            if perms and not current_user.can(*perms):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def any_permission(*perms: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.path))
            if not current_user.is_staff or not current_user.can_any(*perms):
                abort(403)
            if mfa_required_for(current_user) and not current_user.mfa_enabled:
                return redirect(url_for("auth.mfa_setup"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


from app.routes.workspace import admin, cases, editorial, home, moderation, stories, support_desk  # noqa: E402,F401
