# Access NoRepeat from Your Phone (LAN)

Use this when your PC runs the app and your phone is on the **same Wi‑Fi network**.

## 1. Find your PC's local IP

**Windows (PowerShell):**
```powershell
ipconfig
```
Look for `IPv4 Address` under your Wi‑Fi adapter, e.g. `192.168.1.42`.

**WSL / Linux:**
```bash
hostname -I
```

## 2. Configure `.env`

```env
# Allow your phone's browser origin
CORS_ORIGINS=http://localhost:5173,http://192.168.1.42:5173

# Relative API path (Docker nginx proxies /api → backend)
VITE_API_URL=/api/v1
```

Replace `192.168.1.42` with your actual IP.

## 3. Start the server

```bash
cd /mnt/c/Users/smile/Projects/noverep   # WSL
docker compose up --build -d
```

Docker already binds ports on `0.0.0.0`, so they're reachable on your LAN.

## 4. Open on your phone

In the mobile browser:

```
http://192.168.1.42:5173
```

Use your PC's IP, not `localhost`.

## 5. Windows Firewall

If the phone can't connect, allow inbound TCP on ports **5173** and **8000**:

1. Windows Security → Firewall → Advanced settings
2. Inbound Rules → New Rule → Port → TCP → 5173, 8000 → Allow

Or temporarily allow Docker Desktop through the firewall.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Page loads but API fails | Rebuild frontend after setting `VITE_API_URL=/api/v1` |
| CORS error on phone | Add `http://YOUR_IP:5173` to `CORS_ORIGINS`, restart backend |
| Can't reach server | Same Wi‑Fi? VPN off? Firewall open? |
| YouTube won't play on phone | Some mobile browsers block autoplay; tap Play once |

## Without Docker (dev mode)

Run backend on `0.0.0.0:8000` and frontend with:

```bash
npm run dev -- --host 0.0.0.0
```

Set `VITE_API_URL=http://192.168.1.42:8000/api/v1` in `frontend/.env.local` and rebuild/restart.

## Native app (better background audio)

For playback with the screen off, use the **Capacitor** Android/iOS app instead of the mobile browser. See **[docs/CAPACITOR.md](CAPACITOR.md)**.
