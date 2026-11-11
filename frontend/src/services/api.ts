import axios from 'axios';
import { getToken, ensureSilentAuthSession, clearAuthSession } from '../api';

const HOST_BACKEND_URL = (import.meta as any).env?.VITE_HOST_API_URL || 'http://127.0.0.1:8000';

export const api = axios.create({
  baseURL: HOST_BACKEND_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(async (config) => {
  let token =
    getToken() ||
    localStorage.getItem('RAJON_AUTH_TOKEN') ||
    sessionStorage.getItem('RAJON_AUTH_TOKEN') ||
    localStorage.getItem('token') ||
    sessionStorage.getItem('token');

  if (!token && config.url && !config.url.includes('/auth/login')) {
    token = await ensureSilentAuthSession();
  }

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  if (config.url && !config.url.startsWith('/api') && !config.url.startsWith('http')) {
    config.url = `/api${config.url.startsWith('/') ? '' : '/'}${config.url}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalConfig = error.config;
    if (
      error.response &&
      error.response.status === 401 &&
      originalConfig &&
      !originalConfig._retry &&
      !String(originalConfig.url || '').includes('/auth/login')
    ) {
      originalConfig._retry = true;
      clearAuthSession();
      const newToken = await ensureSilentAuthSession();
      if (newToken) {
        originalConfig.headers = originalConfig.headers || {};
        originalConfig.headers.Authorization = `Bearer ${newToken}`;
        return api(originalConfig);
      }
    }
    return Promise.reject(error);
  }
);

export default api;
