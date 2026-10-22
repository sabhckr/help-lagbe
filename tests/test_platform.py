"""Security headers, CSRF, i18n completeness, responsive/offline assets, legacy redirects, leakage."""

import json
import pathlib

from app.i18n import load_translations
from app.models import Case
from tests.conftest import login, make_case


def test_security_headers_on_every_response(client):
    for url in ("/", "/auth/login", "/report/new", "/nonexistent"):
        r = client.get(url)
        h = r.headers
        assert "default-src 'self'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"]
        assert h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff" and h["Referrer-Policy"] == "no-referrer"
        assert "camera=()" in h["Permissions-Policy"]


def test_private_pages_are_not_cacheable(client):
    assert client.get("/report/new").headers["Cache-Control"] == "no-store"
    assert client.get("/track/").headers["Cache-Control"] == "no-store"


def test_csrf_is_enforced_when_enabled(app):
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()
    r = client.post("/auth/login", data={"email": "a@b.co", "password": "x"})
    assert r.status_code == 400 and b"expired" in r.data
    r = client.post("/report/new", data={"title": "x"})
    assert r.status_code == 400
    page = client.get("/auth/login").data.decode()
    token = page.split('name="csrf_token" type="hidden" value="')[1].split('"')[0]
    r = client.post("/auth/login", data={"email": "a@b.co", "password": "x", "csrf_token": token})
    assert r.status_code == 200


def test_session_cookie_flags(client):
    from app.seed import DEMO_PASSWORD
    from tests.conftest import user_by_role

    user = user_by_role("reporter")
    r = client.post("/auth/login", data={"email": user.email, "password": DEMO_PASSWORD})
    cookie = [c for c in r.headers.getlist("Set-Cookie") if c.startswith("hl_session=")][0]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_translations_are_complete_and_bengali_renders(client):
    cat = load_translations()
    missing = [k for k in cat["en"] if k not in cat["bn"]]
    assert missing == []
    identical = [
        k
        for k in cat["en"]
        if cat["en"][k] == cat["bn"][k] and len(cat["en"][k]) > 12 and not k.startswith(("channel.", "site.identity", "site.principle"))
    ]
    assert len(identical) < 5, identical
    r = client.get("/lang/bn")
    assert r.status_code == 302 and "hl_lang=bn" in r.headers["Set-Cookie"]
    r = client.get("/", headers={"Cookie": "hl_lang=bn"})
    assert 'lang="bn"' in r.data.decode() and "অন্যায়ের কথা জানান" in r.data.decode()
    assert "মানুষের পাশে মানুষ" in r.data.decode()
    r = client.get("/report/new", headers={"Cookie": "hl_lang=bn"})
    assert "নাম না জানিয়ে" in r.data.decode()
    assert client.get("/lang/xx").status_code == 404


def test_every_template_key_exists_in_english(app):
    """No t('...') call in any template may resolve to its own key (which would show raw keys to users)."""
    import re

    cat = load_translations()["en"]
    root = pathlib.Path(app.root_path) / "templates"
    bad = []
    for path in root.rglob("*.html"):
        if "/content/" in str(path):
            continue
        for key in re.findall(r"""(?<![\w.])t\(\s*['"]([a-z0-9_.]+)['"]\s*[,)]""", path.read_text()):
            if key not in cat:
                bad.append((path.name, key))
    assert bad == []


def test_public_content_fragments_exist_for_both_languages(app):
    root = pathlib.Path(app.root_path) / "templates" / "public" / "content"
    for slug in (
        "get-help",
        "report-wrongdoing",
        "legal-help",
        "digital-safety",
        "live-support",
        "about",
        "safeguarding",
        "privacy",
        "editorial-policy",
        "corrections",
        "complaints",
        "accessibility",
        "contact",
        "awareness",
        "investigations",
    ):
        for lang in ("en", "bn"):
            assert (root / f"{slug}.{lang}.html").exists(), f"{slug}.{lang}"
    page = client_get(app, "/safeguarding")
    assert b"does not dispatch" in page or b"not dispatch" in page


