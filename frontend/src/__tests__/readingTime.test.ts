import { describe, it, expect } from 'vitest';
import { readingTime } from '../lib/format';

describe('readingTime', () => {
  it('returns 1 for empty string', () => {
    expect(readingTime('')).toBe(1);
  });

  it('returns 1 for whitespace-only string', () => {
    expect(readingTime('   \n  ')).toBe(1);
  });

  it('returns 1 for a single word', () => {
    expect(readingTime('Hello')).toBe(1);
  });

  it('returns 1 for 200 words', () => {
    const text = Array(200).fill('word').join(' ');
    expect(readingTime(text)).toBe(1);
  });

  it('rounds up: 201 words → 2 min', () => {
    const text = Array(201).fill('word').join(' ');
    expect(readingTime(text)).toBe(2);
  });

  it('returns 4 for 800 words', () => {
    const text = Array(800).fill('word').join(' ');
    expect(readingTime(text)).toBe(4);
  });

  it('rounds up: 201 words with extra whitespace and newlines', () => {
    const text = Array(201).fill('word').join('\n  ');
    expect(readingTime(text)).toBe(2);
  });

  it('handles a realistic article snippet', () => {
    // 50 words — rounds up to 1
    const text = 'The quick brown fox jumps over the lazy dog. '.repeat(10).trimEnd();
    expect(readingTime(text)).toBe(1);
  });
});
