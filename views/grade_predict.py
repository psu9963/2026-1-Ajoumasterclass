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


# ── 학점 기준 상수 ────────────────────────────────────────────────
GRADE_CRITERIA = """
[학점 판단 기준]
※ 상대평가 기준 (수강인원 정보 있을 때 우선 적용)
- A+/A0: 상위 30% 이내
- B+/B0: 상위 30~60%
- C+/C0: 상위 60~80%
- D+/D0: 상위 80~95%
- F    : 하위 5%

※ 절대평가 참고 기준 (통계 정보 없을 때 적용)
- A+ : 95점 이상
- A0 : 90점 이상
- B+ : 85점 이상
- B0 : 80점 이상
- C+ : 75점 이상
- C0 : 70점 이상
- D+ : 65점 이상
- D0 : 60점 이상
- F  : 60점 미만
"""


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

    total_my  = sum(a.get('my_score', 0)    for a in assignments)
    total_max = sum(a.get('total_score', 0) for a in assignments)

    if total_max == 0:
        return 0, 0, []

    weighted = round((total_my / total_max) * ratio, 2)
    pct      = round((total_my / total_max) * 100, 1)

    detail = []
    for i, a in enumerate(assignments):
        ts = a.get('total_score', 0)
        ms = a.get('my_score', 0)
        detail.append({
            "index":    i + 1,
            "my_score": ms,
            "total":    ts,
            "average":  a.get('average'),
            "pct":      round(ms / ts * 100, 1) if ts else 0,
        })

    return weighted, pct, detail


# ── AI 분석 함수들 ────────────────────────────────────────────────

