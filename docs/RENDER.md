# Putting Shabetz on the internet with Render

About 20 minutes, no programming. At the end you have a web address where anyone
can sign in with Google, create a project, and invite others to it — from a
computer or a phone.

Three free services are involved:

- **Neon** keeps the **database**: every project, person, schedule and account.
- **Render** runs the **website**: the pages and the server together, from
  `render.yaml` in this project.
- **Firebase** lets people sign in with Google.

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

## 3. Turn on Google sign-in (Firebase)

People sign in — and sign up — with their Google account, the same way as in
AppMyTrip. Google checks who they are through **Firebase**, which is free for
this.

You can reuse the Firebase project you already have for AppMyTrip, or create a
new one. Either works.

1. Go to **https://console.firebase.google.com** and open your project (or
   **Create a project** → name it `shabetz` → you can turn Google Analytics off).
2. **Build → Authentication → Get started** (only the first time).
3. **Sign-in method** tab → **Google** → **Enable** → choose a support email →
   **Save**. (If AppMyTrip already uses Google sign-in here, it is on already.)
4. **Settings** tab → **Authorized domains** → **Add domain** → type your Render
   address **without** `https://`, e.g. `shabetz-xxxx.onrender.com` → **Add**.
   Without this, the Google window closes with an error.
5. Click the gear ⚙ next to **Project Overview** → **Project settings** →
   **General**. Under **Your apps**, click the web icon **`</>`**, name it
   `shabetz`, and **Register app** (skip hosting). Firebase shows a block like:

   ```js
   const firebaseConfig = {
     apiKey: "AIza...",
     authDomain: "your-project.firebaseapp.com",
     projectId: "your-project",
     appId: "1:1234:web:abcd",
     ...
   };
   ```

   Keep this page open for the next step. (These values are not secrets —
   every visitor's browser receives them — but copy them exactly.)

## 4. Give the four values to Render

1. In Render, open the **shabetz** web service → **Environment**.
2. Add these four, one by one (**Add Environment Variable**):

   | Key | Value from the Firebase block |
   | :-- | :-- |
   | `SHABETZ_FIREBASE_API_KEY` | `apiKey` |
   | `SHABETZ_FIREBASE_AUTH_DOMAIN` | `authDomain` |
   | `SHABETZ_FIREBASE_PROJECT_ID` | `projectId` |
   | `SHABETZ_FIREBASE_APP_ID` | `appId` |

   Paste only what is inside the quotes.
3. **Save, rebuild, and deploy**. After a few minutes the service is **Live**
   again.

## 5. Sign in and start a project

1. Open your address, e.g. `https://shabetz-xxxx.onrender.com`.
2. **Continue with Google**. The first time, this creates your account.
3. Name your first project (for example, your organisation) and **Create
   project**. You are its **administrator**; the setup guide opens. The files
   in `examples/` work here too.

Anyone can sign up the same way and create projects of their own. Each project
is separate: nobody sees a project they are not a member of.

## 6. Bring people into your project

**Configuration → Members → Invite by link.**

1. Choose the role:
   - **Administrator** — everything, including members and invite links.
   - **Collaborator** — edits people, jobs and settings, generates schedules
     and approves time off, but cannot manage members.
   - **Staff** — sees their own shifts and asks for time off. Choose which
     person in the roster they are, so they see their shifts.
2. **Create link** → **Copy**, and send it by WhatsApp or email.
3. They open it, sign in with Google, and press **Join the project**.

A link for an administrator, a collaborator or a named person works **once**.
A staff link without a person can be shared with a whole team until it
expires. The link is shown only when created; if it gets lost, **Revoke** it
and create another. Roles can be changed, and people removed, in the list
below the links.

**Add a second administrator** to each project, so it is never left with
nobody able to manage it.

### Already had the site running before Google sign-in?

Nothing is lost. Everything you entered became your first project, and the
administrator you created keeps it. Sign in with **Continue with Google** using
the **same email address** as that administrator; the two are joined
automatically. (**Sign in with email and password instead** also still works
for that account.)

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
- **The Google window opens and closes with an error**, or says the domain is
  not authorized: add the Render address to Firebase → Authentication →
  Settings → **Authorized domains** (step 3.4).
- **There is no Google button.** Check the four `SHABETZ_FIREBASE_…` values
  under the service's **Environment** tab (step 4), then redeploy.
- **Someone's invite link "is not valid any more".** It was used, expired or
  revoked; create a new one.
- **The page loads slowly the first time.** That is the free plan waking up.

## The website and the Windows app are separate

Each keeps its own data. People entered in one do not appear in the other.
