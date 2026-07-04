import type {
  ReceivedShare,
  SentShare,
  ShareAnnotation,
  ShareDetail,
  ShareMessage,
  ShareableUser,
} from '../types';
import { requestJson } from './core';

export async function fetchShareableUsers(): Promise<ShareableUser[]> {
  const data = await requestJson<{ items: ShareableUser[] }>('/api/users');
  return data.items;
}

export async function shareArticle(
  articleId: number,
  toUserId: number,
  note?: string
): Promise<ReceivedShare> {
  return requestJson<ReceivedShare>(`/api/articles/${articleId}/share`, {
    method: 'POST',
    body: JSON.stringify({ to_user_id: toUserId, note: note ?? null }),
  });
}

export interface CreateShareAnnotationPayload {
  highlighted_text: string;
  offset_chars?: number;
  note?: string | null;
}

export async function createShareAnnotation(
  shareId: number,
  payload: CreateShareAnnotationPayload
): Promise<ShareAnnotation> {
  return requestJson<ShareAnnotation>(`/api/shares/${shareId}/annotations`, {
    method: 'POST',
    body: JSON.stringify({
      highlighted_text: payload.highlighted_text,
      offset_chars: payload.offset_chars ?? 0,
      note: payload.note ?? null,
    }),
  });
}

export async function fetchReceivedShares(): Promise<{
  items: ReceivedShare[];
  unread: number;
}> {
  return requestJson('/api/shares');
}

export async function fetchSharesUnreadCount(): Promise<number> {
  const data = await requestJson<{ unread: number }>('/api/shares/unread_count');
  return data.unread;
}

export async function fetchSentShares(): Promise<{ items: SentShare[] }> {
  return requestJson('/api/shares/sent');
}

export async function revokeShare(shareId: number): Promise<void> {
  await requestJson(`/api/shares/${shareId}/revoke`, { method: 'POST' });
}

export async function markShareRead(shareId: number): Promise<void> {
  await requestJson(`/api/shares/${shareId}/read`, { method: 'POST' });
}

export async function fetchShareDetail(shareId: number): Promise<ShareDetail> {
  return requestJson<ShareDetail>(`/api/shares/${shareId}`);
}

export async function fetchShareMessages(shareId: number): Promise<{ items: ShareMessage[] }> {
  return requestJson<{ items: ShareMessage[] }>(`/api/shares/${shareId}/messages`);
}

export async function postShareMessage(shareId: number, message: string): Promise<ShareMessage> {
  return requestJson<ShareMessage>(`/api/shares/${shareId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}
