"""Platform-wide checks: security headers, CSRF, navigation, localisation, accessibility basics,
honest availability, contrast of the palette, and that private data never reaches public pages."""

import json
import pathlib
import re

from app.helplines import NATIONAL
from app.i18n import load_translations
from app.models import Case
from tests.conftest import login, make_case, use_lang

PUBLIC_PAGES = (
    "/",
    "/help",
    "/stories",
    "/about",
    "/safety",
    "/privacy",
    "/contact",
    "/track/",
    "/requests/new",
    "/report/1",
    "/report/2",
    "/report/3",
    "/report/4",
    "/report/5",
)
NAV_ENDPOINT_PATHS = ("/", "/help", "/report/new", "/track/", "/stories", "/about")


def test_security_headers_on_every_response(client):
    for url in ("/", "/auth/login", "/report/1", "/nonexistent"):
        h = client.get(url).headers
        assert "default-src 'self'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"]
        assert h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff" and h["Referrer-Policy"] == "no-referrer"


def test_private_pages_are_not_cacheable(client):
    for url in ("/report/1", "/track/", "/report/received"):
        assert client.get(url).headers["Cache-Control"] == "no-store", url


def test_csrf_is_enforced_when_enabled(app):
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()
    assert client.post("/auth/login", data={"email": "a@b.co", "password": "x"}).status_code == 400
    assert client.post("/report/1", data={"category": "other"}).status_code == 400
    page = client.get("/report/1").data.decode()
    token = page.split('name="csrf_token" value="')[1].split('"')[0]
    assert client.post("/report/1", data={"category": "other", "csrf_token": token}).status_code == 302


def test_session_cookie_flags(client):
    from app.seed import DEMO_PASSWORD
    from tests.conftest import user_by_role

    user = user_by_role("reporter")
    r = client.post("/auth/login", data={"email": user.email, "password": DEMO_PASSWORD})
    cookie = [c for c in r.headers.getlist("Set-Cookie") if c.startswith("hl_session=")][0]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_every_public_page_renders_in_both_languages(client):
    for url in PUBLIC_PAGES:
        for lang in ("en", "bn"):
            use_lang(client, lang)
            r = client.get(url)
            assert r.status_code == 200, (url, lang)
            html = r.data.decode()
            assert f'<html lang="{lang}"' in html and "<h1" in html and 'class="skip-link"' in html, (url, lang)


def test_navigation_links_all_work(client):
    html = client.get("/").data.decode()
    nav = html.split('id="site-nav"')[1].split("</nav>")[0]
    hrefs = re.findall(r'href="([^"]+)"', nav)
    assert len(hrefs) == 6
    for href in hrefs:
        r = client.get(href)
        assert r.status_code in (200, 302), href
    footer = html.split('class="site-footer"')[1]
    for href in re.findall(r'href="(/[^"#]*)', footer):
        assert client.get(href).status_code in (200, 302), href


def test_bangla_is_the_default_outside_tests():
    from config import BaseConfig, DevelopmentConfig, ProductionConfig

    assert BaseConfig.DEFAULT_LANGUAGE == DevelopmentConfig.DEFAULT_LANGUAGE == ProductionConfig.DEFAULT_LANGUAGE == "bn"


def test_home_page_bangla_copy_and_three_actions(client):
    use_lang(client, "bn")
    html = client.get("/").data.decode()
    assert '<html lang="bn"' in html
    for text in ("আপনার কথা শুনতে আমরা আছি।", "সাহায্য চাই", "অভিযোগ জানান", "কারও সঙ্গে কথা বলুন", "মানুষ মানুষের পাশে।", "৯৯৯"):
        assert text in html, text
    assert html.count('class="action"') == 3


def test_translations_are_complete(app):
    cat = load_translations()
    assert [k for k in cat["en"] if k not in cat["bn"]] == []
    assert [k for k in cat["bn"] if k not in cat["en"]] == []
    identical = [
        k for k in cat["en"] if cat["en"][k] == cat["bn"][k] and len(cat["en"][k]) > 14 and not k.startswith(("channel.", "site."))
    ]
    assert identical == [], identical


def test_every_template_key_exists(app):
    cat = load_translations()["en"]
    bad = []
    for path in (pathlib.Path(app.root_path) / "templates").rglob("*.html"):
        for key in re.findall(r"""(?<![\w.])t\(\s*['"]([a-z0-9_.]+)['"]\s*[,)]""", path.read_text()):
            if key not in cat:
                bad.append((path.name, key))
    assert bad == []


def test_dynamic_keys_used_by_the_report_flow_exist(app):
    cat = load_translations()
    from app.permissions import CATEGORIES
    from app.services.status import PUBLIC_STATES

    needed = [f"category.{c}" for c in CATEGORIES] + [f"category.{c}_desc" for c in CATEGORIES]
    needed += (
        [f"pstatus.{s}" for s in PUBLIC_STATES] + [f"pstatus_help.{s}" for s in PUBLIC_STATES] + [f"track.next_{s}" for s in PUBLIC_STATES]
    )
    needed += [f"step.{n}.{part}" for n in range(1, 7) for part in ("title", "question")]
    needed += [f"step.2.{k}" for k in ("yes", "unsure", "no")] + [
        f"step.4.contact.{k}" for k in ("tracking_page", "phone", "email", "none")
    ]
    for lang in ("en", "bn"):
        missing = [k for k in needed if k not in cat[lang]]
        assert missing == [], (lang, missing)


