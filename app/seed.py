from app import db
from app.models.user import User
from app.models.complaint import Complaint, Action

def seed_data():
    admin = User(email='admin@helplagbe.local', name='Admin User', role='admin')
    admin.set_password('admin123')
    support = User(email='support@helplagbe.local', name='Support Staff', role='support')
    support.set_password('support123')
    legal = User(email='legal@helplagbe.local', name='Legal Advisor', role='legal')
    legal.set_password('legal123')
    cyber = User(email='cyber@helplagbe.local', name='Cyber Specialist', role='cyber')
    cyber.set_password('cyber123')
    editor = User(email='editor@helplagbe.local', name='Editor', role='editor')
    editor.set_password('editor123')
    user = User(email='user@helplagbe.local', name='Demo User', role='user')
    user.set_password('user123')

    db.session.add_all([admin, support, legal, cyber, editor, user])
    db.session.commit()

    c1 = Complaint(
        title='Request for emergency shelter assistance',
        description='Family displaced due to flooding needs temporary shelter and food support. No personal identifiers included in public view.',
        category='human_support',
        severity='high',
        is_anonymous=True,
        status='under_review'
    )
    c2 = Complaint(
        title='Suspected online harassment case',
        description='Reports of coordinated online abuse. Technical details for cyber team only.',
        category='cyber',
        severity='medium',
        is_anonymous=True,
        status='investigating'
    )
    db.session.add_all([c1, c2])
    db.session.commit()

    act = Action(complaint_id=c1.id, actor_id=support.id, action_type='note', notes='Initial assessment completed. Severity set to high. Awaiting legal clearance for any public statement.')
    db.session.add(act)
    db.session.commit()
