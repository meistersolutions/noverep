import { useEffect, useState } from 'react';
import { hydrateAuthStorage } from '@/lib/authStorage';
import { scheduleAccessTokenRefresh } from '@/lib/authSession';
import { isNativeApp } from '@/lib/nativePlatform';
import { usePlayerStore } from '@/stores/playerStore';

export function AuthBootstrap({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(!isNativeApp);
  const setAuth = usePlayerStore((s) => s.setAuth);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const snapshot = await hydrateAuthStorage();
      if (cancelled) return;

      if (snapshot?.accessToken) {
        setAuth(
          snapshot.accessToken,
          snapshot.refreshToken || '',
          snapshot.username,
          snapshot.isGuest,
        );
        scheduleAccessTokenRefresh(snapshot.accessToken);
      }

      setReady(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [setAuth]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="glass p-8 flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <p className="text-white/60">Loading NoRepeat...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
