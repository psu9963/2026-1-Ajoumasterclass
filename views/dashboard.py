# views/dashboard.py
from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from models import db, StudyRecord, WeeklyGoal, DailyGoal, CalendarEvent, Subject, WeeklyPlan
from datetime import datetime, date, timedelta
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


def get_dashboard_data(user_id):

    today      = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end   = week_start + timedelta(days=6)

    # ── 강의실 과목 연동: 진행 중 / 완료 분류 ──────────────
    subjects = Subject.query.filter_by(user_id=user_id).all()

    active_subject_count    = 0
    completed_subject_count = 0

    for subj in subjects:
        # start_date 없으면 진행 중으로 간주
        if not subj.start_date:
            active_subject_count += 1
            continue

        try:
            start = datetime.strptime(subj.start_date[:10], '%Y-%m-%d').date()
        except ValueError:
            active_subject_count += 1
            continue

        # 해당 과목의 최대 주차 조회
        max_week_row = db.session.query(
            func.max(WeeklyPlan.week)
        ).filter(WeeklyPlan.subject_id == subj.id).scalar()

        total_weeks = max_week_row if max_week_row else 16  # 기본 16주

        # 종강일 = 개강일 + (총 주차 × 7일)
        end_date = start + timedelta(weeks=total_weeks)

        if today > end_date:
            completed_subject_count += 1
        else:
            active_subject_count += 1

    # ── 기본 통계 ──────────────────────────────────────────
    total_hours_raw = db.session.query(
        func.coalesce(func.sum(StudyRecord.duration_hours), 0)
    ).filter(StudyRecord.user_id == user_id).scalar()
    total_hours = round(float(total_hours_raw), 1)

    # ── 이번 주 학습 시간 ───────────────────────────────────
    weekly_raw = db.session.query(
        func.coalesce(func.sum(StudyRecord.duration_hours), 0)
    ).filter(
        StudyRecord.user_id    == user_id,
        StudyRecord.study_date >= week_start.isoformat(),
        StudyRecord.study_date <= week_end.isoformat()
    ).scalar()
    weekly_hours = round(float(weekly_raw), 1)

    # ── 과목별 학습 비율 ────────────────────────────────────
    subject_rows = db.session.query(
        StudyRecord.subject,
        func.round(func.sum(StudyRecord.duration_hours), 1).label('total_hours')
    ).filter(
        StudyRecord.user_id == user_id
    ).group_by(StudyRecord.subject).order_by(
        func.sum(StudyRecord.duration_hours).desc()
    ).limit(5).all()

    total_all = sum(float(r.total_hours) for r in subject_rows) or 1
    subject_stats = [
        {
            'subject':     r.subject,
            'total_hours': r.total_hours,
            'percent':     min(int(float(r.total_hours) / total_all * 100), 100)
        }
        for r in subject_rows
    ]

    # ── 오늘의 학습 목표 ────────────────────────────────────
    daily_goals = DailyGoal.query.filter_by(
        user_id   = user_id,
        goal_date = today.isoformat()
    ).order_by(DailyGoal.id).all()

    # ── 다가오는 일정 (캘린더 연동) ────────────────────────
    upcoming_events = []
    try:
        events = CalendarEvent.query.filter(
            CalendarEvent.user_id    == user_id,
            CalendarEvent.start_date >= today.isoformat(),
            CalendarEvent.start_date <= (today + timedelta(days=30)).isoformat()
        ).order_by(CalendarEvent.start_date.asc()).limit(4).all()

        for ev in events:
            ev_date = datetime.strptime(ev.start_date[:10], '%Y-%m-%d').date()
            dday    = (ev_date - today).days
            upcoming_events.append({
                'title':   ev.title,
                'month':   ev_date.month,
                'day':     ev_date.day,
                'dday':    dday,
                'is_exam': ev.category in ('시험', 'exam') if ev.category else False
            })
    except Exception:
        pass

    return dict(
        active_subject_count    = active_subject_count,
        completed_subject_count = completed_subject_count,
        total_hours             = total_hours,
        weekly_hours            = weekly_hours,
        subject_stats           = subject_stats,
        daily_goals             = daily_goals,
        upcoming_events         = upcoming_events,
    )


# ── 라우트 ──────────────────────────────────────────────────

@dashboard_bp.route('/')
@login_required
def dashboard():
    user_id      = current_user.id
    display_name = current_user.display_name or current_user.username
    data         = get_dashboard_data(user_id)
    return render_template('dashboard.html', display_name=display_name, **data)


@dashboard_bp.route('/set_weekly_goal', methods=['POST'])
@login_required
def set_weekly_goal():
    user_id    = current_user.id
    goal_hours = float(request.json.get('goal_hours', 10))
    today      = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()

    existing = WeeklyGoal.query.filter_by(
        user_id    = user_id,
        week_start = week_start
    ).first()

    if existing:
        existing.goal_hours = goal_hours
    else:
        db.session.add(WeeklyGoal(
            user_id    = user_id,
            goal_hours = goal_hours,
            week_start = week_start
        ))
    db.session.commit()
    return jsonify({'ok': True})


@dashboard_bp.route('/add_daily_goal', methods=['POST'])
@login_required
def add_daily_goal():
    user_id   = current_user.id
    goal_text = request.json.get('goal_text', '').strip()
    if not goal_text:
        return jsonify({'ok': False})

    new_goal = DailyGoal(
        user_id   = user_id,
        goal_date = date.today().isoformat(),
        goal_text = goal_text,
        is_done   = False
    )
    db.session.add(new_goal)
    db.session.commit()
    return jsonify({'ok': True, 'id': new_goal.id, 'goal_text': goal_text})


@dashboard_bp.route('/toggle_daily_goal/<int:goal_id>', methods=['POST'])
@login_required
def toggle_daily_goal(goal_id):
    user_id = current_user.id
    goal    = DailyGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return jsonify({'ok': False}), 404
    goal.is_done = not goal.is_done
    db.session.commit()
    return jsonify({'ok': True, 'is_done': goal.is_done})


@dashboard_bp.route('/delete_daily_goal/<int:goal_id>', methods=['POST'])
@login_required
def delete_daily_goal(goal_id):
    user_id = current_user.id
    goal    = DailyGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return jsonify({'ok': False}), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify({'ok': True})
