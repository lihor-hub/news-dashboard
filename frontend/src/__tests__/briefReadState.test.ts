// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { estimateReadingMinutes, loadReadStories, useBriefReadState } from '@/lib/briefReadState';

describe('briefReadState', () => {
  beforeEach(() => localStorage.clear());

  it('ignores corrupt or non-array stored values', () => {
    localStorage.setItem('brief.read.1', '{not json');
    expect(loadReadStories(1).size).toBe(0);
    localStorage.setItem('brief.read.1', '{"a":1}');
    expect(loadReadStories(1).size).toBe(0);
    localStorage.setItem('brief.read.1', '[0, "x", 2.5, 3]');
    expect([...loadReadStories(1)]).toEqual([0, 3]);
  });

  it('persists reads per briefing and resyncs when the briefing changes', () => {
    localStorage.setItem('brief.read.2', '[1]');
    const { result, rerender } = renderHook(({ id }) => useBriefReadState(id), {
      initialProps: { id: 1 },
    });
    act(() => result.current.markRead(0));
    act(() => result.current.markRead(0));
    expect(localStorage.getItem('brief.read.1')).toBe('[0]');

    rerender({ id: 2 });
    expect([...result.current.read]).toEqual([1]);
    act(() => result.current.markRead(0));
    expect(localStorage.getItem('brief.read.2')).toBe('[0,1]');
  });

  it('estimates at least one minute at ~200 words per minute', () => {
    expect(estimateReadingMinutes([''])).toBe(1);
    expect(estimateReadingMinutes(['word '.repeat(600)])).toBe(3);
  });
});
