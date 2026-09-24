# Putting Shabetz on the internet with Render

About 20 minutes, no programming. At the end you have a web address anyone
you invite can sign in to, from a computer or a phone.

Two free services are involved:

- **Neon** keeps the **database**: every division, person, schedule and account.
- **Render** runs the **website**: the pages and the server together, from
  `render.yaml` in this project.

The database is kept at Neon rather than Render on purpose: Render's free
database is deleted after a fixed period, with no way to renew it. Neon's
free database has no expiry.

## 1. Create the database at Neon

1. Go to **https://neon.tech** → **Sign up** (with GitHub or Google is easiest).
2. Create a project: name it `shabetz`, pick the region closest to you
   (for Israel: **Europe (Frankfurt)**), and create it.
3. On the project dashboard, click **Connect**. Copy the **connection string**.
   It looks like
   `postgresql://user:password@ep-something.eu-central-1.aws.neon.tech/neondb?sslmode=require`.
   Keep it for step 2; treat it like a password.

## 2. Create the website at Render

1. Go to **https://render.com** → **Get Started** → **Sign up with GitHub**.
   When asked, install the Render GitHub App and give it access to
   **shabetz-na** only.
2. In Render, click **New +** (top right) → **Blueprint**.
3. Pick **shabetz-na** and click **Connect**.
4. **Blueprint Name**: type `shabetz`.
5. Render asks for **SHABETZ_DATABASE_URL**: paste the Neon connection
   string from step 1, exactly as copied.
6. Click **Apply** (or **Deploy Blueprint**). The first build takes about
   5–10 minutes. When the **shabetz** service shows **Live** in green, it is
   ready.

## 3. Find your address and setup code

1. Click the **shabetz** web service. Your address is at the top, like
   `https://shabetz-xxxx.onrender.com`.
2. Open the **Environment** tab. Find **SHABETZ_SETUP_TOKEN** and click the
   eye icon to show it. Copy that value — it is your setup code.

## 4. Create the administrator

1. Open your address. The page asks you to **create the first administrator**.
2. Paste the setup code, then your name, email and a password (at least 12
   characters).
3. You are in. The setup guide opens; the files in `examples/` work here too.

Without the setup code nobody else can claim the site, even if they find the
address first. Once the administrator exists, the code is no longer used.

## 5. Invite people

**Configuration → Accounts → Add account.** Give each person the address and
their password. Staff accounts should be linked to their person in the roster
so they see their own shifts.

Create a **second administrator** too: on the website, a forgotten password is
reset by another administrator (the Windows app's reset-code file does not
exist here).

## Costs and the free plans

Both start free. What that means in practice:

- **Neon (database)**: free with no expiry, and plenty for an organisation's
  roster and schedules. Neon's dashboard shows usage.
- **Render (website)**: the free plan **sleeps** after 15 minutes without
  visitors; the next visit takes about a minute to wake it. Nothing is lost —
  the data is at Neon. For a site that answers instantly, change the service
  to the paid **Starter** plan in Render (service → **Settings** →
  **Instance type**).

## Updates

Nothing to do. When a change is merged into `main` on GitHub, Render rebuilds
and updates the site by itself, in a few minutes. Data stays.

## If something goes wrong

- **The deploy failed.** Open the web service → **Events** → the failed deploy
  → **Logs**. Copy the last lines and send them to whoever supports you.
- **The logs mention the database or a connection.** Check
  **SHABETZ_DATABASE_URL** under the service's **Environment** tab is the whole
  Neon string, including the `?sslmode=require` part.
- **"Incorrect setup code".** Copy **SHABETZ_SETUP_TOKEN** again from the
  Environment tab; it is long, so make sure all of it was pasted.
- **The page loads slowly the first time.** That is the free plan waking up.

## The website and the Windows app are separate

Each keeps its own data. People entered in one do not appear in the other.
