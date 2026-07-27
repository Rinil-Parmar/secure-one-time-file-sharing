from pathlib import Path

from flask import Flask, current_app, render_template
from flask_login import LoginManager, current_user, login_required
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config, DEVELOPMENT_ENCRYPTION_KEY, DEVELOPMENT_SECRET


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_override=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    if app.config["APP_ENV"].lower() == "production":
        insecure_settings = []
        if app.config["SECRET_KEY"] == DEVELOPMENT_SECRET:
            insecure_settings.append("SECRET_KEY")
        if app.config["ENCRYPTION_KEY"] == DEVELOPMENT_ENCRYPTION_KEY:
            insecure_settings.append("ENCRYPTION_KEY")
        if insecure_settings:
            raise RuntimeError(
                "Production requires secure environment values for: "
                + ", ".join(insecure_settings)
            )
        app.config["SESSION_COOKIE_SECURE"] = True

    if app.config["STORAGE_BACKEND"] not in {"local", "s3"}:
        raise RuntimeError("STORAGE_BACKEND must be either 'local' or 's3'.")

    if app.config["STORAGE_BACKEND"] == "s3":
        required_storage_settings = (
            "S3_ENDPOINT_URL",
            "S3_ACCESS_KEY_ID",
            "S3_SECRET_ACCESS_KEY",
            "S3_REGION",
            "STORAGE_BUCKET",
        )
        missing_settings = [
            setting
            for setting in required_storage_settings
            if not app.config.get(setting)
        ]
        if missing_settings:
            raise RuntimeError(
                "S3 storage requires environment values for: "
                + ", ".join(missing_settings)
            )

    if app.config.get("BEHIND_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access your dashboard."

    from app.auth import auth_bp
    from app.files import files_bp
    from app.models import AccessLog, ShareLink, StoredFile, User, utc_now

    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "style-src 'self' https://cdn.jsdelivr.net; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net data:; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return render_template(
            "error.html",
            title="Request could not be verified",
            message="The form expired or was submitted from an untrusted page. Refresh and try again.",
        ), 400

    @app.errorhandler(413)
    def file_too_large(_error):
        return render_template(
            "error.html",
            title="File is too large",
            message="Choose a file smaller than 16 MB and try again.",
        ), 413

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
        active_links = sum(
            1
            for stored_file in uploaded_files
            for link in stored_file.share_links
            if link.used_at is None and link.expires_at > utc_now()
        )
        return render_template(
            "dashboard.html",
            active_links=active_links,
            now=utc_now(),
            recent_logs=recent_logs,
            uploaded_files=uploaded_files,
        )

    @app.get("/health")
    def health():
        db.session.execute(text("SELECT 1"))
        return {"status": "ok"}, 200

    @app.cli.command("init-db")
    def init_db():
        with app.app_context():
            if app.config["STORAGE_BACKEND"] == "local":
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
            removed = cleanup_inactive_files()
        print(f"Removed {removed} inactive encrypted file(s).")

    return app


def ensure_schema():
    db.create_all()
    inspector = inspect(db.engine)
    if "share_link" not in inspector.get_table_names():
        return
    column_names = {
        column["name"]
        for column in inspector.get_columns("share_link")
    }
    if "password_hash" not in column_names:
        db.session.execute(text("ALTER TABLE share_link ADD COLUMN password_hash VARCHAR(255)"))
        db.session.commit()


def cleanup_inactive_files(upload_folder=None):
    from app.models import StoredFile, utc_now
    from app.storage import LocalEncryptedStorage, StorageError, get_encrypted_storage

    now = None
    removed = 0
    storage = (
        LocalEncryptedStorage(upload_folder)
        if upload_folder is not None
        else get_encrypted_storage()
    )

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

        try:
            storage.delete(stored_file.stored_filename)
        except (OSError, StorageError):
            current_app.logger.exception(
                "Could not delete encrypted object %s",
                stored_file.stored_filename,
            )
            continue
        db.session.delete(stored_file)
        removed += 1

    db.session.commit()
    return removed
