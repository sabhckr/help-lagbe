from flask import Blueprint, render_template
from flask_login import current_user, login_required
from app.models.complaint import Complaint

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    public_complaints = Complaint.query.filter_by(public_published=True).order_by(Complaint.created_at.desc()).limit(5).all()
    return render_template('index.html', public_complaints=public_complaints)

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'user':
        my_complaints = Complaint.query.filter_by(complainant_id=current_user.id).all()
        return render_template('dashboard/user.html', complaints=my_complaints)
    else:
        pending = Complaint.query.filter(Complaint.status.in_(['submitted', 'under_review'])).count()
        investigating = Complaint.query.filter_by(status='investigating').count()
        return render_template('dashboard/staff.html', pending=pending, investigating=investigating)
