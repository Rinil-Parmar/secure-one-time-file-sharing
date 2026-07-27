from datetime import timedelta
import hashlib
from io import BytesIO
import secrets
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import update
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app import db
from app.crypto_utils import decrypt_bytes, encrypt_bytes
from app.models import AccessLog, ShareLink, StoredFile, utc_now
from app.storage import StorageError, StorageNotFound, get_encrypted_storage


files_bp = Blueprint("files", __name__)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_expiration_minutes(value):
    try:
        expiration_minutes = int(value)
    except ValueError:
        return None

    if expiration_minutes < 1 or expiration_minutes > 1440:
        return None

    return expiration_minutes


def create_share_link(stored_file, expiration_minutes, password=None):
    token = secrets.token_urlsafe(32)
    password_hash = generate_password_hash(password) if password else None
    share_link = ShareLink(
        file_id=stored_file.id,
        token_hash=hash_token(token),
        password_hash=password_hash,
        expires_at=utc_now() + timedelta(minutes=expiration_minutes),
    )
    db.session.add(share_link)
    return token


def link_password_is_valid(password):
    return len(password) <= 128


def log_access(status, share_link=None):
    user_agent = request.headers.get("User-Agent", "")
    log_entry = AccessLog(
        share_link_id=share_link.id if share_link else None,
        status=status,
        ip_address=request.remote_addr,
        user_agent=user_agent[:255],
    )
    db.session.add(log_entry)


@files_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    uploaded_file = request.files.get("file")
    expiration_minutes = request.form.get("expiration_minutes", "60")
    link_password = request.form.get("link_password", "").strip()

    if uploaded_file is None or uploaded_file.filename == "":
        flash("Please choose a file before uploading.", "error")
        return redirect(url_for("dashboard"))

    if not link_password_is_valid(link_password):
        flash("Link password must be 128 characters or fewer.", "error")
        return redirect(url_for("dashboard"))

    expiration_minutes = parse_expiration_minutes(expiration_minutes)
    if expiration_minutes is None:
        flash("Expiration time must be between 1 minute and 24 hours.", "error")
        return redirect(url_for("dashboard"))

    safe_name = secure_filename(uploaded_file.filename)
    if not safe_name:
        flash("File name is not valid.", "error")
        return redirect(url_for("dashboard"))

    stored_name = f"{uuid4().hex}_{safe_name}"
    plaintext = uploaded_file.read()
    if not plaintext:
        flash("The selected file is empty.", "error")
        return redirect(url_for("dashboard"))

    ciphertext, nonce = encrypt_bytes(plaintext, current_app.config["ENCRYPTION_KEY"])
    try:
        get_encrypted_storage().put(stored_name, ciphertext)
    except (OSError, StorageError):
        current_app.logger.exception("Could not save encrypted upload")
        flash("The encrypted file could not be saved. Please try again.", "error")
        return redirect(url_for("dashboard"))

    stored_file = StoredFile(
        owner_id=current_user.id,
        original_filename=safe_name,
        stored_filename=stored_name,
        nonce=nonce,
    )
    db.session.add(stored_file)
    db.session.flush()

    token = create_share_link(stored_file, expiration_minutes, link_password)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            get_encrypted_storage().delete(stored_name)
        except (OSError, StorageError):
            current_app.logger.exception("Could not roll back encrypted upload")
        current_app.logger.exception("Could not save upload metadata")
        flash("The upload could not be completed. Please try again.", "error")
        return redirect(url_for("dashboard"))

    download_url = url_for("files.download", token=token, _external=True)
    flash(download_url, "secure_link")
    return redirect(url_for("dashboard"))


@files_bp.route("/files/<int:file_id>/share", methods=["POST"])
@login_required
def create_link(file_id):
    stored_file = StoredFile.query.filter_by(id=file_id, owner_id=current_user.id).first()
    if stored_file is None:
        flash("File not found.", "error")
        return redirect(url_for("dashboard"))

    expiration_minutes = parse_expiration_minutes(request.form.get("expiration_minutes", "60"))
    link_password = request.form.get("link_password", "").strip()
    if expiration_minutes is None:
        flash("Expiration time must be between 1 minute and 24 hours.", "error")
        return redirect(url_for("dashboard"))

    if not link_password_is_valid(link_password):
        flash("Link password must be 128 characters or fewer.", "error")
        return redirect(url_for("dashboard"))

    token = create_share_link(stored_file, expiration_minutes, link_password)
    db.session.commit()

    download_url = url_for("files.download", token=token, _external=True)
    flash(download_url, "secure_link")
    return redirect(url_for("dashboard"))


