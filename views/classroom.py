import os
import uuid
import json
import re
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, abort, jsonify
from flask_login import login_required, current_user
from models import db, Subject, WeeklyPlan, StudyPlan, StudyPlanItem, ExamPlan, ExamPlanItem
from werkzeug.utils import secure_filename
from openai import OpenAI
import pdfplumber

classroom_bp = Blueprint('classroom', __name__)

ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MIN_TEXT_LENGTH = 200  # 이 미만이면 스캔 이미지 PDF로 판단

# ── 프롬프트 상수 ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "당신은 대학교 강의계획서에서 주차별 진도를 추출하는 전문가입니다. "
    "반드시 JSON만 반환하세요. 설명, 마크다운, 코드펜스(```)는 절대 포함하지 마세요."
)

_STUDY_PLAN_SYSTEM_PROMPT = (
    "당신은 대학교 수업의 주차별 학습 계획을 짜주는 전문가입니다. "
    "반드시 JSON만 반환하세요. 설명, 마크다운, 코드펜스(```)는 절대 포함하지 마세요."
)

_EXAM_PLAN_SYSTEM_PROMPT = (
    "당신은 대학교 시험 대비 날짜별 학습 계획을 짜주는 전문가입니다. "
    "반드시 JSON만 반환하세요. 설명, 마크다운, 코드펜스(```)는 절대 포함하지 마세요. "
    "주어진 날짜(d_day) 목록에만 맞춰 배분하고, 날짜를 새로 만들지 마세요. "
    "시험이 가까운 날(D-1, D-2)에는 전체 복습·정리, 먼 날에는 새 내용 학습으로 배분하세요. "
    "시험 범위 주제에만 근거하고 없는 내용을 지어내지 마세요. 한국어로 작성하세요."
)

_EXAM_PLAN_USER_PROMPT_TEMPLATE = """아래는 대학교 수업의 시험 범위 주제와 날짜 목록입니다.
각 날짜(d_day)에 무엇을 공부할지 할 일을 1~3개씩 한국어로 배분하세요.

[반환 형식]
{{"daily": [{{"d_day": 7, "tasks": ["할 일1", "할 일2"]}}, ...]}}

[시험 범위 주제]
{weekly_list}

[추가 참고사항]
{scope_note}

[날짜 목록 — d_day가 클수록 시험에서 먼 날]
{day_list}"""

_STUDY_PLAN_USER_PROMPT_TEMPLATE = """아래는 대학교 수업의 주차별 주제 목록입니다.
각 주차마다 구체적이고 실천 가능한 학습 할 일을 2~4개씩 한국어로 생성하세요.

[규칙]
- 주어진 주차 주제에만 근거할 것. 없는 내용을 지어내지 말 것.
- 각 할 일(task)은 동사로 시작하는 1~2문장의 구체적인 행동 지침.
- JSON 외에 아무 텍스트도 출력하지 말 것.

[반환 형식]
{{"plan": [{{"week": 1, "topic": "주제", "tasks": ["할 일1", "할 일2"]}}]}}

[주차별 주제]
{weekly_list}"""

_USER_PROMPT_TEMPLATE = """아래는 대학교 강의계획서 텍스트입니다.
주차별 진도 정보만 추출하여 JSON으로 반환하세요.

[반환 형식]
{{"weekly_plan": [{{"week": 1, "topic": "주제"}}, ...]}}

[규칙]
- week는 정수 (1, 2, 3 ...)
- 강의계획서에 명시된 주차만 포함할 것. 없는 주차는 추측하지 말 것.
- 중간고사/기말고사 주차도 topic에 그대로 적을 것 (예: "중간고사")
- JSON 외에 아무 텍스트도 출력하지 말 것

[강의계획서 텍스트]
{text}"""


# ── 헬퍼 함수들 ───────────────────────────────────────────────────────────────
def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _make_llm_client():
    return OpenAI(
        api_key=os.environ.get("AJOU_API_KEY"),
        base_url="https://factchat-cloud.mindlogic.ai/v1/gateway"
    )


def _extract_text_from_pdf(filepath):
    """PDF에서 텍스트 추출. 실패 시 빈 문자열 반환."""
    text_parts = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception:
        pass
    return "\n".join(text_parts).strip()


