# Serving the front end from Vercel

The React app is static, so it can be served from Vercel's CDN (no cold start)
while the API stays on Render. Vercel proxies `/api/*` to Render, so the browser
sees one origin and cookies and CSRF keep working unchanged.

## Setup

1. Import the repo in Vercel. Set **Root Directory** to `frontend`,
   **Build Command** `npm run build`, **Output Directory** `dist`.
2. Edit `frontend/vercel.json` and set the Render
   service host (already set to `shabetz.onrender.com`).
3. In the Firebase console, add the Vercel domain under
   Authentication → Settings → Authorized domains (Google sign-in).
4. Deploy.

## Caveat

The first API call after an idle period still wakes the Render service
(about a minute on the free plan). The app shows a "waking up the server"
notice. To avoid it, use a paid Render plan or ping `/api/health`
every ~10 minutes from an uptime monitor.
