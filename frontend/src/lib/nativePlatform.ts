import { Capacitor } from '@capacitor/core';

export const isNativeApp = Capacitor.isNativePlatform();
export const nativePlatform = Capacitor.getPlatform();

export function isIOSNative(): boolean {
  return isNativeApp && nativePlatform === 'ios';
}

export function isAndroidNative(): boolean {
  return isNativeApp && nativePlatform === 'android';
}