def _call_llm_for_weekly_plan(text):
    """LLM에 텍스트를 넣어 주차별 진도 JSON을 받아 파싱. 실패 시 None 반환."""
    client = _make_llm_client()
    prompt = _USER_PROMPT_TEMPLATE.format(text=text[:8000])  # 토큰 초과 방지
    try:
        response = client.chat.completions.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        raw = response.choices[0].message.content.strip()
        # 코드펜스가 붙어오면 제거
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
        data = json.loads(raw)
        if "weekly_plan" not in data or not isinstance(data["weekly_plan"], list):
            return None
        return data["weekly_plan"]
    except Exception:
        return None


def _run_analysis(subject):
    """PDF 분석 → WeeklyPlan 저장 → syllabus_analyzed=True. 실패 시 flash 메시지."""
    pdf_path = os.path.join(
        current_app.root_path, 'static', 'uploads', 'syllabi', subject.syllabus_filename
    )
    text = _extract_text_from_pdf(pdf_path)

    if len(text) < MIN_TEXT_LENGTH:
        flash("강의계획서에서 텍스트를 읽을 수 없어요. 스캔 이미지 PDF는 분석이 어렵습니다.", "error")
        return False

    weekly_plan = _call_llm_for_weekly_plan(text)
    if weekly_plan is None:
        flash("AI 분석에 실패했어요. 다시 시도해 주세요.", "error")
        return False

    # 기존 WeeklyPlan 제거 후 새로 저장
    WeeklyPlan.query.filter_by(subject_id=subject.id).delete()
    for item in weekly_plan:
        try:
            week = int(item["week"])
            topic = str(item["topic"]).strip()
        except (KeyError, ValueError, TypeError):
            continue
        if not topic:
            continue
        db.session.add(WeeklyPlan(subject_id=subject.id, week=week, topic=topic))

    subject.syllabus_analyzed = True
    db.session.commit()
    return True


# ── 라우트 ────────────────────────────────────────────────────────────────────
@classroom_bp.route('/classroom', methods=['GET', 'POST'])
@login_required
def classroom():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        start_date = request.form.get('start_date', '').strip() or None
        pdf = request.files.get('syllabus')

        if not name:
            flash('과목명을 입력해주세요.', 'error')
            return redirect(url_for('classroom.classroom'))
        if not pdf or pdf.filename == '':
            flash('강의계획서 PDF 파일을 선택해주세요.', 'error')
            return redirect(url_for('classroom.classroom'))
        if not _allowed_file(pdf.filename):
            flash('PDF 파일만 업로드할 수 있어요.', 'error')
            return redirect(url_for('classroom.classroom'))

        pdf.seek(0, 2)
        if pdf.tell() > MAX_FILE_SIZE:
            flash('파일 크기가 10MB를 초과해요.', 'error')
            return redirect(url_for('classroom.classroom'))
        pdf.seek(0)

        safe_name = secure_filename(pdf.filename)
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'syllabi')
        pdf.save(os.path.join(upload_dir, unique_name))

        subject = Subject(
            user_id=current_user.id,
            name=name,
            start_date=start_date,
            syllabus_filename=unique_name,
            syllabus_analyzed=False,
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        db.session.add(subject)
        db.session.commit()

        # 업로드 직후 자동 분석 1회
        _run_analysis(subject)

        return redirect(url_for('classroom.classroom_detail', subject_id=subject.id))

    subjects = Subject.query.filter_by(user_id=current_user.id).order_by(Subject.created_at.desc()).all()
    return render_template('classroom.html', subjects=subjects)


@classroom_bp.route('/classroom/<int:subject_id>')
@login_required
def classroom_detail(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    plans = WeeklyPlan.query.filter_by(subject_id=subject_id).order_by(WeeklyPlan.week).all()
    study_plans = (
        StudyPlan.query.filter_by(subject_id=subject_id)
                       .order_by(StudyPlan.id.desc()).all()
    )
    exam_plans = (
        ExamPlan.query.filter_by(subject_id=subject_id)
                      .order_by(ExamPlan.id.desc()).all()
    )
    return render_template('classroom_detail.html',
                           subject=subject,
                           plans=plans,
                           study_plans=study_plans,
                           exam_plans=exam_plans)


@classroom_bp.route('/classroom/<int:subject_id>/analyze', methods=['POST'])
@login_required
def reanalyze(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    if not subject.syllabus_filename:
        flash('업로드된 강의계획서가 없어요.', 'error')
        return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))

    subject.syllabus_analyzed = False
    db.session.commit()
    _run_analysis(subject)
    return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))


