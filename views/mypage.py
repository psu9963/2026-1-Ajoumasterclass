from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, StudyRecord, Subject, WeeklyPlan, StudyPlan, StudyPlanItem, ExamPlan, ExamPlanItem
from datetime import datetime
import os, uuid

mypage_bp = Blueprint('mypage', __name__)

_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
_AVATAR_DIR = os.path.join(_STATIC, 'uploads', 'avatars')
_ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp'}

def _allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in _ALLOWED_EXT


@mypage_bp.route('/mypage')
@login_required
def mypage():
    user_id = current_user.id

    subject_count     = Subject.query.filter_by(user_id=user_id).count()
    study_plan_count  = StudyPlan.query.join(Subject).filter(Subject.user_id == user_id).count()
    exam_plan_count   = ExamPlan.query.join(Subject).filter(Subject.user_id == user_id).count()
    done_study = StudyPlanItem.query.join(StudyPlan).join(Subject).filter(
        Subject.user_id == user_id, StudyPlanItem.is_done == True
    ).count()
    done_exam = ExamPlanItem.query.join(ExamPlan).join(Subject).filter(
        Subject.user_id == user_id, ExamPlanItem.is_done == True
    ).count()
    done_count = done_study + done_exam

    if current_user.provider == 'kakao':
        provider_label = '카카오 로그인'
    elif current_user.provider == 'google':
        provider_label = '구글 로그인'
    else:
        provider_label = '일반 로그인'

    display_name  = current_user.display_name or current_user.username
    profile_image = current_user.profile_image

    return render_template('mypage.html',
        display_name=display_name,
        profile_image=profile_image,
        provider_label=provider_label,
        is_social=(current_user.provider in ['kakao', 'google']),
        subject_count=subject_count,
        study_plan_count=study_plan_count,
        exam_plan_count=exam_plan_count,
        done_count=done_count,
    )


@mypage_bp.route('/mypage/update-profile', methods=['POST'])
@login_required
def update_profile():
    display_name = request.form.get('display_name', '').strip()
    if display_name:
        current_user.display_name = display_name[:100]

    file = request.files.get('profile_image')
    if file and file.filename:
        if not _allowed_image(file.filename):
            flash('jpg, png, gif, webp 형식의 이미지만 업로드할 수 있어요.', 'error')
            db.session.commit()
            return redirect(url_for('mypage.mypage'))
        try:
            os.makedirs(_AVATAR_DIR, exist_ok=True)
            old = current_user.profile_image
            if old:
                old_path = os.path.join(_STATIC, old)
                if os.path.exists(old_path):
                    os.remove(old_path)
            ext   = file.filename.rsplit('.', 1)[1].lower()  # secure_filename 대신 원본에서 추출
            fname = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(_AVATAR_DIR, fname))
            current_user.profile_image = f"uploads/avatars/{fname}"
        except Exception:
            flash('이미지 저장에 실패했어요. 다시 시도해 주세요.', 'error')
            db.session.rollback()
            return redirect(url_for('mypage.mypage'))

    db.session.commit()
    flash('프로필이 저장됐어요.', 'success')
    return redirect(url_for('mypage.mypage'))


@mypage_bp.route('/mypage/change-password', methods=['POST'])
@login_required
def change_password():
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


@mypage_bp.route('/mypage/delete-account', methods=['POST'])
@login_required
def delete_account():
    user_id = current_user.id

    subjects = Subject.query.filter_by(user_id=user_id).all()
    for subj in subjects:
        WeeklyPlan.query.filter_by(subject_id=subj.id).delete()
        for sp in StudyPlan.query.filter_by(subject_id=subj.id).all():
            db.session.delete(sp)
        for ep in ExamPlan.query.filter_by(subject_id=subj.id).all():
            db.session.delete(ep)
        if subj.syllabus_filename:
            pdf_path = os.path.join(_STATIC, 'uploads', subj.syllabus_filename)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        db.session.delete(subj)

    StudyRecord.query.filter_by(user_id=user_id).delete()

    user = User.query.get(user_id)
    if user.profile_image:
        img_path = os.path.join(_STATIC, user.profile_image)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(user)
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for('login.login'))
