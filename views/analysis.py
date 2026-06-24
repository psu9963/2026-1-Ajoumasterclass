from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from models import db, StudyRecord, AIFeedback, AIPlan, WeeklyGoal, WeeklyCoaching
from datetime import datetime, timedelta
from collections import defaultdict
from openai import OpenAI
import os, json
from flask_login import login_required, current_user


analysis_bp = Blueprint('analysis', __name__)

MIN_RECORDS_FOR_COACHING = 3  # 코칭 생성에 필요한 최소 기록 수


def get_streaks(records):
    dates = sorted(set(
        datetime.strptime(r.study_date, '%Y-%m-%d').date()
        for r in records if r.study_date
    ), reverse=True)

    if not dates:
        return 0, 0

    today = datetime.now().date()

    current = 0
    for i, d in enumerate(dates):
        if d == today - timedelta(days=i):
            current += 1
        else:
            break

    best = 1
    temp = 1
    sorted_asc = sorted(dates)
    for i in range(1, len(sorted_asc)):
        if sorted_asc[i] == sorted_asc[i-1] + timedelta(days=1):
            temp += 1
            best = max(best, temp)
        else:
            temp = 1

    return current, best

def get_gap_warnings(records, subjects):
    today = datetime.now().date()
    warnings = []
    for subject in subjects:
        s_records = [r for r in records if r.subject == subject and r.study_date]
        if not s_records:
            continue
        last_date = max(
            datetime.strptime(r.study_date, '%Y-%m-%d').date()
            for r in s_records
        )
        gap = (today - last_date).days
        if gap >= 3:
            warnings.append({'subject': subject, 'days': gap})
    warnings.sort(key=lambda x: x['days'], reverse=True)
    return warnings

def get_week_pace(records):
    today = datetime.now().date()
    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(days=7)

    this_week = sum(
        r.duration_hours for r in records
        if r.study_date and datetime.strptime(r.study_date, '%Y-%m-%d').date() >= this_week_start
    )
    last_week = sum(
        r.duration_hours for r in records
        if r.study_date and last_week_start <= datetime.strptime(r.study_date, '%Y-%m-%d').date() < this_week_start
    )

    if last_week == 0:
        change_pct = None
    else:
        change_pct = round((this_week - last_week) / last_week * 100)

    return round(this_week, 1), round(last_week, 1), change_pct

def get_this_week_story(records):
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    day_names = ['월', '화', '수', '목', '금', '토', '일']

    story = []
    for r in records:
        if not r.study_date:
            continue
        d = datetime.strptime(r.study_date, '%Y-%m-%d').date()
        if d >= week_start:
            story.append({
                'day': day_names[d.weekday()],
                'subject': r.subject,
                'hours': r.duration_hours,
                'memo': r.memo or ''
            })
    story.sort(key=lambda x: ['월','화','수','목','금','토','일'].index(x['day']))
    return story

def _make_openai_client():
    return OpenAI(
        api_key=os.environ.get("AJOU_API_KEY"),
        base_url="https://factchat-cloud.mindlogic.ai/v1/gateway"
    )

