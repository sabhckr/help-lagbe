from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models.complaint import Complaint, Action, AccessLog

complaints_bp = Blueprint('complaints', __name__)

@complaints_bp.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        is_anonymous = request.form.get('anonymous') == 'on'
        complainant_id = current_user.id if current_user.is_authenticated and not is_anonymous else None

        complaint = Complaint(
            title=title,
            description=description,
            category=category,
            is_anonymous=is_anonymous,
            complainant_id=complainant_id,
            status='submitted'
        )
        db.session.add(complaint)
        db.session.commit()
        flash('Complaint submitted. Your public ID is: ' + complaint.public_id, 'success')
        return redirect(url_for('main.index'))
    return render_template('complaints/submit.html')

@complaints_bp.route('/case/<int:id>')
@login_required
def case_detail(id):
    complaint = Complaint.query.get_or_404(id)
    if current_user.role == 'user' and complaint.complainant_id != current_user.id:
        abort(403)
    if not complaint.is_anonymous and current_user.role != 'user':
        log = AccessLog(user_id=current_user.id, resource_type='complaint', resource_id=id, action='view_identity')
        db.session.add(log)
        db.session.commit()
    actions = Action.query.filter_by(complaint_id=id).order_by(Action.created_at.desc()).all()
    return render_template('complaints/detail.html', complaint=complaint, actions=actions)

@complaints_bp.route('/case/<int:id>/action', methods=['POST'])
@login_required
def add_action(id):
    if current_user.role == 'user':
        abort(403)
    complaint = Complaint.query.get_or_404(id)
    action_type = request.form.get('action_type')
    notes = request.form.get('notes')
    new_severity = request.form.get('severity')
    new_status = request.form.get('status')

    action = Action(complaint_id=id, actor_id=current_user.id, action_type=action_type, notes=notes)
    db.session.add(action)

    if new_severity:
        complaint.severity = new_severity
    if new_status:
        complaint.status = new_status

    db.session.commit()
    flash('Action recorded', 'success')
    return redirect(url_for('complaints.case_detail', id=id))

@complaints_bp.route('/public/<public_id>')
def public_view(public_id):
    complaint = Complaint.query.filter_by(public_id=public_id, public_published=True).first_or_404()
    return render_template('complaints/public.html', complaint=complaint)
