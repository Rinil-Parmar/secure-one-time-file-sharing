from pathlib import Path

from flask import Flask, render_template
from flask_login import LoginManager, current_user, login_required
from flask_sqlalchemy import SQLAlchemy

from config import Config


db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access your dashboard."

    from app.auth import auth_bp
    from app.files import files_bp
    from app.models import User, utc_now

    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.route("/")
    @login_required
    def dashboard():
        uploaded_files = sorted(
            current_user.files,
            key=lambda file: file.created_at,
            reverse=True,
        )
        return render_template("dashboard.html", now=utc_now(), uploaded_files=uploaded_files)

    @app.cli.command("init-db")
    def init_db():
        with app.app_context():
            Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
            db.create_all()
        print("Database tables created.")

    return app
