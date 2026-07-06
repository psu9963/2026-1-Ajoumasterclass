from flask import Blueprint, render_template, jsonify
from models import db, Subject, WeeklyPlan, StudyPlan, ExamPlan, PlanCoaching
from datetime import datetime, date, timedelta
from openai import OpenAI
import os
from flask_login import login_required, current_user


analysis_bp = Blueprint('analysis', __name__)

LOW_COMPLETION_THRESHOLD = 40  # 이 % 미만이면 실천율 낮음으로 강조
THIS_WEEK_TODO_LIMIT = 5

_COACHING_SYSTEM_PROMPT = (
    "당신은 학습 코치입니다. 실천율이 낮거나 시험이 임박한 과목을 짚고, "
    "오늘/이번 주에 뭘 먼저 공부하면 좋을지 구체적인 행동을 2~3가지 한국어로 제안하세요. "
    "과장하거나 이모지를 남발하지 마세요. "
    "마크다운 문법(#, **, - 등)이나 제목을 쓰지 말고 평범한 문장으로만 답하세요."
)


def _make_openai_client():
    return OpenAI(
        api_key=os.environ.get("AJOU_API_KEY"),
        base_url="https://factchat-cloud.mindlogic.ai/v1/gateway"
    )


def _current_week(subject, max_week):
    """개강일부터 몇 주 지났는지로 현재 주차 계산. 개강일 없으면 None."""
    if not subject.start_date:
        return None
    try:
        start = datetime.strptime(subject.start_date, '%Y-%m-%d').date()
    except ValueError:
        return None
    weeks_elapsed = (date.today() - start).days // 7
    week = max(1, weeks_elapsed + 1)
    if max_week:
        week = min(week, max_week)
    return week


