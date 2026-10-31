const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export function getToken(): string | null {
  return sessionStorage.getItem('BAOBAB_AUTH_TOKEN');
}

export function setAuthSession(token: string, username: string, hsmMode: string) {
  sessionStorage.setItem('BAOBAB_AUTH_TOKEN', token);
  sessionStorage.setItem('BAOBAB_USER', username);
  sessionStorage.setItem('BAOBAB_HSM_MODE', hsmMode);
}

export function clearAuthSession() {
  sessionStorage.removeItem('BAOBAB_AUTH_TOKEN');
  sessionStorage.removeItem('BAOBAB_USER');
  sessionStorage.removeItem('BAOBAB_HSM_MODE');
}

export async function apiFetch<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
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

  if (response.status === 401) {
    clearAuthSession();
    window.location.hash = '#/login';
    throw new Error('Session expired or unauthorized');
  }

  if (!response.ok) {
    let errText = `HTTP ${response.status}`;
    try {
      const errData = await response.json();
      errText = errData.detail || JSON.stringify(errData);
    } catch {
      // ignore
    }
    throw new Error(errText);
  }

  return response.json();
}
