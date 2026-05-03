from flask import Blueprint, render_template, session, redirect, url_for
from functools import wraps

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
def dashboard():
    dummy_data = {
        'total_hours': 0,
        'week_hours': 0,
        'subject_count': 0,
        'recent_records': [],
        'subjects': [],
        'username': session.get('username', '사용자')

        
    }
    return render_template('dashboard.html', **dummy_data)