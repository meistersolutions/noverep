/**
 * Single source of truth for the app version shown in UI and baked into Android builds.
 *
 * When you ship a new mobile build:
 * 1. Bump APP_VERSION (e.g. 1.5.0 → 1.5.1) and/or APP_BUILD (+1)
 * 2. Run: npm run cap:sync
 * 3. Install on phone and confirm Profile shows the new version near the top
 */
export const APP_VERSION = '1.6.4';
export const APP_BUILD = 15;

export function formatAppVersion(): string {
  return `v${APP_VERSION} (${APP_BUILD})`;
}