def ai_midterm_analysis(pred):
    client = get_client()

    my_score    = pred.midterm_score or 0
    total_score = pred.midterm_total or 100
    ratio       = pred.midterm_ratio or 0
    weighted    = calc_normalized(my_score, total_score, ratio)
    pct         = round(my_score / total_score * 100, 1) if total_score else 0

    # ── 입력된 지표만 포함 ──────────────────────────
    stats_lines = []
    if pred.midterm_average:
        stats_lines.append(f"- 반 평균: {pred.midterm_average}점")
    if pred.midterm_median:
        stats_lines.append(f"- 중앙값: {pred.midterm_median}점")
    if pred.midterm_std:
        stats_lines.append(f"- 표준편차: {pred.midterm_std}")

    # ── 분포 해석 (평균+중앙값 둘 다 있을 때만) ────
    skew_comment = ""
    if pred.midterm_average and pred.midterm_median:
        diff = pred.midterm_average - pred.midterm_median
        if diff > 3:
            skew_comment = "평균이 중앙값보다 높아 상위권 점수가 평균을 끌어올린 우편향 분포입니다."
        elif diff < -3:
            skew_comment = "평균이 중앙값보다 낮아 하위권 점수가 평균을 끌어내린 좌편향 분포입니다."
        else:
            skew_comment = "평균과 중앙값이 비슷하여 점수가 고르게 분포된 정규분포에 가깝습니다."

    # ── 통계 정보 유무에 따라 분석 지침 분기 ────────
    if stats_lines:
        stats_section = "\n".join(stats_lines)
        analysis_guide = f"""- 제공된 통계({', '.join(
            ['평균' if pred.midterm_average else '',
             '중앙값' if pred.midterm_median else '',
             '표준편차' if pred.midterm_std else '']
        )})를 활용하여 등수를 예측하세요
- 제공되지 않은 통계는 예측에서 제외하세요
- 반드시 위 [학점 판단 기준]을 참고하여 학점을 결정하세요"""
        if skew_comment:
            analysis_guide += f"\n- 분포 해석: {skew_comment}"
    else:
        stats_section  = "- 통계 정보 없음 (내 점수와 만점만으로 분석)"
        analysis_guide = """- 통계 정보가 없으므로 득점률(%)만으로 학점을 예측하세요
- 등수 예측은 득점률 기반으로 보수적으로 추정하세요
- distribution_type은 '정보 없음'으로 반환하세요
- score_position은 '득점률 기반 추정'으로 반환하세요
- 반드시 위 [학점 판단 기준] 절대평가 기준을 참고하여 학점을 결정하세요"""

    # ── 중간고사만 입력된 상태임을 명시 ────────────
    remaining_ratio = 100 - ratio
    midterm_max_possible = ratio  # 중간고사 만점 환산

    prompt = f"""당신은 대학교 성적 예측 전문가입니다. JSON만 반환하세요.

{GRADE_CRITERIA}

[과목 정보]
- 과목명: {pred.subject_name}
- 수강인원: {pred.total_students or '미입력'}명
- 중간고사 반영비율: {ratio}%

[중간고사 결과]
- 내 점수: {my_score}점 / {total_score}점 만점 ({pct}%)
- 환산 점수(반영 후): {weighted}점 / {midterm_max_possible}점 만점
{stats_section}

[중요 안내]
- 현재 입력된 항목: 중간고사({ratio}%)만 입력된 상태
- 나머지 {remaining_ratio}%는 아직 미입력 (기말/과제/출석/기타)
- predicted_grade_so_far는 중간고사 득점률({pct}%)과 통계 기반으로 현재까지의 예상 학점을 반환하세요
- 나머지 항목 미입력으로 최종 학점은 달라질 수 있음을 comment에 반드시 언급하세요

[분석 지침]
{analysis_guide}

[반환 JSON]
{{
  "weighted_score": {weighted},
  "raw_pct": {pct},
  "predicted_rank_percent": 상위_퍼센트_숫자,
  "score_position": "평균 대비 위치 또는 득점률 기반 추정",
  "distribution_type": "분포 유형 또는 정보 없음",
  "predicted_grade_so_far": "현재까지_예측학점(A+/A0/B+/B0/C+/C0/D+/D0/F)",
  "comment": "중간고사 성적 분석 3문장 (나머지 항목 미입력 언급 포함)",
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

    midterm_weighted  = midterm_data.get('weighted_score', 0)
    combined          = round(float(midterm_weighted) + weighted, 2)
    combined_ratio    = (pred.midterm_ratio or 0) + ratio
    remaining_ratio   = 100 - combined_ratio

    # ── 기말 단독 통계 분석 ──────────────────────────
    stats_lines = []
    if pred.final_average:
        stats_lines.append(f"- 기말 반 평균: {pred.final_average}점 (기말 단독 점수 기준)")
    if pred.final_median:
        stats_lines.append(f"- 기말 중앙값: {pred.final_median}점 (기말 단독 점수 기준)")
    if pred.final_std:
        stats_lines.append(f"- 기말 표준편차: {pred.final_std}")

    # ── 기말 단독 기준 내 위치 계산 ─────────────────
    final_rank_comment = ""
    if pred.final_average:
        diff_from_avg = round(my_score - pred.final_average, 2)
        if diff_from_avg >= 20:
            final_rank_comment = f"기말 단독 기준: 평균({pred.final_average}점) 대비 +{diff_from_avg}점 → 상위 10~15% 추정"
        elif diff_from_avg >= 10:
            final_rank_comment = f"기말 단독 기준: 평균({pred.final_average}점) 대비 +{diff_from_avg}점 → 상위 20~30% 추정"
        elif diff_from_avg >= 0:
            final_rank_comment = f"기말 단독 기준: 평균({pred.final_average}점) 대비 +{diff_from_avg}점 → 상위 40~50% 추정"
        elif diff_from_avg >= -10:
            final_rank_comment = f"기말 단독 기준: 평균({pred.final_average}점) 대비 {diff_from_avg}점 → 상위 50~65% 추정"
        else:
            final_rank_comment = f"기말 단독 기준: 평균({pred.final_average}점) 대비 {diff_from_avg}점 → 상위 65% 이하 추정"

    skew_comment = ""
    if pred.final_average and pred.final_median:
        diff = pred.final_average - pred.final_median
        if diff > 3:
            skew_comment = "기말고사 점수가 우편향 분포 (상위권 쏠림)"
        elif diff < -3:
            skew_comment = "기말고사 점수가 좌편향 분포 (하위권 쏠림)"
        else:
            skew_comment = "기말고사 점수가 정규분포에 가까움"

    if stats_lines:
        stats_section  = "\n".join(stats_lines)
        analysis_guide = f"""- 기말 통계(평균/중앙값)는 기말 단독 점수 기준입니다
