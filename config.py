import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DEVELOPMENT_SECRET = "dev-secret-key-change-later"
DEVELOPMENT_ENCRYPTION_KEY = "dev-encryption-key-change-later"


def normalize_database_url(database_url):
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development")
    SECRET_KEY = os.environ.get("SECRET_KEY", DEVELOPMENT_SECRET)
    ENCRYPTION_KEY = os.environ.get(
        "ENCRYPTION_KEY",
        DEVELOPMENT_ENCRYPTION_KEY,
    )
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.environ.get(
            "DATABASE_URL",
            f"sqlite:///{BASE_DIR / 'instance' / 'app.db'}",
        )
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }
    UPLOAD_FOLDER = BASE_DIR / "instance" / "uploads"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    WTF_CSRF_TIME_LIMIT = 3600
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()
    STORAGE_BUCKET = os.environ.get("STORAGE_BUCKET", "encrypted-files")
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
    S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY")
    S3_REGION = os.environ.get("S3_REGION", "us-east-1")
    BEHIND_PROXY = os.environ.get("BEHIND_PROXY", "0") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
