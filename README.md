<div align="center">

# A+ 스터디 플래너 (에스플)

강의계획서 PDF 하나로 학습 계획부터 학점 예측까지

<img src="static/img/screenshot-classroom.png" width="32%" alt="강의실">
<img src="static/img/screenshot-grade.png" width="32%" alt="학점 예측">
<img src="static/img/screenshot-analysis.png" width="32%" alt="학습 분석">

</div>

<br>

## 프로젝트 개요

2026 아주마스터클래스 「파이썬을 활용한 AI 학습 설계 웹 개발」 프로젝트입니다.

생성형 AI는 이제 대학생의 기본 학습 도구가 되었지만, 기존 AI는 우리 학교의 커리큘럼이나 내 강의계획서, 내 성적을 알지 못합니다. 쓸 때마다 "나는 아주대 ○○과 ○학년인데…"처럼 배경을 다시 설명해야 합니다.

또한 대학생은 학기 초에 과목별 강의계획서를 받지만, 이를 주차별 공부 계획으로 옮기고 시험 일정에 맞춰 분량을 나누는 일은 직접 해야 합니다. 중간고사 이후 현재 성적으로 최종 학점이 어느 정도일지 가늠하기도 어렵습니다.

에스플(A+ 스터디 플래너)은 이용 대상을 아주대학교 학생으로 정하고, 강의계획서 PDF를 AI로 분석해 주차별 학습 계획과 시험 대비 계획을 만들고, 학습 기록과 실천율, 학점 예측까지 한 서비스에서 관리할 수 있도록 만든 웹 서비스입니다.

특히 모든 AI 기능을 **아주대학교 LLM API**로 구현했습니다. 아주대 학생이라면 누구나 아주대 LLM API 키를 발급받아 등록하는 것만으로 서비스를 이어서 사용할 수 있기 때문에, 프로젝트가 끝난 뒤에도 아주대 학생들이 매 학기 꾸준히 사용하고 발전시킬 수 있는 지속 가능한 서비스를 목표로 했습니다.

<br>

## 프로젝트 소개

**1. 강의계획서 자동 분석**
강의계획서 PDF를 업로드하면 텍스트를 추출하고 AI가 주차별 진도를 정리합니다. 결과는 사용자가 직접 수정할 수 있습니다.

**2. AI 학습 계획 · 시험 대비 계획**
주차별 주제를 바탕으로 주차마다 할 일을 생성하고, 시험 날짜와 범위를 등록하면 시험일까지 날짜별 할 일을 배분합니다. 모든 항목은 체크리스트로 관리합니다.

**3. AI 학점 예측**
중간고사, 기말고사, 과제·출석 점수와 반 통계를 단계별로 입력하면 예상 학점과 상위 %를 분석하고 학점 향상 방법을 제시합니다.

**4. 학습 분석 · AI 코칭**
과목별 현재 주차와 계획 실천율, 이번 주 할 일, 시험 D-day를 보여주고, 요청 시 AI가 우선 공부할 내용을 제안합니다.

**5. 대시보드 · 캘린더 · 학습 기록**
학습 시간, 과목별 비율, 연속 학습일, 주간·일일 목표, 일정을 한 곳에서 관리합니다.

<br>

## 기술 스택

| 분류 | 기술 |
| --- | --- |
| Backend | Flask 3.1 (Blueprint), Flask-Login, Flask-SQLAlchemy, SQLAlchemy 2.0 |
| Database | MySQL (PyMySQL), 로컬 개발 시 SQLite |
| AI | 아주대학교 LLM API 게이트웨이 · Claude Sonnet 4.6 (OpenAI 호환 SDK) |
| PDF | pdfplumber |
| Frontend | Jinja2, HTML / CSS / JavaScript, FullCalendar 6, Pretendard |
| Auth | Kakao OAuth, Google OAuth 2.0, Werkzeug 비밀번호 해시 |
| 배포 · DB 호스팅 | Railway (GitHub 연동 배포, 클라우드 MySQL) |
| 협업 | GitHub (기능별 브랜치 작업 후 병합) |

