import { requestJson } from './core';

export type LessonVerdict = 'skip' | 'skim' | 'read' | 'study';

export interface LessonCitation {
  text: string;
  note: string | null;
}

export interface LessonContent {
  gist: string;
  explanation: string;
  key_claims: string[];
  prerequisites: string[];
  why_it_matters: string;
  verdict: LessonVerdict;
  verdict_rationale: string;
  intended_readers: string[];
  guiding_questions: string[];
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
  lesson_content: LessonContent | null;
  generation_status: 'pending' | 'complete' | 'failed';
  generation_error: string | null;
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
