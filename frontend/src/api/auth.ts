import type { User } from '../types';
import { requestJson } from './core';

export interface AuthConfig {
  provider: 'password' | 'keycloak';
  keycloak_enabled: boolean;
  login_url: string | null;
  logout_url: string;
  registration_url?: string | null;
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  return requestJson<AuthConfig>('/api/auth/config');
}

export async function fetchMe(): Promise<User> {
  return requestJson<User>('/api/auth/me');
}

export async function loginUser(username: string, password: string): Promise<User> {
  return requestJson<User>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export async function requestOtp(email: string): Promise<void> {
  await requestJson<{ status: string }>('/api/auth/otp/request', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export async function loginWithOtp(email: string, otp: string): Promise<User> {
  return requestJson<User>('/api/auth/otp/login', {
    method: 'POST',
    body: JSON.stringify({ email, otp }),
  });
}

export async function logoutUser(): Promise<void> {
  const config = await fetchAuthConfig().catch(() => null);
  if (config?.provider === 'keycloak' && config.logout_url) {
    window.location.assign(config.logout_url);
    return;
  }
  await fetch('/api/auth/logout', { credentials: 'same-origin' });
}
