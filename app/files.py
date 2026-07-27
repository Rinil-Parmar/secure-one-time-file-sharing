from datetime import timedelta
import hashlib
from io import BytesIO
from pathlib import Path
import secrets
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import db
from app.crypto_utils import decrypt_bytes, encrypt_bytes
from app.models import ShareLink, StoredFile, utc_now


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


def create_share_link(stored_file, expiration_minutes):
    token = secrets.token_urlsafe(32)
    share_link = ShareLink(
        file_id=stored_file.id,
        token_hash=hash_token(token),
        expires_at=utc_now() + timedelta(minutes=expiration_minutes),
    )
    db.session.add(share_link)
    return token


@files_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    uploaded_file = request.files.get("file")
    expiration_minutes = request.form.get("expiration_minutes", "60")

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

    token = create_share_link(stored_file, expiration_minutes)
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
    if expiration_minutes is None:
        flash("Expiration time must be between 1 minute and 24 hours.", "error")
        return redirect(url_for("dashboard"))

    token = create_share_link(stored_file, expiration_minutes)
    db.session.commit()

    download_url = url_for("files.download", token=token, _external=True)
    flash(f"New secure link: {download_url}", "success")
    return redirect(url_for("dashboard"))


@files_bp.route("/download/<token>")
def download(token):
    share_link = ShareLink.query.filter_by(token_hash=hash_token(token)).first()
    if share_link is None:
        return render_template(
            "download.html",
            title="Invalid link",
            message="This download link is not recognized.",
        ), 404

    if share_link.expires_at <= utc_now():
        return render_template(
            "download.html",
            title="Link expired",
            message="This download link has expired.",
        ), 410

    if share_link.used_at is not None:
        return render_template(
            "download.html",
            title="Link already used",
            message="This download link has already been used.",
        ), 410

    stored_file = share_link.file
    stored_path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_file.stored_filename
    if not stored_path.exists():
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
    db.session.commit()

    return send_file(
        BytesIO(plaintext),
        as_attachment=True,
        download_name=stored_file.original_filename,
    )