<br>

## 주요 기능

### 1. 회원 관리
- 일반 회원가입 / 로그인 (비밀번호 pbkdf2:sha256 해시 저장)
- 카카오, 구글 소셜 로그인
- 마이페이지: 표시 이름·프로필 이미지 변경, 비밀번호 변경, 회원 탈퇴

### 2. 강의실
- 과목명, 개강일, 강의계획서 PDF(최대 10MB)로 과목 생성
- pdfplumber로 텍스트 추출 후 AI가 주차별 진도를 JSON으로 반환
- 텍스트가 200자 미만이면 스캔 이미지 PDF로 판단해 안내
- 주차별 주제 수정·추가·삭제, PDF 교체, 다시 분석, 과목별 학습 시간 기록

### 3. AI 학습 계획
- 주차별 주제마다 실천 가능한 할 일 2~4개 생성 (과목당 1개)
- 주차별 체크리스트로 완료 여부 관리

### 4. 시험 일정 · AI 시험 대비 계획
- 시험 종류, 날짜, 범위(시작~끝 주차) 등록
- 오늘부터 시험일까지 날짜별(D-day) 할 일 1~3개 배분
- 시험이 가까운 날은 복습·정리, 먼 날은 새 내용 학습 위주로 구성

### 5. AI 학점 예측
- 과목별 반영 비율(중간·기말·과제·출석·기타)과 수강 인원 설정
- 1단계 중간고사 → 2단계 기말고사 → 3단계 과제·출석·기타 순으로 입력
- 각 단계에서 점수, 만점, 평균, 중앙값, 표준편차 입력
- 환산 점수는 서버에서 계산하고, AI는 통계 해석과 학점 판단을 담당
- 최종 결과: 예상 학점, 상위 %, 반 평균 대비 위치, 학점 향상 팁

### 6. 학습 분석 · AI 코칭
- 개강일 기준 과목별 현재 주차와 주제 계산
- 현재 주차까지의 계획 실천율 (40% 미만 과목 강조)
- 이번 주 할 일 최대 5개, 다가오는 시험 D-day
- AI 코칭은 버튼을 눌렀을 때만 생성하고 결과를 저장해 재사용

### 7. 대시보드
- 진행 중 / 종강 과목 수
- 전체·이번 주 학습 시간, 과목별 학습 비율, 연속 학습일, 최근 7일 기록
- 주간 목표 시간, 오늘의 목표, 다가오는 일정

### 8. 캘린더 · 학습 기록
- 일정 추가·수정·삭제, 색상·카테고리·시간 지정
- 과목별 학습 기록 추가·수정·삭제

<br>

## 구현 특징

1. **아주대 LLM API 기반의 지속 가능한 운영** — 강의계획서 분석, 학습·시험 계획 생성, 학점 예측, 학습 코칭까지 모든 AI 기능이 아주대학교 LLM API 하나로 동작합니다. 발급받은 아주대 LLM API 키(`AJOU_API_KEY`)만 등록하면 되므로, 아주대 학생이 계속 사용하고 이어서 발전시킬 수 있습니다.
2. **JSON 형식 응답** — AI 응답은 정해진 JSON 형식으로만 받고, 형식이 맞지 않으면 저장하지 않습니다.
3. **근거 밖 내용 제한** — 강의계획서에 없는 주차는 추측하지 않고, 계획은 주어진 주차 주제에만 근거하도록 프롬프트를 구성했습니다.
4. **날짜는 서버에서 지정** — 시험 대비 계획은 서버가 만든 날짜 목록 안에서만 배분하고, 목록에 없는 날짜는 제외합니다.
5. **계산과 해석 분리** — 학점 환산 점수는 코드로 계산하고, AI는 입력된 통계를 바탕으로 해석만 합니다.

<br>

## 보안 적용 사항

### 1. 자체 로그인 비밀번호 해시
- `werkzeug.security`의 pbkdf2:sha256 알고리즘으로 비밀번호를 단방향 해시
- 비밀번호 원문은 저장하지 않고 해시값만 DB에 저장 (회원가입, 로그인, 비밀번호 변경 모두 동일)
- DB가 유출되거나 관리자가 조회해도 원래 비밀번호를 알 수 없음

