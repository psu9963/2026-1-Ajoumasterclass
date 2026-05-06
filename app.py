from flask import Flask, render_template, redirect, request, url_for
from views.login import login_bp
from models import db
from views.dashboard import dashboard_bp
from views.study_history import study_history_bp
from views.ai_plan import ai_plan_bp
from flask_login import login_user, LoginManager
import requests
from models import User
from dotenv import load_dotenv
import os

load_dotenv()  # .env 파일 로드

# 1. 🌟 가장 먼저 플라스크 앱(app)을 만들어 줍니다! 🌟
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 2. 앱이 만들어진 후에 데이터베이스 설정을 해줍니다.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. 앱에 데이터베이스 연결
db.init_app(app)

# 서버가 켜질 때 데이터베이스 표 생성
with app.app_context():
    db.create_all()

# 🌟 환경변수에서 불러오기
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# 블루프린트 등록
app.register_blueprint(study_history_bp)
app.register_blueprint(ai_plan_bp)
app.register_blueprint(dashboard_bp)


@app.route('/')
def home():
    return render_template('index.html')

# 1. 유저가 카카오 로그인 버튼을 눌렀을 때 가는 곳
@app.route('/login/kakao')
def kakao_login():
    kakao_oauth_url = f"https://kauth.kakao.com/oauth/authorize?client_id={KAKAO_CLIENT_ID}&redirect_uri={KAKAO_REDIRECT_URI}&response_type=code&scope=profile_nickname,profile_image"
    return redirect(kakao_oauth_url)

# 2. 카카오 로그인이 성공하고 유저가 다시 우리 사이트로 돌아오는 곳
@app.route('/login/kakao/callback')
def kakao_callback():
    code = request.args.get("code")
    
    token_request_url = "https://kauth.kakao.com/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "code": code,
        "client_secret": KAKAO_CLIENT_SECRET,
    }
    token_response = requests.post(token_request_url, data=payload).json()
    access_token = token_response.get("access_token")
    print("=== 토큰 응답 ===")
    print(token_response)
    print("=================")
    print(f"access_token: {access_token}")

    if not access_token:
        print("❌ access_token 발급 실패!")
        return f"토큰 오류: {token_response}", 400
    
    profile_request_url = "https://kapi.kakao.com/v2/user/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    profile_response = requests.get(profile_request_url, headers=headers).json()
    
    kakao_id = str(profile_response.get("id"))
    properties = profile_response.get("properties", {})
    kakao_profile = profile_response.get("kakao_account", {}).get("profile", {})
    nickname = (kakao_profile.get("nickname") or properties.get("nickname") or f"카카오유저_{kakao_id[-4:]}")

    user = User.query.filter_by(social_id=kakao_id, provider='kakao').first()
    
    if not user:
        user = User(username=nickname, provider='kakao', social_id=kakao_id)
        db.session.add(user)
        db.session.commit()
        
    login_user(user)
    return redirect(url_for('dashboard.dashboard'))

# 🌟 1. 구글 로그인 버튼을 눌렀을 때 가는 곳
@login_bp.route('/login/google')
def google_login():
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&response_type=code&scope=openid email profile"
    return redirect(google_auth_url)

# 🌟 2. 구글 로그인 성공 후 돌아오는 곳 (콜백)
@login_bp.route('/oauth/google/callback')
def google_callback():
    code = request.args.get('code')
    
    token_endpoint = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    token_res = requests.post(token_endpoint, data=token_data).json()
    access_token = token_res.get("access_token")

    userinfo_endpoint = "https://www.googleapis.com/oauth2/v2/userinfo"
    userinfo_res = requests.get(userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"}).json()

    google_id = str(userinfo_res.get("id"))
    email = userinfo_res.get("email", "")
    name = userinfo_res.get("name", "")
    
    email_id = email.split('@')[0] if email else ""
    username = name or email_id or f"구글유저_{google_id[:4]}"

    user = User.query.filter_by(social_id=google_id, provider='google').first()
    
    if not user:
        user = User(username=username, provider='google', social_id=google_id)
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect(url_for('dashboard.dashboard'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

app.register_blueprint(login_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
