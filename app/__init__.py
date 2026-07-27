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
    from app.models import AccessLog, ShareLink, StoredFile, User, utc_now

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
        file_ids = [file.id for file in uploaded_files]
        recent_logs = []
        if file_ids:
            recent_logs = (
                AccessLog.query.join(AccessLog.share_link)
                .filter(ShareLink.file_id.in_(file_ids))
                .order_by(AccessLog.created_at.desc())
                .limit(10)
                .all()
            )
        return render_template(
            "dashboard.html",
            now=utc_now(),
            recent_logs=recent_logs,
            uploaded_files=uploaded_files,
        )

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

    @app.cli.command("cleanup-files")
    def cleanup_files():
        with app.app_context():
            removed = cleanup_inactive_files(app.config["UPLOAD_FOLDER"])
        print(f"Removed {removed} inactive encrypted file(s).")

    return app


def ensure_schema():
    db.create_all()
    columns = db.session.execute(text("PRAGMA table_info(share_link)")).fetchall()
    column_names = {column[1] for column in columns}
    if "password_hash" not in column_names:
        db.session.execute(text("ALTER TABLE share_link ADD COLUMN password_hash VARCHAR(255)"))
        db.session.commit()


def cleanup_inactive_files(upload_folder):
    from app.models import StoredFile, utc_now

    now = None
    removed = 0
    upload_folder = Path(upload_folder)

    for stored_file in StoredFile.query.all():
        if not stored_file.share_links:
            continue

        now = now or utc_now()
        has_active_link = any(
            link.used_at is None and link.expires_at > now
            for link in stored_file.share_links
        )
        if has_active_link:
            continue

        stored_path = upload_folder / stored_file.stored_filename
        stored_path.unlink(missing_ok=True)
        db.session.delete(stored_file)
        removed += 1

    db.session.commit()
    return removed
