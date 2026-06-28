# Free cloud hosting (no home PC required)

Host **NoRepeat** for **$0/month** using:

| Piece | Service | Free tier |
|-------|---------|-----------|
| Code | GitHub | Free |
| Database | [Neon](https://neon.tech) | Free Postgres (no credit card for basic) |
| API (FastAPI + yt-dlp) | [Render](https://render.com) | Free web service |
| Website (React) | Render | Free static site |

**Your app URL:** `https://noverep.onrender.com`  
**API URL:** `https://noverep-api.onrender.com`

> Free Render APIs **sleep after ~15 minutes** of no traffic. First visit after sleep may take **30–60 seconds** to wake up. Music playback works once it is awake.

---

## Before you start (one-time)

1. **GitHub account** — repo: `https://github.com/meistersolutions/noverep`
2. **Push your code** to GitHub (see README or section below)
3. **Render account** — sign up at https://render.com (GitHub login is easiest)
4. **Neon account** — sign up at https://neon.tech

---

## Step 1 — Push code to GitHub

If not pushed yet, on a machine with Git installed:

```bash
cd /path/to/noverep
git remote add origin https://github.com/meistersolutions/noverep.git
git push -u origin main
```

Use a [GitHub Personal Access Token](https://github.com/settings/tokens) as the password if prompted.

---

## Step 2 — Create free Postgres (Neon)

1. Open https://console.neon.tech → **New Project**
2. Name: `noverep`, region: closest to you
3. Open **Connection details** → copy the **connection string**
4. Copy the **connection string** and paste it into Render as `DATABASE_URL`  
   (You can use Neon’s default `postgresql://...?sslmode=require` — the app fixes it automatically.)

Save this — you will paste it into Render in Step 4.

---

## Step 3 — Deploy with Render Blueprint

1. Go to https://dashboard.render.com
2. **New** → **Blueprint**
3. Connect GitHub → select **meistersolutions/noverep**
4. Render reads `render.yaml` and proposes two services:
   - `noverep-api` (Docker backend)
   - `noverep` (static frontend)
5. When asked for **DATABASE_URL** on `noverep-api`, paste your Neon URL from Step 2
6. Click **Apply** / **Deploy**

Wait ~10–15 minutes for the first Docker build (ffmpeg + Python deps).

---

## Step 4 — Confirm CORS matches your frontend URL

After deploy, your frontend URL is shown on the `noverep` static service (usually `https://noverep.onrender.com`).

1. Render → **noverep-api** → **Environment**
2. Set **CORS_ORIGINS** to your exact frontend URL, e.g.:

   ```
   https://noverep.onrender.com
   ```

3. **Save Changes** (backend redeploys)

If you renamed services in Render, update `VITE_API_URL` on the static site to match your API URL and **redeploy** the static site.

---

## Step 5 — Open the app

**Use the frontend URL (not the API):**

| Service | URL | Purpose |
|---------|-----|---------|
| **Web app** | **https://noverep.onrender.com** | Open this in your browser to play music |
| API only | https://noverep-api.onrender.com | Backend JSON — `/` alone returns API info |
| Health check | https://noverep-api.onrender.com/health | Verify database is connected |
| API docs | https://noverep-api.onrender.com/docs | Swagger UI |

Visit: **https://noverep.onrender.com**

1. Click **Continue as Guest** (or register)
2. Complete onboarding
3. Search and play — YouTube audio runs in your browser

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| API slow first time | Normal on free tier — wait 30–60s, refresh |
| `CORS` error in browser console | Fix `CORS_ORIGINS` on API to match frontend URL exactly |
| `database unhealthy` on `/health` | Check `DATABASE_URL` is the Neon connection string; redeploy after env changes |
| Search returns nothing | yt-dlp may be rate-limited; try again in a minute |
| Build failed on Render | Open **Logs** on `noverep-api` — often out of memory on first build; retry deploy |

Health check:

```
https://noverep-api.onrender.com/health
```

Expected: `"status":"ok","database":"healthy"`

---

## Optional: custom domain (still free on Render static)

1. Render → `noverep` static site → **Custom Domains**
2. Add your domain and DNS records Render shows
3. Update **CORS_ORIGINS** on the API to include `https://yourdomain.com`
4. Rebuild static site with updated `VITE_API_URL` if API also has a custom domain

---

## Limits of free hosting

- API sleeps when idle (cold starts)
- ~512 MB RAM on free Render — enough for light use, not heavy traffic
- YouTube playback rules still apply (background play may be limited on mobile)
- Not for App Store / commercial music licensing (see product notes)

---

## Alternative: always-on free VM (advanced)

**Oracle Cloud “Always Free”** ARM VM (24 GB RAM) can run full `docker compose up -d` 24/7. Requires credit card verification, more setup. Use if cold starts on Render bother you.

```bash
# On the VM after installing Docker:
git clone https://github.com/meistersolutions/noverep.git
cd noverep
cp .env.example .env   # edit SECRET_KEY, CORS_ORIGINS
docker compose up --build -d
```

Open port `5173` in Oracle security list + firewall.

---

## Quick reference — start/stop on Render

Render manages start/stop automatically. To redeploy after code changes:

1. Push to GitHub `main`
2. Render auto-deploys (if enabled) or click **Manual Deploy** on each service

No `docker compose` commands needed on your PC.
