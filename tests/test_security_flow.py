from datetime import timedelta
from pathlib import Path
import re
from threading import Barrier, Thread

import pytest

from app import cleanup_inactive_files, create_app, db
from app.models import AccessLog, ShareLink, StoredFile, User, utc_now

from tests.conftest import get_user, register_and_login, upload_file


def test_register_login_and_dashboard_protection(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.location

    response = client.post(
        "/register",
        data={"username": "alice", "password": "password123"},
        follow_redirects=True,
    )
    assert b"Account created" in response.data

    response = client.post(
        "/login",
        data={"username": "alice", "password": "password123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Secure file sharing" in response.data


def test_csrf_rejects_post_without_token(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post(
        "/register",
        data={"username": "mallory", "password": "password123"},
    )
    app.config["WTF_CSRF_ENABLED"] = False

    assert response.status_code == 400
    assert b"Request could not be verified" in response.data


def test_production_rejects_development_secrets():
    with pytest.raises(RuntimeError, match="Production requires secure environment values"):
        create_app(
            {
                "APP_ENV": "production",
                "SECRET_KEY": "dev-secret-key-change-later",
                "ENCRYPTION_KEY": "dev-encryption-key-change-later",
            }
        )


def test_upload_encrypts_file_and_hashes_token(client, app):
    register_and_login(client)
    payload = b"very secret content"
    response, token = upload_file(client, payload=payload)

    user = get_user()
    stored_file = StoredFile.query.filter_by(owner_id=user.id).one()
    share_link = ShareLink.query.filter_by(file_id=stored_file.id).one()
    stored_path = Path(app.config["UPLOAD_FOLDER"]) / stored_file.stored_filename
    ciphertext = stored_path.read_bytes()

    assert response.status_code == 200
    assert stored_file.original_filename == "secret.txt"
    assert ciphertext != payload
    assert payload not in ciphertext
    assert len(share_link.token_hash) == 64
    assert token != share_link.token_hash


def test_valid_download_works_once(client):
    register_and_login(client)
    payload = b"download once"
    _, token = upload_file(client, payload=payload)

    first = client.get(f"/download/{token}")
    second = client.get(f"/download/{token}")

    assert first.status_code == 200
    assert first.data == payload
    assert second.status_code == 410
    assert b"already been used" in second.data


def test_invalid_expired_and_revoked_links_are_rejected(client):
    register_and_login(client)
    _, token = upload_file(client)
    user = get_user()
    stored_file = StoredFile.query.filter_by(owner_id=user.id).one()
    share_link = ShareLink.query.filter_by(file_id=stored_file.id).one()

    invalid = client.get("/download/modified-token")
    assert invalid.status_code == 404

    share_link.expires_at = utc_now() - timedelta(minutes=1)
    db.session.commit()
    expired = client.get(f"/download/{token}")
    assert expired.status_code == 410
    assert b"expired" in expired.data

    fresh = client.post(
        f"/files/{stored_file.id}/share",
        data={"expiration_minutes": "15"},
        follow_redirects=True,
    )
    fresh_token = re.search(rb"/download/([A-Za-z0-9_\-]+)", fresh.data).group(1).decode("ascii")
    fresh_link = ShareLink.query.order_by(ShareLink.id.desc()).first()
    revoked = client.post(f"/links/{fresh_link.id}/revoke", follow_redirects=True)
    revoked_download = client.get(f"/download/{fresh_token}")

    assert b"Secure link revoked" in revoked.data
    assert revoked_download.status_code == 410


def test_password_protected_link_rejects_wrong_password(client):
    register_and_login(client)
    payload = b"protected content"
    _, token = upload_file(client, payload=payload, password="open-sesame")

    prompt = client.get(f"/download/{token}")
    wrong = client.post(f"/download/{token}", data={"password": "wrong"})
    correct = client.post(f"/download/{token}", data={"password": "open-sesame"})

    assert prompt.status_code == 200
    assert b"Password required" in prompt.data
    assert wrong.status_code == 403
    assert b"Incorrect password" in wrong.data
    assert correct.status_code == 200
    assert correct.data == payload


def test_access_logs_are_recorded(client):
    register_and_login(client)
    _, token = upload_file(client, password="secret")

    client.get("/download/bad-token")
    client.post(f"/download/{token}", data={"password": "wrong"})
    client.post(f"/download/{token}", data={"password": "secret"})
    client.post(f"/download/{token}", data={"password": "secret"})

    statuses = [log.status for log in AccessLog.query.order_by(AccessLog.id).all()]
    assert statuses == ["invalid_token", "wrong_password", "success", "reused"]


def test_modified_ciphertext_is_rejected(client, app):
    register_and_login(client)
    _, token = upload_file(client, payload=b"integrity protected")
    stored_file = StoredFile.query.one()
    stored_path = Path(app.config["UPLOAD_FOLDER"]) / stored_file.stored_filename
    ciphertext = bytearray(stored_path.read_bytes())
    ciphertext[0] ^= 1
    stored_path.write_bytes(ciphertext)

    response = client.get(f"/download/{token}")

    assert response.status_code == 409
    assert b"integrity check failed" in response.data
    assert ShareLink.query.one().used_at is None
    assert AccessLog.query.one().status == "integrity_error"


def test_concurrent_download_only_succeeds_once(app, client):
    register_and_login(client)
    payload = b"only one concurrent response"
    _, token = upload_file(client, payload=payload)
    barrier = Barrier(2)
    results = []

    def download_at_same_time():
        with app.test_client() as thread_client:
            barrier.wait()
            response = thread_client.get(f"/download/{token}")
            results.append((response.status_code, response.data))

    threads = [Thread(target=download_at_same_time) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(status for status, _ in results) == [200, 410]
    assert sum(body == payload for _, body in results) == 1


def test_cleanup_removes_inactive_files_only(client, app):
    register_and_login(client)
    upload_file(client, filename="active.txt")
    upload_file(client, filename="used.txt")

    user = get_user()
    files = StoredFile.query.filter_by(owner_id=user.id).order_by(StoredFile.id).all()
    active_file, used_file = files
    used_link = ShareLink.query.filter_by(file_id=used_file.id).one()
    used_link.used_at = utc_now()
    db.session.commit()

    removed = cleanup_inactive_files(app.config["UPLOAD_FOLDER"])

    active_path = Path(app.config["UPLOAD_FOLDER"]) / active_file.stored_filename
    used_path = Path(app.config["UPLOAD_FOLDER"]) / used_file.stored_filename
    assert removed == 1
    assert active_path.exists()
    assert not used_path.exists()
    assert StoredFile.query.filter_by(id=active_file.id).first() is not None
    assert StoredFile.query.filter_by(id=used_file.id).first() is None
