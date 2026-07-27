from datetime import datetime, timezone

from flask_login import UserMixin

from app import db


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    files = db.relationship("StoredFile", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"


class StoredFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    nonce = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    owner = db.relationship("User", back_populates="files")
    share_links = db.relationship(
        "ShareLink",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="ShareLink.created_at",
    )

    def __repr__(self):
        return f"<StoredFile {self.original_filename}>"


class ShareLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey("stored_file.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    file = db.relationship("StoredFile", back_populates="share_links")
    access_logs = db.relationship("AccessLog", back_populates="share_link", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ShareLink file_id={self.file_id}>"


class AccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    share_link_id = db.Column(db.Integer, db.ForeignKey("share_link.id"), nullable=True, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    ip_address = db.Column(db.String(80), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    share_link = db.relationship("ShareLink", back_populates="access_logs")

    def __repr__(self):
        return f"<AccessLog {self.status}>"
