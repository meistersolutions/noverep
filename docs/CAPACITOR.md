# Capacitor native app (background audio)

Wrap NoRepeat in a **Capacitor** shell so iOS/Android treat playback as a media app (background audio mode, lock-screen controls via Media Session).

The web app and YouTube iframe player stay the same — the native shell improves background survival on mobile.

## Prerequisites

| Platform | Tools |
|----------|--------|
| **Android** | [Android Studio](https://developer.android.com/studio), JDK 17+ |
| **iOS** | macOS, Xcode, Apple Developer account (for device install) |
| **Both** | Node.js 18+, npm |

## One-time setup

From `frontend/`:

```bash
npm install
npm run build:capacitor
npx cap add android          # Windows/macOS/Linux
npx cap add ios              # macOS only
npm run cap:patch-native     # background audio permissions + iOS AVAudioSession
```

Copy env for production API (Render):

```bash
cp .env.capacitor.example .env.production.local
# Edit VITE_API_URL to your deployed API, e.g. https://noverep-api.onrender.com/api/v1
```

Rebuild with that env, then sync:

```bash
npm run cap:sync
npm run cap:patch-native
```

### Backend CORS

Add Capacitor origins to your API `.env` / Render env:

```env
CORS_ORIGINS=http://localhost:5173,https://noverep.onrender.com,capacitor://localhost,https://localhost,http://localhost
```

Redeploy the API after changing CORS.

## Run on device

### Android

```bash
npm run cap:run:android
# or
npm run cap:sync && npm run cap:android   # opens Android Studio → Run
```

Enable **USB debugging** on the phone, connect via USB, pick the device in Android Studio.

### iOS (Mac)

```bash
npm run cap:sync && npm run cap:ios
```

Open the workspace in Xcode, select your team, run on a physical device (background audio is unreliable in Simulator).

## Dev with live reload (optional)

1. Start Vite on your LAN IP:

   ```bash
   npm run dev -- --host 0.0.0.0
   ```

2. In `capacitor.config.ts`, temporarily set:

   ```ts
   server: {
     url: 'http://192.168.1.42:5173',
     cleartext: true,
   },
   ```

3. `npm run cap:sync` and run from Android Studio / Xcode.

4. Add your LAN origin to API `CORS_ORIGINS`.

Remove `server.url` before store builds.

## What the native shell changes

- **iOS** `UIBackgroundModes: audio` + `AVAudioSession` playback category
- **Android** `WAKE_LOCK`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK`
- **Capacitor `App` plugin** — resume playback when app goes to background
- **Off-screen YouTube iframe** — 320×180 on native (tiny 1×1 iframes get paused on iOS)
- **Faster keep-alive retries** when backgrounded in the native app

## Limitations

- YouTube may still pause in edge cases (OS updates, low memory). This is much better than mobile Safari but not identical to Spotify.
- **iOS Simulator** often stops background audio — test on a real iPhone.
- YouTube ToS still applies; this does not download or re-stream video.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| API network error in app | Set `VITE_API_URL` to full HTTPS API URL before `npm run build` |
| CORS blocked | Add `capacitor://localhost` and `https://localhost` to API CORS |
| Android cleartext HTTP | `cap:patch-native` sets `usesCleartextTraffic` for LAN dev |
| No sound when locked | Confirm `npm run cap:patch-native` ran; rebuild in Xcode/Android Studio |
| White screen | Run `npm run cap:sync` after every web build |

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run build:capacitor` | Production web build → `dist/` |
| `npm run cap:sync` | Build + copy web assets to native projects |
| `npm run cap:patch-native` | Apply background-audio native patches |
| `npm run cap:android` | Open Android Studio |
| `npm run cap:ios` | Open Xcode |
