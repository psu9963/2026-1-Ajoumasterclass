from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from models import db, StudyRecord, AIFeedback
from datetime import datetime, timedelta
from collections import defaultdict
from openai import OpenAI
import os, json
from flask_login import login_required, current_user


analysis_bp = Blueprint('analysis', __name__)



def get_streaks(records):
    dates = sorted(set(
        datetime.strptime(r.study_date, '%Y-%m-%d').date()
        for r in records if r.study_date
    ), reverse=True)

    if not dates:
        return 0, 0

    today = datetime.now().date()

    # 현재 스트릭
    current = 0
    for i, d in enumerate(dates):
        if d == today - timedelta(days=i):
            current += 1
        else:
            break

    # 최고 스트릭
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

@analysis_bp.route('/analysis')
@login_required
def analysis():
    user_id = current_user.id
    records = StudyRecord.query.filter(
        StudyRecord.user_id == user_id,
        StudyRecord.duration_hours > 0
    ).order_by(StudyRecord.study_date.desc()).all()

    subjects = list(set(r.subject for r in records))

    # 스트릭
    current_streak, best_streak = get_streaks(records)

    # 공백 경고
    gap_warnings = get_gap_warnings(records, subjects)

    # 주간 페이스
    this_week_h, last_week_h, pace_pct = get_week_pace(records)

    # 레이더 차트 (과목별 시간 → 0~100 정규화)
    subject_hours = {s: 0.0 for s in subjects}
    for r in records:
        subject_hours[r.subject] += r.duration_hours
    max_h = max(subject_hours.values()) if subject_hours else 1
    radar_labels = list(subject_hours.keys())
    radar_values = [round(v / max_h * 100, 1) for v in subject_hours.values()]
    radar_raw    = [round(v, 1) for v in subject_hours.values()]

    # 이번 주 스토리 데이터
    week_story = get_this_week_story(records)

    # 과목별 상세 (과목별 탭용)
    subject_details = {}
    for subject in subjects:
        s_recs = [r for r in records if r.subject == subject]
        total = round(sum(r.duration_hours for r in s_recs), 1)
        count = len(s_recs)
        avg   = round(total / count, 1) if count else 0
        last  = s_recs[0].study_date if s_recs else '-'

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

    # 저장된 AI 피드백 (과목별)
    saved_feedbacks = {}
    feedbacks = AIFeedback.query.filter_by(user_id=user_id)\
                                .order_by(AIFeedback.id.desc()).all()
    for f in feedbacks:
        if f.subject not in saved_feedbacks:
            saved_feedbacks[f.subject] = []
        saved_feedbacks[f.subject].append({
            'id':         f.id,
            'content':    json.loads(f.feedback_content),
            'created_at': f.created_at
        })

    return render_template('analysis.html',
        username       = current_user.username,
        has_data       = len(records) > 0,
        subjects       = subjects,
        current_streak = current_streak,
        best_streak    = best_streak,
        gap_warnings   = gap_warnings,
        this_week_h    = this_week_h,
        last_week_h    = last_week_h,
        pace_pct       = pace_pct,
        radar_labels   = json.dumps(radar_labels, ensure_ascii=False),
        radar_values   = json.dumps(radar_values),
        radar_raw      = json.dumps(radar_raw),
        week_story     = week_story,
        subject_details   = json.dumps(subject_details, ensure_ascii=False),
        saved_feedbacks   = json.dumps(saved_feedbacks, ensure_ascii=False),
    )

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

    client = OpenAI(
        api_key=os.environ.get("AJOU_API_KEY"),
        base_url="https://factchat-cloud.mindlogic.ai/v1/gateway"
    )
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

        # DB 저장
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

    client = OpenAI(
        api_key=os.environ.get("AJOU_API_KEY"),
        base_url="https://factchat-cloud.mindlogic.ai/v1/gateway"
    )
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
