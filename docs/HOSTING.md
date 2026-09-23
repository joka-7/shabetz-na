# Hosting the Shabetz website

This is the version people sign in to from anywhere with their own accounts.
It is the same application as the Windows desktop app, run as a server with
MySQL. (The desktop app keeps its data on one computer; the two do not share
data.)

## What you need

- A server or container host that can run a Docker image.
- A MySQL 8 database (most hosts offer a managed one).
- A domain name, and HTTPS in front of the app — from the host, or from a
  reverse proxy such as Caddy or nginx.

## 1. Configure

Create a `.env` file from `.env.example`. The values that matter:

| Setting | Value |
| :-- | :-- |
| `SHABETZ_DATABASE_URL` | `mysql+pymysql://USER:PASS@HOST:3306/DB?charset=utf8mb4` — keep `charset=utf8mb4` |
| `SHABETZ_SECRET_KEY` | A long random string, kept the same across restarts. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Google sign-in refuses to work in production without it. |
| `SHABETZ_COOKIE_SECURE` | `true` (the image sets this). Only turn it off for plain-http testing. |
| `SHABETZ_FORWARDED_ALLOW_IPS` | The address of your reverse proxy. **Required for correct sign-in throttling** — without it every visitor looks like the proxy, and one person's failed sign-ins throttle everyone. |

Google sign-in is optional: set `SHABETZ_GOOGLE_CLIENT_ID`,
`SHABETZ_GOOGLE_CLIENT_SECRET`, and `SHABETZ_GOOGLE_REDIRECT_URI` to
`https://your-domain/api/auth/google/callback`. Leave them empty and the Google
button simply does not appear.

## 2. Run

```bash
docker build -t shabetz .
docker run -d --name shabetz -p 8000:8000 --env-file .env --restart unless-stopped shabetz
```

The server applies database migrations itself on start.

## 3. Claim it — do this straight away

Until an administrator exists, the server's log shows a **setup code**:

```bash
docker logs shabetz
```

```
============================================================
  No administrator exists yet.
  Open this site and enter setup code:  ABCD-EFGH-JKMN
============================================================
```

Open your site, enter that code, and create the administrator account. Without
the code nobody can claim the site, so a newly deployed server is not open to
whoever finds it first. The code changes on every restart until the first
administrator exists, then it is no longer needed.

Then add everyone else under **Configuration → Accounts**.

## Security notes

- **Always run behind HTTPS.** Session cookies are marked secure, so over plain
  http nobody can stay signed in.
- **Sign-in throttling:** repeated failed sign-ins from one address are slowed
  down before they can lock the targeted account, so an attacker cannot lock
  your administrators out. This depends on `SHABETZ_FORWARDED_ALLOW_IPS` being
  set correctly (above).
- **Keep two administrators.** The last administrator cannot be removed or
  demoted, but a second one is what lets you recover a forgotten password.
- **Back up the MySQL database** with your host's tools or `mysqldump`.

## Without Docker

Any machine with Python 3.11+ and Node 22:

```bash
make install web
uv run shabetz serve --host 0.0.0.0 --port 8000
```
