from flask import Flask, render_template, redirect, request, url_for
from views.login import login_bp
from views.dashboard import dashboard_bp
from views.study_history import study_history_bp
from views.ai_plan import ai_plan_bp
from views.analysis import analysis_bp
from models import db, User
from flask_login import login_user, LoginManager
import requests
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

#연결 끊김 방지용
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,      # 280초마다 연결 선을 아예 새것으로 교체
    'pool_pre_ping': True     # 쿼리를 날리기 전에 연결이 살아있는지 확인
}
db.init_app(app)

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

# ── 블루프린트 등록 ───────────────────────────────
app.register_blueprint(login_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(study_history_bp)
app.register_blueprint(ai_plan_bp)
app.register_blueprint(analysis_bp)

# ── 홈 ───────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

# ── 유저 로더 ─────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

if __name__ == '__main__':
    app.run(debug=True, port=5001)
