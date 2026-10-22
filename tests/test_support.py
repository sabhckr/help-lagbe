"""Live human support: truthful availability, presence, private conversations, escalation."""

from datetime import timedelta

from app import db
from app.models import AgentPresence, AuditEvent, SupportConversation
from app.models.base import utcnow
from app.services import support as svc
from tests.conftest import login, user_by_role


def test_closed_when_no_agent_is_present(client):
    r = client.get("/support/status")
    assert r.get_json() == {"open": False, "agents_online": 0, "waiting": 0, "service_enabled": True}
    r = client.get("/live-support")
    assert b"No agent is available" in r.data and b"start-chat" not in r.data
    r = client.post("/support/start", data={"topic": "other", "consent": "y"})
    assert r.status_code == 302 and SupportConversation.query.count() == 0


def test_presence_makes_chat_open_and_times_out(client, app):
    agent = user_by_role("support")
    svc.set_presence(agent, "available")
    assert client.get("/support/status").get_json()["open"] is True
    presence = AgentPresence.query.filter_by(user_id=agent.id).one()
    presence.last_seen_at = utcnow() - timedelta(seconds=app.config["SUPPORT_PRESENCE_TIMEOUT_SECONDS"] + 5)
    db.session.commit()
    assert client.get("/support/status").get_json()["open"] is False


def test_service_disabled_by_admin_is_closed_even_with_agents(client):
    from app.models import DepartmentConfig

    cfg = DepartmentConfig.query.filter_by(department="support").one()
    cfg.is_staffed = False
    db.session.commit()
    svc.set_presence(user_by_role("support"), "available")
    assert client.get("/support/status").get_json()["open"] is False


def test_visitor_conversation_flow_and_isolation(client, app):
    svc.set_presence(user_by_role("support"), "available")
    r = client.post("/support/start", data={"topic": "safety", "immediate_danger": "y", "consent": "y"})
    assert r.status_code == 302
    conv = SupportConversation.query.one()
    assert conv.status == "waiting" and conv.safety_flag
    r = client.get(f"/support/chat/{conv.reference}")
    assert r.status_code == 200
    r = client.post(f"/support/chat/{conv.reference}/send", json={"body": "hello, I need help"})
    assert r.status_code == 200
    r = client.get(f"/support/chat/{conv.reference}/messages?after=0")
    assert r.get_json()["status"] == "waiting" and any(m["body"] == "hello, I need help" for m in r.get_json()["messages"])
    # another visitor cannot read it
    other = app.test_client()
    assert other.get(f"/support/chat/{conv.reference}").status_code == 403
    assert other.get(f"/support/chat/{conv.reference}/messages").status_code == 403
    # leaving closes and clears
    r = client.post(f"/support/chat/{conv.reference}/leave")
    assert r.status_code == 200 and SupportConversation.query.one().status == "closed"
    assert client.get(f"/support/chat/{conv.reference}").status_code == 403


def test_agent_accept_reply_escalate_and_supervisor_logging(client, app):
    agent = user_by_role("support")
    svc.set_presence(agent, "available")
    conv, token = svc.start_conversation(language="en", topic="safety", safety_flag=False)
    login(client, "support")
    r = client.get("/workspace/support")
    assert r.status_code == 200 and conv.reference.encode() in r.data
    r = client.post(f"/workspace/support/conversations/{conv.reference}/accept", data={})
    assert r.status_code == 302 and conv.status == "active" and conv.agent_id == agent.id
    assert AgentPresence.query.filter_by(user_id=agent.id).one().status == "busy"
    r = client.post(f"/workspace/support/conversations/{conv.reference}/send", json={"body": "Hello, I am here with you."})
    assert r.status_code == 200
    r = client.post(
        f"/workspace/support/conversations/{conv.reference}/escalate", data={"reason": "Visitor describes a threat to their life tonight."}
    )
    assert r.status_code == 302 and conv.escalated_to_id == user_by_role("supervisor").id and conv.safety_flag
    client.post("/auth/logout")
    # a second support agent cannot read an active conversation they are not part of
    from app.models import User

    other_agent = User.query.filter_by(email="support2@helplagbe.local").one()
    import pyotp

    from tests.conftest import TOTP_SECRET, enrol_mfa

    enrol_mfa(other_agent)
    client.post("/auth/login", data={"email": other_agent.email, "password": "demo-password-2026"})
    client.post("/auth/mfa/verify", data={"code": pyotp.TOTP(TOTP_SECRET).now()})
    assert client.get(f"/workspace/support/conversations/{conv.reference}").status_code == 403
    assert client.post(f"/workspace/support/conversations/{conv.reference}/send", json={"body": "intruding"}).status_code == 400
    client.post("/auth/logout")
    # the escalated conversation is open to the supervisor directly (they were escalated to)
    login(client, "supervisor")
    assert b"Hello, I am here" in client.get(f"/workspace/support/conversations/{conv.reference}").data
    # a conversation the supervisor is NOT part of needs a written reason, which is logged
    svc.set_presence(agent, "available")
    conv2, _ = svc.start_conversation(language="en", topic="other", safety_flag=False)
    svc.accept(conv2, agent)
    svc.agent_message(conv2, agent, "Second conversation text")
    r = client.get(f"/workspace/support/conversations/{conv2.reference}")
    assert r.status_code == 200 and b"Second conversation text" not in r.data and b"reason" in r.data.lower()
    r = client.get(f"/workspace/support/conversations/{conv2.reference}?reason=Safeguarding review of a long-running chat")
    assert b"Second conversation text" in r.data
    assert AuditEvent.query.filter_by(event_type="support.supervisor_read").count() == 1


def test_admin_cannot_read_support_conversations(client):
    svc.set_presence(user_by_role("support"), "available")
    conv, _ = svc.start_conversation(language="bn", topic="other", safety_flag=False)
    login(client, "admin")
    assert client.get("/workspace/support").status_code == 403
    assert client.get(f"/workspace/support/conversations/{conv.reference}").status_code == 403


def test_follow_up_requires_consent_record(client):
    agent = user_by_role("support")
    svc.set_presence(agent, "available")
    conv, _ = svc.start_conversation(language="en", topic="other", safety_flag=False)
    svc.accept(conv, agent)
    svc.set_follow_up(conv, agent, True, "Call back Tuesday 11:00 on the number given in chat")
    assert conv.consent_follow_up and "Tuesday" in conv.follow_up_note
    svc.set_follow_up(conv, agent, False, "ignored")
    assert conv.follow_up_note is None


def test_abandoned_conversations_expire(app):
    svc.set_presence(user_by_role("support"), "available")
    conv, _ = svc.start_conversation(language="en", topic="other", safety_flag=False)
    conv.last_visitor_seen_at = utcnow() - timedelta(minutes=45)
    db.session.commit()
    assert svc.expire_abandoned() == 1 and conv.status == "closed" and conv.closed_by == "system"
