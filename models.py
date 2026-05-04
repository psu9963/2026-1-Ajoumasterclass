from flask_sqlalchemy import SQLAlchemy

# 데이터베이스 객체 생성
db = SQLAlchemy()

# 회원 정보 테이블(표) 설계
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True) # 회원 번호 (1, 2, 3... 자동 생성)
    userid = db.Column(db.String(50), unique=True, nullable=False) # 아이디 (중복 불가)
    password = db.Column(db.String(100), nullable=False) # 비밀번호

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