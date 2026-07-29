# SecureShare

SecureShare is a Flask web application for sharing confidential files through
encrypted, expiring, one-time download links. Files are encrypted before
storage, raw access tokens are never saved, and every successful or rejected
access attempt is recorded.

## Live Application

**[Open the deployed SecureShare application](https://secure-one-time-file-sharing.onrender.com/)**

The production environment runs on Render with Supabase PostgreSQL and a
private Supabase Storage bucket. Render's free service may require a short
cold-start delay after inactivity.

## Main Features

- User registration, login, logout, and an owner-only dashboard
- Maximum upload size of 16 MB
- AES-GCM encryption before server-side storage
- Local encrypted storage during development
- Private S3-compatible Supabase Storage in production
- Cryptographically secure 256-bit access tokens
- SHA-256 token hashes stored instead of raw download tokens
- Custom expiration from 1 minute to 7 days
- Live expiration countdown and browser-local timestamps
- Atomic one-time download enforcement
- Concurrent replay prevention
- Optional password protection with Werkzeug hashing
- New-link and revoke-link owner controls
- Permanent owner-only deletion of encrypted files and associated records
- Clear rejection pages for invalid, expired, revoked, and used links
- Audit logging for successful and rejected access attempts
- AES-GCM integrity verification for modified ciphertext
- CSRF protection and secure production response headers
- Automated security tests and GitHub Actions CI

## Architecture

```text
Browser
   |
   | HTTPS
   v
Render Web Service
Flask + Gunicorn
   |
   +---- Supabase PostgreSQL
   |     Users, file metadata, token hashes, link state, audit logs
   |
   +---- Private Supabase Storage bucket
         AES-GCM ciphertext only
```

For local development, SQLite replaces PostgreSQL and `instance/uploads/`
replaces Supabase Storage.

## Secure File Flow

```text
Authenticated owner uploads a file
              |
              v
Server validates and encrypts it with AES-GCM
              |
              v
Ciphertext is stored; metadata is saved separately
              |
              v
Random token is generated; only its SHA-256 hash is stored
              |
              v
Recipient opens the temporary link
              |
              v
Token, expiry, revocation, and optional password are validated
              |
              v
File is integrity-checked, decrypted in memory, and downloaded once
              |
              v
Atomic database update permanently consumes the link
```

## Technology

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, Flask, Gunicorn |
| Authentication | Flask-Login, Werkzeug password hashing |
| Forms and CSRF | Flask-WTF |
| Data access | Flask-SQLAlchemy |
| Local database | SQLite |
| Production database | Supabase PostgreSQL |
| Encryption | `cryptography` AES-GCM |
| Production file storage | Supabase Storage through its S3-compatible API |
| Frontend | HTML, Bootstrap, custom CSS and JavaScript |
| Testing | pytest, GitHub Actions |
| Hosting | Render |

## Local Setup

### Windows PowerShell

```powershell
git clone https://github.com/Rinil-Parmar/secure-one-time-file-sharing.git
cd secure-one-time-file-sharing

python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

Copy-Item .env.example .env
flask --app run:app init-db
python run.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

### Ubuntu

```bash
git clone https://github.com/Rinil-Parmar/secure-one-time-file-sharing.git
cd secure-one-time-file-sharing

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
flask --app run:app init-db
python run.py
```

## Configuration

Copy `.env.example` to `.env` and replace its development secrets. Never commit
the `.env` file.

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Use `development` locally and `production` on Render |
| `SECRET_KEY` | Signs Flask sessions and CSRF tokens |
| `ENCRYPTION_KEY` | Derives the 256-bit AES encryption key |
| `DATABASE_URL` | SQLite locally or Supabase PostgreSQL in production |
| `STORAGE_BACKEND` | `local` or `s3` |
| `STORAGE_BUCKET` | Private S3 bucket name |
| `S3_ENDPOINT_URL` | Supabase S3-compatible endpoint |
| `S3_ACCESS_KEY_ID` | Server-side S3 access-key ID |
| `S3_SECRET_ACCESS_KEY` | Server-side S3 secret |
| `S3_REGION` | Supabase project region |
| `BEHIND_PROXY` | Set to `1` behind Render's HTTPS proxy |

Changing or losing `ENCRYPTION_KEY` makes previously uploaded ciphertext
impossible to decrypt. Store the production key securely.

## Database and Maintenance Commands

```powershell
flask --app run:app init-db
flask --app run:app upgrade-db
flask --app run:app cleanup-files
flask --app run:app routes
```

- `init-db` creates missing tables and applies supported schema upgrades.
- `upgrade-db` applies supported upgrades to an existing database.
- `cleanup-files` removes encrypted files that have no active links.

Local runtime data is written to `instance/` and is intentionally excluded from
Git.

## Automated Tests

```powershell
python -m pytest -q
```

Current result:

```text
15 passed
```

The test suite covers:

- Registration, authentication, and dashboard authorization
- CSRF rejection
- Production secret validation
- Encryption at rest and token hashing
- Custom expiration validation
- Cross-database UTC timestamp handling
- Valid one-time downloads and replay rejection
- Modified and expired tokens
- Revocation
- Optional link passwords
- Audit logging
- AES-GCM integrity failures
- Concurrent download attempts
- Owner-only deletion
- Automatic cleanup

## Production Deployment

Render deploys the `feature/render-supabase-deployment` branch. Application
features are developed and tested on `main`, then promoted to the deployment
branch.

```text
main
  |
  | merge after testing
  v
feature/render-supabase-deployment
  |
  | automatic Render deployment
  v
https://secure-one-time-file-sharing.onrender.com/
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for the complete Render and Supabase setup,
required environment variables, private bucket configuration, and deployment
verification procedure.

## Manual Security Demonstration

1. Register and log in.
2. Upload a small confidential file.
3. Confirm that only encrypted ciphertext exists in server storage.
4. Copy the generated one-time link.
5. Try an incorrect link password and confirm rejection.
6. Download with the correct password.
7. Open the same link again and confirm replay rejection.
8. Modify the token and confirm invalid-token rejection.
9. Create another link and revoke it.
10. Create a short-lived link and demonstrate expiration.
11. Review the dashboard audit trail.
12. Permanently delete the encrypted file.

## Security Notes

- Files are encrypted before storage and decrypted only in memory.
- AES-GCM provides confidentiality and authenticated integrity.
- Raw download tokens, passwords, and encryption keys are never written to the
  database or audit log.
- One-time consumption uses an atomic conditional database update.
- Used, expired, revoked, modified, and unknown links are rejected.
- File and link operations require owner authorization.
- Access passwords and account passwords are stored as salted hashes.
- Forms use CSRF tokens; logout, revoke, and deletion use POST requests.
- Production cookies are secure and HTTP-only.
- Security headers restrict framing, MIME sniffing, permissions, referrers, and
  external content sources.

## Project Structure

```text
secure-one-time-file-sharing/
|-- app/
|   |-- templates/       HTML pages
|   |-- static/          CSS and JavaScript
|   |-- auth.py          Registration and authentication
|   |-- files.py         Upload, links, downloads, logs, deletion
|   |-- models.py        SQLAlchemy models and UTC handling
|   |-- crypto_utils.py  AES-GCM encryption and decryption
|   `-- storage.py       Local and S3 storage backends
|-- tests/               Security and lifecycle tests
|-- config.py            Environment-based configuration
|-- run.py               Application entry point
|-- render.yaml          Render Blueprint configuration
|-- DEPLOYMENT.md        Production deployment guide
`-- requirements.txt     Python dependencies
```

## License

This repository is an academic security project. No open-source license has
been assigned.