@classroom_bp.route('/classroom/<int:subject_id>/weekly-plan/save', methods=['POST'])
@login_required
def save_weekly_plan(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)

    weeks = request.form.getlist('week[]')
    topics = request.form.getlist('topic[]')
    plan_ids = request.form.getlist('plan_id[]')

    WeeklyPlan.query.filter_by(subject_id=subject_id).delete()
    for week_str, topic, plan_id in zip(weeks, topics, plan_ids):
        topic = topic.strip()
        if not topic:
            continue
        try:
            week = int(week_str)
        except ValueError:
            continue
        db.session.add(WeeklyPlan(subject_id=subject_id, week=week, topic=topic))

    db.session.commit()
    flash('주차별 진도가 저장됐어요.', 'success')
    return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))


@classroom_bp.route('/classroom/<int:subject_id>/weekly-plan/add', methods=['POST'])
@login_required
def add_weekly_plan_row(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)

    # 현재 마지막 week 번호 다음으로 추가
    last = WeeklyPlan.query.filter_by(subject_id=subject_id).order_by(WeeklyPlan.week.desc()).first()
    next_week = (last.week + 1) if last else 1
    db.session.add(WeeklyPlan(subject_id=subject_id, week=next_week, topic=""))
    db.session.commit()
    return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))


@classroom_bp.route('/classroom/<int:subject_id>/weekly-plan/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_weekly_plan_row(subject_id, plan_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    plan = WeeklyPlan.query.filter_by(id=plan_id, subject_id=subject_id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))


@classroom_bp.route('/classroom/uploads/<path:filename>')
@login_required
def serve_syllabus(filename):
    subject = Subject.query.filter_by(syllabus_filename=filename, user_id=current_user.id).first_or_404()
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'syllabi')
    return send_from_directory(upload_dir, filename, as_attachment=False)


def _call_llm_for_exam_plan(weekly_items, scope_note, day_list):
    """날짜별 시험 대비 할 일 생성. 실패 시 None 반환."""
    weekly_list = "\n".join(f"{w.week}주차: {w.topic}" for w in weekly_items)
    day_str = "\n".join(f"D-{d['d_day']} ({d['date']})" for d in day_list)
    prompt = _EXAM_PLAN_USER_PROMPT_TEMPLATE.format(
        weekly_list=weekly_list,
        scope_note=scope_note or "없음",
        day_list=day_str,
    )
    client = _make_llm_client()
    try:
        response = client.chat.completions.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            messages=[
                {"role": "system", "content": _EXAM_PLAN_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ]
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw.strip())
        if "daily" not in data or not isinstance(data["daily"], list):
            return None
        return data["daily"]
    except Exception:
        return None


def _call_llm_for_study_plan(weekly_items):
    """WeeklyPlan 목록을 받아 주차별 학습 계획 JSON을 파싱. 실패 시 None 반환."""
    weekly_list = "\n".join(f"{w.week}주차: {w.topic}" for w in weekly_items)
    prompt = _STUDY_PLAN_USER_PROMPT_TEMPLATE.format(weekly_list=weekly_list)
    client = _make_llm_client()
    try:
        response = client.chat.completions.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            messages=[
                {"role": "system", "content": _STUDY_PLAN_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ]
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw.strip())
        if "plan" not in data or not isinstance(data["plan"], list):
            return None
        return data["plan"]
    except Exception:
        return None


