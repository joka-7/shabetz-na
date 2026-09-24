# Putting Shabetz on the internet with Render

About 15 minutes, no programming. At the end you have a web address anyone
you invite can sign in to, from a computer or a phone.

Render runs two things for you: the **website** (pages and server together)
and its **database**. Both are described in `render.yaml` in this project,
so Render sets them up in one go.

## 1. Create a Render account

1. Go to **https://render.com** and click **Get Started**.
2. Choose **Sign up with GitHub** and allow access. This is how Render reads
   the project.

## 2. Create the website from this project

1. In Render, click **New +** (top right) → **Blueprint**.
2. Find **shabetz-na** in the list and click **Connect**.
   - Not in the list? Click **Configure account** / **Configure GitHub App**,
     give Render access to *shabetz-na*, and come back.
3. **Blueprint Name**: type `shabetz`.
4. Render shows what it will create: a web service **shabetz** and a database
   **shabetz-db**. Click **Apply** (or **Deploy Blueprint**).
5. Wait. The first build takes about 5–10 minutes. When the web service shows
   **Live** in green, it is ready.

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

## Costs and the free plan — read before entering real data

The project starts on Render's **free** plans. That is fine for trying it,
with two catches:

- **The free website sleeps** after 15 minutes without visitors. The next
  visit takes about a minute to wake it. The paid **Starter** plan stays on.
- **Render deletes free databases after a trial period** (Render shows the
  date on the database page). Everything in it is lost.

Before you rely on it: open **shabetz-db** → **Info** / **Settings** →
change the plan to a paid one, and consider the same for the web service.
Prices are on Render's pricing page.

## Updates

Nothing to do. When a change is merged into `main` on GitHub, Render rebuilds
and updates the site by itself, in a few minutes. Data stays.

## If something goes wrong

- **The deploy failed.** Open the web service → **Events** → the failed deploy
  → **Logs**. Copy the last lines and send them to whoever supports you.
- **"Incorrect setup code".** Copy **SHABETZ_SETUP_TOKEN** again from the
  Environment tab; it is long, so make sure all of it was pasted.
- **The page loads slowly the first time.** That is the free plan waking up.

## The website and the Windows app are separate

Each keeps its own data. People entered in one do not appear in the other.
