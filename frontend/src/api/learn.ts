import { requestJson } from './core';

export interface LessonReadWorthiness {
  verdict: 'skip' | 'skim' | 'read' | 'study';
  rationale: string;
}

export interface LessonCitation {
  label: string;
  snippet: string;
  source: string;
}

export interface LessonDetail {
  gist: string;
  explanation: string;
  key_claims: string[];
  prerequisite_concepts: string[];
  why_it_matters: string;
  read_worthiness: LessonReadWorthiness;
  who_should_read: string[];
  questions_to_keep_in_mind: string[];
  citations: LessonCitation[];
}

export interface Lesson {
  id: number;
  user_id: number;
  original_url: string;
  normalized_url: string;
  title: string | null;
  source_name: string | null;
  author: string | null;
  published_at: string | null;
  source_content: string | null;
  generation_status: 'pending' | 'complete' | 'failed';
  generation_error: string | null;
  lesson_detail: LessonDetail | null;
  created_at: string;
  updated_at: string;
}

export async function createLessonFromLink(url: string): Promise<Lesson> {
  return requestJson<Lesson>('/api/learn/lessons', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export async function fetchLesson(id: number): Promise<Lesson> {
  return requestJson<Lesson>(`/api/learn/lessons/${id}`);
}

export interface LessonChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export async function askLessonQuestion(
  lessonId: number,
  question: string,
  history: LessonChatMessage[]
): Promise<{ reply: string }> {
  return requestJson<{ reply: string }>(`/api/learn/lessons/${lessonId}/questions`, {
    method: 'POST',
    body: JSON.stringify({ question, history }),
  });
}
