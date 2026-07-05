import { requestJson } from './core';

export type AiFeedbackSubjectType = 'briefing' | 'recommendation';
export type AiFeedbackVerdict = -1 | 1;

export interface AiFeedback {
  id: number;
  user_id: number;
  subject_type: AiFeedbackSubjectType;
  subject_id: number;
  article_id: number | null;
  verdict: AiFeedbackVerdict;
  comment: string | null;
  created_at: string;
}

export async function postAiFeedback(
  subjectType: AiFeedbackSubjectType,
  subjectId: number,
  verdict: AiFeedbackVerdict,
  options?: { articleId?: number; comment?: string }
): Promise<AiFeedback> {
  return requestJson<AiFeedback>('/api/ai-feedback', {
    method: 'POST',
    body: JSON.stringify({
      subject_type: subjectType,
      subject_id: subjectId,
      article_id: options?.articleId ?? null,
      verdict,
      comment: options?.comment ?? null,
    }),
  });
}

export async function deleteAiFeedback(
  subjectType: AiFeedbackSubjectType,
  subjectId: number,
  options?: { articleId?: number }
): Promise<{ deleted: boolean }> {
  const params = new URLSearchParams({
    subject_type: subjectType,
    subject_id: String(subjectId),
  });
  if (options?.articleId != null) {
    params.set('article_id', String(options.articleId));
  }
  return requestJson<{ deleted: boolean }>(`/api/ai-feedback?${params}`, {
    method: 'DELETE',
  });
}

export async function fetchAiFeedback(
  subjectType: AiFeedbackSubjectType,
  subjectIds: number[]
): Promise<Record<string, AiFeedbackVerdict>> {
  if (subjectIds.length === 0) return {};
  const params = new URLSearchParams({
    subject_type: subjectType,
    subject_ids: subjectIds.join(','),
  });
  const response = await requestJson<{ items: Record<string, AiFeedbackVerdict> }>(
    `/api/ai-feedback?${params}`
  );
  return response.items;
}
