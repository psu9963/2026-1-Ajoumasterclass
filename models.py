from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import date, datetime


# 데이터베이스 객체 생성
db = SQLAlchemy()

# 회원 정보 테이블(표) 설계
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True) # 회원 번호 (1, 2, 3... 자동 생성)
    username = db.Column(db.String(50), nullable=False) # 아이디 (중복 불가)
    password = db.Column(db.String(255), nullable=True) # 비밀번호
    provider = db.Column(db.String(50)) # 'kakao', 'google' 등
    social_id = db.Column(db.String(100), unique=True) # 소셜에서 주는 고유 번호
    display_name = db.Column(db.String(100), nullable=True)
    profile_image = db.Column(db.String(255), nullable=True)

class StudyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True) # 고유 번호
    user_id = db.Column(db.Integer, nullable=False) # 유저 id (동원 추가)
    subject = db.Column(db.String(100), nullable=False) # 과목명
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True) # 강의실(Subject) 연결(선택)
    duration_hours = db.Column(db.Float, nullable=False) # 학습 시간 (예: 1.5시간)
    study_date = db.Column(db.String(20), nullable=False) # 학습 날짜 (예: 2023-10-25)
    memo = db.Column(db.Text) # 메모 (선택 사항)

class AIPlan(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, nullable=False)
    subject      = db.Column(db.String(100), nullable=False)
    goal_weeks   = db.Column(db.Integer, nullable=False)
    plan_content = db.Column(db.Text, nullable=False)
    created_at   = db.Column(db.String(30), nullable=False)

class AIFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    feedback_content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.String(30), nullable=False)

class WeeklyGoal(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, nullable=False)
    goal_hours = db.Column(db.Float, nullable=False, default=10.0)
    week_start = db.Column(db.String(20), nullable=False)  # '2024-05-20'

class DailyGoal(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, nullable=False)
    goal_date = db.Column(db.String(20), nullable=False)   # '2024-05-20'
    goal_text = db.Column(db.String(200), nullable=False)
    is_done   = db.Column(db.Boolean, default=False)

class WeeklyCoaching(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, nullable=False)
    week_start = db.Column(db.String(20), nullable=False)  # '2024-05-20' (월요일)
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.String(30), nullable=False)

class PlanCoaching(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, nullable=False, unique=True)
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.String(30), nullable=False)

class CalendarEvent(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, nullable=False)
    title       = db.Column(db.String(200), nullable=False)       # 일정 제목
    description = db.Column(db.Text)                              # 상세 내용
    start_date  = db.Column(db.String(20), nullable=False)        # '2024-05-20'
    end_date    = db.Column(db.String(20))                        # 종료일 (선택)
    start_time  = db.Column(db.String(10))                        # '09:00' (선택)
    end_time    = db.Column(db.String(10))                        # '11:00' (선택)
    color       = db.Column(db.String(20), default='blue')        # 색상 카테고리
    category    = db.Column(db.String(50), default='일반')         # 카테고리명
    created_at  = db.Column(db.String(30), nullable=False)

class GradePrediction(db.Model):
    __tablename__ = 'grade_predictions'

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject_name     = db.Column(db.String(100), nullable=False)
    total_students   = db.Column(db.Integer)
    created_at       = db.Column(db.String(30))
    current_step     = db.Column(db.Integer, default=1)

    # 반영 비율
    midterm_ratio    = db.Column(db.Float, default=30)
    final_ratio      = db.Column(db.Float, default=40)
    assignment_ratio = db.Column(db.Float, default=20)
    attendance_ratio = db.Column(db.Float, default=10)
    other_ratio      = db.Column(db.Float, default=0)

    # 중간고사
    midterm_score    = db.Column(db.Float)
    midterm_total    = db.Column(db.Float, default=100)   # ← 추가
    midterm_average  = db.Column(db.Float)
    midterm_median   = db.Column(db.Float)                # ← 추가
    midterm_std      = db.Column(db.Float)
    midterm_analysis = db.Column(db.Text)

    # 기말고사
    final_score      = db.Column(db.Float)
    final_total      = db.Column(db.Float, default=100)   # ← 추가
    final_average    = db.Column(db.Float)
    final_median     = db.Column(db.Float)                # ← 추가
    final_std        = db.Column(db.Float)
    final_analysis   = db.Column(db.Text)

    # 과제 (JSON 배열)
    assignment_data  = db.Column(db.Text)                 # ← 추가

    # 출석
    attendance_score = db.Column(db.Float)
    attendance_total = db.Column(db.Float, default=100)   # ← 추가

    # 기타
    other_score      = db.Column(db.Float)
    other_total      = db.Column(db.Float, default=100)   # ← 추가

    # 최종 결과
    final_result     = db.Column(db.Text)
    
class Subject(db.Model):
    id                 = db.Column(db.Integer, primary_key=True)
    user_id            = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name               = db.Column(db.String(100), nullable=False)
    start_date         = db.Column(db.String(20), nullable=True)
    syllabus_filename  = db.Column(db.String(255), nullable=True)
    syllabus_analyzed  = db.Column(db.Boolean, default=False)
    created_at         = db.Column(db.String(30), nullable=False)

class WeeklyPlan(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    week       = db.Column(db.Integer, nullable=False)
    topic      = db.Column(db.String(200), nullable=False)

class StudyPlan(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    week_from  = db.Column(db.Integer, nullable=False)
    week_to    = db.Column(db.Integer, nullable=False)
    name       = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.String(30), nullable=False)
    items      = db.relationship('StudyPlanItem', backref='plan', lazy=True, cascade='all, delete-orphan')

class StudyPlanItem(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('study_plan.id'), nullable=False)
    week    = db.Column(db.Integer, nullable=False)
    topic   = db.Column(db.String(200), nullable=False)
    task    = db.Column(db.String(400), nullable=False)
    is_done = db.Column(db.Boolean, default=False, nullable=False)

class ExamPlan(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    exam_date  = db.Column(db.String(20), nullable=False)
    scope_from = db.Column(db.Integer, nullable=False)
    scope_to   = db.Column(db.Integer, nullable=False)
    scope_note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.String(30), nullable=False)
    items      = db.relationship('ExamPlanItem', backref='exam_plan', lazy=True, cascade='all, delete-orphan')

class ExamPlanItem(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    exam_plan_id = db.Column(db.Integer, db.ForeignKey('exam_plan.id'), nullable=False)
    plan_date    = db.Column(db.String(20), nullable=False)
    d_day        = db.Column(db.Integer, nullable=False)
    task         = db.Column(db.String(400), nullable=False)
    is_done      = db.Column(db.Boolean, default=False, nullable=False)

