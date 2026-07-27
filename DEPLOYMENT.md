# Free Deployment: Render and Supabase

## Architecture

- Render Free Web Service runs Flask with Gunicorn.
- Supabase PostgreSQL stores accounts, file metadata, token hashes, and logs.
- A private Supabase Storage bucket stores AES-GCM ciphertext only.
- Render terminates HTTPS and forwards requests to Gunicorn.

## Supabase values required by Render

Create a Supabase project and keep its database password in a password manager.

1. Create a private Storage bucket named `encrypted-files`.
2. Open the project connection dialog and copy the **Session pooler** connection
   string on port `5432`. Add `?sslmode=require` if it has no query string.
3. Open Storage settings and its S3 configuration.
4. Generate server-side S3 access keys.
5. Copy the direct storage endpoint, access key ID, secret access key, region,
   and bucket name.

Never commit these values. S3 access keys bypass Storage row-level security and
must be used only by the Flask server.

## Render configuration

Create a new Blueprint from this GitHub repository. Render reads `render.yaml`.
Enter these secret values when prompted:

- `DATABASE_URL`
- `S3_ENDPOINT_URL`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `S3_REGION`

The remaining environment values are defined by `render.yaml`. Render generates
the Flask session secret and file-encryption secret once. Save a secure backup
of `ENCRYPTION_KEY`; losing or changing it makes every stored file impossible
to decrypt.

After deployment:

1. Open `/health` and confirm `{"status":"ok"}`.
2. Register a test account.
3. Upload a small text file.
4. Confirm an object appears in the private `encrypted-files` bucket.
5. Confirm the object content is ciphertext, not plaintext.
6. Send the generated URL using the email button.
7. Download once and confirm the second request is rejected.

Free Render services sleep after inactivity, so open the app shortly before a
demonstration. Free Supabase projects also pause after extended inactivity.
