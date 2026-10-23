"""Lightweight JSON-based internationalisation.

Translation files live in app/translations/<lang>/*.json and are merged at startup.
Keys are dotted ("nav.home"). Missing Bengali keys fall back to English, then to the key
itself, so a missing string is visible rather than silent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import current_app, has_request_context, request

log = logging.getLogger(__name__)

TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"
LANGUAGE_NAMES = {"en": "English", "bn": "বাংলা"}
COOKIE_NAME = "hl_lang"


def load_translations() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for lang_dir in sorted(TRANSLATIONS_DIR.iterdir()):
        if not lang_dir.is_dir():
            continue
        merged: dict[str, str] = {}
        for path in sorted(lang_dir.glob("*.json")):
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            for key, value in _flatten(data).items():
                if key in merged:
                    log.warning("duplicate translation key %s in %s", key, path.name)
                merged[key] = value
        catalog[lang_dir.name] = merged
    return catalog


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, full + "."))
        else:
            out[full] = str(value)
    return out


def get_locale() -> str:
    if has_request_context():
        cached = request.environ.get("helplagbe.locale")
        if cached:
            return cached
    languages = tuple(current_app.config.get("LANGUAGES", ("en",)))
    default = current_app.config.get("DEFAULT_LANGUAGE", "en")
    locale = default
    if has_request_context():
        # Bangla first: the browser's language is not consulted; only the visitor's own choice is.
        cookie = request.cookies.get(COOKIE_NAME)
        if cookie in languages:
            locale = cookie
        request.environ["helplagbe.locale"] = locale
    return locale


def translate(key: str, **kwargs: Any) -> str:
    catalog = current_app.extensions.get("translations", {})
    locale = get_locale()
    text = catalog.get(locale, {}).get(key)
    if text is None:
        text = catalog.get("en", {}).get(key)
    if text is None:
        return key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def init_i18n(app) -> None:
    app.extensions["translations"] = load_translations()

    @app.context_processor
    def _inject():
        return {
            "t": translate,
            "current_locale": get_locale(),
            "LANGUAGE_NAMES": LANGUAGE_NAMES,
            "LANGUAGES": app.config["LANGUAGES"],
        }

    app.jinja_env.globals["t"] = translate
    app.jinja_env.filters["t"] = translate
