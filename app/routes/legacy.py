"""Paths from the original prototype, kept as redirects so old links keep working."""

from flask import Blueprint, redirect, url_for

legacy_bp = Blueprint("legacy", __name__)


@legacy_bp.route("/submit")
def submit():
    return redirect(url_for("report.new"), code=301)


@legacy_bp.route("/login")
def login():
    return redirect(url_for("auth.login"), code=301)


@legacy_bp.route("/register")
def register():
    return redirect(url_for("auth.register"), code=301)


@legacy_bp.route("/logout")
def logout():
    return redirect(url_for("auth.logout"), code=301)


@legacy_bp.route("/dashboard")
def dashboard():
    return redirect(url_for("workspace.home"), code=301)


@legacy_bp.route("/editorial")
def editorial():
    return redirect(url_for("workspace.publications"), code=301)


@legacy_bp.route("/logs")
def logs():
    return redirect(url_for("workspace.audit"), code=301)
