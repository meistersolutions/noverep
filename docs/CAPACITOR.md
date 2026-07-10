# NoRepeat Android app (Capacitor)

Native Android shell around the NoRepeat web app. Uses your deployed API at
`https://noverep-api.onrender.com` and includes the latest queue / history features.

## What you need

1. **Node.js 18+** and npm
2. **Android Studio** (latest stable) with:
   - Android SDK 35
   - Android SDK Platform-Tools
   - A device or emulator
3. On your phone: **Developer options → USB debugging** ON

## One-time setup

```powershell
cd C:\Users\smile\Projects\noverep\frontend
npm install
```

Confirm API URL is set (already created for you):

`frontend/.env.production.local`

```env
VITE_API_URL=https://noverep-api.onrender.com/api/v1
```

### Backend CORS (Render)

In the **noverep-api** Render env, ensure `CORS_ORIGINS` includes Capacitor origins, for example:

```env
CORS_ORIGINS=http://localhost:5173,https://noverep.onrender.com,capacitor://localhost,https://localhost,http://localhost
```

Redeploy the API after changing CORS.

---

## Build + install on your phone (recommended)

### Option A — USB + Android Studio (easiest)

1. Plug in your phone with USB debugging enabled.
2. From `frontend/`:

```powershell
cd C:\Users\smile\Projects\noverep\frontend
npm run cap:sync
npm run cap:android
```

3. Android Studio opens the `android/` project.
4. Wait for Gradle sync to finish.
5. Select your phone in the device dropdown.
6. Click **Run** (green play).

The app installs as **NoRepeat** (`com.noverep.app`).

### Option B — CLI install

```powershell
cd C:\Users\smile\Projects\noverep\frontend
npm run cap:run:android
```

### Option C — Build APK and sideload

```powershell
cd C:\Users\smile\Projects\noverep\frontend
npm run cap:apk
```

APK path:

```
frontend\android\app\build\outputs\apk\debug\app-debug.apk
```

Copy that file to your phone and open it to install (allow “Install unknown apps” for Files/Chrome if prompted).

---

## After every web/app code change

Re-sync so the Android shell gets the new UI:

```powershell
cd C:\Users\smile\Projects\noverep\frontend
npm run cap:sync
```

Then Run again from Android Studio (or `npm run cap:run:android` / `npm run cap:apk`).

---

## What’s included in this shell

| Feature | Status |
|---------|--------|
| Latest web UI (queue remove, history CSV, NoRepeat memory) | Bundled via `cap:sync` |
| Production API (`noverep-api.onrender.com`) | Baked via `.env.production.local` |
| Background / lock-screen keep-alive | Wake lock + App plugin + Media Session |
| Autoplay in WebView | `mediaPlaybackRequiresUserGesture=false` |
| YouTube iframe playback | Off-screen 320×180 player |

## Background playback (Android) — NewPipe-style

The Android app no longer relies on the YouTube iframe for audio when the screen
is off. Like NewPipe, it:

1. Resolves a direct audio stream URL (`GET /tracks/audio-stream` via yt-dlp)
2. Plays it with **ExoPlayer** inside a **foreground media service**

You should see a persistent **NoRepeat** notification while a song plays, and
audio should continue with the screen locked.

### Requirements

1. Deploy the latest **noverep-api** (includes `/tracks/audio-stream`)
2. Rebuild/reinstall the Android app (**v1.4.0+**)
3. Phone: Notifications allowed + Battery → Unrestricted for NoRepeat

### After updating

```powershell
cd C:\Users\smile\Projects\noverep\frontend
npm run cap:sync
npm run cap:android
```

Then **Run ▶** on your phone.

### Limitations

- Stream URLs come from yt-dlp on the API host; if extraction fails on Render, playback will error (check API logs).
- Web / mobile browser still uses the YouTube iframe (background limits remain there).
- YouTube ToS still applies; this is for personal sideload use.


## Troubleshooting

| Problem | Fix |
|---------|-----|
| White screen | Run `npm run cap:sync` again, then reinstall |
| API / network errors | Confirm `.env.production.local` has HTTPS API URL, then rebuild |
| CORS errors | Add `https://localhost` and `capacitor://localhost` to API `CORS_ORIGINS` |
| Gradle sync fails | Open Android Studio → SDK Manager → install SDK 35 + Build-Tools |
| Phone not listed | Enable USB debugging; try another cable; accept the RSA prompt on phone |
| Audio stops when screen off | Phone Settings → Apps → NoRepeat → Battery → Unrestricted |

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run cap:sync` | Build web app + copy into Android project + native patches |
| `npm run cap:android` | Open Android Studio |
| `npm run cap:run:android` | Sync + install/run on connected device |
| `npm run cap:apk` | Sync + build debug APK for sideload |
| `npm run cap:patch-native` | Re-apply background-audio manifest patches only |

## Optional: live reload while developing

1. Start Vite on your LAN IP:

```powershell
npm run dev -- --host 0.0.0.0
```

2. Temporarily set in `capacitor.config.ts`:

```ts
server: {
  url: 'http://YOUR_PC_LAN_IP:5173',
  cleartext: true,
},
```

3. `npm run cap:sync` and run from Android Studio.

4. Remove `server.url` before production/sideload builds.
