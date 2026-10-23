"""Fictional demo data for local development. Never runs in production.

Every person, place and institution here is invented. Staff passwords are the same demo
password so a developer can try each workspace; MFA enrolment is forced at first login.
"""

from __future__ import annotations

from datetime import timedelta

from app import permissions as P
from app.extensions import db
from app.models.base import utcnow
from app.models.case import CaseNote, CaseUpdate, SeverityAssessment, StatusChange
from app.models.publication import (
    LABEL_ALLEGATION,
    LABEL_AWARENESS,
    STAGE_PUBLISHED,
    STAGE_REDACTION,
    Correction,
    Publication,
    PublicationReview,
)
from app.models.settings import DepartmentConfig, EmergencyContact, SiteSetting
from app.models.user import User
from app.services import cases as case_service

DEMO_PASSWORD = "demo-password-2026"  # nosec B105  # fictional local demo accounts, never seeded in production

DEMO_STAFF = (
    ("admin@helplagbe.local", "Farzana Admin (fictional)", P.ROLE_ADMIN),
    ("supervisor@helplagbe.local", "Tanvir Supervisor (fictional)", P.ROLE_SUPERVISOR),
    ("support@helplagbe.local", "Nusrat Support (fictional)", P.ROLE_SUPPORT),
    ("support2@helplagbe.local", "Rafi Support (fictional)", P.ROLE_SUPPORT),
    ("legal@helplagbe.local", "Adv. Mahmud Legal (fictional)", P.ROLE_LEGAL),
    ("cyber@helplagbe.local", "Sabbir Cyber (fictional)", P.ROLE_CYBER),
    ("editor@helplagbe.local", "Shirin Editorial (fictional)", P.ROLE_EDITORIAL),
    ("editor2@helplagbe.local", "Imran Editorial (fictional)", P.ROLE_EDITORIAL),
    ("action@helplagbe.local", "Lubna Action (fictional)", P.ROLE_ACTION),
    ("moderator@helplagbe.local", "Kamal Moderator (fictional)", P.ROLE_MODERATOR),
    ("user@helplagbe.local", "Demo Reporter (fictional)", P.ROLE_REPORTER),
)


