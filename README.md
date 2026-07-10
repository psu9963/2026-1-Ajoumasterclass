# 파이썬을 활용한 AI 학습 설계 웹 개발 (아주마스터클래스)

# 시작 전: 
가상환경 드가기
VS Code 하단 터미널을 열고 가상환경이 켜져 있는지 확인 ((venv) 표시 확인)


파일 열고 
git checkout develop
git pull origin develop
git checkout -b feature/만들기능이름


# 파일 구조:
app.py에서 합치는 구조임
.py파일들은 views 폴더 안에 py 파일 만들면 됨


# mysql data 확인
1. real_study_records 에서 작성자별 기록 확인 ㄱㄴ
2. study_records 에서 확인하려면

    SELECT 
    user.username AS '작성자', 
    study_record.subject AS '과목', 
    study_record.duration_hours AS '학습시간',
    study_record.study_date AS '날짜'
FROM study_record
JOIN user ON study_record.user_id = user.id
WHERE study_record.duration_hours > 0;
를 쿼리에 추가
