import re
from io import BytesIO

import pytest

from app import create_app, db, ensure_schema
from app.models import User


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
            "UPLOAD_FOLDER": tmp_path / "uploads",
            "ENCRYPTION_KEY": "test-encryption-key",
            "SECRET_KEY": "test-secret-key",
        }
    )

    with app.app_context():
        ensure_schema()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def register_and_login(client, username="alice", password="password123"):
    client.post("/register", data={"username": username, "password": password})
    client.post("/login", data={"username": username, "password": password})


def upload_file(client, filename="secret.txt", payload=b"confidential", password=""):
    response = client.post(
        "/upload",
        data={
            "file": (BytesIO(payload), filename),
            "expiration_minutes": "15",
            "link_password": password,
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    match = re.search(rb"/download/([A-Za-z0-9_\-]+)", response.data)
    assert match is not None
    return response, match.group(1).decode("ascii")


def get_user(username="alice"):
    return User.query.filter_by(username=username).first()
