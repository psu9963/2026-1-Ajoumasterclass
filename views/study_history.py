from flask import Blueprint, render_template, request, redirect, url_for
from models import db, StudyRecord
from sqlalchemy import func
from flask_login import login_required, current_user
from datetime import datetime, timedelta


study_history_bp = Blueprint('study_history', __name__)


@study_history_bp.route('/study-history', methods=['GET', 'POST'])
@login_required
def history():
    if request.method == 'POST':
        subject_name = request.form.get('subject')
        new_folder = StudyRecord(
            user_id=current_user.id,
            subject=subject_name,
            duration_hours=0,
            study_date='',
            memo='과목 생성'
        )
        db.session.add(new_folder)
        db.session.commit()
        return redirect(url_for('study_history.history'))

    # 과목 목록 (중복 제거)
    subjects = db.session.query(StudyRecord.subject)\
        .filter_by(user_id=current_user.id)\
        .distinct().all()
    subject_list = [s[0] for s in subjects]

    # ── 통계 ──────────────────────────────────────────
    # 총 학습 기록 수 (duration_hours > 0 인 것만)
    total_records = StudyRecord.query.filter(
        StudyRecord.user_id == current_user.id,
        StudyRecord.duration_hours > 0
    ).count()

    # 총 학습 시간
    total_hours_raw = db.session.query(func.sum(StudyRecord.duration_hours))\
        .filter(
            StudyRecord.user_id == current_user.id,
            StudyRecord.duration_hours > 0
        ).scalar() or 0
    total_hours = round(total_hours_raw, 1)

    # 이번 주 학습 시간 (월요일 ~ 오늘)
    today = datetime.today().date()
    week_start = today - timedelta(days=today.weekday())  # 이번 주 월요일

    week_hours_raw = db.session.query(func.sum(StudyRecord.duration_hours))\
        .filter(
            StudyRecord.user_id == current_user.id,
            StudyRecord.duration_hours > 0,
            StudyRecord.study_date >= str(week_start)
        ).scalar() or 0
    week_hours = round(week_hours_raw, 1)
    # ──────────────────────────────────────────────────

    return render_template(
        'study_history.html',
        username=current_user.username,
        subjects=subject_list,
        total_records=total_records,
        total_hours=total_hours,
        week_hours=week_hours
    )


@study_history_bp.route('/study-history/<subject>', methods=['GET', 'POST'])
@login_required
def subject_detail(subject):
    if request.method == 'POST':
        duration = request.form.get('duration')
        date = request.form.get('date')
        memo = request.form.get('memo')
        new_record = StudyRecord(
            user_id=current_user.id,
            subject=subject,
            duration_hours=float(duration),
            study_date=date,
            memo=memo
        )
        db.session.add(new_record)
        db.session.commit()
        return redirect(url_for('study_history.subject_detail', subject=subject))

    records = StudyRecord.query.filter(
        StudyRecord.user_id == current_user.id,
        StudyRecord.subject == subject,
        StudyRecord.duration_hours > 0
    ).order_by(StudyRecord.study_date.desc()).all()

    return render_template(
        'subject_detail.html',
        username=current_user.username,
        subject=subject,
        records=records
    )


@study_history_bp.route('/study-history/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record_to_delete = StudyRecord.query.get_or_404(record_id)
    subject_name = record_to_delete.subject
    db.session.delete(record_to_delete)
    db.session.commit()
    return redirect(url_for('study_history.subject_detail', subject=subject_name))


@study_history_bp.route('/study-history/<subject>/delete', methods=['POST'])
@login_required
def delete_subject(subject):
    StudyRecord.query.filter_by(
        user_id=current_user.id,
        subject=subject
    ).delete()
    db.session.commit()
    return redirect(url_for('study_history.history'))


@study_history_bp.route('/study-history/edit/<int:record_id>', methods=['POST'])
@login_required
def edit_record(record_id):
    record_to_edit = StudyRecord.query.get_or_404(record_id)
    subject_name = record_to_edit.subject
    record_to_edit.duration_hours = float(request.form.get('duration'))
    record_to_edit.study_date = request.form.get('date')
    record_to_edit.memo = request.form.get('memo')
    db.session.commit()
    return redirect(url_for('study_history.subject_detail', subject=subject_name))
