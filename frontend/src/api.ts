const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

const DEFAULT_OPERATOR_USER = 'admin';
const DEFAULT_OPERATOR_PASS = 'AdminPassword123!';

let autoAuthPromise: Promise<string | null> | null = null;

export function getToken(): string | null {
  const token =
    localStorage.getItem('RAJON_AUTH_TOKEN') ||
    sessionStorage.getItem('RAJON_AUTH_TOKEN') ||
    localStorage.getItem('token') ||
    sessionStorage.getItem('token');

  if (token) {
    // Keep both storages synchronized so refreshes, new tabs, and pop-outs never lose session
    if (!sessionStorage.getItem('RAJON_AUTH_TOKEN')) {
      sessionStorage.setItem('RAJON_AUTH_TOKEN', token);
    }
    if (!localStorage.getItem('RAJON_AUTH_TOKEN')) {
      localStorage.setItem('RAJON_AUTH_TOKEN', token);
    }
  }
  return token;
}

export function setAuthSession(token: string, username: string, hsmMode: string) {
  localStorage.setItem('RAJON_AUTH_TOKEN', token);
  localStorage.setItem('RAJON_USER', username);
  localStorage.setItem('RAJON_HSM_MODE', hsmMode);
  sessionStorage.setItem('RAJON_AUTH_TOKEN', token);
  sessionStorage.setItem('RAJON_USER', username);
  sessionStorage.setItem('RAJON_HSM_MODE', hsmMode);
}

export function clearAuthSession() {
  localStorage.removeItem('RAJON_AUTH_TOKEN');
  localStorage.removeItem('RAJON_USER');
  localStorage.removeItem('RAJON_HSM_MODE');
  sessionStorage.removeItem('RAJON_AUTH_TOKEN');
  sessionStorage.removeItem('RAJON_USER');
  sessionStorage.removeItem('RAJON_HSM_MODE');
}

export async function ensureSilentAuthSession(): Promise<string | null> {
  const existing = getToken();
  if (existing) return existing;

  if (autoAuthPromise) return autoAuthPromise;

  autoAuthPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: DEFAULT_OPERATOR_USER,
          password: DEFAULT_OPERATOR_PASS,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data?.access_token) {
          setAuthSession(
            data.access_token,
            data.username || DEFAULT_OPERATOR_USER,
            data.hsm_mode || 'SOFT_HSM_REMOTE'
          );
          return data.access_token as string;
        }
      }
    } catch {
      // Ignore network errors during silent auth bootstrap
    } finally {
      autoAuthPromise = null;
    }
    return null;
  })();

  return autoAuthPromise;
}

export async function apiFetch<T = any>(
  endpoint: string,
  options: RequestInit = {},
  _retried = false
): Promise<T> {
  let token = getToken();
  if (!token && endpoint !== '/auth/login') {
    token = await ensureSilentAuthSession();
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401 && endpoint !== '/auth/login' && !_retried) {
    clearAuthSession();
    const freshToken = await ensureSilentAuthSession();
    if (freshToken) {
      return apiFetch<T>(endpoint, options, true);
    }
  }

  if (response.status === 401) {
    clearAuthSession();
    window.location.hash = '#/login';
    throw new Error('Session expired or unauthorized');
  }

  if (!response.ok) {
    let errText = `HTTP ${response.status}`;
    try {
      const errData = await response.json();
      const d = errData.detail;
      if (Array.isArray(d)) {
        errText = d
          .map((x: any) => `${(x.loc || []).filter((p: any) => p !== 'body').join('.')}: ${x.msg}`)
          .join('; ');
      } else {
        errText = typeof d === 'string' ? d : d ? JSON.stringify(d) : JSON.stringify(errData);
      }
    } catch {
      // ignore
    }
    throw new Error(errText);
  }

  return response.json();
}
