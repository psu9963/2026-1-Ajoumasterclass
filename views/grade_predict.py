import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from openai import OpenAI
from dotenv import load_dotenv
from models import db, GradePrediction

load_dotenv()

grade_predict_bp = Blueprint('grade_predict', __name__)


def get_client():
    return OpenAI(
        api_key=os.getenv("AJOU_API_KEY"),
        base_url="https://factchat-cloud.mindlogic.ai/v1/gateway"
    )


def parse_json_response(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ── 환산 점수 계산 헬퍼 ──────────────────────────────────────────
def calc_normalized(my_score, total_score, ratio):
    """내 점수 / 총점 * 비율 = 환산 점수"""
    if not my_score or not total_score or total_score == 0:
        return 0
    return round((my_score / total_score) * ratio, 2)


def calc_assignment_normalized(assignments, ratio):
    """
    과제 목록: [{"my_score": 18, "total_score": 20, "average": 15}, ...]
    전체 과제 합산 후 비율 환산
    """
    if not assignments:
        return 0, 0, []
    
    total_my    = sum(a.get('my_score', 0)    for a in assignments)
    total_max   = sum(a.get('total_score', 0) for a in assignments)
    
    if total_max == 0:
        return 0, 0, []
    
    weighted = round((total_my / total_max) * ratio, 2)
    pct      = round((total_my / total_max) * 100, 1)
    
    detail = []
    for i, a in enumerate(assignments):
        ts = a.get('total_score', 0)
        ms = a.get('my_score', 0)
        detail.append({
            "index":      i + 1,
            "my_score":   ms,
            "total":      ts,
            "average":    a.get('average'),
            "pct":        round(ms / ts * 100, 1) if ts else 0,
        })
    
    return weighted, pct, detail


# ── AI 분석 함수들 ────────────────────────────────────────────────

def ai_midterm_analysis(pred):
    client = get_client()

    my_score    = pred.midterm_score    or 0
    total_score = pred.midterm_total    or 100
    ratio       = pred.midterm_ratio    or 0
    weighted    = calc_normalized(my_score, total_score, ratio)
    pct         = round(my_score / total_score * 100, 1) if total_score else 0

    skew_comment = ""
    if pred.midterm_average and pred.midterm_median:
        diff = pred.midterm_average - pred.midterm_median
        if diff > 3:
            skew_comment = "평균이 중앙값보다 높아 상위권 점수가 평균을 끌어올린 우편향 분포입니다."
        elif diff < -3:
            skew_comment = "평균이 중앙값보다 낮아 하위권 점수가 평균을 끌어내린 좌편향 분포입니다."
        else:
            skew_comment = "평균과 중앙값이 비슷하여 점수가 고르게 분포된 정규분포에 가깝습니다."

    prompt = f"""당신은 대학교 성적 예측 전문가입니다. JSON만 반환하세요.

[과목 정보]
- 과목명: {pred.subject_name}
- 수강인원: {pred.total_students or '미입력'}명
- 중간고사 반영비율: {ratio}%

[중간고사 결과]
- 내 점수: {my_score}점 / {total_score}점 만점 ({pct}%)
- 환산 점수(반영 후): {weighted}점
- 반 평균: {pred.midterm_average or '미입력'}점
- 중앙값: {pred.midterm_median or '미입력'}점
- 표준편차: {pred.midterm_std or '미입력'}
- 분포 해석: {skew_comment or '데이터 부족'}

[분석 지침]
- 환산 점수 기준으로 현재까지의 예측 학점을 계산하세요
- 평균과 중앙값이 모두 있으면 점수 분포의 왜도를 고려하여 등수를 예측하세요

[반환 JSON]
{{
  "weighted_score": {weighted},
  "raw_pct": {pct},
  "predicted_rank_percent": 상위_퍼센트_숫자,
  "score_position": "평균 대비 위치 (예: 평균+1.2σ)",
  "distribution_type": "분포 유형 (정규/우편향/좌편향)",
  "predicted_grade_so_far": "현재까지_예측학점(A+/A0/B+/B0/C+/C0/D+/D0/F)",
  "comment": "중간고사 성적 분석 3문장 (만점 대비 득점률, 분포 해석 포함)",
  "next_step_tip": "기말고사를 위한 조언 2문장"
}}"""

    res = client.chat.completions.create(
        model="claude-sonnet-4-6",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}]
    )
    return parse_json_response(res.choices[0].message.content)


