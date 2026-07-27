# Secure One-Time File Sharing

A Flask web application for encrypted one-time file sharing with expiring access tokens, optional link passwords, and access-attempt logging.

## Features

- User registration, login, logout, and protected dashboard
- Secure upload storage outside the public static folder
- Local filesystem storage for development and private S3-compatible storage in production
- AES-GCM encryption before files are written to disk
- Secure random download tokens generated with Python `secrets`
- SHA-256 token hashes stored in SQLite instead of raw tokens
- Configurable link expiration
- One-time download enforcement
- Atomic replay prevention for concurrent download requests
- Optional password-protected download links
- CSRF protection for all state-changing forms
- Authenticated encryption integrity checks and secure response headers
- Owner controls for creating new links and revoking active links
- Access logging for success, invalid token, expired, reused, wrong password, and missing file attempts
- Cleanup command for encrypted files that no longer have active links
- Automated security tests and GitHub Actions CI

## Technology

- Python
- Flask
- SQLite
- Flask-SQLAlchemy
- Flask-Login
- Flask-WTF
- Werkzeug password hashing
- `cryptography` AES-GCM
- Supabase PostgreSQL and private Storage for cloud deployment
- Bootstrap UI
- pytest

## Local Setup

```powershell
cd D:\NDS\NetworkingProject\secure-one-time-file-share
.\.venv\Scripts\activate
pip install -r requirements.txt
```

If the virtual environment does not exist:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Environment Variables

Copy `.env.example` to `.env`, then replace both secrets before a proper demo or deployment:

```text
APP_ENV=development
FLASK_DEBUG=0
SECRET_KEY=replace-with-a-long-random-secret
ENCRYPTION_KEY=replace-with-a-long-random-encryption-secret
```

Do not commit `.env`. It is ignored by Git.

## Database Setup

```powershell
.\.venv\Scripts\flask.exe --app run.py init-db
.\.venv\Scripts\flask.exe --app run.py upgrade-db
```

The SQLite database is stored at:

```text
instance/app.db
```

Uploaded encrypted files are stored at:

```text
instance/uploads/
```

Both are intentionally ignored by Git.

## Run App

```powershell
.\.venv\Scripts\python.exe run.py
```

Open:

```text
http://127.0.0.1:5000
```

Debug mode is off by default. Never enable the Flask debugger for an Ubuntu
demonstration or production deployment. When `APP_ENV=production`, the
application refuses to start with the development fallback secrets.

## Test

```powershell
.\.venv\Scripts\pytest.exe -q
```

The suite covers authentication, CSRF, encryption at rest, integrity failure,
one-time use, concurrent replay attempts, expiration, revocation, password
protection, audit logs, and cleanup.

```text
11 passed
```

GitHub Actions runs the same test suite on every push and pull request to `main`.

## Render and Supabase

The cloud deployment uses Render for Flask compute and Supabase for persistent
PostgreSQL data and private encrypted-object storage. See `DEPLOYMENT.md` for
the complete setup procedure.

## Demo Flow

1. Register a user.
2. Log in.
3. Upload a small confidential file.
4. Copy the generated secure download link from the success message.
5. Open the encrypted file in `instance/uploads/` and show that the plaintext is unreadable.
6. Open the generated download link and download the original file.
7. Open the same link again and show that it is rejected as already used.
8. Modify the token in the URL and show invalid-token rejection.
9. Create a new password-protected link from the dashboard.
10. Try the wrong password and show rejection.
11. Try the correct password and download successfully.
12. Create another link, revoke it, and show that it no longer downloads.
13. Show recent access attempts on the dashboard.
14. Run cleanup:

```powershell
.\.venv\Scripts\flask.exe --app run.py cleanup-files
```

## Security Notes

- Raw download tokens are shown only once and are never stored.
- Passwords are stored as hashes.
- Link passwords are stored as hashes.
- Files are encrypted before server-side storage.
- Decrypted files are streamed from memory during download, not written to disk.
- Used, expired, revoked, and invalid links are rejected.
- Concurrent requests are resolved atomically so only one download can succeed.
- AES-GCM rejects modified or corrupted ciphertext.
- CSRF tokens protect authentication, upload, link, revoke, and logout forms.
- Security headers prevent framing, referrer leakage, and MIME sniffing.
- Access logs do not store raw tokens, passwords, or encryption keys.

## Useful Commands

```powershell
git status
git log --oneline
.\.venv\Scripts\flask.exe --app run.py routes
.\.venv\Scripts\pytest.exe -q
```
