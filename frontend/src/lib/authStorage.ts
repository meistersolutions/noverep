import { Preferences } from '@capacitor/preferences';
import { isNativeApp } from '@/lib/nativePlatform';

export const AUTH_KEYS = {
  accessToken: 'noverep_token',
  refreshToken: 'noverep_refresh_token',
  username: 'noverep_username',
  guest: 'noverep_guest',
} as const;

export interface AuthSnapshot {
  accessToken: string;
  refreshToken: string | null;
  username: string;
  isGuest: boolean;
}

let cachedAccessToken: string | null = null;
let cachedRefreshToken: string | null = null;
let cachedUsername: string | null = null;
let cachedIsGuest = false;
let hydrated = false;

function readLocalSnapshot(): AuthSnapshot | null {
  const accessToken = localStorage.getItem(AUTH_KEYS.accessToken);
  if (!accessToken) return null;
  return {
    accessToken,
    refreshToken: localStorage.getItem(AUTH_KEYS.refreshToken),
    username: localStorage.getItem(AUTH_KEYS.username) || '',
    isGuest: localStorage.getItem(AUTH_KEYS.guest) === 'true',
  };
}

function applySnapshot(snapshot: AuthSnapshot | null): AuthSnapshot | null {
  if (!snapshot?.accessToken) {
    cachedAccessToken = null;
    cachedRefreshToken = null;
    cachedUsername = null;
    cachedIsGuest = false;
    return null;
  }
  cachedAccessToken = snapshot.accessToken;
  cachedRefreshToken = snapshot.refreshToken;
  cachedUsername = snapshot.username;
  cachedIsGuest = snapshot.isGuest;
  return snapshot;
}

function mirrorToLocalStorage(snapshot: AuthSnapshot): void {
  localStorage.setItem(AUTH_KEYS.accessToken, snapshot.accessToken);
  if (snapshot.refreshToken) {
    localStorage.setItem(AUTH_KEYS.refreshToken, snapshot.refreshToken);
  } else {
    localStorage.removeItem(AUTH_KEYS.refreshToken);
  }
  localStorage.setItem(AUTH_KEYS.username, snapshot.username);
  localStorage.setItem(AUTH_KEYS.guest, String(snapshot.isGuest));
}

async function readNativeSnapshot(): Promise<AuthSnapshot | null> {
  const [access, refresh, username, guest] = await Promise.all([
    Preferences.get({ key: AUTH_KEYS.accessToken }),
    Preferences.get({ key: AUTH_KEYS.refreshToken }),
    Preferences.get({ key: AUTH_KEYS.username }),
    Preferences.get({ key: AUTH_KEYS.guest }),
  ]);
  if (!access.value) return null;
  return {
    accessToken: access.value,
    refreshToken: refresh.value,
    username: username.value || '',
    isGuest: guest.value === 'true',
  };
}

async function writeNativeSnapshot(snapshot: AuthSnapshot): Promise<void> {
  await Promise.all([
    Preferences.set({ key: AUTH_KEYS.accessToken, value: snapshot.accessToken }),
    snapshot.refreshToken
      ? Preferences.set({ key: AUTH_KEYS.refreshToken, value: snapshot.refreshToken })
      : Preferences.remove({ key: AUTH_KEYS.refreshToken }),
    Preferences.set({ key: AUTH_KEYS.username, value: snapshot.username }),
    Preferences.set({ key: AUTH_KEYS.guest, value: String(snapshot.isGuest) }),
  ]);
}

async function clearNativeSnapshot(): Promise<void> {
  await Promise.all(
    Object.values(AUTH_KEYS).map((key) => Preferences.remove({ key })),
  );
}

export function getAccessTokenSync(): string | null {
  if (cachedAccessToken) return cachedAccessToken;
  return localStorage.getItem(AUTH_KEYS.accessToken);
}

export function getRefreshTokenSync(): string | null {
  if (cachedRefreshToken) return cachedRefreshToken;
  return localStorage.getItem(AUTH_KEYS.refreshToken);
}

export function hasStoredAuthSync(): boolean {
  return !!getAccessTokenSync();
}

/** Re-read persisted auth (e.g. after cache clear or before login). */
export async function rehydrateAuthStorage(): Promise<AuthSnapshot | null> {
  if (isNativeApp) {
    const nativeSnapshot = await readNativeSnapshot();
    if (nativeSnapshot) {
      mirrorToLocalStorage(nativeSnapshot);
      hydrated = true;
      return applySnapshot(nativeSnapshot);
    }
  }
  hydrated = true;
  return applySnapshot(readLocalSnapshot());
}

export async function hydrateAuthStorage(): Promise<AuthSnapshot | null> {
  if (hydrated) {
    return rehydrateAuthStorage();
  }

  if (isNativeApp) {
    const nativeSnapshot = await readNativeSnapshot();
    if (nativeSnapshot) {
      mirrorToLocalStorage(nativeSnapshot);
      hydrated = true;
      return applySnapshot(nativeSnapshot);
    }

    const legacySnapshot = readLocalSnapshot();
    if (legacySnapshot) {
      await writeNativeSnapshot({
        ...legacySnapshot,
        refreshToken: legacySnapshot.refreshToken || '',
      });
      hydrated = true;
      return applySnapshot(legacySnapshot);
    }

    hydrated = true;
    return applySnapshot(null);
  }

  hydrated = true;
  return applySnapshot(readLocalSnapshot());
}

export async function setStoredAuth(snapshot: AuthSnapshot): Promise<void> {
  mirrorToLocalStorage(snapshot);
  applySnapshot(snapshot);
  if (isNativeApp) {
    await writeNativeSnapshot(snapshot);
  }
}

export async function clearStoredAuth(): Promise<void> {
  for (const key of Object.values(AUTH_KEYS)) {
    localStorage.removeItem(key);
  }
  applySnapshot(null);
  if (isNativeApp) {
    await clearNativeSnapshot();
  }
}
