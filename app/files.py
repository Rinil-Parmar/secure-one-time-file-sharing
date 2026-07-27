from flask import Blueprint, flash, redirect, request, url_for
from flask_login import login_required


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

    flash("Upload form is connected. Secure file storage comes in the next step.", "success")
    return redirect(url_for("dashboard"))
