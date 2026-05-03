from flask import Flask, render_template
from views.login import login_bp
from models import db
from views.dashboard import dashboard_bp
from views.study_history import study_history_bp


# 1. 🌟 가장 먼저 플라스크 앱(app)을 만들어 줍니다! 🌟
app = Flask(__name__)
app.secret_key = 'dev-secret-key'

app.register_blueprint(dashboard_bp) 

# 2. 앱이 만들어진 후에 데이터베이스 설정을 해줍니다.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. 앱에 데이터베이스 연결
db.init_app(app)

# 서버가 켜질 때 데이터베이스 표 생성
with app.app_context():
    db.create_all()

# 블루프린트 등록
app.register_blueprint(login_bp)
app.register_blueprint(study_history_bp)


@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)