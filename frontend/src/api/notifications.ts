import type {
  NotificationSettings,
  NotificationSettingsUpdate,
  PushSubscribeRequest,
} from '../types';
import { requestJson } from './core';

export async function fetchNotificationSettings(): Promise<NotificationSettings> {
  return requestJson<NotificationSettings>('/api/settings/notifications');
}

export async function updateNotificationSettings(
  update: NotificationSettingsUpdate
): Promise<Omit<NotificationSettings, 'vapid_public_key'>> {
  return requestJson('/api/settings/notifications', {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}

export async function sendEmailBriefingPreview(): Promise<{ sent: boolean }> {
  return requestJson('/api/settings/notifications/email/preview', {
    method: 'POST',
  });
}

export async function subscribePush(
  payload: PushSubscribeRequest
): Promise<{ subscribed: boolean }> {
  return requestJson('/api/notifications/subscribe', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function unsubscribePush(endpoint?: string): Promise<{ unsubscribed: boolean }> {
  return requestJson('/api/notifications/subscribe', {
    method: 'DELETE',
    body: endpoint ? JSON.stringify({ endpoint }) : undefined,
  });
}
