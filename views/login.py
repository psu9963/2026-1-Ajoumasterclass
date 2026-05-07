from flask import Blueprint, render_template, request, redirect, url_for, session
from models import db, User  # 🌟 데이터베이스와 User 모델 불러오기
from werkzeug.security import generate_password_hash, check_password_hash 
from flask_login import login_user


login_bp = Blueprint('login', __name__)

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form.get('userid')
        user_pw = request.form.get('password')
        
        user = User.query.filter_by(username=user_id).first()
        
        # 🌟 비밀번호 비교는 아주 잘 되어있습니다! 그대로 유지합니다.
        if user and check_password_hash(user.password, user_pw):
            # ❌ 기존 세션 방식은 이제 지워주세요! (에러의 원인)
            # session['user_id'] = user.id     
            # session['username'] = user.userid   
            
            # ⭕ 새로운 통합 방식: 이 한 줄이면 모든 세션 관리가 끝납니다!
            login_user(user) 
            
            return redirect(url_for('dashboard.dashboard'))
        else:
            return render_template('login.html', error="아이디 또는 비밀번호가 잘못되었습니다.")
    
    success_msg = request.args.get('success')
    return render_template('login.html', success=success_msg)




@login_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_id = request.form.get('new_userid')
        new_pw = request.form.get('new_password')
        new_pw_confirm = request.form.get('new_password_confirm')
        
        if new_pw != new_pw_confirm:
            return render_template('register.html', error="비밀번호가 일치하지 않습니다.")
            
        existing_user = User.query.filter_by(username=new_id).first()
        if existing_user:
            return render_template('register.html', error="이미 존재하는 아이디입니다.")
            
        # 🌟 여기에 pbkdf2:sha256 방식을 명시합니다!
        hashed_password = generate_password_hash(new_pw, method='pbkdf2:sha256')
        
        new_user = User(username=new_id, password=hashed_password)

        db.session.add(new_user)
        db.session.commit()
        
        return redirect(url_for('login.login', success="회원가입이 완료되었습니다! 로그인해주세요."))
        
    return render_template('register.html')

@login_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login.login'))
