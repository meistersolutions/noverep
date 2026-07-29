import {
  AUTH_KEYS,
  clearStoredAuth,
  getRefreshTokenSync,
  setStoredAuth,
} from '@/lib/authStorage';

const API_URL = import.meta.env.VITE_API_URL || '/api/v1';
const REFRESH_BUFFER_MS = 5 * 60 * 1000;

export interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  username: string;
  is_guest: boolean;
}

let refreshTimer: ReturnType<typeof setTimeout> | null = null;
let refreshInFlight: Promise<boolean> | null = null;

export function parseJwtExpiryMs(token: string): number | null {
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    return typeof decoded.exp === 'number' ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function clearRefreshTimer(): void {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

export function scheduleAccessTokenRefresh(accessToken: string): void {
  clearRefreshTimer();
  const expiresAt = parseJwtExpiryMs(accessToken);
  if (!expiresAt) return;
  const delay = Math.max(0, expiresAt - Date.now() - REFRESH_BUFFER_MS);
  refreshTimer = setTimeout(() => {
    void tryRefreshAccessToken();
  }, delay);
}

async function refreshTokensFromServer(refreshToken: string): Promise<TokenPairResponse | null> {
  const res = await fetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) return null;
  return (await res.json()) as TokenPairResponse;
}

export async function tryRefreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refreshToken = getRefreshTokenSync();
    if (!refreshToken) return false;

    const data = await refreshTokensFromServer(refreshToken);
    if (!data?.access_token || !data.refresh_token) return false;

    await setStoredAuth({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      username: data.username,
      isGuest: data.is_guest,
    });

    const { usePlayerStore } = await import('@/stores/playerStore');
    usePlayerStore
      .getState()
      .setAuth(data.access_token, data.refresh_token, data.username, data.is_guest);

    scheduleAccessTokenRefresh(data.access_token);
    return true;
  })();

  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

export async function revokeRefreshTokenOnLogout(): Promise<void> {
  const refreshToken = getRefreshTokenSync();
  if (!refreshToken) return;
  try {
    await fetch(`${API_URL}/auth/logout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    // Best-effort server revocation; local clear still proceeds.
  }
}

export async function handleAuthExpired(): Promise<void> {
  clearRefreshTimer();
  await clearStoredAuth();
  const { usePlayerStore } = await import('@/stores/playerStore');
  usePlayerStore.getState().logout({ skipServerRevoke: true });
}

export function getAuthStorageKeys() {
  return AUTH_KEYS;
}
