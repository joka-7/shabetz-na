# Hosting the Shabetz website

This is the version people sign in to from anywhere with their own accounts.

**Using Render?** Follow [RENDER.md](RENDER.md) instead: `render.yaml` sets up
the site and its database in one step. This page is for any other host.
It is the same application as the Windows desktop app, run as a server with
MySQL. (The desktop app keeps its data on one computer; the two do not share
data.)

## What you need

- A server or container host that can run a Docker image.
- A PostgreSQL (13 or newer) or MySQL 8 database; most hosts offer a managed one.
- A domain name, and HTTPS in front of the app — from the host, or from a
  reverse proxy such as Caddy or nginx.

## 1. Configure

Create a `.env` file from `.env.example`. The values that matter:

| Setting | Value |
| :-- | :-- |
| `SHABETZ_DATABASE_URL` | PostgreSQL: the URL exactly as your host shows it (`postgres://…` or `postgresql://…`). MySQL: `mysql+pymysql://USER:PASS@HOST:3306/DB?charset=utf8mb4` — keep `charset=utf8mb4` |
| `SHABETZ_SECRET_KEY` | A long random string, kept the same across restarts. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `SHABETZ_COOKIE_SECURE` | `true` (the image sets this). Only turn it off for plain-http testing. |
| `SHABETZ_FORWARDED_ALLOW_IPS` | The address of your reverse proxy, so the server knows requests arrived over HTTPS. |
| `SHABETZ_DATA_KEY` | Optional. Encrypts personal data in the database (names, emails, notes, schedules), so someone with database access alone sees ciphertext. Generate with `shabetz generate-data-key` and **keep a copy: without it the data cannot be read again.** See [PRIVACY.md](PRIVACY.md). |
| `SHABETZ_ALLOWED_EMAILS` (or `ALLOWED_EMAILS`) | Comma-separated addresses allowed to sign up or sign in. **Empty in production lets nobody in**; `*` lets anyone in. Checked on every request, so removing an address ends its sessions. |
| `SHABETZ_TRUSTED_PROXY_HOPS` | How many proxies sit in front of the server (usually `1`). **Required for correct sign-in throttling** — the visitor's address is read that many entries from the right of `X-Forwarded-For`. Too low and every visitor looks like the proxy, so one person's failed sign-ins throttle everyone; too high and a visitor can forge their address. |

**Google sign-in** (recommended): set `SHABETZ_FIREBASE_API_KEY`,
`SHABETZ_FIREBASE_AUTH_DOMAIN`, `SHABETZ_FIREBASE_PROJECT_ID` and
`SHABETZ_FIREBASE_APP_ID` from a Firebase web app, with Google enabled as a
sign-in provider and your domain under **Authorized domains** — the steps are
in [RENDER.md](RENDER.md#3-turn-on-google-sign-in-firebase). Then anyone can
sign up, create projects and invite others by link, and step 3 below does not
apply. Leave them empty for a site with password accounts only.

## 2. Run

```bash
docker build -t shabetz .
docker run -d --name shabetz -p 8000:8000 --env-file .env --restart unless-stopped shabetz
```

The server applies database migrations itself on start.

## 3. Claim it — do this straight away (without Google sign-in)

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

Then bring everyone else in under **Configuration → Members**.

## Security notes

- **Always run behind HTTPS.** Session cookies are marked secure, so over plain
  http nobody can stay signed in.
- **Sign-in throttling:** repeated failed sign-ins from one address are slowed
  down before they can lock the targeted account, so an attacker cannot lock
  your administrators out. This depends on `SHABETZ_TRUSTED_PROXY_HOPS` being
  set correctly (above).
- **Keep two administrators.** The last administrator cannot be removed or
  demoted, but a second one is what lets you recover a forgotten password.
- **Back up the database.** `shabetz backup --folder backups` writes a dump
  with `pg_dump` (PostgreSQL) or `mysqldump` (MySQL), which must be installed;
  run it from a scheduled job. Restore with `pg_restore` or the `mysql` client.
- **Housekeeping** runs on every start: sessions and invite links that ended
  over 30 days ago are deleted. `shabetz cleanup --keep-drafts 20` also prunes
  old unpublished schedules (published ones are never touched).

## Without Docker

Any machine with Python 3.11+ and Node 22:

```bash
make install web
uv run shabetz serve --host 0.0.0.0 --port 8000
```
