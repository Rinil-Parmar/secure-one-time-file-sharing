from pathlib import Path

from flask import Flask, render_template
from flask_login import LoginManager, current_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

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
            ensure_schema()
        print("Database tables created.")

    @app.cli.command("upgrade-db")
    def upgrade_db():
        with app.app_context():
            ensure_schema()
        print("Database schema upgraded.")

    return app


def ensure_schema():
    columns = db.session.execute(text("PRAGMA table_info(share_link)")).fetchall()
    column_names = {column[1] for column in columns}
    if "password_hash" not in column_names:
        db.session.execute(text("ALTER TABLE share_link ADD COLUMN password_hash VARCHAR(255)"))
        db.session.commit()
