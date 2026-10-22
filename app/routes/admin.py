from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.complaint import Complaint, Action, AccessLog

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/editorial')
@login_required
def editorial():
    if not current_user.has_role('editor', 'admin'):
        return 'Unauthorized', 403
    pending = Complaint.query.filter_by(public_published=False).filter(Complaint.status.in_(['investigating', 'resolved'])).all()
    return render_template('admin/editorial.html', complaints=pending)

@admin_bp.route('/editorial/<int:id>/approve', methods=['POST'])
@login_required
def approve_publication(id):
    if not current_user.has_role('editor', 'admin'):
        return 'Unauthorized', 403
    complaint = Complaint.query.get_or_404(id)
    public_summary = request.form.get('public_summary')
    complaint.public_summary = public_summary
    complaint.public_published = True
    complaint.status = 'published'
    action = Action(complaint_id=id, actor_id=current_user.id, action_type='editorial_approve', notes='Approved for public publication. Summary redacted of all identities.')
    db.session.add(action)
    db.session.commit()
    flash('Publication approved. Identities remain protected.', 'success')
    return redirect(url_for('admin.editorial'))

@admin_bp.route('/social/<int:id>')
@login_required
def social_draft(id):
    if not current_user.has_role('editor', 'admin'):
        return 'Unauthorized', 403
    complaint = Complaint.query.get_or_404(id)
    if not complaint.public_published:
        flash('Only published cases can have social drafts prepared', 'error')
        return redirect(url_for('admin.editorial'))
    draft = f"Help Lagbe? public report ({complaint.public_id}): {complaint.title}. Severity: {complaint.severity}. Full details on platform. Identities protected. #HelpLagbe #Accountability"
    return render_template('admin/social.html', complaint=complaint, draft=draft)

@admin_bp.route('/logs')
@login_required
def access_logs():
    if not current_user.has_role('admin'):
        return 'Unauthorized', 403
    logs = AccessLog.query.order_by(AccessLog.timestamp.desc()).limit(50).all()
    return render_template('admin/logs.html', logs=logs)
