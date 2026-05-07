from flask import Blueprint, render_template, request, redirect, url_for, session
from models import db, StudyRecord # 🌟 방금 만든 모델 불러오기
from sqlalchemy import func # 🌟 중복된 과목을 묶기 위해 추가
from flask_login import login_required, current_user


study_history_bp = Blueprint('study_history', __name__)

# methods=['GET', 'POST'] 를 추가해서 데이터 입력(POST)도 받을 수 있게 합니다.
@study_history_bp.route('/study-history', methods=['GET', 'POST'])
@login_required # 🌟 로그인 안 한 사람은 접근 불가
def history():
    # 🌟 새 과목(폴더)을 만들 때
    if request.method == 'POST':
        subject_name = request.form.get('subject')
        # ⭕ session['user_id'] 대신 current_user.id 사용
        new_folder = StudyRecord(user_id=current_user.id, subject=subject_name, duration_hours=0, study_date='', memo='과목 생성')
        db.session.add(new_folder)
        db.session.commit()
        return redirect(url_for('study_history.history'))
        
    # 🌟 DB에서 '과목명'만 중복 없이 가져오기 (폴더처럼 보여주기 위함)
    subjects = db.session.query(StudyRecord.subject)\
        .filter_by(user_id=current_user.id)\
        .distinct().all() # ⭕ session['user_id'] 대신 current_user.id 사용
        
    #[('수학',), ('데이터베이스',)] 형태로 오기 때문에, 이름만 깔끔하게 리스트로 바꿉니다.
    subject_list =[s[0] for s in subjects]
    
    # ⭕ session.get 대신 current_user.username (또는 userid 등 모델에 맞게) 사용
    return render_template('study_history.html', username=current_user.username, subjects=subject_list)


@study_history_bp.route('/study-history/<subject>', methods=['GET', 'POST'])
@login_required # 🌟 로그인 안 한 사람은 접근 불가
def subject_detail(subject):
    if request.method == 'POST':
        # 상세 기록 추가
        duration = request.form.get('duration')
        date = request.form.get('date')
        memo = request.form.get('memo')
        
        # ⭕ session['user_id'] 대신 current_user.id 사용
        new_record = StudyRecord(user_id=current_user.id, subject=subject, duration_hours=float(duration), study_date=date, memo=memo)
        db.session.add(new_record)
        db.session.commit()
        return redirect(url_for('study_history.subject_detail', subject=subject))
        
    # 🌟 해당 과목(subject)의 기록만 최신순으로 가져옵니다 
    # ⭕ (중요!) 다른 사람의 똑같은 과목명이 섞이지 않도록 user_id 필터를 추가했습니다!
    records = StudyRecord.query.filter(
        StudyRecord.user_id == current_user.id, 
        StudyRecord.subject == subject, 
        StudyRecord.duration_hours > 0
    ).order_by(StudyRecord.study_date.desc()).all()
    
    # ⭕ session.get 대신 current_user.username 사용
    return render_template('subject_detail.html', username=current_user.username, subject=subject, records=records)



@study_history_bp.route('/study-history/delete/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    # 1. 지울 데이터를 DB에서 꺼내옵니다.
    record_to_delete = StudyRecord.query.get_or_404(record_id)
    
    # 2. 🌟 지우기 전에!! 이 기록이 어떤 과목이었는지 이름을 안전하게 저장해 둡니다.
    subject_name = record_to_delete.subject 
    
    # 3. 데이터를 지우고 DB에 반영합니다.
    db.session.delete(record_to_delete)
    db.session.commit()
    
    # 4. 아까 저장해둔 과목명(subject_name)을 이용해 그 과목 페이지로 돌아갑니다.
    return redirect(url_for('study_history.subject_detail', subject=subject_name))


@study_history_bp.route('/study-history/<subject>/delete', methods=['POST'])
def delete_subject(subject):
    # 해당 과목명(subject)을 가진 모든 기록을 찾아서 한 번에 싹 지웁니다.
    StudyRecord.query.filter_by(subject=subject).delete()
    db.session.commit()
    # 과목이 사라졌으니 과목 목록 화면으로 돌아갑니다.
    return redirect(url_for('study_history.history'))
# 3. 기록 수정 기능 (새로 추가)
@study_history_bp.route('/study-history/edit/<int:record_id>', methods=['POST'])
def edit_record(record_id):
    record_to_edit = StudyRecord.query.get_or_404(record_id)
    subject_name = record_to_edit.subject
    
    # 폼에서 새로 입력받은 값으로 덮어씌웁니다.
    record_to_edit.duration_hours = float(request.form.get('duration'))
    record_to_edit.study_date = request.form.get('date')
    record_to_edit.memo = request.form.get('memo')
    db.session.commit()
    
    return redirect(url_for('study_history.subject_detail', subject=subject_name))