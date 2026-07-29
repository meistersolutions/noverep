import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, formatDuration } from './api';

describe('formatDuration', () => {
  it('formats seconds correctly', () => {
    expect(formatDuration(125)).toBe('2:05');
    expect(formatDuration(null)).toBe('--:--');
  });
});

describe('api auth requests', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('login 401 shows invalid credentials, not session expired', async () => {
    localStorage.setItem('noverep_token', 'stale-token');
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Invalid credentials' }),
    });

    await expect(api.login('user', 'wrong')).rejects.toMatchObject({
      message: 'Invalid email or password',
      status: 401,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it('authenticated 401 after failed refresh throws session expired', async () => {
    localStorage.setItem('noverep_token', 'stale-token');
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Invalid token' }),
    });

    await expect(api.getMe()).rejects.toMatchObject({
      message: 'Session expired — please sign in again',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain('/me');
    const firstHeaders = fetchMock.mock.calls[0][1].headers as Record<string, string>;
    expect(firstHeaders.Authorization).toBe('Bearer stale-token');
  });

  it('guest login does not attach Authorization header', async () => {
    localStorage.setItem('noverep_token', 'stale-token');
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          access_token: 'new-access',
          refresh_token: 'new-refresh',
          username: 'guest_abc',
          is_guest: true,
        }),
    });

    await api.guestLogin();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toContain('/auth/guest');
  });
});
