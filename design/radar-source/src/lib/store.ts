import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Article, WorkflowState, Source, Category } from "./types";
import { ARTICLES, SOURCES } from "./mock-data";

export type Theme = "light" | "dark" | "system";

interface UndoSnapshot {
  article: Article;
}

interface Filters {
  categories: Category[];
  sources: string[];
  states: WorkflowState[];
  includeArchived: boolean;
  starredOnly: boolean;
  dateRange: "all" | "today" | "week" | "month";
}

interface AppState {
  articles: Article[];
  sources: Source[];
  ingestIntervalMin: number;
  ingestPaused: boolean;
  nextRunAt: string;
  theme: Theme;
  filters: Filters;
  setTheme: (t: Theme) => void;
  setFilters: (f: Partial<Filters>) => void;
  resetFilters: () => void;
  update: (id: string, patch: Partial<Article>) => UndoSnapshot;
  setState: (id: string, state: WorkflowState) => UndoSnapshot | null;
  toggleStar: (id: string) => UndoSnapshot;
  sendLater: (id: string, days?: number) => UndoSnapshot | null;
  restore: (snap: UndoSnapshot) => void;
  toggleSource: (id: string) => void;
  setInterval: (min: number) => void;
  setPaused: (p: boolean) => void;
  refreshNow: () => void;
}

const defaultFilters: Filters = {
  categories: [],
  sources: [],
  states: [],
  includeArchived: false,
  starredOnly: false,
  dateRange: "all",
};

export const useApp = create<AppState>()(
  persist(
    (set, get) => ({
      articles: ARTICLES,
      sources: SOURCES,
      ingestIntervalMin: 30,
      ingestPaused: false,
      nextRunAt: new Date(Date.now() + 18 * 60 * 1000).toISOString(),
      theme: "system",
      filters: defaultFilters,
      setTheme: (t) => set({ theme: t }),
      setFilters: (f) => set({ filters: { ...get().filters, ...f } }),
      resetFilters: () => set({ filters: defaultFilters }),
      update: (id, patch) => {
        const before = get().articles.find((a) => a.id === id)!;
        set({
          articles: get().articles.map((a) => (a.id === id ? { ...a, ...patch } : a)),
        });
        return { article: before };
      },
      setState: (id, state) => {
        const a = get().articles.find((x) => x.id === id);
        if (!a) return null;
        if (state === "skipped" && a.starred) return null;
        const now = new Date().toISOString();
        const patch: Partial<Article> = { state };
        if (state === "done") patch.done_at = now;
        if (state === "skipped") patch.skipped_at = now;
        if (state === "archived") patch.archived_at = now;
        if (state === "today") {
          patch.restored_at = now;
          patch.later_until = undefined;
        }
        return get().update(id, patch);
      },
      toggleStar: (id) => {
        const a = get().articles.find((x) => x.id === id)!;
        const now = new Date().toISOString();
        return get().update(id, {
          starred: !a.starred,
          starred_at: !a.starred ? now : a.starred_at,
        });
      },
      sendLater: (id, days = 1) => {
        const a = get().articles.find((x) => x.id === id);
        if (!a) return null;
        const until = new Date(Date.now() + days * 24 * 3600 * 1000).toISOString();
        return get().update(id, { state: "later", later_until: until, snoozed_until: until });
      },
      restore: (snap) => {
        set({
          articles: get().articles.map((a) => (a.id === snap.article.id ? snap.article : a)),
        });
      },
      toggleSource: (id) =>
        set({
          sources: get().sources.map((s) =>
            s.id === id ? { ...s, enabled: !s.enabled } : s,
          ),
        }),
      setInterval: (min) => set({ ingestIntervalMin: min, nextRunAt: new Date(Date.now() + min * 60 * 1000).toISOString() }),
      setPaused: (p) => set({ ingestPaused: p }),
      refreshNow: () => set({ nextRunAt: new Date(Date.now() + get().ingestIntervalMin * 60 * 1000).toISOString() }),
    }),
    {
      name: "radar-app",
      partialize: (s) => ({
        articles: s.articles,
        sources: s.sources,
        ingestIntervalMin: s.ingestIntervalMin,
        ingestPaused: s.ingestPaused,
        theme: s.theme,
      }),
    },
  ),
);

// Theme effect helper
export function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  root.classList.toggle("dark", isDark);
}
