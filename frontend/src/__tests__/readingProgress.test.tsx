// @vitest-environment happy-dom
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import { ReadingDnaPage } from '../pages/ReadingDnaPage';
import type { Achievement, ReadingDna, ReadingStreak } from '../types';

const dna: ReadingDna = {
  range_days: 30,
  generated_at: '2026-06-21T10:00:00Z',
  categories: [{ category: 'science', done: 12, skipped: 2, total: 14, percentage: 100 }],
  sources: [],
  monthly_time: [],
  average_dwell_seconds: 42,
};

const streak: ReadingStreak = {
  current_streak_days: 7,
  longest_streak_days: 9,
  last_active_date: '2026-07-01',
  active_days: ['2026-07-01'],
  qualifying_activity: 'days with a finished article or article dwell event',
};

const achievements: Achievement[] = [
  {
    key: 'seven_day_streak',
    title: '7-day streak',
    description: 'Read on seven consecutive active days.',
    unlocked: true,
    unlocked_at: '2026-07-01T10:00:00Z',
    progress: 7,
    target: 7,
  },
  {
    key: 'hundred_articles_read',
    title: '100 articles read',
    description: 'Mark 100 articles as done.',
    unlocked: false,
    unlocked_at: null,
    progress: 12,
    target: 100,
  },
];

describe('ReadingDnaPage reading progress', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, 'fetchReadingDna').mockResolvedValue(dna);
    vi.spyOn(api, 'fetchRecommendationPreferences').mockResolvedValue({
      category_weights: {},
      novelty_weight: 1,
    });
    vi.spyOn(api, 'fetchReadingStreak').mockResolvedValue(streak);
    vi.spyOn(api, 'fetchAchievements').mockResolvedValue(achievements);
  });

  it('renders streak and achievement progress on Reading DNA', async () => {
    render(<ReadingDnaPage />);

    await waitFor(() => expect(screen.getByText('Reading streak')).toBeTruthy());
    expect(screen.getByText('Longest streak: 9 days')).toBeTruthy();
    expect(screen.getByText('7-day streak')).toBeTruthy();
    expect(screen.getByText('Unlocked')).toBeTruthy();
    expect(screen.getByText('100 articles read')).toBeTruthy();
    expect(screen.getByText('12/100 progress')).toBeTruthy();
  });
});
