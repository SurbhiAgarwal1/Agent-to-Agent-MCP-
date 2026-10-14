import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest, SESSION_STORAGE_KEY, SessionExpiredError } from '../api/client.js';

function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('API authentication boundary', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('preserves the backend login error for an unauthenticated 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      jsonResponse({ detail: 'Invalid email or password.' }, 401)
    ));
    const expiredEvent = vi.fn();
    window.addEventListener('bdm:auth:expired', expiredEvent);

    await expect(apiRequest('/api/v1/auth/login', { method: 'POST' }))
      .rejects.toMatchObject({ status: 401, message: 'Invalid email or password.' });

    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    expect(expiredEvent).not.toHaveBeenCalled();
    window.removeEventListener('bdm:auth:expired', expiredEvent);
  });

  it('treats a 401 from an authenticated request as session expiration', async () => {
    sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ token: 'test-token' }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      jsonResponse({ detail: 'Not authenticated' }, 401)
    ));
    const expiredEvent = vi.fn();
    window.addEventListener('bdm:auth:expired', expiredEvent);

    await expect(apiRequest('/api/v1/auth/me'))
      .rejects.toBeInstanceOf(SessionExpiredError);

    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    expect(expiredEvent).toHaveBeenCalledTimes(1);
    window.removeEventListener('bdm:auth:expired', expiredEvent);
  });
});
