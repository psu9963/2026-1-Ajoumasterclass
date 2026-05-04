from flask import Blueprint, render_template, session, redirect, url_for
from functools import wraps
from models import db, StudyRecord
from datetime import datetime, timedelta, date

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
def dashboard():
    # 1. 모든 학습 기록 가져오기 (빈 폴더용 시간 0짜리는 제외)
    valid_records = StudyRecord.query.filter(StudyRecord.duration_hours > 0).all()
    
    # 2. 총 학습 시간 계산
    total_hours = sum(r.duration_hours for r in valid_records)
    
    # 3. 학습 중인 과목 수 계산 (중복 제거)
    unique_subjects = set(r.subject for r in valid_records)
    subject_count = len(unique_subjects)
    
    # 4. 이번 주 학습 시간 계산 (월요일부터 오늘까지)
    today_date = date.today() # 현재 '시간'은 빼고 '날짜'만 가져옵니다.
    start_of_week = today_date - timedelta(days=today_date.weekday()) # 이번 주 월요일 날짜

    # 🌟 5. 과목별 학습 비율 계산 (새로 추가)
    subject_hours = {}
    for r in valid_records:
        if r.subject in subject_hours:
            subject_hours[r.subject] += r.duration_hours
        else:
            subject_hours[r.subject] = r.duration_hours
            
    # 차트에 넣기 위해 이름(labels)과 시간(data)을 각각 리스트로 쪼갭니다.
    import json
    subject_labels = json.dumps(list(subject_hours.keys())) # ['수학', '영어']
    subject_data = json.dumps(list(subject_hours.values())) # [10.5, 5.0]
    
    weekly_hours = 0
    for r in valid_records:
        if r.study_date:
            try:
                # DB에 저장된 "2024-05-20" 형태의 글자를 진짜 날짜(date)로 바꿉니다.
                record_date = datetime.strptime(r.study_date, '%Y-%m-%d').date()
                
                # 그 날짜가 이번 주 월요일보다 크거나 같으면(즉, 이번주면) 더합니다!
                if record_date >= start_of_week:
                    weekly_hours += r.duration_hours
            except ValueError:
                pass
                
    # 5. 최근 학습 기록 (최신순으로 3개만 가져오기)
    recent_records = StudyRecord.query.filter(StudyRecord.duration_hours > 0).order_by(StudyRecord.study_date.desc()).limit(3).all()
    
    return render_template(
        'dashboard.html', 
        username= session.get('username', '사용자'), 
        total_hours=round(total_hours, 1), 
        weekly_hours=round(weekly_hours, 1), 
        subject_count=subject_count,
        recent_records=recent_records,
        subject_labels=subject_labels,
        subject_data=subject_data
    )