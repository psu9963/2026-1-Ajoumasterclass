from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, StudyRecord
from datetime import datetime

mypage_bp = Blueprint('mypage', __name__)


@mypage_bp.route('/mypage')
@login_required
def mypage():
    user_id = current_user.id

    # 학습 과목 목록 (중복 제거)
    records  = StudyRecord.query.filter(
        StudyRecord.user_id == user_id,
        StudyRecord.duration_hours > 0
    ).all()
    subjects = list({r.subject for r in records})
    subject_count = len(subjects)

    # 가입 방식
    if current_user.provider == 'kakao':
        provider_label = '카카오 로그인'
        provider_icon  = 'kakao'
    elif current_user.provider == 'google':
        provider_label = '구글 로그인'
        provider_icon  = 'google'
    else:
        provider_label = '일반 로그인'
        provider_icon  = 'default'

    return render_template('mypage.html',
        username=current_user.username,
        provider_label=provider_label,
        provider_icon=provider_icon,
        is_social=(current_user.provider in ['kakao', 'google']),
        subjects=subjects,
        subject_count=subject_count,
    )


# ── 비밀번호 변경 ──────────────────────────────────
@mypage_bp.route('/mypage/change-password', methods=['POST'])
@login_required
def change_password():
    # 소셜 로그인 유저는 비밀번호 변경 불가
    if current_user.provider in ['kakao', 'google']:
        flash('소셜 로그인 계정은 비밀번호를 변경할 수 없어요.', 'error')
        return redirect(url_for('mypage.mypage'))

    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    if not check_password_hash(current_user.password, current_pw):
        flash('현재 비밀번호가 올바르지 않아요.', 'error')
        return redirect(url_for('mypage.mypage'))

    if len(new_pw) < 6:
        flash('새 비밀번호는 6자 이상이어야 해요.', 'error')
        return redirect(url_for('mypage.mypage'))

    if new_pw != confirm_pw:
        flash('새 비밀번호가 일치하지 않아요.', 'error')
        return redirect(url_for('mypage.mypage'))

    current_user.password = generate_password_hash(new_pw, method='pbkdf2:sha256')
    db.session.commit()
    flash('비밀번호가 변경되었어요.', 'success')
    return redirect(url_for('mypage.mypage'))


# ── 회원 탈퇴 ──────────────────────────────────────
@mypage_bp.route('/mypage/delete-account', methods=['POST'])
@login_required
def delete_account():
    user_id = current_user.id

    # 학습 기록 삭제
    StudyRecord.query.filter_by(user_id=user_id).delete()

    # 유저 삭제
    user = User.query.get(user_id)
    db.session.delete(user)
    db.session.commit()

    logout_user()
    session.clear()
    return redirect(url_for('login.login'))