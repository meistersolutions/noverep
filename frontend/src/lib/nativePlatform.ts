import { Capacitor } from '@capacitor/core';

export const isNativeApp = Capacitor.isNativePlatform();
export const nativePlatform = Capacitor.getPlatform();

export function isIOSNative(): boolean {
  return isNativeApp && nativePlatform === 'ios';
}

export function isAndroidNative(): boolean {
  return isNativeApp && nativePlatform === 'android';
}

/** Mobile browser (Chrome/Safari) — not the Capacitor shell. */
export function isMobileBrowser(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
}

/** YouTube iframe needs real dimensions off-screen on mobile WebViews and mobile browsers. */
export function needsOffscreenPlayer(): boolean {
  return isNativeApp || isMobileBrowser();
}
