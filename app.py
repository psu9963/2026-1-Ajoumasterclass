from flask import Flask, render_template
from datetime import datetime as _dt
from views.login import login_bp
from views.dashboard import dashboard_bp
from views.study_history import study_history_bp
from views.classroom import classroom_bp
from views.analysis import analysis_bp
from views.mypage import mypage_bp
from views.calendar import calendar_bp
from views.grade_predict import grade_predict_bp
from models import db, User
from flask_login import LoginManager
from dotenv import load_dotenv
import os

load_dotenv()

# ── 앱 생성 ──────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# ── DB 설정 ──────────────────────────────────────
db_url = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
print("🔥 현재 연결된 DB 주소는:", db_url)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

#연결 끊김 방지용
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,      # 280초마다 연결 선을 아예 새것으로 교체
    'pool_pre_ping': True     # 쿼리를 날리기 전에 연결이 살아있는지 확인
}
db.init_app(app)

@app.template_filter('exam_date_label')
def exam_date_label_filter(date_str):
    try:
        d = _dt.strptime(date_str, '%Y-%m-%d')
        days = ['월', '화', '수', '목', '금', '토', '일']
        return f"{d.month}월 {d.day}일({days[d.weekday()]})"
    except Exception:
        return date_str


@app.template_filter('minutes_label')
def minutes_label_filter(minutes):
    """분을 '45분' / '1시간' / '1시간 20분' 형식으로 표시."""
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes}분"
    hours, mins = divmod(minutes, 60)
    return f"{hours}시간 {mins}분" if mins else f"{hours}시간"

# ── 로그인 매니저 ─────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login.login'

# ── 환경변수 ──────────────────────────────────────
KAKAO_CLIENT_ID      = os.getenv("KAKAO_CLIENT_ID")
KAKAO_REDIRECT_URI   = os.getenv("KAKAO_REDIRECT_URI")
KAKAO_CLIENT_SECRET  = os.getenv("KAKAO_CLIENT_SECRET")
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI")

# ── DB 테이블 생성 ────────────────────────────────
with app.app_context():
    db.create_all()
    # 기존 subject 테이블에 syllabus_analyzed 컬럼이 없으면 추가
    try:
        db.session.execute(db.text("ALTER TABLE subject ADD COLUMN syllabus_analyzed BOOLEAN DEFAULT 0"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text("ALTER TABLE study_plan ADD COLUMN name VARCHAR(100)"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text("ALTER TABLE user ADD COLUMN display_name VARCHAR(100)"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text("ALTER TABLE user ADD COLUMN profile_image VARCHAR(255)"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text("ALTER TABLE study_record ADD COLUMN subject_id INTEGER"))
        db.session.commit()
    except Exception:
        db.session.rollback()

# ── 블루프린트 등록 ───────────────────────────────
app.register_blueprint(login_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(study_history_bp)
app.register_blueprint(grade_predict_bp)
app.register_blueprint(classroom_bp)
app.register_blueprint(analysis_bp)
app.register_blueprint(mypage_bp)
app.register_blueprint(calendar_bp)

# ── 홈 ───────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

# ── 유저 로더 ─────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))

    