@analysis_bp.route('/analysis')
@login_required
def analysis():
    user_id = current_user.id
    records = StudyRecord.query.filter(
        StudyRecord.user_id == user_id,
        StudyRecord.duration_hours > 0
    ).order_by(StudyRecord.study_date.desc()).all()

    subjects = list(set(r.subject for r in records))

    # ── 스트릭
    current_streak, best_streak = get_streaks(records)

    # ── 공백 경고
    gap_warnings = get_gap_warnings(records, subjects)

    # ── 주간 페이스
    this_week_h, last_week_h, pace_pct = get_week_pace(records)

    # ── 전체 누적 시간
    total_hours = round(sum(r.duration_hours for r in records), 1)

    # ── 과목별 시간 (도넛 차트 + 레이더)
    subject_hours = defaultdict(float)
    for r in records:
        subject_hours[r.subject] += r.duration_hours
    s_labels = list(subject_hours.keys())
    s_raw    = [round(v, 1) for v in subject_hours.values()]
    max_h    = max(s_raw) if s_raw else 1
    radar_values = [round(v / max_h * 100, 1) for v in s_raw]

    # ── 최근 8주 주간 추이
    today           = datetime.now().date()
    week_start_date = today - timedelta(days=today.weekday())
    weekly_labels_list = []
    weekly_values_list = []
    for i in range(7, -1, -1):
        ws = week_start_date - timedelta(weeks=i)
        we = ws + timedelta(days=6)
        wh = sum(
            r.duration_hours for r in records
            if r.study_date and ws <= datetime.strptime(r.study_date, '%Y-%m-%d').date() <= we
        )
        weekly_labels_list.append(ws.strftime('%m/%d'))
        weekly_values_list.append(round(wh, 1))

    # ── 요일별 패턴
    day_totals = [0.0] * 7
    for r in records:
        if r.study_date:
            day_totals[datetime.strptime(r.study_date, '%Y-%m-%d').date().weekday()] += r.duration_hours
    day_names_list  = ['월', '화', '수', '목', '금', '토', '일']
    day_values_list = [round(v, 1) for v in day_totals]

    # ── 이번 주 스토리
    week_story = get_this_week_story(records)

    # ── 주간 목표 달성률
    week_start_str = week_start_date.strftime('%Y-%m-%d')
    weekly_goal    = WeeklyGoal.query.filter_by(user_id=user_id, week_start=week_start_str).first()
    goal_hours     = weekly_goal.goal_hours if weekly_goal else 10.0
    goal_pct       = min(round(this_week_h / goal_hours * 100), 100) if goal_hours > 0 else 0
    goal_diff      = round(this_week_h - last_week_h, 1)

    # ── 과목별 상세 (과목별 탭용)
    subject_details = {}
    for subject in subjects:
        s_recs = [r for r in records if r.subject == subject]
        total  = round(sum(r.duration_hours for r in s_recs), 1)
        count  = len(s_recs)
        avg    = round(total / count, 1) if count else 0
        last   = s_recs[0].study_date if s_recs else '-'

        monthly = defaultdict(float)
        for r in s_recs:
            if r.study_date:
                d = datetime.strptime(r.study_date, '%Y-%m-%d')
                monthly[d.strftime('%y/%m')] += r.duration_hours
        sorted_m = sorted(monthly.items())[-6:]

        subject_details[subject] = {
            'total_hours':    total,
            'session_count':  count,
            'avg_hours':      avg,
            'last_date':      last,
            'monthly_labels': [m[0] for m in sorted_m],
            'monthly_values': [round(m[1], 1) for m in sorted_m],
        }

    # ── 저장된 AI 피드백
    saved_feedbacks = {}
    feedbacks = AIFeedback.query.filter_by(user_id=user_id).order_by(AIFeedback.id.desc()).all()
    for f in feedbacks:
        if f.subject not in saved_feedbacks:
            saved_feedbacks[f.subject] = []
        saved_feedbacks[f.subject].append({
            'id':         f.id,
            'content':    json.loads(f.feedback_content),
            'created_at': f.created_at
        })

    # ── AI 학습 계획
    ai_plans_raw  = AIPlan.query.filter_by(user_id=user_id).order_by(AIPlan.id.desc()).all()
    ai_plans_data = [{'id':p.id,'subject':p.subject,'goal_weeks':p.goal_weeks,'created_at':p.created_at,'plan':json.loads(p.plan_content)} for p in ai_plans_raw]

    # ── 주간 코칭 캐시
    has_enough_data   = len(records) >= MIN_RECORDS_FOR_COACHING
    cached_coaching   = WeeklyCoaching.query.filter_by(user_id=user_id, week_start=week_start_str).first()
    coaching_content  = cached_coaching.content    if cached_coaching else None
    coaching_created  = cached_coaching.created_at if cached_coaching else None

    return render_template('analysis.html',
        username        = current_user.username,
        has_data        = len(records) > 0,
        subjects        = subjects,
        streak          = current_streak,
        best_streak     = best_streak,
        gap_warnings    = gap_warnings,
        this_week_h     = this_week_h,
        last_week_h     = last_week_h,
        pace_pct        = pace_pct,
        total_hours     = total_hours,
        week_hours      = this_week_h,
        weekly_labels   = json.dumps(weekly_labels_list),
        weekly_values   = json.dumps(weekly_values_list),
        subject_labels  = json.dumps(s_labels, ensure_ascii=False),
        subject_values  = json.dumps(s_raw),
        radar_labels    = json.dumps(s_labels, ensure_ascii=False),
        radar_values    = json.dumps(radar_values),
        radar_raw       = json.dumps(s_raw),
        day_names       = json.dumps(day_names_list, ensure_ascii=False),
        day_values      = json.dumps(day_values_list),
        week_story      = week_story,
        goal_hours      = goal_hours,
        goal_pct        = goal_pct,
        goal_diff       = goal_diff,
        subject_details    = json.dumps(subject_details, ensure_ascii=False),
        saved_feedbacks    = json.dumps(saved_feedbacks, ensure_ascii=False),
        ai_plans           = json.dumps(ai_plans_data, ensure_ascii=False),
        has_enough_data    = has_enough_data,
        coaching_content   = coaching_content,
        coaching_created   = coaching_created,
    )

