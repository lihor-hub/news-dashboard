import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatInteger,
  readingTime,
  relativeCountdown,
  relativeTime,
  signalLabel,
} from '../lib/format';

// A fixed "now" keeps relativeTime / relativeCountdown deterministic.
const NOW = new Date('2026-06-23T12:00:00Z').getTime();

describe('relativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const iso = (msAgo: number) => new Date(NOW - msAgo).toISOString();

  it('reports "just now" for sub-minute past', () => {
    expect(relativeTime(iso(30_000))).toBe('just now');
  });

  it('reports "soon" for sub-minute future', () => {
    expect(relativeTime(iso(-30_000))).toBe('soon');
  });

  it('formats minutes, hours, days and weeks ago', () => {
    expect(relativeTime(iso(5 * 60_000))).toBe('5m ago');
    expect(relativeTime(iso(3 * 3_600_000))).toBe('3h ago');
    expect(relativeTime(iso(2 * 86_400_000))).toBe('2d ago');
    expect(relativeTime(iso(3 * 7 * 86_400_000))).toBe('3w ago');
  });

  it('formats future offsets with an "in" prefix', () => {
    expect(relativeTime(iso(-5 * 60_000))).toBe('in 5m');
    expect(relativeTime(iso(-3 * 3_600_000))).toBe('in 3h');
    expect(relativeTime(iso(-2 * 86_400_000))).toBe('in 2d');
  });

  it('falls back to an absolute date beyond ~5 weeks', () => {
    const result = relativeTime(iso(60 * 86_400_000));
    expect(result).not.toMatch(/ago|in /);
    expect(result.length).toBeGreaterThan(0);
  });
});

describe('formatDate / formatDateTime', () => {
  it('formats a valid ISO string', () => {
    expect(formatDate('2026-06-23T12:00:00Z')).toMatch(/\d/);
  });

  it('formatDateTime returns a dash for empty input', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime(undefined)).toBe('—');
    expect(formatDateTime('')).toBe('—');
  });

  it('formatDateTime echoes back unparseable values', () => {
    expect(formatDateTime('not-a-date')).toBe('not-a-date');
  });

  it('formatDateTime formats a valid value', () => {
    expect(formatDateTime('2026-06-23T12:00:00Z')).toMatch(/\d/);
  });
});

describe('signalLabel', () => {
  it('maps each signal level', () => {
    expect(signalLabel('high')).toBe('High signal');
    expect(signalLabel('mid')).toBe('Maybe');
    expect(signalLabel('low')).toBe('Low signal');
  });
});

describe('formatDuration', () => {
  it('returns a dash for nullish input', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(undefined)).toBe('—');
  });

  it('formats milliseconds, seconds and minutes', () => {
    expect(formatDuration(250)).toBe('250ms');
    expect(formatDuration(5_000)).toBe('5s');
    expect(formatDuration(60_000)).toBe('1m');
    expect(formatDuration(90_000)).toBe('1m 30s');
  });
});

describe('formatInteger', () => {
  it('groups thousands', () => {
    expect(formatInteger(1234567)).toBe(new Intl.NumberFormat().format(1234567));
    expect(formatInteger(0)).toBe('0');
  });
});

// readingTime previously lived in its own readingTime.test.ts; consolidated here
// since it is part of lib/format.
describe('readingTime', () => {
  it('clamps to a minimum of 1 minute', () => {
    expect(readingTime('')).toBe(1);
    expect(readingTime('   \n  ')).toBe(1);
    expect(readingTime('Hello')).toBe(1);
    expect(readingTime(Array(200).fill('word').join(' '))).toBe(1);
  });

  it('rounds up partial pages', () => {
    expect(readingTime(Array(201).fill('word').join(' '))).toBe(2);
    expect(readingTime(Array(800).fill('word').join(' '))).toBe(4);
  });

  it('ignores extra whitespace between words', () => {
    expect(readingTime(Array(201).fill('word').join('\n  '))).toBe(2);
  });
});

describe('relativeCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const inFuture = (ms: number) => new Date(NOW + ms).toISOString();

  it('returns a dash for null', () => {
    expect(relativeCountdown(null)).toBe('—');
  });

  it('returns "now" for past or current timestamps', () => {
    expect(relativeCountdown(new Date(NOW - 1000).toISOString())).toBe('now');
  });

  it('formats hours, minutes and seconds', () => {
    expect(relativeCountdown(inFuture(3_600_000 + 120_000))).toBe('1h 2m');
    expect(relativeCountdown(inFuture(120_000 + 5_000))).toBe('2m 5s');
    expect(relativeCountdown(inFuture(45_000))).toBe('45s');
  });
});