def client_get(app, url):
    return app.test_client().get(url).data


def test_all_public_pages_render_in_both_languages(client):
    for slug in (
        "get-help",
        "report-wrongdoing",
        "legal-help",
        "digital-safety",
        "live-support",
        "about",
        "safeguarding",
        "privacy",
        "editorial-policy",
        "corrections",
        "complaints",
        "accessibility",
        "contact",
        "awareness",
        "investigations",
    ):
        for lang in ("en", "bn"):
            r = client.get(f"/{slug}", headers={"Cookie": f"hl_lang={lang}"})
            assert r.status_code == 200, (slug, lang)
            assert b"<h1>" in r.data


def test_legacy_paths_redirect(client):
    for old, new in (
        ("/submit", "/report/new"),
        ("/login", "/auth/login"),
        ("/register", "/auth/register"),
        ("/dashboard", "/workspace/"),
        ("/editorial", "/workspace/publications"),
        ("/logs", "/workspace/admin/audit"),
    ):
        r = client.get(old)
        assert r.status_code == 301 and r.headers["Location"].endswith(new), old
    assert client.get("/case/1").status_code == 404
    assert client.get("/public/abcd1234").status_code == 404


def test_error_pages_and_offline_assets(client):
    assert b"Page not found" in client.get("/does-not-exist").data
    login(client, "reporter")
    r = client.get("/workspace/")
    assert r.status_code == 403 and b"need-to-know" in r.data
    assert client.get("/offline").status_code == 200
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and b"/workspace" in sw.data and sw.headers["Service-Worker-Allowed"] == "/"
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/healthz").get_json() == {"status": "ok"}


def test_quick_exit_clears_private_session(client):
    case, secret = make_case()
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    assert client.get(f"/track/{case.reference}").status_code == 200
    r = client.post("/quick-exit")
    assert r.status_code == 303 and "google.com" in r.headers["Location"]
    assert client.get(f"/track/{case.reference}").status_code == 403


def test_identity_never_leaks_to_public_surfaces(client, app):
    case, secret = make_case(
        submission_type="confidential",
        identity_name="Leak Test Name",
        identity_phone="01733333333",
        identity_email="leak@example.org",
        consent_publication=True,
    )
    needles = (b"Leak Test Name", b"01733333333", b"leak@example.org")
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    for url in ("/", "/investigations", "/awareness", f"/track/{case.reference}", "/healthz", "/support/status", "/sw.js"):
        data = client.get(url).data
        for n in needles:
            assert n not in data, (url, n)
    # the audit trail and CSV export hold no identity either
    login(client, "admin")
    data = client.get("/workspace/admin/audit?sensitive=1").data
    for n in needles:
        assert n not in data
    # the case row has no identity columns at all
    row = {c.name: getattr(case, c.name) for c in Case.__table__.columns}
    assert not any(isinstance(v, str) and ("Leak Test" in v or "01733333333" in v) for v in row.values())


def test_app_logs_do_not_contain_narratives(app, caplog):
    import logging

    caplog.set_level(logging.INFO)
    make_case(narrative="UNIQUE-NARRATIVE-TOKEN-XYZ that must not be logged anywhere at all.")
    assert "UNIQUE-NARRATIVE-TOKEN-XYZ" not in caplog.text


def test_json_endpoints_return_401_not_redirect(client):
    r = client.get("/workspace/support/heartbeat", headers={"Accept": "application/json"})
    assert r.status_code in (401, 405)


def test_env_example_has_no_real_secrets():
    text = pathlib.Path(__file__).resolve().parent.parent.joinpath(".env.example").read_text()
    assert "IDENTITY_ENCRYPTION_KEY=\n" in text and "change-me" in text
    assert json.dumps(text).count("gho_") == 0
