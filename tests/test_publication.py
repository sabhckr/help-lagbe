"""Gated publication: consent, safety, source, redaction, two-person rule, legal review, corrections, social."""

import pytest

from app.models import Publication, SocialDraft
from app.services import publication as pub_svc
from app.services.publication import PublicationError
from app.services.redaction import REDACTION_CHECKLIST, scan_for_identifiers
from tests.conftest import case_by_text, login, make_case, user_by_role

CLEAN = "Residents of a fictional area report being asked for unofficial payments for a certificate that is free by law. These are reported allegations."
ALL_OK = {k: True for k in REDACTION_CHECKLIST}


def _draft(case=None, body=CLEAN, kind="story"):
    return pub_svc.create_draft(
        user_by_role("editorial"),
        {
            "kind": kind,
            "label": "reported_allegation" if kind == "story" else "awareness_material",
            "headline": "Residents report unofficial payments",
            "body": body,
        },
        case=case,
    )


def test_draft_from_case_requires_consent(app):
    no_consent, _ = make_case(consent_publication=False)
    with pytest.raises(PublicationError):
        _draft(no_consent)
    consented, _ = make_case(consent_publication=True)
    assert _draft(consented).stage == "draft"


def test_identifier_scanner(app):
    assert {f.kind for f in scan_for_identifiers("call 01712345678 or mail a@b.com see https://x.y @handle NID 1234567890123")} >= {
        "phone",
        "email",
        "url",
        "handle",
        "nid",
    }
    assert scan_for_identifiers(CLEAN) == []
    assert any(f.kind == "bn_phone" for f in scan_for_identifiers("ফোন ০১৭১২৩৪৫৬৭৮"))


def test_full_pipeline_with_two_person_rule_and_gates(app):
    case = case_by_text("speed money")
    editor, editor2, sup, legal = user_by_role("editorial"), None, user_by_role("supervisor"), user_by_role("legal")
    from app.models import User

    editor2 = User.query.filter_by(email="editor2@helplagbe.local").one()
    pub = _draft(case)
    with pytest.raises(PublicationError):
        pub_svc.publish(pub, editor)  # gates not passed
    pub_svc.submit_for_review(pub, editor)
    assert pub.stage == "consent_safety_review"
    with pytest.raises(PublicationError):
        pub_svc.consent_safety_review(pub, editor, "approve", "Editorial has no safety-review permission.")
    pub_svc.consent_safety_review(pub, sup, "approve", "Reporter consented; no safety concern.")
    assert pub.stage == "source_assessment" and pub.consent_verified and pub.safety_reviewed
    with pytest.raises(PublicationError):  # drafter cannot assess own sources
        pub_svc.source_review(pub, editor, "approve", "Looks fine to me honestly.", conflict_checked=True, right_of_response=True)
    with pytest.raises(PublicationError):  # right of response required
        pub_svc.source_review(pub, editor2, "approve", "Two sources corroborate.", conflict_checked=True, right_of_response=False)
    pub_svc.source_review(
        pub, editor2, "approve", "Two sources corroborate; office offered a response.", conflict_checked=True, right_of_response=True
    )
    assert pub.stage == "redaction"
    # redaction fails on identifiers
    pub.body_redacted = CLEAN + " Contact 01712345678."
    problems = pub_svc.redaction_check(pub, editor, ALL_OK, "Checked every item carefully.")
    assert problems and pub.stage == "redaction"
    pub.body_redacted = CLEAN
    missing = pub_svc.redaction_check(pub, editor, {**ALL_OK, "no_names": False}, "Checked every item carefully.")
    assert missing and pub.stage == "redaction"
    assert pub_svc.redaction_check(pub, editor, ALL_OK, "Checked every item carefully.") == []
    assert pub.stage == "editorial_review"
    with pytest.raises(PublicationError):
        pub_svc.editorial_review(pub, editor, "approve", "Approving my own draft.")
    pub_svc.editorial_review(pub, editor2, "approve", "Accurate, labelled as allegation, redacted.")
    assert pub.stage == "legal_review"
    with pytest.raises(PublicationError):
        pub_svc.publish(pub, editor)
    pub_svc.legal_review(pub, legal, "approve", "No defamation risk given the allegation wording.")
    assert pub.stage == "approved" and pub.ready_to_publish()
    pub_svc.publish(pub, editor)
    assert pub.is_public and pub.published_by_id == editor.id
    with pytest.raises(PublicationError):
        pub_svc.update_draft(pub, editor, {"headline": "edit after publish", "body": CLEAN})


