from flask import Blueprint, render_template, request, redirect, url_for, session
from models import db, User  # 🌟 데이터베이스와 User 모델 불러오기
from werkzeug.security import generate_password_hash, check_password_hash 


login_bp = Blueprint('login', __name__)

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form.get('userid')
        user_pw = request.form.get('password')
        
        user = User.query.filter_by(userid=user_id).first()
        
        # 🌟 변경된 부분: 원본 비교(==) 대신 check_password_hash 도구 사용!
        if user and check_password_hash(user.password, user_pw):
            session['user_id'] = user.id     
            session['username'] = user.userid   
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
            
        existing_user = User.query.filter_by(userid=new_id).first()
        if existing_user:
            return render_template('register.html', error="이미 존재하는 아이디입니다.")
            
        # 🌟 여기에 pbkdf2:sha256 방식을 명시합니다!
        hashed_password = generate_password_hash(new_pw, method='pbkdf2:sha256')
        
        new_user = User(userid=new_id, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        return redirect(url_for('login.login', success="회원가입이 완료되었습니다! 로그인해주세요."))
        
    return render_template('register.html')

@login_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login.login'))
