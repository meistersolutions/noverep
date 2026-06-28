import { Capacitor } from '@capacitor/core';
import { StatusBar, Style } from '@capacitor/status-bar';
import { SplashScreen } from '@capacitor/splash-screen';

/** One-time native shell setup (status bar, splash, body class). */
export async function initCapacitorShell(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;

  document.documentElement.classList.add('capacitor-native');
  document.body.classList.add('capacitor-native');

  try {
    await SplashScreen.hide();
  } catch {
    /* optional */
  }

  if (Capacitor.getPlatform() === 'android') {
    try {
      await StatusBar.setStyle({ style: Style.Dark });
      await StatusBar.setBackgroundColor({ color: '#0f0f14' });
    } catch {
      /* optional */
    }
  }
}
