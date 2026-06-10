export type Category =
  | "Python"
  | "AI/LLM"
  | "Agents"
  | "Cloud/Infra"
  | "Engineering"
  | "Trending"
  | "Repositories";

export const CATEGORIES: Category[] = [
  "Python",
  "AI/LLM",
  "Agents",
  "Cloud/Infra",
  "Engineering",
  "Trending",
  "Repositories",
];

export type WorkflowState = "today" | "later" | "done" | "skipped" | "archived";

export const STATE_LABELS: Record<WorkflowState, string> = {
  today: "Today",
  later: "Later",
  done: "Done",
  skipped: "Skipped",
  archived: "Archived",
};

export type Signal = "high" | "mid" | "low";

export type SourceKind = "rss" | "github" | "trending" | "scraped";

export type SourceHealth = "ok" | "stale" | "error";

export interface Source {
  id: string;
  name: string;
  kind: SourceKind;
  category: Category;
  enabled: boolean;
  health: SourceHealth;
  lastChecked: string; // ISO
  lastSuccess: string; // ISO
  itemsFetched: number;
  itemsInserted: number;
  errorMessage?: string;
}

export interface Article {
  id: string;
  title: string;
  sourceId: string;
  sourceName: string;
  category: Category;
  url: string;
  publishedAt: string; // ISO
  ingestedAt: string; // ISO
  reason: string; // why this matters
  summary: string;
  signal: Signal;
  tags: string[];
  body?: string; // extracted full text (markdown-ish)
  bodyStatus: "ok" | "missing" | "error";
  state: WorkflowState;
  starred: boolean;
  done_at?: string;
  skipped_at?: string;
  archived_at?: string;
  starred_at?: string;
  later_until?: string;
  snoozed_until?: string;
  restored_at?: string;
}

export interface FeedRun {
  id: string;
  startedAt: string;
  durationMs: number;
  status: "ok" | "partial" | "error";
  itemsFound: number;
  itemsInserted: number;
  perSource: { sourceId: string; sourceName: string; found: number; inserted: number; status: "ok" | "error"; error?: string }[];
}

export interface LogLine {
  ts: string;
  level: "info" | "warn" | "error" | "ok";
  text: string;
}