def ai_final_analysis(pred):
    client = get_client()
    midterm_data = json.loads(pred.midterm_analysis) if pred.midterm_analysis else {}

    my_score    = pred.final_score or 0
    total_score = pred.final_total or 100
    ratio       = pred.final_ratio or 0
    weighted    = calc_normalized(my_score, total_score, ratio)
    pct         = round(my_score / total_score * 100, 1) if total_score else 0

    skew_comment = ""
    if pred.final_average and pred.final_median:
        diff = pred.final_average - pred.final_median
        if diff > 3:
            skew_comment = "기말고사 점수가 우편향 분포 (상위권 쏠림)"
        elif diff < -3:
            skew_comment = "기말고사 점수가 좌편향 분포 (하위권 쏠림)"
        else:
            skew_comment = "기말고사 점수가 정규분포에 가까움"

    midterm_weighted = midterm_data.get('weighted_score', 0)
    combined         = round(float(midterm_weighted) + weighted, 2)

    prompt = f"""당신은 대학교 성적 예측 전문가입니다. JSON만 반환하세요.

[과목 정보]
- 과목명: {pred.subject_name}
- 수강인원: {pred.total_students or '미입력'}명
- 중간고사 반영비율: {pred.midterm_ratio}%
- 기말고사 반영비율: {ratio}%

[중간고사]
- 내 점수: {pred.midterm_score}점 / {pred.midterm_total}점 만점
- 반영 후: {midterm_weighted}점

[기말고사]
- 내 점수: {my_score}점 / {total_score}점 만점 ({pct}%)
- 반영 후: {weighted}점
- 중간+기말 합산: {combined}점
- 반 평균: {pred.final_average or '미입력'}점
- 중앙값: {pred.final_median or '미입력'}점
- 표준편차: {pred.final_std or '미입력'}
- 분포 해석: {skew_comment or '데이터 부족'}

[반환 JSON]
{{
  "midterm_weighted": {midterm_weighted},
  "final_weighted": {weighted},
  "combined_score": {combined},
  "predicted_rank_percent": 상위_퍼센트_숫자,
  "score_position": "평균/중앙값 대비 위치",
  "distribution_type": "분포 유형",
  "predicted_grade": "예측학점(A+/A0/B+/B0/C+/C0/D+/D0/F)",
  "comment": "중간+기말 합산 분석 3문장 (만점 대비 득점률, 분포 해석 포함)",
  "remaining_tip": "남은 과제/출석으로 학점 올리는 조언 2문장"
}}"""

    res = client.chat.completions.create(
        model="claude-sonnet-4-6",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}]
    )
    return parse_json_response(res.choices[0].message.content)


def ai_final_result(pred):
    midterm_data = json.loads(pred.midterm_analysis) if pred.midterm_analysis else {}
    final_data   = json.loads(pred.final_analysis)   if pred.final_analysis   else {}

    # 과제 환산
    assignments      = json.loads(pred.assignment_data) if pred.assignment_data else []
    asg_weighted, asg_pct, asg_detail = calc_assignment_normalized(
        assignments, pred.assignment_ratio or 0
    )

    # 출석 환산
    att_weighted = calc_normalized(
        pred.attendance_score, pred.attendance_total, pred.attendance_ratio or 0
    )

    # 기타 환산
    oth_weighted = calc_normalized(
        pred.other_score, pred.other_total, pred.other_ratio or 0
    )

    midterm_weighted = midterm_data.get('weighted_score', 0)
    final_weighted   = final_data.get('final_weighted', 0)
    total            = round(
        float(midterm_weighted) + float(final_weighted) +
        asg_weighted + att_weighted + oth_weighted, 2
    )

    prompt = f"""당신은 대학교 성적 예측 전문가입니다. JSON만 반환하세요.

[과목 정보]
- 과목명: {pred.subject_name}
- 수강인원: {pred.total_students or '미입력'}명

[반영 비율]
- 중간고사: {pred.midterm_ratio}%
- 기말고사: {pred.final_ratio}%
- 과제: {pred.assignment_ratio}%
- 출석: {pred.attendance_ratio}%
- 기타: {pred.other_ratio}%

[환산 점수]
- 중간고사: {midterm_weighted}점
- 기말고사: {final_weighted}점
- 과제: {asg_weighted}점 (득점률 {asg_pct}%)
- 출석: {att_weighted}점
- 기타: {oth_weighted}점
- 최종 합계: {total}점

[과제 상세]
{json.dumps(asg_detail, ensure_ascii=False)}

[반환 JSON]
{{
  "midterm_weighted": {midterm_weighted},
  "final_weighted": {final_weighted},
  "assignment_weighted": {asg_weighted},
  "attendance_weighted": {att_weighted},
  "other_weighted": {oth_weighted},
  "total_score": {total},
  "predicted_grade": "최종예측학점(A+/A0/B+/B0/C+/C0/D+/D0/F)",
  "predicted_rank_percent": 상위_퍼센트_숫자,
  "overall_comment": "최종 성적 종합 평가 3문장",
  "grade_up_tips": ["팁1", "팁2", "팁3"]
}}"""

    res = get_client().chat.completions.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return parse_json_response(res.choices[0].message.content)


