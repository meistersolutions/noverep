# Deploy Songs Library (Render + Neon) — same pattern as NoRepeat

## 1. Create a Postgres database (Neon)

1. Go to https://console.neon.tech and sign in.
2. Create a project, e.g. `songs-library` (or a second database in your existing Neon project).
3. Copy the connection string. Prefer the **pooled** URL if Neon shows one.
4. It should look like:
   `postgresql://user:pass@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`

Do **not** reuse the NoRepeat database — keep catalogs separate.

## 2. Push this branch / merge to GitHub

Songs Library lives in the `noverep` repo under `songs-library/`. Ensure latest code is on GitHub (`main` or your PR branch).

## 3. Create the Render web service

### Option A — Blueprint (updates `render.yaml`)

1. https://dashboard.render.com → **New** → **Blueprint**
2. Connect `meistersolutions/noverep`
3. Approve the new `songs-library` service from `render.yaml`
4. When prompted for `DATABASE_URL`, paste the Neon URL from step 1

### Option B — Manual (recommended if NoRepeat is already live)

1. Render → **New** → **Web Service**
2. Connect repo `meistersolutions/noverep`
3. Settings:
   - **Name:** `songs-library`
   - **Region:** Oregon (or same as noverep-api)
   - **Runtime:** Docker
   - **Dockerfile path:** `./songs-library/Dockerfile`
   - **Docker build context:** `./songs-library`
   - **Plan:** Free
   - **Health check path:** `/health`
4. Environment variables:

| Key | Value |
|-----|--------|
| `DATABASE_URL` | Neon URL from step 1 |
| `CORS_ORIGINS` | `https://noverep.onrender.com,https://songs-library.onrender.com` |
| `YOUTUBE_API_KEY` | Same Google YouTube Data API key as NoRepeat (recommended) |
| `YOUTUBE_COOKIES_B64` | Optional Netscape cookies.txt as base64 (yt-dlp fallback) |

5. Deploy. Public URL will be like: `https://songs-library.onrender.com`

## 4. Point NoRepeat API at the library

On **noverep-api** (existing Render service) → Environment → Add:

| Key | Value |
|-----|--------|
| `SONGS_LIBRARY_URL` | `https://songs-library.onrender.com` |
| `SONGS_LIBRARY_ENABLED` | `true` |

Save → service redeploys.

## 5. Verify

```bash
curl https://songs-library.onrender.com/health
curl https://songs-library.onrender.com/api/stats
```

Open the UI: https://songs-library.onrender.com/

## 6. Seed composers later (optional)

From a machine that can reach the public API:

```bash
curl -X POST https://songs-library.onrender.com/api/discover \
  -H "Content-Type: application/json" \
  -d '{"seeds":["Ilaiyaraaja","A. R. Rahman","Yuvan Shankar Raja"],"limit_per_seed":300}'
```

Or use the **Discover 3 composers** button on the library homepage.

## Notes

- Free Render services **spin down** after idle; first request may take ~30–60s.
- Use **Neon Postgres**, not SQLite on Render — disk is ephemeral and data would vanish on redeploy.
- Tables are created automatically on startup (`create_all`).
- Background YouTube mapping uses **YouTube Data API** when `YOUTUBE_API_KEY` is set. Without it, yt-dlp search often fails with **HTTP 403** from Render IPs — set the API key (reuse NoRepeat’s key) on the `songs-library` service.
- **Keepalive caveat:** NoRepeat pings Songs Library every minute, and Songs Library pings NoRepeat back (`NOREPEAT_KEEPALIVE_URL`). That only works while **at least one** of the two free-tier services is awake. If **both** sleep (no traffic overnight), both stay down until a user hits either URL. For always-on, use a free external cron (e.g. [cron-job.org](https://cron-job.org)) to hit both `/health` endpoints every 5–10 minutes.
- Jobs left `running` after a sleep are auto-requeued on wake; use **Resume** on the home page if a seed looks stuck.
