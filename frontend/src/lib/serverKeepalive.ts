import { Capacitor } from '@capacitor/core';
import { App } from '@capacitor/app';

const INTERVAL_MS = 60_000;

function apiHealthUrl(): string {
  const base = import.meta.env.VITE_API_URL || '/api/v1';
  if (base.startsWith('http')) {
    try {
      return `${new URL(base).origin}/health`;
    } catch {
      /* fall through */
    }
  }
  return 'https://noverep-api.onrender.com/health';
}

function songsLibraryHealthUrl(): string {
  return (
    import.meta.env.VITE_SONGS_LIBRARY_URL ||
    'https://songs-library.onrender.com/health'
  );
}

async function ping(url: string): Promise<void> {
  try {
    await fetch(url, { method: 'GET', cache: 'no-store' });
  } catch {
    /* best-effort */
  }
}

async function pingBoth(): Promise<void> {
  await Promise.all([ping(apiHealthUrl()), ping(songsLibraryHealthUrl())]);
}

let timer: ReturnType<typeof setInterval> | null = null;

function startForegroundKeepalive(): void {
  if (timer) return;
  void pingBoth();
  timer = setInterval(() => void pingBoth(), INTERVAL_MS);
}

function stopForegroundKeepalive(): void {
  if (!timer) return;
  clearInterval(timer);
  timer = null;
}

/** Ping Render health endpoints while the native app is in the foreground. */
export async function initServerKeepalive(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;

  const { isActive } = await App.getState();
  if (isActive) startForegroundKeepalive();

  await App.addListener('appStateChange', ({ isActive: active }) => {
    if (active) startForegroundKeepalive();
    else stopForegroundKeepalive();
  });
}