# ── 라우트 ────────────────────────────────────────────────────────

@grade_predict_bp.route('/grade-predict')
@login_required
def grade_predict():
    raw_list = GradePrediction.query.filter_by(
        user_id=current_user.id
    ).order_by(GradePrediction.created_at.desc()).all()

    predictions = []
    for p in raw_list:
        predictions.append({
            'id':               p.id,
            'subject_name':     p.subject_name,
            'current_step':     p.current_step,
            'total_students':   p.total_students,
            'midterm_ratio':    p.midterm_ratio    or 0,
            'final_ratio':      p.final_ratio      or 0,
            'assignment_ratio': p.assignment_ratio or 0,
            'attendance_ratio': p.attendance_ratio or 0,
            'other_ratio':      p.other_ratio      or 0,
            'midterm_score':    p.midterm_score    or 0,
            'midterm_total':    p.midterm_total    or 100,
            'final_score':      p.final_score      or 0,
            'final_total':      p.final_total      or 100,
            'midterm_data': json.loads(p.midterm_analysis) if p.midterm_analysis else None,
            'final_data':   json.loads(p.final_analysis)   if p.final_analysis   else None,
            'result_data':  json.loads(p.final_result)     if p.final_result     else None,
        })

    return render_template('grade_predict.html', predictions=predictions)


@grade_predict_bp.route('/grade-predict/create', methods=['POST'])
@login_required
def create():
    data = request.get_json()
    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    pred = GradePrediction(
        user_id          = current_user.id,
        subject_name     = data['subject_name'],
        total_students   = data.get('total_students'),
        midterm_ratio    = data.get('midterm_ratio', 30),
        final_ratio      = data.get('final_ratio', 40),
        assignment_ratio = data.get('assignment_ratio', 20),
        attendance_ratio = data.get('attendance_ratio', 10),
        other_ratio      = data.get('other_ratio', 0),
        current_step     = 1,
        created_at       = now,
    )
    db.session.add(pred)
    db.session.commit()
    return jsonify({'success': True, 'id': pred.id})


@grade_predict_bp.route('/grade-predict/midterm/<int:pred_id>', methods=['POST'])
@login_required
def midterm(pred_id):
    pred = GradePrediction.query.get_or_404(pred_id)
    if pred.user_id != current_user.id:
        return jsonify({'success': False}), 403

    data = request.get_json()
    pred.midterm_score   = data.get('midterm_score')
    pred.midterm_total   = data.get('midterm_total', 100)
    pred.midterm_average = data.get('midterm_average')
    pred.midterm_median  = data.get('midterm_median')
    pred.midterm_std     = data.get('midterm_std')
    pred.current_step    = 2

    try:
        result = ai_midterm_analysis(pred)
        pred.midterm_analysis = json.dumps(result, ensure_ascii=False)
        db.session.commit()
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@grade_predict_bp.route('/grade-predict/final/<int:pred_id>', methods=['POST'])
@login_required
def final(pred_id):
    pred = GradePrediction.query.get_or_404(pred_id)
    if pred.user_id != current_user.id:
        return jsonify({'success': False}), 403

    data = request.get_json()
    pred.final_score   = data.get('final_score')
    pred.final_total   = data.get('final_total', 100)
    pred.final_average = data.get('final_average')
    pred.final_median  = data.get('final_median')
    pred.final_std     = data.get('final_std')
    pred.current_step  = 3

    try:
        result = ai_final_analysis(pred)
        pred.final_analysis = json.dumps(result, ensure_ascii=False)
        db.session.commit()
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@grade_predict_bp.route('/grade-predict/result/<int:pred_id>', methods=['POST'])
@login_required
def result(pred_id):
    pred = GradePrediction.query.get_or_404(pred_id)
    if pred.user_id != current_user.id:
        return jsonify({'success': False}), 403

    data = request.get_json()

    # 과제 데이터 (배열)
    pred.assignment_data  = json.dumps(data.get('assignments', []), ensure_ascii=False)

    # 출석
    pred.attendance_score = data.get('attendance_score')
    pred.attendance_total = data.get('attendance_total', 100)

    # 기타
    pred.other_score      = data.get('other_score')
    pred.other_total      = data.get('other_total', 100)

    pred.current_step = 4

    try:
        result_data = ai_final_result(pred)
        pred.final_result = json.dumps(result_data, ensure_ascii=False)
        db.session.commit()
        return jsonify({'success': True, 'result': result_data})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@grade_predict_bp.route('/grade-predict/delete/<int:pred_id>', methods=['DELETE'])
@login_required
def delete_prediction(pred_id):
    pred = GradePrediction.query.get_or_404(pred_id)
    if pred.user_id != current_user.id:
        return jsonify({'success': False}), 403
    db.session.delete(pred)
    db.session.commit()
    return jsonify({'success': True})
