import type { AdminAiQuality, AdminAnalytics, User } from '../types';
import { requestJson } from './core';

export async function fetchAdminAnalytics(days = 30): Promise<AdminAnalytics> {
  return requestJson<AdminAnalytics>(`/api/admin/analytics?days=${days}`);
}

export async function fetchAdminAiQuality(days = 30): Promise<AdminAiQuality> {
  return requestJson<AdminAiQuality>(`/api/admin/ai/quality?days=${days}`);
}

export interface GeneratedUser {
  id: number | string | null;
  username: string;
  email?: string | null;
  is_admin?: boolean;
  password: string;
  provider: 'keycloak' | 'password';
  temporary?: boolean;
  created_at?: string | null;
}

export async function fetchAdminUsers(): Promise<User[]> {
  const data = await requestJson<{ items: User[] }>('/api/admin/users');
  return data.items;
}

export async function generateAdminUser(
  username: string,
  options?: { email?: string | null; is_admin?: boolean }
): Promise<GeneratedUser> {
  return requestJson<GeneratedUser>('/api/admin/users/generate', {
    method: 'POST',
    body: JSON.stringify({
      username,
      email: options?.email ?? null,
      is_admin: options?.is_admin ?? false,
    }),
  });
}

export async function deleteAdminUser(userId: number): Promise<void> {
  await requestJson<{ status: string }>(`/api/admin/users/${userId}`, {
    method: 'DELETE',
  });
}