- 내 기말 점수({my_score}점)를 기말 평균({pred.final_average}점)과 비교하여 등수를 추정하세요
- {final_rank_comment}
- combined_score({combined}점)는 중간+기말 합산이며 {combined_ratio}점 만점입니다
- combined_score를 기말 통계와 직접 비교하지 마세요 (기준이 다름)
- 반드시 위 [학점 판단 기준]을 참고하여 학점을 결정하세요"""
        if skew_comment:
            analysis_guide += f"\n- 분포 해석: {skew_comment}"
    else:
        stats_section  = "- 통계 정보 없음 (내 점수와 만점만으로 분석)"
        analysis_guide = """- 통계 정보가 없으므로 득점률(%)만으로 학점을 예측하세요
- distribution_type은 '정보 없음'으로 반환하세요
- 반드시 위 [학점 판단 기준] 절대평가 기준을 참고하여 학점을 결정하세요"""

    midterm_pct = midterm_data.get('raw_pct', 0)
    avg_pct     = round((midterm_pct + pct) / 2, 1)

    prompt = f"""당신은 대학교 성적 예측 전문가입니다. JSON만 반환하세요.

{GRADE_CRITERIA}

[과목 정보]
- 과목명: {pred.subject_name}
- 수강인원: {pred.total_students or '미입력'}명
- 중간고사 반영비율: {pred.midterm_ratio}%
- 기말고사 반영비율: {ratio}%

[중간고사]
- 내 점수: {pred.midterm_score}점 / {pred.midterm_total}점 만점
- 환산 점수(반영 후): {midterm_weighted}점

[기말고사]
- 내 점수: {my_score}점 / {total_score}점 만점 (득점률 {pct}%)
- 환산 점수(반영 후): {weighted}점

[기말고사 통계 - 기말 단독 점수 기준]
{stats_section}
- 기말 단독 내 위치: {final_rank_comment}

[중간+기말 합산]
- 합산 점수: {combined}점 / {combined_ratio}점 만점 (득점률 {round(combined/combined_ratio*100,1) if combined_ratio else 0}%)
- 나머지 미입력: {remaining_ratio}%

[⚠️ 중요 주의사항]
- 기말 통계(평균 {pred.final_average}점, 중앙값 {pred.final_median}점)는 기말 100점 만점 기준입니다
- combined_score({combined}점)는 {combined_ratio}점 만점이므로 기말 통계와 직접 비교 절대 금지
- 내 기말 점수({my_score}점) vs 기말 평균({pred.final_average}점) 비교로 등수 추정하세요
- 나머지 {remaining_ratio}%는 중간+기말 평균 득점률({avg_pct}%)로 가정하여 최종 학점 추정
- 반드시 위 [학점 판단 기준]을 참고하여 학점을 결정하세요

[분석 지침]
{analysis_guide}