def _subject_timeline(user_id):
    """과목별 현재 주차 기준 완료율 + 이번 주 할 일 + 시험 D-day 우선순위를 계산"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    subjects = Subject.query.filter_by(user_id=user_id).order_by(Subject.created_at.desc()).all()

    subject_rows = []
    exam_rows = []
    todo_candidates = []

    for subject in subjects:
        weekly_plans = WeeklyPlan.query.filter_by(subject_id=subject.id).order_by(WeeklyPlan.week).all()
        max_week = weekly_plans[-1].week if weekly_plans else None
        current_week = _current_week(subject, max_week)

        week_topic = None
        if current_week is not None:
            wp = next((w for w in weekly_plans if w.week == current_week), None)
            week_topic = wp.topic if wp else None

        study_plans = StudyPlan.query.filter_by(subject_id=subject.id).all()
        exam_plans = ExamPlan.query.filter_by(subject_id=subject.id).all()

        done = 0
        total = 0
        this_week_total = 0
        this_week_done = 0

        for sp in study_plans:
            for item in sp.items:
                # 개강일 미등록 과목은 전체 기준으로 폴백
                if current_week is not None and item.week > current_week:
                    continue
                total += 1
                if item.is_done:
                    done += 1
                if current_week is not None and item.week == current_week:
                    this_week_total += 1
                    if item.is_done:
                        this_week_done += 1
                    else:
                        todo_candidates.append({
                            'subject_id': subject.id,
                            'subject': subject.name,
                            'task': item.task,
                            'sort_key': (1, item.week, item.id),
                        })

        for ep in exam_plans:
            for item in ep.items:
                try:
                    item_date = datetime.strptime(item.plan_date, '%Y-%m-%d').date()
                except ValueError:
                    continue
                if item_date > today:
                    continue
                total += 1
                if item.is_done:
                    done += 1
                if week_start <= item_date <= week_end and not item.is_done:
                    todo_candidates.append({
                        'subject_id': subject.id,
                        'subject': subject.name,
                        'task': item.task,
                        'sort_key': (0, item_date.toordinal(), item.id),
                    })

        nearest_dday = None
        for ep in exam_plans:
            try:
                d_day = (datetime.strptime(ep.exam_date, '%Y-%m-%d').date() - today).days
            except ValueError:
                continue
            if d_day < 0:
                continue
            if nearest_dday is None or d_day < nearest_dday:
                nearest_dday = d_day
            exam_rows.append({
                'subject': subject.name,
                'exam_name': ep.name,
                'd_day': d_day,
            })

        is_behind = current_week is not None and this_week_total > 0 and this_week_done == 0

        subject_rows.append({
            'name': subject.name,
            'current_week': current_week,
            'week_topic': week_topic,
            'done': done,
            'total': total,
            'percent': round(done / total * 100) if total > 0 else None,
            'is_behind': is_behind,
            'nearest_dday': nearest_dday,
        })

    exam_rows.sort(key=lambda e: e['d_day'])
    todo_candidates.sort(key=lambda t: t['sort_key'])
    this_week_todos = todo_candidates[:THIS_WEEK_TODO_LIMIT]

    total_done = sum(s['done'] for s in subject_rows)
    total_count = sum(s['total'] for s in subject_rows)

    return subject_rows, exam_rows, this_week_todos, total_done, total_count


@analysis_bp.route('/analysis')
@login_required
def analysis():
    user_id = current_user.id
    subject_rows, exam_rows, this_week_todos, total_done, total_count = _subject_timeline(user_id)

    has_enough_data = len(subject_rows) > 0 and total_count > 0

    cached = PlanCoaching.query.filter_by(user_id=user_id).first()

    return render_template('analysis.html',
        has_subjects=len(subject_rows) > 0,
        has_enough_data=has_enough_data,
        subject_rows=subject_rows,
        exam_rows=exam_rows,
        this_week_todos=this_week_todos,
        low_threshold=LOW_COMPLETION_THRESHOLD,
        coaching_content=cached.content if cached else None,
        coaching_created=cached.created_at if cached else None,
    )


# ── AI 학습 코칭 생성 (버튼 클릭 시만 호출) ──
@analysis_bp.route('/analysis/coaching', methods=['POST'])
@login_required
def coaching():
    user_id = current_user.id
    subject_rows, exam_rows, this_week_todos, total_done, total_count = _subject_timeline(user_id)

    if not subject_rows or total_count == 0:
        return jsonify({'error': 'insufficient_data'}), 400

    subject_lines = []
    for s in subject_rows:
        week_str = f"{s['current_week']}주차" if s['current_week'] is not None else "개강일 미등록"
        pct = f"{s['percent']}%" if s['percent'] is not None else "계획 없음"
        topic = f" (이번 주 주제: {s['week_topic']})" if s['week_topic'] else ""
        dday = f", 시험 D-{s['nearest_dday']}" if s['nearest_dday'] is not None else ""
        subject_lines.append(
            f"- {s['name']} [{week_str}]{topic}: 이번 주차까지 완료 {s['done']}/{s['total']} ({pct}){dday}"
        )

    summary = "[과목별 현재 진행 상황]\n" + '\n'.join(subject_lines)

    if this_week_todos:
        todo_lines = [f"- {t['subject']}: {t['task']}" for t in this_week_todos]
        summary += "\n\n[이번 주 아직 안 한 항목]\n" + '\n'.join(todo_lines)

    if exam_rows:
        exam_lines = [f"- {e['subject']} {e['exam_name']}: D-{e['d_day']}" for e in exam_rows[:5]]
        summary += "\n\n[다가오는 시험]\n" + '\n'.join(exam_lines)

    client = _make_openai_client()
    try:
        response = client.chat.completions.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[
                {"role": "system", "content": _COACHING_SYSTEM_PROMPT},
                {"role": "user", "content": summary},
            ]
        )
        content = response.choices[0].message.content.strip()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        record = PlanCoaching.query.filter_by(user_id=user_id).first()
        if record:
            record.content = content
            record.created_at = now_str
        else:
            record = PlanCoaching(user_id=user_id, content=content, created_at=now_str)
            db.session.add(record)
        db.session.commit()

        return jsonify({'success': True, 'content': content, 'created_at': now_str})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
