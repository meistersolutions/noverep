/**
 * Syncs APP_VERSION / APP_BUILD from src/lib/appVersion.ts into:
 * - package.json
 * - android/app/build.gradle (versionName / versionCode)
 *
 * Run automatically as part of `npm run cap:sync`.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const versionFile = path.join(root, 'src', 'lib', 'appVersion.ts');
const packageJsonPath = path.join(root, 'package.json');
const gradlePath = path.join(root, 'android', 'app', 'build.gradle');

const source = fs.readFileSync(versionFile, 'utf8');
const versionMatch = source.match(/export const APP_VERSION = '([^']+)'/);
const buildMatch = source.match(/export const APP_BUILD = (\d+)/);

if (!versionMatch || !buildMatch) {
  console.error('Could not parse APP_VERSION / APP_BUILD from appVersion.ts');
  process.exit(1);
}

const version = versionMatch[1];
const build = buildMatch[1];

const pkg = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
pkg.version = version;
fs.writeFileSync(packageJsonPath, `${JSON.stringify(pkg, null, 2)}\n`);
console.log(`package.json → ${version}`);

if (fs.existsSync(gradlePath)) {
  let gradle = fs.readFileSync(gradlePath, 'utf8');
  gradle = gradle.replace(/versionCode\s+\d+/, `versionCode ${build}`);
  gradle = gradle.replace(/versionName\s+"[^"]+"/, `versionName "${version}"`);
  fs.writeFileSync(gradlePath, gradle);
  console.log(`android/app/build.gradle → versionName ${version}, versionCode ${build}`);
} else {
  console.log('skip android build.gradle (not present)');
}

console.log(`App version synced: v${version} (${build})`);