def test_edit_after_gate_resets_signoffs(app):
    case = case_by_text("speed money")
    pub = Publication.query.filter_by(case_id=case.id).one()  # seeded at redaction stage
    pub.redaction_done = True
    pub.editorial_approved = True
    pub.stage = "editorial_review"
    pub_svc.update_draft(pub, user_by_role("editorial"), {"headline": pub.headline, "body": CLEAN})
    assert pub.stage == "redaction" and not pub.redaction_done and not pub.editorial_approved


def test_child_safety_cases_never_become_stories(app):
    case, _ = make_case(category="child_safety", consent_publication=True)
    pub = _draft(case)
    pub_svc.submit_for_review(pub, user_by_role("editorial"))
    with pytest.raises(PublicationError):
        pub_svc.consent_safety_review(pub, user_by_role("supervisor"), "approve", "Trying to approve a child-safety story.")


def test_awareness_material_skips_legal_but_still_needs_two_people(app):
    pub = _draft(None, kind="awareness")
    assert pub.legal_review_required is False
    editor = user_by_role("editorial")
    pub_svc.submit_for_review(pub, editor)
    pub_svc.consent_safety_review(pub, user_by_role("supervisor"), "approve", "No case, no consent needed.")
    from app.models import User

    editor2 = User.query.filter_by(email="editor2@helplagbe.local").one()
    pub_svc.source_review(pub, editor2, "approve", "Educational content checked.", conflict_checked=True, right_of_response=False)
    pub_svc.redaction_check(pub, editor, ALL_OK, "No identifiers in awareness text.")
    pub_svc.editorial_review(pub, editor2, "approve", "Good to publish as awareness.")
    assert pub.stage == "approved"


def test_public_site_only_shows_published_and_not_withdrawn(client):
    published = Publication.query.filter_by(stage="published").first()
    pending = Publication.query.filter_by(stage="redaction").first()
    assert client.get(f"/stories/{published.slug}").status_code == 200
    assert client.get(f"/stories/{pending.slug}").status_code == 404
    r = client.get("/stories")
    assert pending.headline.encode() not in r.data
    pub_svc.withdraw(published, user_by_role("editorial"), "Withdrawn pending a correction request.")
    assert client.get(f"/stories/{published.slug}").status_code == 404


def test_corrections_are_public_and_scanned(client):
    published = Publication.query.filter_by(stage="published").first()
    editor = user_by_role("editorial")
    with pytest.raises(PublicationError):
        pub_svc.add_correction(published, editor, "correction", "Reach the editor at editor@example.org for details.")
    pub_svc.add_correction(published, editor, "correction", "The original text misstated the platform name.")
    r = client.get(f"/stories/{published.slug}")
    assert b"misstated the platform name" in r.data
    assert b"misstated the platform name" in client.get("/stories").data


def test_social_drafts_never_auto_post_and_require_url_to_confirm(app):
    published = Publication.query.filter_by(stage="published").first()
    editor = user_by_role("editorial")
    from app.models import User

    editor2 = User.query.filter_by(email="editor2@helplagbe.local").one()
    draft = pub_svc.create_social_draft(
        published, editor, "facebook", "New awareness guide: recognising online blackmail and what to do first."
    )
    assert draft.status == "drafted"
    with pytest.raises(PublicationError):
        pub_svc.approve_social_draft(draft, editor)
    pub_svc.approve_social_draft(draft, editor2)
    with pytest.raises(PublicationError):
        pub_svc.confirm_posted(draft, editor, "posted it")
    pub_svc.confirm_posted(draft, editor, "https://www.facebook.com/example/posts/1")
    assert SocialDraft.query.one().status == "posted_confirmed" and draft.posted_confirmed_by_id == editor.id


def test_http_pipeline_permissions(client):
    pub = Publication.query.filter_by(stage="redaction").first()
    login(client, "support")
    r = client.post(
        f"/workspace/publications/{pub.id}/redaction", data={**{k: "y" for k in REDACTION_CHECKLIST}, "notes": "Support trying to redact."}
    )
    assert r.status_code == 403
    assert client.get(f"/workspace/publications/{pub.id}").status_code == 403
    client.post("/auth/logout")
    login(client, "editorial")
    assert client.get(f"/workspace/publications/{pub.id}").status_code == 200
    r = client.post(f"/workspace/publications/{pub.id}/publish", data={})
    assert r.status_code == 302 and Publication.query.get(pub.id).stage == "redaction"
