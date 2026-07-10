from flask import Blueprint, render_template, request, redirect, url_for, session
from models import db, User
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required
import requests, os
from dotenv import load_dotenv

load_dotenv()

login_bp = Blueprint('login', __name__)

KAKAO_CLIENT_ID      = os.getenv("KAKAO_CLIENT_ID")
KAKAO_REDIRECT_URI   = os.getenv("KAKAO_REDIRECT_URI")
KAKAO_CLIENT_SECRET  = os.getenv("KAKAO_CLIENT_SECRET")
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI")

# ── 일반 로그인 ───────────────────────────────────
@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form.get('userid')
        user_pw = request.form.get('password')

        user = User.query.filter_by(username=user_id).first()

        if user and check_password_hash(user.password, user_pw):
            login_user(user)
            return redirect(url_for('dashboard.dashboard'))
        else:
            return render_template('login.html', error="아이디 또는 비밀번호가 잘못되었습니다.")

    success_msg = request.args.get('success')
    return render_template('login.html', success=success_msg)

# ── 회원가입 ──────────────────────────────────────
@login_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_id         = request.form.get('new_userid', '').strip()
        new_pw         = request.form.get('new_password', '')
        new_pw_confirm = request.form.get('new_password_confirm', '')

        # ── 유효성 검사 ──────────────────────────
        # 아이디 빈값
        if not new_id:
            return render_template('register.html',
                error="아이디를 입력해주세요.",
                userid=new_id)

        # 아이디 길이 (4~20자)
        if len(new_id) < 4 or len(new_id) > 20:
            return render_template('register.html',
                error="아이디는 4자 이상 20자 이하로 입력해주세요.",
                userid=new_id)

        # 아이디 영문/숫자만
        if not new_id.replace('_', '').isalnum():
            return render_template('register.html',
                error="아이디는 영문, 숫자, 밑줄(_)만 사용할 수 있습니다.",
                userid=new_id)

        # 비밀번호 빈값
        if not new_pw:
            return render_template('register.html',
                error="비밀번호를 입력해주세요.",
                userid=new_id)

        # 비밀번호 8자 이상
        if len(new_pw) < 8:
            return render_template('register.html',
                error="비밀번호는 8자 이상이어야 합니다.",
                userid=new_id)

        # 비밀번호 확인 빈값
        if not new_pw_confirm:
            return render_template('register.html',
                error="비밀번호 확인을 입력해주세요.",
                userid=new_id)

        # 비밀번호 불일치
        if new_pw != new_pw_confirm:
            return render_template('register.html',
                error="비밀번호가 일치하지 않습니다.",
                userid=new_id)

        # 중복 아이디
        existing_user = User.query.filter_by(username=new_id).first()
        if existing_user:
            return render_template('register.html',
                error="이미 사용 중인 아이디입니다. 다른 아이디를 입력해주세요.",
                userid=new_id)

        # ── DB 저장 ──────────────────────────────
        try:
            hashed_password = generate_password_hash(new_pw, method='pbkdf2:sha256')
            new_user = User(username=new_id, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login.login',
                success="회원가입이 완료되었습니다! 로그인해주세요."))
        except Exception:
            db.session.rollback()
            return render_template('register.html',
                error="회원가입 중 오류가 발생했습니다. 다시 시도해주세요.",
                userid=new_id)

    return render_template('register.html')

# ── 로그아웃 ──────────────────────────────────────
@login_bp.route('/logout')
@login_required
def logout():
    logout_user()          # 🌟 flask_login 방식으로 통일
    session.clear()
    return redirect(url_for('login.login'))

# ── 카카오 로그인 ─────────────────────────────────
@login_bp.route('/login/kakao')
def kakao_login():
    kakao_oauth_url = (
        f"https://kauth.kakao.com/oauth/authorize"
        f"?client_id={KAKAO_CLIENT_ID}"
        f"&redirect_uri={KAKAO_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=profile_nickname,profile_image"
    )
    return redirect(kakao_oauth_url)

@login_bp.route('/login/kakao/callback')
def kakao_callback():
    code = request.args.get("code")

    token_response = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type":    "authorization_code",
            "client_id":     KAKAO_CLIENT_ID,
            "redirect_uri":  KAKAO_REDIRECT_URI,
            "code":          code,
            "client_secret": KAKAO_CLIENT_SECRET,
        }
    ).json()

    access_token = token_response.get("access_token")
    if not access_token:
        return f"카카오 토큰 오류: {token_response}", 400

    profile_response = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    kakao_id      = str(profile_response.get("id"))
    properties    = profile_response.get("properties", {})
    kakao_profile = profile_response.get("kakao_account", {}).get("profile", {})
    nickname      = (
        kakao_profile.get("nickname")
        or properties.get("nickname")
        or f"카카오유저_{kakao_id[-4:]}"
    )

    user = User.query.filter_by(social_id=kakao_id, provider='kakao').first()
    if not user:
        user = User(username=nickname, provider='kakao', social_id=kakao_id)
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect(url_for('dashboard.dashboard'))

# ── 구글 로그인 ───────────────────────────────────
@login_bp.route('/login/google')
def google_login():
    print("REDIRECT:", GOOGLE_REDIRECT_URI)
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=openid email profile"
    )
    return redirect(google_auth_url)

@login_bp.route('/oauth/google/callback')
def google_callback():
    code = request.args.get('code')

    token_res = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  GOOGLE_REDIRECT_URI,
            "grant_type":    "authorization_code",
        }
    ).json()

    access_token = token_res.get("access_token")
    if not access_token:
        return f"구글 토큰 오류: {token_res}", 400

    userinfo_res = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    google_id = str(userinfo_res.get("id"))
    email     = userinfo_res.get("email", "")
    name      = userinfo_res.get("name", "")
    email_id  = email.split('@')[0] if email else ""
    username  = name or email_id or f"구글유저_{google_id[:4]}"

    user = User.query.filter_by(social_id=google_id, provider='google').first()
    if not user:
        user = User(username=username, provider='google', social_id=google_id)
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect(url_for('dashboard.dashboard'))
