from datetime import datetime, date, timedelta


def compute_time_totals(records):
    """학습 기록 목록에서 전체 학습 시간과 이번 주(월~일) 학습 시간을 분 단위로 계산."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    total_minutes = 0
    week_minutes = 0
    for r in records:
        minutes = r.duration_hours * 60
        total_minutes += minutes
        try:
            r_date = datetime.strptime(r.study_date, '%Y-%m-%d').date()
        except ValueError:
            continue
        if week_start <= r_date <= week_end:
            week_minutes += minutes

    return round(total_minutes), round(week_minutes)
