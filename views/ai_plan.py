from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from models import db, StudyRecord, AIPlan
from datetime import datetime
from openai import OpenAI
import os
import json
from flask_login import login_required, current_user
from dotenv import load_dotenv

load_dotenv()

ai_plan_bp = Blueprint('ai_plan', __name__)



def generate_study_plan(subject, total_hours, recent_dates, goal_weeks=4):
    client = OpenAI(
        api_key=os.getㅎenv("AJOU_API_KEY"),
        base_url="https://factchat-cloud.mindlogic.ai/v1/gateway"
    )
    prompt = f"""당신은 대학생 학습 분석 전문가입니다.
아래 학생의 학습 데이터를 분석하고, 학습 계획을 JSON 형식으로만 반환하세요.
절대 JSON 외의 텍스트를 포함하지 마세요.

[학생 학습 데이터]
- 과목: {subject}
- 지금까지 총 학습 시간: {total_hours}시간
- 최근 학습 날짜: {', '.join(recent_dates) if recent_dates else '기록 없음'}
- 앞으로 목표 기간: {goal_weeks}주

[반환할 JSON 형식]
{{
  "subject": "과목명",
  "diagnosis": "현재 학습 상태 진단 (2문장)",
  "weekly_goal_hours": 주당_권장_학습시간_숫자,
  "total_plan_hours": 전체_계획_시간_숫자,
  "weeks": [
    {{
      "week": 1,
      "theme": "이번 주 핵심 테마",
      "daily_hours": 하루_권장_시간_숫자,
      "topics": ["학습 주제1", "학습 주제2", "학습 주제3"],
      "checkpoint": "이번 주 마무리 점검 방법"
    }}
  ],
  "tips": ["학습 팁1", "학습 팁2", "학습 팁3"]
}}

반드시 {goal_weeks}개의 week 객체를 포함하고, JSON만 반환하세요."""

    response = client.chat.completions.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    return json.loads(raw)

@ai_plan_bp.route('/ai-plan')
@login_required
def ai_plan():
    user_id  = current_user.id
    records  = StudyRecord.query.filter_by(user_id=current_user.id).all()
    subjects = list({r.subject for r in records if r.duration_hours > 0})
    return render_template('ai_plan.html',
                           subjects=subjects,
                           username=current_user.username)

@ai_plan_bp.route('/ai-plan/analyze', methods=['POST'])
@login_required
def analyze():
    user_id    = current_user.id
    subject    = request.form.get('subject', '')
    goal_weeks = int(request.form.get('weeks', 4))

    if not subject:
        return jsonify({'error': '과목을 선택해 주세요.'}), 400

    records = StudyRecord.query.filter(
        StudyRecord.user_id == current_user.id,
        StudyRecord.subject == subject,
        StudyRecord.duration_hours > 0
    ).order_by(StudyRecord.study_date.desc()).all()

    if not records:
        return jsonify({'error': '해당 과목의 학습 기록이 없습니다.'}), 400

    total_hours  = round(sum(r.duration_hours for r in records), 1)
    recent_dates = [r.study_date for r in records[:5]]

    try:
        plan = generate_study_plan(
            subject=subject,
            total_hours=total_hours,
            recent_dates=recent_dates,
            goal_weeks=goal_weeks
        )
        new_plan = AIPlan(
            user_id=current_user.id,
            subject=subject,
            goal_weeks=goal_weeks,
            plan_content=json.dumps(plan, ensure_ascii=False),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        db.session.add(new_plan)
        db.session.commit()
        return jsonify({'success': True, 'plan': plan})

    except Exception as e:
        return jsonify({'error': f'AI 분석 중 오류가 발생했습니다: {str(e)}'}), 500

@ai_plan_bp.route('/ai-plan/history')
@login_required
def plan_history():
    user_id = current_user.id
    plans   = AIPlan.query.filter_by(user_id=current_user.id)\
                          .order_by(AIPlan.id.desc()).all()
    plans_by_subject = {}
    for p in plans:
        plan_data = {
            'id':         p.id,
            'subject':    p.subject,
            'goal_weeks': p.goal_weeks,
            'created_at': p.created_at,
            'plan':       json.loads(p.plan_content)
        }
        if p.subject not in plans_by_subject:
            plans_by_subject[p.subject] = []
        plans_by_subject[p.subject].append(plan_data)
    return render_template('ai_plan_history.html',
                           plans_by_subject=plans_by_subject,
                           username=current_user.username)

@ai_plan_bp.route('/ai-plan/delete/<int:plan_id>', methods=['POST'])
@login_required
def delete_plan(plan_id):
    plan = AIPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return redirect(url_for('ai_plan.plan_history'))