@files_bp.route("/links/<int:link_id>/revoke", methods=["POST"])
@login_required
def revoke_link(link_id):
    share_link = ShareLink.query.join(StoredFile).filter(
        ShareLink.id == link_id,
        StoredFile.owner_id == current_user.id,
    ).first()

    if share_link is None:
        flash("Share link not found.", "error")
        return redirect(url_for("dashboard"))

    if share_link.used_at is not None:
        flash("That link is already inactive.", "error")
        return redirect(url_for("dashboard"))

    share_link.used_at = utc_now()
    db.session.commit()

    flash("Secure link revoked.", "success")
    return redirect(url_for("dashboard"))


@files_bp.route("/download/<token>", methods=["GET", "POST"])
def download(token):
    share_link = ShareLink.query.filter_by(token_hash=hash_token(token)).first()
    if share_link is None:
        log_access("invalid_token")
        db.session.commit()
        return render_template(
            "download.html",
            title="Invalid link",
            message="This download link is not recognized.",
        ), 404

    if share_link.expires_at <= utc_now():
        log_access("expired", share_link)
        db.session.commit()
        return render_template(
            "download.html",
            title="Link expired",
            message="This download link has expired.",
        ), 410

    if share_link.used_at is not None:
        log_access("reused", share_link)
        db.session.commit()
        return render_template(
            "download.html",
            title="Link already used",
            message="This download link has already been used.",
        ), 410

    if share_link.password_hash:
        password = request.form.get("password", "")
        if request.method == "GET":
            return render_template(
                "download.html",
                title="Password required",
                message="Enter the password provided by the sender to download this file.",
                requires_password=True,
            )

        if not check_password_hash(share_link.password_hash, password):
            log_access("wrong_password", share_link)
            db.session.commit()
            return render_template(
                "download.html",
                title="Password required",
                message="Incorrect password. Please try again.",
                requires_password=True,
                error=True,
            ), 403

    stored_file = share_link.file
    try:
        ciphertext = get_encrypted_storage().get(stored_file.stored_filename)
    except StorageNotFound:
        log_access("missing_file", share_link)
        db.session.commit()
        return render_template(
            "download.html",
            title="File unavailable",
            message="The encrypted file could not be found on the server.",
        ), 404
    except (OSError, StorageError):
        db.session.rollback()
        current_app.logger.exception("Could not retrieve encrypted file %s", stored_file.id)
        return render_template(
            "download.html",
            title="Storage temporarily unavailable",
            message="The encrypted file could not be retrieved. Please try again later.",
        ), 503

    try:
        plaintext = decrypt_bytes(
            ciphertext,
            stored_file.nonce,
            current_app.config["ENCRYPTION_KEY"],
        )
    except (InvalidTag, OSError, TypeError, ValueError):
        db.session.rollback()
        log_access("integrity_error", share_link)
        db.session.commit()
        current_app.logger.warning("Encrypted file integrity check failed for file %s", stored_file.id)
        return render_template(
            "download.html",
            title="File integrity check failed",
            message="The encrypted file was changed or damaged and cannot be downloaded safely.",
        ), 409

    claimed_at = utc_now()
    claim = db.session.execute(
        update(ShareLink)
        .where(
            ShareLink.id == share_link.id,
            ShareLink.used_at.is_(None),
            ShareLink.expires_at > claimed_at,
        )
        .values(used_at=claimed_at)
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        db.session.rollback()
        current_link = db.session.get(ShareLink, share_link.id)
        status = "expired" if current_link.expires_at <= claimed_at else "reused"
        log_access(status, current_link)
        db.session.commit()
        title = "Link expired" if status == "expired" else "Link already used"
        message = (
            "This download link has expired."
            if status == "expired"
            else "This download link has already been used."
        )
        return render_template("download.html", title=title, message=message), 410

    log_access("success", share_link)
    db.session.commit()

    return send_file(
        BytesIO(plaintext),
        as_attachment=True,
        download_name=stored_file.original_filename,
    )
