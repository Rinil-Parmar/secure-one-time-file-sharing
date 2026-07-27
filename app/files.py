from datetime import timedelta
import hashlib
from io import BytesIO
from pathlib import Path
import secrets
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app import db
from app.crypto_utils import decrypt_bytes, encrypt_bytes
from app.models import AccessLog, ShareLink, StoredFile, utc_now


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

    expiration_minutes = parse_expiration_minutes(expiration_minutes)
    if expiration_minutes is None:
        flash("Expiration time must be between 1 minute and 24 hours.", "error")
        return redirect(url_for("dashboard"))

    safe_name = secure_filename(uploaded_file.filename)
    if not safe_name:
        flash("File name is not valid.", "error")
        return redirect(url_for("dashboard"))

    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4().hex}_{safe_name}"
    stored_path = upload_folder / stored_name
    plaintext = uploaded_file.read()
    ciphertext, nonce = encrypt_bytes(plaintext, current_app.config["ENCRYPTION_KEY"])
    stored_path.write_bytes(ciphertext)

    stored_file = StoredFile(
        owner_id=current_user.id,
        original_filename=safe_name,
        stored_filename=stored_name,
        nonce=nonce,
    )
    db.session.add(stored_file)
    db.session.flush()

    token = create_share_link(stored_file, expiration_minutes, link_password)
    db.session.commit()

    download_url = url_for("files.download", token=token, _external=True)
    flash(f"File encrypted. Secure link: {download_url}", "success")
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

    token = create_share_link(stored_file, expiration_minutes, link_password)
    db.session.commit()

    download_url = url_for("files.download", token=token, _external=True)
    flash(f"New secure link: {download_url}", "success")
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
    stored_path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_file.stored_filename
    if not stored_path.exists():
        log_access("missing_file", share_link)
        db.session.commit()
        return render_template(
            "download.html",
            title="File unavailable",
            message="The encrypted file could not be found on the server.",
        ), 404

    ciphertext = stored_path.read_bytes()
    plaintext = decrypt_bytes(
        ciphertext,
        stored_file.nonce,
        current_app.config["ENCRYPTION_KEY"],
    )

    share_link.used_at = utc_now()
    log_access("success", share_link)
    db.session.commit()

    return send_file(
        BytesIO(plaintext),
        as_attachment=True,
        download_name=stored_file.original_filename,
    )
