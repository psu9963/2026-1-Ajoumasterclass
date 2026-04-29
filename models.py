from flask_sqlalchemy import SQLAlchemy

# 데이터베이스 객체 생성
db = SQLAlchemy()

# 회원 정보 테이블(표) 설계
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True) # 회원 번호 (1, 2, 3... 자동 생성)
    userid = db.Column(db.String(50), unique=True, nullable=False) # 아이디 (중복 불가)
    password = db.Column(db.String(100), nullable=False) # 비밀번호
