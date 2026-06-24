from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from functools import wraps
from models import db, StudyRecord, WeeklyGoal, DailyGoal
from datetime import datetime, timedelta, date
from flask_login import login_required, current_user
import json

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    # 1. 유효한 학습 기록
    valid_records = StudyRecord.query.filter(
        StudyRecord.user_id == current_user.id,
        StudyRecord.duration_hours > 0
    ).all()

    # 2. 총 학습 시간
    total_hours = sum(r.duration_hours for r in valid_records)

    # 3. 진행 중인 과목 (중복 제거)
    unique_subjects = list(set(r.subject for r in valid_records))
    subject_count = len(unique_subjects)

    # 4. 이번 주 학습 시간
    today_date = date.today()
    start_of_week = today_date - timedelta(days=today_date.weekday())

    weekly_hours = 0
    for r in valid_records:
        if r.study_date:
            try:
                record_date = datetime.strptime(r.study_date, '%Y-%m-%d').date()
                if record_date >= start_of_week:
                    weekly_hours += r.duration_hours
            except ValueError:
                pass

    # 5. 과목별 학습 비율
    subject_hours = {}
    for r in valid_records:
        subject_hours[r.subject] = subject_hours.get(r.subject, 0) + r.duration_hours

    total_h = sum(subject_hours.values()) or 1
    subject_stats = [
        {
            'subject': subj,
            'total_hours': round(hrs, 1),
            'percent': round(hrs / total_h * 100)
        }
        for subj, hrs in sorted(subject_hours.items(), key=lambda x: -x[1])
    ]

    subject_labels = json.dumps(list(subject_hours.keys()))
    subject_data   = json.dumps(list(subject_hours.values()))

    # 6. 최근 학습 기록
    recent_records = StudyRecord.query.filter(
        StudyRecord.user_id == current_user.id,
        StudyRecord.duration_hours > 0
    ).order_by(StudyRecord.study_date.desc()).limit(3).all()

    # 7. 진행 중인 과목 목록 (과목명 + 총 시간)
    active_subjects = [
        {'subject': subj, 'total_hours': round(hrs, 1)}
        for subj, hrs in sorted(subject_hours.items(), key=lambda x: -x[1])
    ]

    # 8. 완료한 학습 기록 (오늘 날짜 기록)
    today_str = today_date.strftime('%Y-%m-%d')
    completed_records = StudyRecord.query.filter(
        StudyRecord.user_id == current_user.id,
        StudyRecord.study_date == today_str,
        StudyRecord.duration_hours > 0
    ).order_by(StudyRecord.id.desc()).all()

    # 9. 주간 목표 가져오기
    week_start_str = start_of_week.strftime('%Y-%m-%d')
    weekly_goal = WeeklyGoal.query.filter_by(
        user_id=current_user.id,
        week_start=week_start_str
    ).first()
    goal_hours   = weekly_goal.goal_hours if weekly_goal else 10.0
    goal_percent = min(round(weekly_hours / goal_hours * 100), 100) if goal_hours else 0

    # 10. 오늘의 학습 목표
    daily_goals = DailyGoal.query.filter_by(
        user_id=current_user.id,
        goal_date=today_str
    ).order_by(DailyGoal.id.asc()).all()

    total_records = len(valid_records)

    return render_template(
        'dashboard.html',
        username=current_user.username,
        total_hours=round(total_hours, 1),
        weekly_hours=round(weekly_hours, 1),
        subject_count=subject_count,
        total_subjects=subject_count,
        total_records=total_records,
        recent_records=recent_records,
        subject_labels=subject_labels,
        subject_data=subject_data,
        subject_stats=subject_stats,
        active_subjects=active_subjects,
        completed_records=completed_records,
        daily_goals=daily_goals,
        goal_hours=goal_hours,
        goal_percent=goal_percent,
        week_start_str=week_start_str,
        today_str=today_str,
    )


# ── 주간 목표 설정 API ──
@dashboard_bp.route('/dashboard/set_weekly_goal', methods=['POST'])
@login_required
def set_weekly_goal():
    data       = request.get_json()
    goal_hours = float(data.get('goal_hours', 10))
    today_date = date.today()
    week_start = (today_date - timedelta(days=today_date.weekday())).strftime('%Y-%m-%d')

    wg = WeeklyGoal.query.filter_by(
        user_id=current_user.id,
        week_start=week_start
    ).first()

    if wg:
        wg.goal_hours = goal_hours
    else:
        wg = WeeklyGoal(
            user_id=current_user.id,
            goal_hours=goal_hours,
            week_start=week_start
        )
        db.session.add(wg)

    db.session.commit()
    return jsonify({'ok': True, 'goal_hours': goal_hours})


# ── 오늘의 목표 추가 API ──
@dashboard_bp.route('/dashboard/add_daily_goal', methods=['POST'])
@login_required
def add_daily_goal():
    data      = request.get_json()
    goal_text = data.get('goal_text', '').strip()
    if not goal_text:
        return jsonify({'ok': False, 'msg': '내용을 입력하세요'})

    today_str = date.today().strftime('%Y-%m-%d')
    dg = DailyGoal(
        user_id=current_user.id,
        goal_date=today_str,
        goal_text=goal_text,
        is_done=False
    )
    db.session.add(dg)
    db.session.commit()
    return jsonify({'ok': True, 'id': dg.id, 'goal_text': dg.goal_text})


# ── 오늘의 목표 완료 토글 API ──
@dashboard_bp.route('/dashboard/toggle_daily_goal/<int:goal_id>', methods=['POST'])
@login_required
def toggle_daily_goal(goal_id):
    dg = DailyGoal.query.filter_by(
        id=goal_id,
        user_id=current_user.id
    ).first_or_404()
    dg.is_done = not dg.is_done
    db.session.commit()
    return jsonify({'ok': True, 'is_done': dg.is_done})


# ── 오늘의 목표 삭제 API ──
@dashboard_bp.route('/dashboard/delete_daily_goal/<int:goal_id>', methods=['POST'])
@login_required
def delete_daily_goal(goal_id):
    dg = DailyGoal.query.filter_by(
        id=goal_id,
        user_id=current_user.id
    ).first_or_404()
    db.session.delete(dg)
    db.session.commit()
    return jsonify({'ok': True})
