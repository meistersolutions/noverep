import { describe, it, expect } from 'vitest';
import { parseJwtExpiryMs } from './authSession';

function makeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = btoa(JSON.stringify(payload));
  return `${header}.${body}.signature`;
}

describe('parseJwtExpiryMs', () => {
  it('returns expiry in milliseconds', () => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const token = makeJwt({ sub: 'user', exp });
    expect(parseJwtExpiryMs(token)).toBe(exp * 1000);
  });

  it('returns null for invalid tokens', () => {
    expect(parseJwtExpiryMs('not-a-jwt')).toBeNull();
  });
});