@classroom_bp.route('/classroom/<int:subject_id>/study-plan/generate', methods=['POST'])
@login_required
def generate_study_plan(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)

    # 이미 학습 계획이 있으면 차단 (과목당 1개 고정)
    if StudyPlan.query.filter_by(subject_id=subject_id).first():
        return jsonify({'error': '이미 학습 계획이 있어요.'}), 409

    # 등록된 전체 WeeklyPlan 사용
    weekly_items = WeeklyPlan.query.filter_by(subject_id=subject_id).order_by(WeeklyPlan.week).all()
    if not weekly_items:
        return jsonify({'error': '등록된 주차 주제가 없어요.'}), 400

    plan_data = _call_llm_for_study_plan(weekly_items)
    if plan_data is None:
        return jsonify({'error': 'AI 계획 생성에 실패했어요. 다시 시도해 주세요.'}), 500

    week_from = weekly_items[0].week
    week_to   = weekly_items[-1].week
    study_plan = StudyPlan(
        subject_id=subject_id,
        week_from=week_from,
        week_to=week_to,
        name="AI 학습 계획",
        created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    db.session.add(study_plan)
    db.session.flush()

    for entry in plan_data:
        try:
            week  = int(entry['week'])
            topic = str(entry['topic']).strip()
            tasks = entry.get('tasks', [])
        except (KeyError, ValueError, TypeError):
            continue
        for task_text in tasks:
            task_text = str(task_text).strip()
            if not task_text:
                continue
            db.session.add(StudyPlanItem(
                plan_id=study_plan.id,
                week=week,
                topic=topic,
                task=task_text,
                is_done=False,
            ))

    db.session.commit()

    result_items = [
        {'id': item.id, 'week': item.week, 'topic': item.topic,
         'task': item.task, 'is_done': item.is_done}
        for item in StudyPlanItem.query.filter_by(plan_id=study_plan.id)
                                       .order_by(StudyPlanItem.week, StudyPlanItem.id).all()
    ]
    return jsonify({
        'plan_id': study_plan.id,
        'items':   result_items,
    })


@classroom_bp.route('/classroom/<int:subject_id>/study-plan/<int:plan_id>/item/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_study_plan_item(subject_id, plan_id, item_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    item = StudyPlanItem.query.filter_by(id=item_id, plan_id=plan_id).first_or_404()
    item.is_done = not item.is_done
    db.session.commit()
    return jsonify({'is_done': item.is_done})


@classroom_bp.route('/classroom/<int:subject_id>/study-plan/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_study_plan(subject_id, plan_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    plan = StudyPlan.query.filter_by(id=plan_id, subject_id=subject_id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({'ok': True})


@classroom_bp.route('/classroom/<int:subject_id>/exam-plan/generate', methods=['POST'])
@login_required
def generate_exam_plan(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)

    body          = request.json or {}
    exam_date_str = str(body.get('exam_date', '')).strip()
    scope_note    = str(body.get('scope_note', '')).strip() or None
    plan_name     = str(body.get('name', '')).strip()

    try:
        scope_from = int(body.get('scope_from', 1))
        scope_to   = int(body.get('scope_to', 1))
    except (TypeError, ValueError):
        return jsonify({'error': '주차 범위가 올바르지 않아요.'}), 400

    try:
        exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': '시험 날짜가 올바르지 않아요.'}), 400

    today = datetime.now().date()
    if exam_date <= today:
        return jsonify({'error': '시험 날짜는 오늘 이후여야 해요.'}), 400

    # 날짜 목록 코드로 계산 (오늘 ~ 시험 당일)
    total_days = (exam_date - today).days
    day_list = [
        {'date': (today + timedelta(days=i)).strftime('%Y-%m-%d'),
         'd_day': total_days - i}
        for i in range(total_days + 1)
    ]

    weekly_items = WeeklyPlan.query.filter(
        WeeklyPlan.subject_id == subject_id,
        WeeklyPlan.week >= scope_from,
        WeeklyPlan.week <= scope_to,
    ).order_by(WeeklyPlan.week).all()

    if not weekly_items:
        return jsonify({'error': '선택한 범위에 등록된 주차 주제가 없어요.'}), 400

    if not plan_name:
        plan_name = f"{exam_date_str} 시험 대비"

    daily_data = _call_llm_for_exam_plan(weekly_items, scope_note, day_list)
    if daily_data is None:
        return jsonify({'error': 'AI 계획 생성에 실패했어요. 다시 시도해 주세요.'}), 500

    dday_to_date = {d['d_day']: d['date'] for d in day_list}

    exam_plan = ExamPlan(
        subject_id=subject_id,
        name=plan_name,
        exam_date=exam_date_str,
        scope_from=scope_from,
        scope_to=scope_to,
        scope_note=scope_note,
        created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    db.session.add(exam_plan)
    db.session.flush()

    for entry in daily_data:
        try:
            d_day_val = int(entry['d_day'])
            tasks     = entry.get('tasks', [])
        except (KeyError, ValueError, TypeError):
            continue
        plan_date = dday_to_date.get(d_day_val)
        if plan_date is None:
            continue
        for task_text in tasks:
            task_text = str(task_text).strip()
            if not task_text:
                continue
            db.session.add(ExamPlanItem(
                exam_plan_id=exam_plan.id,
                plan_date=plan_date,
                d_day=d_day_val,
                task=task_text,
                is_done=False,
            ))

    db.session.commit()

    result_items = [
        {'id': it.id, 'plan_date': it.plan_date, 'd_day': it.d_day,
         'task': it.task, 'is_done': it.is_done}
        for it in ExamPlanItem.query.filter_by(exam_plan_id=exam_plan.id)
                                    .order_by(ExamPlanItem.d_day.asc(), ExamPlanItem.id).all()
    ]
    return jsonify({
        'plan_id':    exam_plan.id,
        'name':       exam_plan.name,
        'exam_date':  exam_plan.exam_date,
        'created_at': exam_plan.created_at,
        'items':      result_items,
    })


@classroom_bp.route('/classroom/<int:subject_id>/exam-plan/<int:plan_id>/item/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_exam_plan_item(subject_id, plan_id, item_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    item = ExamPlanItem.query.filter_by(id=item_id, exam_plan_id=plan_id).first_or_404()
    item.is_done = not item.is_done
    db.session.commit()
    return jsonify({'is_done': item.is_done})


@classroom_bp.route('/classroom/<int:subject_id>/exam-plan/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_exam_plan(subject_id, plan_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    plan = ExamPlan.query.filter_by(id=plan_id, subject_id=subject_id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({'ok': True})


@classroom_bp.route('/classroom/<int:subject_id>/rename', methods=['POST'])
@login_required
def rename_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    body = request.get_json(silent=True) or {}
    name = str(body.get('name', '')).strip()
    if not name:
        return jsonify({'error': '과목명을 입력해주세요.'}), 400
    if len(name) > 100:
        return jsonify({'error': '과목명은 100자 이내여야 해요.'}), 400
    subject.name = name
    db.session.commit()
    return jsonify({'ok': True, 'name': subject.name})


@classroom_bp.route('/classroom/<int:subject_id>/replace-pdf', methods=['POST'])
@login_required
def replace_pdf(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)

    pdf = request.files.get('syllabus')
    if not pdf or pdf.filename == '':
        flash('PDF 파일을 선택해주세요.', 'error')
        return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))
    if not _allowed_file(pdf.filename):
        flash('PDF 파일만 업로드할 수 있어요.', 'error')
        return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))

    pdf.seek(0, 2)
    if pdf.tell() > MAX_FILE_SIZE:
        flash('파일 크기가 10MB를 초과해요.', 'error')
        return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))
    pdf.seek(0)

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'syllabi')
    safe_name = secure_filename(pdf.filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    pdf.save(os.path.join(upload_dir, unique_name))

    # 이전 파일 삭제
    if subject.syllabus_filename:
        old_path = os.path.join(upload_dir, subject.syllabus_filename)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    subject.syllabus_filename = unique_name
    subject.syllabus_analyzed = False
    db.session.commit()

    # 재분석 (성공 시에만 WeeklyPlan 교체, StudyPlan/ExamPlan은 건드리지 않음)
    ok = _run_analysis(subject)
    if ok:
        flash('강의계획서가 교체됐어요. 주차별 주제가 새로 분석됐어요.', 'success')

    return redirect(url_for('classroom.classroom_detail', subject_id=subject_id))


@classroom_bp.route('/classroom/<int:subject_id>/delete', methods=['POST'])
@login_required
def delete_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)

    # 하위 데이터 삭제 (StudyPlan/ExamPlan은 cascade로 item까지 삭제됨)
    WeeklyPlan.query.filter_by(subject_id=subject_id).delete()
    for sp in StudyPlan.query.filter_by(subject_id=subject_id).all():
        db.session.delete(sp)
    for ep in ExamPlan.query.filter_by(subject_id=subject_id).all():
        db.session.delete(ep)

    # PDF 파일 삭제
    if subject.syllabus_filename:
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'syllabi')
        pdf_path = os.path.join(upload_dir, subject.syllabus_filename)
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass

    db.session.delete(subject)
    db.session.commit()
    return jsonify({'ok': True})