# ── 주간 코칭 리포트 생성 (버튼 클릭 시만 호출)
@analysis_bp.route('/analysis/weekly-coaching', methods=['POST'])
@login_required
def weekly_coaching():
    user_id = current_user.id

    records = StudyRecord.query.filter(
        StudyRecord.user_id == user_id,
        StudyRecord.duration_hours > 0
    ).all()

    if len(records) < MIN_RECORDS_FOR_COACHING:
        return jsonify({'error': 'insufficient_data'}), 400

    today           = datetime.now().date()
    week_start_date = today - timedelta(days=today.weekday())
    week_start_str  = week_start_date.strftime('%Y-%m-%d')
    last_week_start = week_start_date - timedelta(days=7)

    this_week_recs = [r for r in records if r.study_date and datetime.strptime(r.study_date, '%Y-%m-%d').date() >= week_start_date]
    last_week_recs = [r for r in records if r.study_date and last_week_start <= datetime.strptime(r.study_date, '%Y-%m-%d').date() < week_start_date]

    this_week_h = round(sum(r.duration_hours for r in this_week_recs), 1)
    last_week_h = round(sum(r.duration_hours for r in last_week_recs), 1)

    subj_hours = defaultdict(float)
    for r in this_week_recs:
        subj_hours[r.subject] += r.duration_hours

    weekly_goal = WeeklyGoal.query.filter_by(user_id=user_id, week_start=week_start_str).first()
    goal_hours  = weekly_goal.goal_hours if weekly_goal else 10.0
    goal_pct    = round(this_week_h / goal_hours * 100) if goal_hours > 0 else 0

    subj_summary = ', '.join(f"{s}: {round(h,1)}h" for s, h in subj_hours.items()) or '없음'
    diff = round(this_week_h - last_week_h, 1)
    diff_str = ('+' if diff >= 0 else '') + str(diff) + 'h'

    summary = (
        f"이번 주 학습 요약:\n"
        f"- 총 학습 시간: {this_week_h}h (주간 목표 {goal_hours}h 대비 {goal_pct}%)\n"
        f"- 과목별: {subj_summary}\n"
        f"- 지난주 대비: {diff_str}\n"
        f"- 이번 주 학습 세션 수: {len(this_week_recs)}회"
    )

    client = _make_openai_client()
    try:
        response = client.chat.completions.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 대학생 학습 코치입니다. "
                        "학생의 이번 주 학습 데이터를 보고 칭찬 1가지와 개선 제안 1~2가지를 "
                        "자연스러운 한국어 2~3문장으로 말해주세요. "
                        "과장하거나 이모지를 남발하지 마세요."
                    )
                },
                {"role": "user", "content": summary}
            ]
        )
        content  = response.choices[0].message.content.strip()
        now_str  = datetime.now().strftime('%Y-%m-%d %H:%M')

        coaching = WeeklyCoaching.query.filter_by(user_id=user_id, week_start=week_start_str).first()
        if coaching:
            coaching.content    = content
            coaching.created_at = now_str
        else:
            coaching = WeeklyCoaching(
                user_id    = user_id,
                week_start = week_start_str,
                content    = content,
                created_at = now_str
            )
            db.session.add(coaching)
        db.session.commit()

        return jsonify({'success': True, 'content': content, 'created_at': now_str})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── AI 피드백 생성 + 저장
