/**
 * Patches generated Capacitor native projects for background audio playback.
 * Run after: npx cap add android/ios  &&  npm run cap:patch-native
 *
 * Safe to re-run: skips permissions / cleartext already present.
 * Does not remove network_security_config or other custom app settings.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(root, '..');

const ANDROID_MANIFEST = path.join(frontend, 'android', 'app', 'src', 'main', 'AndroidManifest.xml');
const IOS_APP_DELEGATE = path.join(frontend, 'ios', 'App', 'App', 'AppDelegate.swift');

const ANDROID_PERMISSIONS = [
  'android.permission.INTERNET',
  'android.permission.ACCESS_NETWORK_STATE',
  'android.permission.WAKE_LOCK',
  'android.permission.FOREGROUND_SERVICE',
  'android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK',
];

function patchAndroidManifest() {
  if (!fs.existsSync(ANDROID_MANIFEST)) {
    console.log('skip android manifest (run: npx cap add android)');
    return;
  }

  let xml = fs.readFileSync(ANDROID_MANIFEST, 'utf8');
  let changed = false;

  for (const perm of ANDROID_PERMISSIONS) {
    if (!xml.includes(perm)) {
      xml = xml.replace(
        /(<manifest[^>]*>)/,
        `$1\n    <uses-permission android:name="${perm}" />`,
      );
      changed = true;
      console.log(`added permission ${perm}`);
    }
  }

  if (!xml.includes('android:usesCleartextTraffic')) {
    xml = xml.replace(
      /<application([^>]*)>/,
      '<application$1 android:usesCleartextTraffic="true">',
    );
    changed = true;
    console.log('enabled cleartext traffic for LAN dev API');
  }

  if (changed) {
    fs.writeFileSync(ANDROID_MANIFEST, xml);
    console.log('patched AndroidManifest.xml');
  } else {
    console.log('AndroidManifest.xml already patched');
  }
}

function patchIOSAppDelegate() {
  if (!fs.existsSync(IOS_APP_DELEGATE)) {
    console.log('skip iOS AppDelegate (run: npx cap add ios on macOS)');
    return;
  }

  let swift = fs.readFileSync(IOS_APP_DELEGATE, 'utf8');
  if (swift.includes('AVAudioSession')) {
    console.log('AppDelegate.swift already patched');
    return;
  }

  if (!swift.includes('import AVFoundation')) {
    swift = swift.replace(
      /import UIKit/,
      'import UIKit\nimport AVFoundation',
    );
  }

  const hook = `
        // NoRepeat: keep audio alive when app is backgrounded
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [.mixWithOthers])
        try? AVAudioSession.sharedInstance().setActive(true)
`;

  if (swift.includes('didFinishLaunchingWithOptions')) {
    swift = swift.replace(
      /(func application\([^)]*didFinishLaunchingWithOptions[^)]*\)[^{]*\{)/,
      `$1${hook}`,
    );
  } else {
    console.warn('Could not find didFinishLaunchingWithOptions in AppDelegate.swift — patch manually');
    return;
  }

  fs.writeFileSync(IOS_APP_DELEGATE, swift);
  console.log('patched AppDelegate.swift for background audio');
}

patchAndroidManifest();
patchIOSAppDelegate();