[반환 JSON]
{{
  "midterm_weighted": {midterm_weighted},
  "final_weighted": {weighted},
  "combined_score": {combined},
  "estimated_total": 나머지_항목_포함_추정_총점,
  "predicted_rank_percent": 상위_퍼센트_숫자,
  "score_position": "기말 평균 대비 위치 명시",
  "distribution_type": "분포 유형 또는 정보 없음",
  "predicted_grade": "예측학점(A+/A0/B+/B0/C+/C0/D+/D0/F)",
  "comment": "기말 단독 통계 기반 분석 3문장 (합산과 기말 통계 혼용 금지)",
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

    assignments      = json.loads(pred.assignment_data) if pred.assignment_data else []
    asg_weighted, asg_pct, asg_detail = calc_assignment_normalized(
        assignments, pred.assignment_ratio or 0
    )

    att_weighted = calc_normalized(
        pred.attendance_score, pred.attendance_total, pred.attendance_ratio or 0
    )
    oth_weighted = calc_normalized(
        pred.other_score, pred.other_total, pred.other_ratio or 0
    )

    midterm_weighted = midterm_data.get('weighted_score', 0)
    final_weighted   = final_data.get('final_weighted', 0)
    total            = round(
        float(midterm_weighted) + float(final_weighted) +
        asg_weighted + att_weighted + oth_weighted, 2
    )

    # ── 입력된 항목 / 미입력 항목 분리 ────────────
    entered_ratio = (pred.midterm_ratio or 0) + (pred.final_ratio or 0)
    missing_items = []

    score_lines = [
        f"- 중간고사: {midterm_weighted}점 (반영 후, {pred.midterm_ratio}%)",
        f"- 기말고사: {final_weighted}점 (반영 후, {pred.final_ratio}%)",
        f"- 과제: {asg_weighted}점 (득점률 {asg_pct}%, {pred.assignment_ratio}%)",
    ]
    entered_ratio += (pred.assignment_ratio or 0)

    if pred.attendance_score:
        score_lines.append(f"- 출석: {att_weighted}점 (반영 후, {pred.attendance_ratio}%)")
        entered_ratio += (pred.attendance_ratio or 0)
    else:
        score_lines.append(f"- 출석: 미입력 (예측에서 제외, {pred.attendance_ratio}%)")
        missing_items.append(f"출석({pred.attendance_ratio}%)")

    if pred.other_score:
        score_lines.append(f"- 기타: {oth_weighted}점 (반영 후, {pred.other_ratio}%)")
        entered_ratio += (pred.other_ratio or 0)
    else:
        score_lines.append(f"- 기타: 미입력 (예측에서 제외, {pred.other_ratio}%)")
        if pred.other_ratio:
            missing_items.append(f"기타({pred.other_ratio}%)")

    missing_str = ", ".join(missing_items) if missing_items else "없음 (모든 항목 입력됨)"

    # ── 중간/기말 통계로 반 평균 총점 추정 ──────────
    midterm_avg = pred.midterm_average or 0
    final_avg   = pred.final_average   or 0

    midterm_avg_weighted = round((midterm_avg / (pred.midterm_total or 100)) * (pred.midterm_ratio or 0), 2) if midterm_avg else 0
    final_avg_weighted   = round((final_avg   / (pred.final_total   or 100)) * (pred.final_ratio   or 0), 2) if final_avg   else 0

    # 과제 평균 환산 (각 과제의 average 필드 활용)
    asg_avg_weighted = 0
    asg_avg_lines    = []
    if assignments:
        total_avg_score = sum(a.get('average', 0) or 0 for a in assignments)
        total_max_score = sum(a.get('total_score', 0) or 0 for a in assignments)
        if total_max_score > 0:
            asg_avg_weighted = round((total_avg_score / total_max_score) * (pred.assignment_ratio or 0), 2)
            asg_avg_lines.append(
                f"- 과제 평균 합계: {total_avg_score}/{total_max_score}점 → 환산 {asg_avg_weighted}점"
            )

    class_avg_total = round(midterm_avg_weighted + final_avg_weighted + asg_avg_weighted, 2)
    my_vs_avg_diff  = round(total - class_avg_total, 2)

    # ── 반 평균 대비 내 위치 추정 ───────────────────
    if class_avg_total > 0:
        if my_vs_avg_diff >= 15:
            rank_estimate = "상위 10~20% 추정 (반 평균 대비 +15점 이상)"
        elif my_vs_avg_diff >= 10:
            rank_estimate = "상위 20~30% 추정 (반 평균 대비 +10점 이상)"
        elif my_vs_avg_diff >= 5:
            rank_estimate = "상위 30~40% 추정 (반 평균 대비 +5점 이상)"
        elif my_vs_avg_diff >= 0:
            rank_estimate = "상위 40~55% 추정 (반 평균 근처)"
        elif my_vs_avg_diff >= -5:
            rank_estimate = "상위 55~65% 추정 (반 평균 소폭 하회)"
        else:
            rank_estimate = "상위 65% 이하 추정 (반 평균 하회)"
    else:
        rank_estimate = "통계 정보 부족으로 득점률 기반 추정"

    # ── 통계 섹션 구성 ───────────────────────────────
    stats_section_lines = []
    if midterm_avg_weighted:
        stats_section_lines.append(
            f"- 중간고사 반 평균 환산: {midterm_avg_weighted}점 (평균 {midterm_avg}점 기준)"
        )
    if final_avg_weighted:
        stats_section_lines.append(
            f"- 기말고사 반 평균 환산: {final_avg_weighted}점 (평균 {final_avg}점 기준)"
        )
    if asg_avg_lines:
        stats_section_lines.extend(asg_avg_lines)
    if class_avg_total > 0:
        stats_section_lines.append(
            f"- 추정 반 평균 총점: {class_avg_total}점"
        )
        stats_section_lines.append(
            f"- 내 점수 vs 반 평균: {total}점 - {class_avg_total}점 = {my_vs_avg_diff:+.2f}점"
        )
        stats_section_lines.append(
            f"- 위치 추정: {rank_estimate}"
        )

    stats_section = "\n".join(stats_section_lines) if stats_section_lines else "- 통계 정보 없음"

    prompt = f"""당신은 대학교 성적 예측 전문가입니다. JSON만 반환하세요.

{GRADE_CRITERIA}

[과목 정보]
- 과목명: {pred.subject_name}
- 수강인원: {pred.total_students or '미입력'}명

[반영 비율]
- 중간고사: {pred.midterm_ratio}%
- 기말고사: {pred.final_ratio}%
- 과제: {pred.assignment_ratio}%
- 출석: {pred.attendance_ratio}% {'(미입력)' if not pred.attendance_score else ''}
- 기타: {pred.other_ratio}% {'(미입력)' if not pred.other_score else ''}

[환산 점수 (내 점수)]
{chr(10).join(score_lines)}
- 현재 합계: {total}점 (입력된 {entered_ratio}% 기준)

[반 평균 통계 기반 위치 분석]
{stats_section}

[미입력 항목]
- {missing_str}

[과제 상세]
{json.dumps(asg_detail, ensure_ascii=False)}

[⚠️ 중요 안내]
- total_score {total}점은 입력된 항목({entered_ratio}%)만의 합산입니다
- 반드시 반 평균 통계({class_avg_total}점)와 비교하여 상대평가 기준으로 학점을 결정하세요
- 절대평가(80점=B0)가 아닌 상대평가(반 평균 대비 위치)를 우선 적용하세요
- 위치 추정: {rank_estimate}
- 미입력 항목({missing_str})은 0점 처리되어 실제와 다를 수 있음을 overall_comment에 언급하세요
- 반드시 위 [학점 판단 기준]을 참고하여 학점을 결정하세요

[반환 JSON]
{{
  "midterm_weighted": {midterm_weighted},
  "final_weighted": {final_weighted},
  "assignment_weighted": {asg_weighted},
  "attendance_weighted": {att_weighted},
  "other_weighted": {oth_weighted},
  "total_score": {total},
  "class_avg_total": {class_avg_total},
  "my_vs_avg_diff": {my_vs_avg_diff},
  "predicted_grade": "최종예측학점(A+/A0/B+/B0/C+/C0/D+/D0/F)",
  "predicted_rank_percent": 상위_퍼센트_숫자,
  "overall_comment": "최종 성적 종합 평가 3문장 (반 평균 대비 위치 및 미입력 항목 언급 포함)",
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

    pred.assignment_data  = json.dumps(data.get('assignments', []), ensure_ascii=False)
    pred.attendance_score = data.get('attendance_score')
    pred.attendance_total = data.get('attendance_total', 100)
    pred.other_score      = data.get('other_score')
    pred.other_total      = data.get('other_total', 100)
    pred.current_step     = 4

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
