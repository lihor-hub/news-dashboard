import type { LessonRecap } from '../types';
import { requestJson } from './core';

export type LessonDepth = 'tiny' | 'normal' | 'deep' | 'expert';
export type LessonPersona = 'developer' | 'product_builder' | 'new_to_ai' | 'preparing_talk';

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

export interface ComprehensionQuestion {
  question: string;
  expected_answer: string;
}

export interface Flashcard {
  concept: string;
  claim: string;
}

export interface QuizQuestion {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

export interface StudyArtifacts {
  comprehension_questions: ComprehensionQuestion[];
  flashcards: Flashcard[];
  quiz: QuizQuestion[];
}

export interface Slide {
  title: string;
  bullets: string[];
}

export interface SlideDeck {
  slides: Slide[];
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
  study_artifacts: StudyArtifacts | null;
  depth: LessonDepth;
  persona: LessonPersona;
  podcast_status: 'complete' | 'failed' | null;
  podcast_error: string | null;
  slide_deck: SlideDeck | null;
  slide_deck_status: 'complete' | 'failed' | null;
  slide_deck_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface LessonGeneration {
  id: number;
  lesson_id: number;
  depth: LessonDepth;
  persona: LessonPersona;
  lesson_detail: LessonDetail | null;
  generation_status: 'complete' | 'failed';
  generation_error: string | null;
  created_at: string;
}

export async function createLessonFromLink(
  url: string,
  depth: LessonDepth = 'normal',
  persona: LessonPersona = 'developer'
): Promise<Lesson> {
  return requestJson<Lesson>('/api/learn/lessons', {
    method: 'POST',
    body: JSON.stringify({ url, depth, persona }),
  });
}

export async function fetchLesson(id: number): Promise<Lesson> {
  return requestJson<Lesson>(`/api/learn/lessons/${id}`);
}

export async function regenerateLesson(
  id: number,
  depth: LessonDepth,
  persona: LessonPersona
): Promise<Lesson> {
  return requestJson<Lesson>(`/api/learn/lessons/${id}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({ depth, persona }),
  });
}

export async function fetchLessonGenerations(id: number): Promise<LessonGeneration[]> {
  return requestJson<LessonGeneration[]>(`/api/learn/lessons/${id}/generations`);
}

export async function generateLessonPodcast(id: number, force = false): Promise<Lesson> {
  return requestJson<Lesson>(`/api/learn/lessons/${id}/podcast${force ? '?force=true' : ''}`, {
    method: 'POST',
  });
}

export async function generateLessonSlideDeck(id: number, force = false): Promise<Lesson> {
  return requestJson<Lesson>(`/api/learn/lessons/${id}/slides${force ? '?force=true' : ''}`, {
    method: 'POST',
  });
}

export interface ListLessonsParams {
  q?: string;
  status?: Lesson['generation_status'];
  verdict?: LessonReadWorthiness['verdict'];
}

export async function listLessons(params: ListLessonsParams = {}): Promise<Lesson[]> {
  const search = new URLSearchParams();
  if (params.q?.trim()) search.set('q', params.q.trim());
  if (params.status) search.set('status', params.status);
  if (params.verdict) search.set('verdict', params.verdict);
  const query = search.toString();
  const { lessons } = await requestJson<{ lessons: Lesson[] }>(
    `/api/learn/lessons${query ? `?${query}` : ''}`
  );
  return lessons;
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

export interface LessonSuggestion {
  article_id: number;
  title: string;
  url: string;
  source_name: string | null;
  category: string | null;
  score: number;
  reasons: string[];
}

export async function listLessonSuggestions(): Promise<LessonSuggestion[]> {
  const { items } = await requestJson<{ items: LessonSuggestion[] }>('/api/learn/suggestions');
  return items;
}

export async function dismissLessonSuggestion(
  articleId: number
): Promise<{ dismissed: boolean; article_id: number }> {
  return requestJson('/api/learn/suggestions/dismiss', {
    method: 'POST',
    body: JSON.stringify({ article_id: articleId }),
  });
}

export async function fetchLessonRecaps(): Promise<LessonRecap[]> {
  const { items } = await requestJson<{ items: LessonRecap[] }>('/api/lesson-recaps');
  return items;
}

export async function generateLessonRecap(): Promise<LessonRecap> {
  return requestJson<LessonRecap>('/api/lesson-recaps/generate', { method: 'POST' });
}

export async function generateLessonRecapPodcast(
  recapId: number,
  force = false
): Promise<LessonRecap> {
  return requestJson<LessonRecap>(
    `/api/lesson-recaps/${recapId}/podcast${force ? '?force=true' : ''}`,
    { method: 'POST' }
  );
}
