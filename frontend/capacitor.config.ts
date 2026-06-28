import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Native shell for background audio on iOS/Android.
 *
 * Dev live-reload (optional): set server.url to your LAN Vite URL, e.g.
 *   server: { url: 'http://192.168.1.42:5173', cleartext: true }
 */
const config: CapacitorConfig = {
  appId: 'com.noverep.app',
  appName: 'NoRepeat',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    iosScheme: 'https',
  },
  ios: {
    contentInset: 'automatic',
    allowsLinkPreview: false,
    backgroundColor: '#0f0f14',
    infoPlist: {
      UIBackgroundModes: ['audio'],
    },
  },
  android: {
    backgroundColor: '#0f0f14',
    allowMixedContent: true,
  },
  plugins: {
    SplashScreen: {
      launchAutoHide: true,
      backgroundColor: '#0f0f14',
      showSpinner: false,
    },
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#0f0f14',
    },
  },
};

export default config;
