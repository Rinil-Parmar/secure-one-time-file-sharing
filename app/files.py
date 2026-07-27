from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import db
from app.models import StoredFile


files_bp = Blueprint("files", __name__)


@files_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    uploaded_file = request.files.get("file")
    expiration_minutes = request.form.get("expiration_minutes", "60")

    if uploaded_file is None or uploaded_file.filename == "":
        flash("Please choose a file before uploading.", "error")
        return redirect(url_for("dashboard"))

    try:
        expiration_minutes = int(expiration_minutes)
    except ValueError:
        flash("Expiration time must be a number.", "error")
        return redirect(url_for("dashboard"))

    if expiration_minutes < 1 or expiration_minutes > 1440:
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
    uploaded_file.save(stored_path)

    stored_file = StoredFile(
        owner_id=current_user.id,
        original_filename=safe_name,
        stored_filename=stored_name,
    )
    db.session.add(stored_file)
    db.session.commit()

    flash("File uploaded successfully. Secure link creation is coming next.", "success")
    return redirect(url_for("dashboard"))
