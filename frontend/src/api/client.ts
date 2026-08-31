import axios, { AxiosError } from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';
import type { AuthTokens } from '../types/auth';
import toast from 'react-hot-toast';
import { extractApiError, skipInterceptorToast } from './errors';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add the auth token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const tokensString = localStorage.getItem('auth_tokens');
    if (tokensString) {
      try {
        const tokens: AuthTokens = JSON.parse(tokensString);
        if (tokens.access_token) {
          config.headers.Authorization = `Bearer ${tokens.access_token}`;
        }
      } catch (e) {
        // ignore JSON parse error
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle 401 and refresh token
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;

      const tokensString = localStorage.getItem('auth_tokens');
      if (tokensString) {
        try {
          const tokens: AuthTokens = JSON.parse(tokensString);
          if (tokens.refresh_token) {
            // Attempt to refresh
            const response = await axios.post(`${BASE_URL}/auth/refresh`, {
              refresh_token: tokens.refresh_token,
            });

            if (response.data && response.data.success) {
              // Usually the new tokens are inside data.data or directly in data
              // Let's assume response.data.data has the tokens
              const newTokens: AuthTokens = response.data.data;
              localStorage.setItem('auth_tokens', JSON.stringify(newTokens));

              // Update authorization header
              originalRequest.headers.Authorization = `Bearer ${newTokens.access_token}`;
              return apiClient(originalRequest);
            }
          }
        } catch (refreshError) {
          localStorage.removeItem('auth_tokens');
          window.dispatchEvent(new Event('auth_unauthorized'));
          toast.error('Session expired. Please log in again.');
        }
      } else {
        toast.error('Unauthorized access. Please log in.');
      }
    } else if (error.response) {
      const parsed = extractApiError(error);
      if (error.response.status !== 401 && !skipInterceptorToast(parsed.code)) {
        toast.error(parsed.message);
      }
    } else {
      toast.error('Network error. Please try again.');
    }

    return Promise.reject(error);
  }
);