def test_palette_meets_wcag_contrast():
    def lum(hex_colour):
        rgb = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

    def ratio(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    css = (pathlib.Path(__file__).resolve().parent.parent / "app/static/css/app.css").read_text()
    tokens = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6});", css))
    text_pairs = [
        ("text", "bg"),
        ("text-2", "bg"),
        ("text-2", "surface"),
        ("text-2", "coral"),
        ("primary", "surface"),
        ("primary", "bg"),
        ("primary-ink", "primary"),
        ("teal-ink", "teal"),
        ("coral-ink", "coral"),
        ("primary", "coral"),
    ]
    for fg, bg in text_pairs:
        assert ratio(tokens[fg], tokens[bg]) >= 4.5, (fg, bg, ratio(tokens[fg], tokens[bg]))
    assert ratio(tokens["border-strong"], tokens["surface"]) >= 3.0  # control boundaries (WCAG 1.4.11)


def test_helplines_are_sourced_and_unconfirmed_numbers_absent(client):
    assert {h["number"] for h in NATIONAL} == {"999", "109"}
    assert all(h["source"].startswith("https://") for h in NATIONAL)
    html = client.get("/").data.decode()
    assert 'href="tel:999"' in html and 'href="tel:109"' in html and "1098" not in html
    assert "does not call emergency services" in html


def test_support_is_shown_closed_when_no_one_is_present(client):
    html = client.get("/").data.decode()
    assert "No one is available right now" in html and "A person is available" not in html
    html = client.get("/help").data.decode()
    assert 'action="/support/start"' not in html


def test_public_pages_never_show_internal_workflow_words(client):
    for url in PUBLIC_PAGES:
        html = client.get(url).data.decode()
        main = html.split('id="main"')[1].split("</main>")[0]
        for word in ("Triage", "Specialist review", "severity", "Level 4"):
            assert word not in main, (url, word)


def test_legacy_paths_redirect(client):
    pairs = (
        ("/submit", "/report/new"),
        ("/login", "/auth/login"),
        ("/dashboard", "/workspace/"),
        ("/get-help", "/help"),
        ("/live-support", "/help"),
        ("/report-wrongdoing", "/report/new"),
        ("/legal-help", "/safety"),
        ("/digital-safety", "/safety"),
        ("/safeguarding", "/about"),
        ("/awareness", "/stories"),
        ("/investigations", "/stories"),
        ("/corrections", "/stories"),
        ("/complaints", "/contact"),
        ("/accessibility", "/contact"),
        ("/editorial-policy", "/about"),
    )
    for old, new in pairs:
        r = client.get(old)
        assert r.status_code == 301 and r.headers["Location"].endswith(new), old
    assert client.get("/case/1").status_code == 404


def test_error_pages_offline_assets_and_svg_art(client):
    assert b"Page not found" in client.get("/does-not-exist").data
    login(client, "reporter")
    r = client.get("/workspace/")
    assert r.status_code == 403 and b"need-to-know" in r.data
    assert client.get("/offline").status_code == 200
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and b"/workspace" in sw.data and b"/report" in sw.data
    for name in (
        "support-hands",
        "two-talking",
        "private-report",
        "privacy-shield",
        "calm-empty",
        "report-received",
        "agent-support",
        "safety-guidance",
    ):
        r = client.get(f"/static/art/{name}.svg")
        assert r.status_code == 200 and b"<title" in r.data and len(r.data) < 4000, name


def test_quick_exit_clears_private_session(client):
    case, secret = make_case()
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    client.post("/report/1", data={"category": "other"})
    r = client.post("/quick-exit")
    assert r.status_code == 303 and "google.com" in r.headers["Location"]
    assert client.get(f"/track/{case.reference}").status_code == 403
    assert b'value="other" checked' not in client.get("/report/1").data


def test_identity_never_leaks_to_public_surfaces(client):
    case, secret = make_case(
        submission_type="confidential",
        identity_name="Leak Test Name",
        identity_phone="01733333333",
        identity_email="leak@example.org",
        consent_publication=True,
    )
    needles = (b"Leak Test Name", b"01733333333", b"leak@example.org")
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    for url in ("/", "/stories", "/help", f"/track/{case.reference}", "/healthz", "/support/status", "/sw.js"):
        data = client.get(url).data
        for n in needles:
            assert n not in data, (url, n)
    login(client, "admin")
    data = client.get("/workspace/admin/audit?sensitive=1").data
    assert not any(n in data for n in needles)
    row = {c.name: getattr(case, c.name) for c in Case.__table__.columns}
    assert not any(isinstance(v, str) and ("Leak Test" in v or "01733333333" in v) for v in row.values())


def test_app_logs_do_not_contain_narratives(app, caplog):
    import logging

    caplog.set_level(logging.INFO)
    make_case(narrative="UNIQUE-NARRATIVE-TOKEN-XYZ that must not be logged anywhere at all.")
    assert "UNIQUE-NARRATIVE-TOKEN-XYZ" not in caplog.text


def test_forms_have_labels_for_every_visible_field(client):
    for url in ("/report/3", "/report/4", "/track/", "/requests/new", "/auth/login"):
        html = client.get(url).data.decode()
        main = html.split('id="main"')[1]
        for field_id in re.findall(r'<(?:input|textarea|select)[^>]*\bid="([^"]+)"', main):
            tag = re.search(rf'<(?:input|textarea|select)[^>]*\bid="{re.escape(field_id)}"[^>]*>', main).group(0)
            if 'type="hidden"' in tag:
                continue
            assert f'for="{field_id}"' in main, (url, field_id)


def test_env_example_has_no_real_secrets():
    text = (pathlib.Path(__file__).resolve().parent.parent / ".env.example").read_text()
    assert "IDENTITY_ENCRYPTION_KEY=\n" in text and "change-me" in text
    assert json.dumps(text).count("gho_") == 0