@analysis_bp.route('/analysis/ai-feedback', methods=['POST'])
@login_required
def ai_feedback():
    user_id = current_user.id
    subject = request.json.get('subject', '')

    records = StudyRecord.query.filter(
        StudyRecord.user_id == user_id,
        StudyRecord.subject == subject,
        StudyRecord.duration_hours > 0
    ).order_by(StudyRecord.study_date.desc()).all()

    if not records:
        return jsonify({'error': '기록이 없습니다.'}), 400

    total_hours   = round(sum(r.duration_hours for r in records), 1)
    session_count = len(records)
    avg_hours     = round(total_hours / session_count, 1)
    dates         = [r.study_date for r in records[:10]]

    client = _make_openai_client()
    prompt = f"""학생의 '{subject}' 과목 학습 데이터를 분석해주세요.

[학습 데이터]
- 총 학습 시간: {total_hours}시간
- 총 학습 세션: {session_count}회
- 평균 세션 시간: {avg_hours}시간
- 최근 학습 날짜들: {', '.join(dates)}

아래 JSON 형식으로만 응답하세요:
{{
  "diagnosis": "현재 학습 패턴 진단 (2-3문장)",
  "strengths": ["잘하고 있는 점1", "잘하고 있는 점2"],
  "improvements": ["개선할 점1", "개선할 점2"],
  "recommendation": "구체적인 학습 추천 방법 (2-3문장)"
}}"""

    try:
        response = client.chat.completions.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        feedback = json.loads(raw.strip())

        new_fb = AIFeedback(
            user_id          = user_id,
            subject          = subject,
            feedback_content = json.dumps(feedback, ensure_ascii=False),
            created_at       = datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        db.session.add(new_fb)
        db.session.commit()

        return jsonify({'success': True, 'feedback': feedback,
                        'id': new_fb.id, 'created_at': new_fb.created_at})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── AI 피드백 삭제
@analysis_bp.route('/analysis/ai-feedback/delete/<int:fb_id>', methods=['POST'])
@login_required
def delete_feedback(fb_id):
    fb = AIFeedback.query.filter_by(id=fb_id, user_id=current_user.id).first_or_404()
    db.session.delete(fb)
    db.session.commit()
    return jsonify({'success': True})

# ── 이번 주 학습 스토리 AI 요약
@analysis_bp.route('/analysis/weekly-story', methods=['POST'])
@login_required
def weekly_story():
    user_id = current_user.id
    story   = request.json.get('story', [])

    if not story:
        return jsonify({'error': '이번 주 학습 기록이 없어요.'}), 400

    story_text = '\n'.join(
        f"{s['day']}요일 — {s['subject']} {s['hours']}h / 메모: {s['memo'] or '없음'}"
        for s in story
    )

    client = _make_openai_client()
    prompt = f"""이번 주 학생의 학습 기록입니다:
{story_text}

아래 JSON 형식으로만 응답하세요:
{{
  "comment": "이번 주 학습에 대한 따뜻하고 구체적인 AI 한마디 (2-3문장, 칭찬+개선점 포함)"
}}"""

    try:
        response = client.chat.completions.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return jsonify({'success': True, 'result': json.loads(raw.strip())})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
