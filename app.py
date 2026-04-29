from flask import Flask, render_template
from views.dashboard import dashboard_bp

app = Flask(__name__)
app.secret_key = 'dev-secret-key'

app.register_blueprint(dashboard_bp) 

@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)