def seed_demo() -> None:
    users: dict[str, User] = {}
    for email, name, role in DEMO_STAFF:
        user = User(email=email, name=name, role=role, must_change_password=False)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        users[role if role not in users else email] = user
    db.session.commit()
    editor2 = User.query.filter_by(email="editor2@helplagbe.local").one()

    # Departments: only Human Support is marked staffed in the demo; the others accept cases
    # but are shown truthfully as "not currently staffed for live response".
    for dept in P.DEPARTMENTS:
        db.session.add(
            DepartmentConfig(
                department=dept,
                is_staffed=(dept == P.DEPT_SUPPORT),
                accepts_cases=True,
                hours_en="Saturday–Thursday, 10:00–18:00 (Dhaka time)" if dept == P.DEPT_SUPPORT else None,
                hours_bn="শনিবার–বৃহস্পতিবার, সকাল ১০টা–সন্ধ্যা ৬টা (ঢাকা সময়)" if dept == P.DEPT_SUPPORT else None,
            )
        )
    contacts = (
        ("emergency", "National Emergency Service", "জাতীয় জরুরি সেবা", "999", "Police, fire and ambulance. Verify before relying on it."),
        (
            "women_children",
            "Violence Against Women and Children helpline",
            "নারী ও শিশু নির্যাতন প্রতিরোধ হেল্পলাইন",
            "109",
            "Government helpline for violence against women and children.",
        ),
        ("child", "Child Helpline", "শিশু হেল্পলাইন", "1098", "Helpline for children in need of protection."),
        ("legal_aid", "National Legal Aid helpline", "জাতীয় আইনগত সহায়তা হেল্পলাইন", "16430", "Government legal aid information line."),
    )
    for i, (kind, en, bn, number, desc) in enumerate(contacts):
        db.session.add(
            EmergencyContact(
                kind=kind, name_en=en, name_bn=bn, number=number, description_en=desc, verified=False, is_active=True, sort_order=i
            )
        )
    db.session.add(SiteSetting(key="public_registration", value="1"))
    db.session.add(SiteSetting(key="mfa_required", value="1"))
    db.session.commit()

    # ---- Cases (all fictional) ----
    c1, _ = case_service.create_case(
        {
            "category": "harassment",
            "title": "Repeated harassment near a college gate in a fictional town",
            "narrative": "A group of young men gather at the college gate most afternoons and shout comments at students. "
            "It has happened for three weeks. We would like advice on what can be done and who can help. "
            "No one has been physically hurt so far but students are afraid to walk alone.",
            "approximate_time": "Weekday afternoons, past three weeks",
            "location_text": "Fictional college gate, Example Upazila",
            "immediate_danger": "no",
            "submission_type": "anonymous",
            "consent_process": True,
            "consent_publication": True,
        },
        language="bn",
    )
    c2, _ = case_service.create_case(
        {
            "category": "threats_blackmail",
            "title": "Threats to share private photos unless money is paid",
            "narrative": "Someone I met online is threatening to send private pictures to my family unless I pay them. "
            "They message me every day from new accounts. I am scared and do not know what to do first.",
            "approximate_time": "Started about ten days ago",
            "immediate_danger": "unsure",
            "submission_type": "confidential",
            "identity_name": "Fictional Reporter B",
            "identity_phone": "01700000000",
            "contact_preference": "phone",
            "safe_contact_notes": "Only call between 11:00 and 14:00. Never leave voicemail.",
            "do_not_contact": "Do not contact my family.",
            "consent_process": True,
            "consent_contact": True,
        }
    )
    c3, _ = case_service.create_case(
        {
            "category": "corruption_exploitation",
            "title": "Fees demanded for a free public service at a fictional office",
            "narrative": "At a local office, staff ask for 'speed money' before issuing a certificate that should be free. "
            "I have a receipt-less payment and a recording of the conversation. Several neighbours report the same.",
            "approximate_time": "Last month",
            "location_text": "Fictional service office",
            "immediate_danger": "no",
            "submission_type": "anonymous",
            "consent_process": True,
            "consent_publication": True,
        }
    )
    c4, _ = case_service.create_case(
        {
            "category": "abuse_violence",
            "title": "Need help leaving a violent household safely",
            "narrative": "I am being hit regularly and I am worried for my child. I cannot call from home. I need to understand "
            "where we can go and whether there is legal help. Please do not contact my husband or his family.",
            "immediate_danger": "yes",
            "child_involved": True,
            "submission_type": "confidential",
            "identity_name": "Fictional Reporter D",
            "identity_email": "reporter-d@example.invalid",
            "contact_preference": "email",
            "safe_contact_notes": "Email only; I check it at work.",
            "do_not_contact": "Husband, in-laws.",
            "consent_process": True,
            "consent_contact": True,
        }
    )
    c5, _ = case_service.create_case(
        {
            "category": "online_harm",
            "title": "Facebook account hijacked and used to message contacts",
            "narrative": "My account was taken over two days ago. The attacker changed the email and is asking my contacts for money. "
            "I still have the phone number attached. I need help recovering it and warning people.",
            "immediate_danger": "no",
            "submission_type": "anonymous",
            "consent_process": True,
        }
    )
    c6, _ = case_service.create_case(
        {
            "category": "corruption_exploitation",
            "title": "Allocation of relief supplies diverted in a fictional union",
            "narrative": "Relief goods meant for flood-affected households were reportedly distributed to relatives of an official. "
            "There are lists and photographs. Several families who were on the list received nothing.",
            "immediate_danger": "no",
            "submission_type": "anonymous",
            "consent_process": True,
            "consent_publication": True,
        }
    )

    supervisor = users[P.ROLE_SUPERVISOR]
    support = users[P.ROLE_SUPPORT]
    legal = users[P.ROLE_LEGAL]
    cyber = users[P.ROLE_CYBER]
    editor = users[P.ROLE_EDITORIAL]
    action = users[P.ROLE_ACTION]

    case_service.assess_severity(
        c1,
        supervisor,
        2,
        "Ongoing harassment affecting several students; no physical violence reported; needs timely review and a referral to the institution.",
    )
    case_service.assign(c1, supervisor, support)
    case_service.change_status(
        c1, support, "under_review", "Reviewing with the reporter via the tracking page before contacting the college."
    )
    case_service.add_reporter_update(
        c1,
        support,
        "Thank you for your report. A support worker has been assigned. We will suggest safe next steps here within two working days.",
    )

    case_service.assess_severity(
        c2, supervisor, 3, "Coercive blackmail with daily threats and new accounts; credible risk of image-based abuse. High concern."
    )
    case_service.assign(c2, supervisor, support, "support")
    case_service.assign(c2, supervisor, cyber, "cyber")
    case_service.add_note(
        c2,
        cyber,
        "Preserve screenshots with timestamps; advise reporter not to pay; prepare platform reporting steps.",
        note_type="cyber_review",
    )

    case_service.assess_severity(
        c3,
        editor,
        1,
        "Allegation of petty bribery with possible recording; no personal safety element; routine review and source assessment.",
    )
    case_service.assign(c3, editor, editor, "editorial")

    case_service.assess_severity(
        c4,
        supervisor,
        4,
        "Reporter states immediate danger and a child is involved. Critical: safeguarding protocol, shelter options and legal aid referral today.",
    )
    case_service.assign(c4, supervisor, support, "support")
    case_service.assign(c4, supervisor, legal, "legal")
    case_service.change_status(c4, supervisor, "under_review", "Safeguarding lead reviewing shelter and legal options before any contact.")
    case_service.add_referral(
        c4,
        legal,
        {
            "referral_type": "legal_aid",
            "organisation": "Fictional District Legal Aid Office",
            "consent_obtained": True,
            "notes": "Reporter consented via tracking page.",
        },
    )
    case_service.add_note(
        c4, legal, "Protection order pathway possible; needs reporter instructions. Do not contact spouse.", visibility="legal_privileged"
    )

    case_service.assess_severity(
        c5, cyber, 2, "Active account takeover being used for fraud against contacts; time-sensitive recovery but no physical risk."
    )
    case_service.assign(c5, cyber, cyber, "cyber")

    case_service.assess_severity(
        c6,
        editor,
        2,
        "Public-interest allegation with documents; requires source verification and right of response before any publication.",
    )
    case_service.assign(c6, editor, editor, "editorial")
    case_service.assign(c6, editor, action, "action")

    # ---- Publications ----
    awareness = Publication(
        case_id=None,
        slug="recognising-online-blackmail-and-what-to-do-first",
        kind="awareness",
        label=LABEL_AWARENESS,
        headline="Recognising online blackmail, and what to do first",
        headline_bn="অনলাইন ব্ল্যাকমেইল চেনা এবং প্রথমে কী করবেন",
        body_redacted=(
            "If someone threatens to share private images or messages unless you pay, you are not alone and it is not your fault. "
            "Do not pay: paying rarely ends the demands. Do not delete anything yet: screenshots with dates and account names are evidence. "
            "Stop replying, block the account, and report it to the platform. If you are under 18, tell a trusted adult or a child helpline. "
            "Help Lagbe? support workers can walk you through platform reporting and legal options; see Get Help."
        ),
        body_redacted_bn=(
            "কেউ যদি টাকা না দিলে আপনার ব্যক্তিগত ছবি বা বার্তা ছড়িয়ে দেওয়ার হুমকি দেয়, আপনি একা নন এবং এতে আপনার কোনো দোষ নেই। "
            "টাকা দেবেন না: টাকা দিলে সাধারণত দাবি থামে না। এখনই কিছু মুছবেন না: তারিখ ও অ্যাকাউন্টের নামসহ স্ক্রিনশট প্রমাণ হিসেবে কাজে লাগে। "
            "উত্তর দেওয়া বন্ধ করুন, অ্যাকাউন্টটি ব্লক করুন এবং প্ল্যাটফর্মে রিপোর্ট করুন। আপনার বয়স ১৮-এর নিচে হলে বিশ্বস্ত কোনো প্রাপ্তবয়স্ককে বা শিশু হেল্পলাইনে জানান। "
            "হেল্প লাগবে?-এর সহায়তাকর্মীরা প্ল্যাটফর্মে রিপোর্ট করা ও আইনি বিকল্প বুঝতে আপনাকে সাহায্য করতে পারেন; ‘সাহায্য নিন’ পাতা দেখুন।"
        ),
        stage=STAGE_PUBLISHED,
        consent_verified=True,
        safety_reviewed=True,
        source_reviewed=True,
        redaction_done=True,
        conflict_of_interest_checked=True,
        editorial_approved=True,
        legal_review_required=False,
        legal_reviewed=False,
        right_of_response_offered=False,
        drafted_by_id=editor.id,
        approved_by_id=editor2.id,
        published_by_id=editor.id,
        published_at=utcnow() - timedelta(days=3),
    )
    db.session.add(awareness)
    db.session.flush()
    db.session.add(
        PublicationReview(
            publication_id=awareness.id,
            reviewer_id=editor2.id,
            stage="editorial_review",
            decision="approve",
            notes="Awareness material, no case identifiers, plain language.",
        )
    )
    db.session.add(
        Correction(
            publication_id=awareness.id,
            author_id=editor.id,
            kind="clarification",
            text="Clarified that platform reporting steps differ by service; added a note for readers under 18.",
            text_bn="স্পষ্ট করা হয়েছে যে প্ল্যাটফর্মভেদে রিপোর্ট করার ধাপ ভিন্ন; ১৮-এর নিচের পাঠকদের জন্য একটি নোট যোগ করা হয়েছে।",
        )
    )

    story = Publication(
        case_id=c3.id,
        slug="fees-demanded-for-a-free-certificate-draft",
        kind="story",
        label=LABEL_ALLEGATION,
        headline="Residents report being asked for 'speed money' for a free certificate",
        body_redacted=(
            "Several residents of a fictional area told Help Lagbe? that staff at a local office asked for unofficial payments "
            "before issuing a certificate that is free by law. One resident provided an audio recording. These are reported "
            "allegations; the office has been offered a right of response and no official finding has been made."
        ),
        stage=STAGE_REDACTION,
        consent_verified=True,
        safety_reviewed=True,
        source_reviewed=True,
        conflict_of_interest_checked=True,
        right_of_response_offered=True,
        drafted_by_id=editor.id,
        legal_review_required=True,
    )
    db.session.add(story)
    db.session.flush()
    db.session.add(
        PublicationReview(
            publication_id=story.id,
            reviewer_id=supervisor.id,
            stage="consent_safety_review",
            decision="approve",
            notes="Reporter consented to redacted publication; no safety concern identified.",
        )
    )
    db.session.add(
        PublicationReview(
            publication_id=story.id,
            reviewer_id=editor2.id,
            stage="source_assessment",
            decision="approve",
            notes="Recording reviewed; two further residents corroborate; right of response sent.",
        )
    )
    db.session.commit()


def _unused(*_args):  # keep imports referenced for static analysis
    return CaseNote, CaseUpdate, SeverityAssessment, StatusChange
