/**
 * Build debug APK and install on a connected Android device (USB or wireless adb).
 *
 * Usage:
 *   node scripts/deploy-android.mjs
 *   node scripts/deploy-android.mjs --connect 192.168.1.42:5555
 *
 * Wireless pairing (Android 11+):
 *   1. Phone: Developer options → Wireless debugging → Pair device with pairing code
 *   2. adb pair <ip>:<pairing-port> <code>
 *   3. adb connect <ip>:<connect-port>
 *   4. node scripts/deploy-android.mjs
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const gradlew = isWin
  ? path.join(root, 'android', 'gradlew.bat')
  : path.join(root, 'android', 'gradlew');
const apkPath = path.join(
  root,
  'android',
  'app',
  'build',
  'outputs',
  'apk',
  'debug',
  'app-debug.apk',
);

function run(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    cwd: opts.cwd ?? root,
    stdio: 'inherit',
    shell: isWin && cmd === 'npm',
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function adb(args) {
  const result = spawnSync('adb', args, { encoding: 'utf8' });
  return result;
}

const connectArg = process.argv.find((a) => a.startsWith('--connect='));
const connectHost = connectArg?.slice('--connect='.length);

console.log('→ Syncing Capacitor web bundle…');
run('npm', ['run', 'cap:sync']);

if (connectHost) {
  console.log(`→ adb connect ${connectHost}`);
  const connect = adb(['connect', connectHost]);
  process.stdout.write(connect.stdout ?? '');
  process.stderr.write(connect.stderr ?? '');
}

const devices = adb(['devices']);
const lines = (devices.stdout ?? '')
  .split('\n')
  .map((l) => l.trim())
  .filter((l) => l && !l.startsWith('List of devices'));
const online = lines.filter((l) => l.endsWith('device'));

if (online.length === 0) {
  console.error('\nNo Android device found via adb.');
  console.error('Wireless debugging steps:');
  console.error('  adb pair <ip>:<pairing-port> <6-digit-code>');
  console.error('  adb connect <ip>:<connect-port>');
  console.error('  node scripts/deploy-android.mjs');
  process.exit(1);
}

console.log(`→ Device(s): ${online.join(', ')}`);

console.log('→ Building debug APK…');
run(gradlew, ['assembleDebug'], { cwd: path.join(root, 'android') });

if (!fs.existsSync(apkPath)) {
  console.error('APK not found at', apkPath);
  process.exit(1);
}

console.log('→ Installing', apkPath);
const install = adb(['install', '-r', apkPath]);
process.stdout.write(install.stdout ?? '');
process.stderr.write(install.stderr ?? '');
if (install.status !== 0) {
  process.exit(install.status ?? 1);
}

console.log('✓ Installed NoRepeat (com.noverep.app)');