### 2. 소셜 로그인 (OAuth 2.0)
- 카카오 · 구글 로그인에 OAuth 2.0 Authorization Code Grant 방식 적용
- 인증은 카카오 · 구글 서버에서 처리하며, 서비스는 사용자의 카카오 · 구글 비밀번호를 보거나 저장하지 않음
- 회원가입 절차를 줄이고 비밀번호 관리 부담 자체를 없앰

| 구분 | 자체 회원가입 | 소셜 로그인 |
| --- | --- | --- |
| 비밀번호 저장 | 해시값으로 DB 저장 | 저장하지 않음 (NULL) |
| 사용자 식별 | username | provider + social_id (unique) |
| 인증 책임 | 서비스 서버 | 카카오 · 구글 서버 |

### 3. 민감 정보 분리 (.env)
- Flask `SECRET_KEY`, `DATABASE_URL`, 카카오 · 구글 OAuth 키, LLM API 키를 코드와 분리해 `.env`에 저장
- `python-dotenv`의 `load_dotenv()`로 앱 시작 시 환경 변수로 읽고, 코드에서는 `os.getenv("KAKAO_CLIENT_ID")`처럼 이름으로만 참조

### 4. .gitignore로 업로드 차단
- `.env`, 로컬 DB 폴더(`instance/`) 등을 `.gitignore`에 등록해 민감 정보가 GitHub에 올라가지 않도록 차단

<br>

## 배포 및 데이터베이스

1. **Railway 배포** — GitHub 저장소와 연동해 Railway에 웹 서비스를 배포했습니다.
2. **클라우드 MySQL** — 팀원 모두가 같은 데이터베이스를 보고 관리할 수 있도록 Railway의 MySQL을 사용합니다.
3. **모델 기반 테이블 관리** — `models.py`에 정의한 모델로 앱 시작 시 테이블을 생성합니다.

<br>

## 서비스 흐름

```
강의계획서 PDF 업로드
  → AI 주차별 진도 추출
  → AI 학습 계획 / 시험 대비 계획 생성
  → 체크리스트로 실천 · 학습 시간 기록
  → 학습 분석에서 실천율 확인 · AI 코칭

학점 예측: 과목 설정 → 중간고사 분석 → 기말고사 분석 → 최종 학점 예측
```

<br>

## 프로젝트 구조

```
├── app.py               # 앱 생성, DB 설정, Blueprint 등록
├── models.py            # 데이터 모델
├── study_stats.py       # 학습 시간 집계
├── views/
│   ├── login.py         # 회원가입 · 로그인 · 소셜 로그인
│   ├── dashboard.py     # 대시보드
│   ├── classroom.py     # 강의실 · 강의계획서 분석 · 학습/시험 계획
│   ├── analysis.py      # 학습 분석 · AI 코칭
│   ├── grade_predict.py # 학점 예측
│   ├── study_history.py # 학습 기록
│   ├── calendar.py      # 캘린더
│   └── mypage.py        # 마이페이지
├── templates/           # HTML 템플릿
└── static/              # CSS, 이미지
```

<br>

## 설치 및 실행

**1. 저장소 클론 및 패키지 설치**

```bash
git clone https://github.com/psu9963/2026-1-Ajoumasterclass.git
cd 2026-1-Ajoumasterclass

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. 환경 변수 설정**

프로젝트 루트에 `.env` 파일을 만듭니다.

```env
SECRET_KEY=your-flask-secret-key
AJOU_API_KEY=your-llm-api-key

# 선택
DATABASE_URL=mysql+pymysql://user:password@host/dbname   # 미설정 시 SQLite
KAKAO_CLIENT_ID=
KAKAO_CLIENT_SECRET=
KAKAO_REDIRECT_URI=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
```

**3. 실행**

```bash
python app.py
```

`http://localhost:5001` 에서 접속할 수 있으며, 첫 실행 시 DB 테이블이 자동으로 생성됩니다.

<br>

