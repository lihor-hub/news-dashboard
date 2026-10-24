import { useCallback, useState } from 'react';

// Briefing payloads carry no per-story read state, so story progress is tracked
// locally per briefing. Keys are `brief.read.<briefingId>` → JSON array of
// section indexes the reader has opened.
const KEY_PREFIX = 'brief.read.';

function storageKey(briefingId: number): string {
  return `${KEY_PREFIX}${briefingId}`;
}

export function loadReadStories(briefingId: number): Set<number> {
  try {
    const raw = localStorage.getItem(storageKey(briefingId));
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((v): v is number => Number.isInteger(v)));
  } catch {
    return new Set();
  }
}

function saveReadStories(briefingId: number, read: Set<number>): void {
  try {
    const sorted = [...read].sort((a, b) => a - b);
    localStorage.setItem(storageKey(briefingId), JSON.stringify(sorted));
  } catch {
    // Storage full or unavailable — progress simply won't persist.
  }
}

/** Per-briefing read-story state, persisted to localStorage. */
export function useBriefReadState(briefingId: number) {
  const [state, setState] = useState(() => ({
    briefingId,
    read: loadReadStories(briefingId),
  }));
  // Re-sync during render when the briefing changes (e.g. after Refresh).
  const current =
    state.briefingId === briefingId ? state : { briefingId, read: loadReadStories(briefingId) };
  if (current !== state) setState(current);

  const markRead = useCallback(
    (index: number) => {
      setState((prev) => {
        if (prev.briefingId === briefingId && prev.read.has(index)) return prev;
        const base = prev.briefingId === briefingId ? prev.read : loadReadStories(briefingId);
        const read = new Set(base).add(index);
        saveReadStories(briefingId, read);
        return { briefingId, read };
      });
    },
    [briefingId]
  );

  return { read: current.read, markRead };
}

/** Rough reading time for a brief at ~200 wpm, never below one minute. */
export function estimateReadingMinutes(texts: string[]): number {
  const words = texts.reduce((n, text) => n + text.split(/\s+/).filter(Boolean).length, 0);
  return Math.max(1, Math.round(words / 200));
}
