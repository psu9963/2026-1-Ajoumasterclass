from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import date

# 데이터베이스 객체 생성
db = SQLAlchemy()

# 회원 정보 테이블(표) 설계
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True) # 회원 번호 (1, 2, 3... 자동 생성)
    username = db.Column(db.String(50), nullable=False) # 아이디 (중복 불가)
    password = db.Column(db.String(255), nullable=True) # 비밀번호
    provider = db.Column(db.String(50)) # 'kakao', 'google' 등
    social_id = db.Column(db.String(100), unique=True) # 소셜에서 주는 고유 번호

class StudyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True) # 고유 번호
    user_id = db.Column(db.Integer, nullable=False) # 유저 id (동원 추가)
    subject = db.Column(db.String(100), nullable=False) # 과목명
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

