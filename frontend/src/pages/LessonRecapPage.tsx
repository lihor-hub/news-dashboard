import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { AlertCircle, GraduationCap, Headphones, Loader2 } from 'lucide-react';
import { fetchLessonRecaps, generateLessonRecap, generateLessonRecapPodcast } from '../api';
import { Button } from '@/components/ui/button';
import { classifyGenerationError, type FriendlyError } from '@/lib/errorPresentation';
import type { LessonRecap, LessonRecapConcept } from '../types';

interface PageState {
  recaps: LessonRecap[];
  loading: boolean;
  error: string | null;
}

export function LessonRecapPage() {
  const [state, setState] = useState<PageState>({ recaps: [], loading: true, error: null });
  const [isGenerating, setIsGenerating] = useState(false);
  const [isGeneratingPodcast, setIsGeneratingPodcast] = useState(false);
  const [podcastError, setPodcastError] = useState<FriendlyError | null>(null);

  function load() {
    setState((s) => ({ ...s, loading: true }));
    fetchLessonRecaps()
      .then((recaps) => {
        setState({ recaps, loading: false, error: null });
      })
      .catch((err) => {
        setState((s) => ({
          ...s,
          loading: false,
          error: err instanceof Error ? err.message : 'Failed to load learning recaps',
        }));
      });
  }

  useEffect(() => {
    load();
  }, []);

  async function handleGenerate() {
    setIsGenerating(true);
    try {
      await generateLessonRecap();
      load();
    } catch (err) {
      setState((s) => ({
        ...s,
        error: err instanceof Error ? err.message : 'Failed to generate learning recap',
      }));
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleGeneratePodcast(recapId: number, force: boolean) {
    setIsGeneratingPodcast(true);
    setPodcastError(null);
    try {
      const updated = await generateLessonRecapPodcast(recapId, force);
      setState((s) => ({
        ...s,
        recaps: s.recaps.map((r) => (r.id === updated.id ? updated : r)),
      }));
    } catch (err) {
      setPodcastError(classifyGenerationError(err));
    } finally {
      setIsGeneratingPodcast(false);
    }
  }

  const { recaps, loading, error } = state;
  const [latest, ...history] = recaps;

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center p-8">
        <Loader2 className="text-muted-foreground size-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl space-y-5 p-4 md:p-5">
      <section className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[22px] font-semibold tracking-tight">Weekly Learning Recap</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            A summary of the lessons you worked through this week
          </p>
        </div>
        <Button size="sm" onClick={() => void handleGenerate()} disabled={isGenerating}>
          {isGenerating ? 'Generating…' : 'Generate now'}
        </Button>
      </section>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {!latest ? (
        <Panel title="This week">
          <EmptyLine />
        </Panel>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Metric label="Lessons touched" value={String(latest.data.lessons_touched)} />
            <Metric label="Lessons completed" value={String(latest.data.lessons_completed)} />
            <Metric label="Unfinished" value={String(latest.data.unfinished_lessons.length)} />
            <Metric
              label="Week"
              value={`${formatDate(latest.data.week_start)} – ${formatDate(latest.data.week_end)}`}
            />
          </section>

          {latest.narrative && (
            <Panel title="What you learned">
              <div className="flex items-start gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded bg-primary/10 text-primary">
                  <GraduationCap className="size-5" />
                </div>
                <div className="space-y-2 text-sm">
                  {latest.narrative
                    .split(/\n\s*\n/)
                    .map((paragraph) => paragraph.trim())
                    .filter(Boolean)
                    .map((paragraph, index) => (
                      <p key={index}>{paragraph}</p>
                    ))}
                </div>
              </div>
            </Panel>
          )}

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Key concepts">
              <ConceptBars items={latest.data.key_concepts} />
            </Panel>
            <Panel title="Repeated themes">
              <ConceptBars items={latest.data.repeated_themes} />
            </Panel>
          </section>

          {latest.data.unfinished_lessons.length > 0 && (
            <Panel title="Unfinished lessons">
              <ul className="divide-y divide-border">
                {latest.data.unfinished_lessons.map((lesson) => (
                  <li key={lesson.id} className="py-2 text-sm">
                    <Link to={`/learn/${lesson.id}`} className="hover:underline">
                      {lesson.title}
                    </Link>
                    <span className="ml-2 text-xs text-muted-foreground capitalize">
                      {lesson.generation_status}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {latest.data.notable_articles.length > 0 && (
            <Panel title="Notable articles">
              <ul className="divide-y divide-border">
                {latest.data.notable_articles.map((article) => (
                  <li key={article.id} className="flex items-center justify-between py-2 text-sm">
                    <Link to={`/learn/${article.id}`} className="hover:underline">
                      {article.title}
                    </Link>
                    <span className="text-xs text-muted-foreground">{article.source_name}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="Podcast audio">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Headphones className="size-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Listen to this week's recap</span>
                </div>
                <Button
                  size="sm"
                  variant={latest.podcast_status ? 'outline' : 'default'}
                  onClick={() =>
                    void handleGeneratePodcast(latest.id, latest.podcast_status !== null)
                  }
                  disabled={isGeneratingPodcast}
                >
                  {isGeneratingPodcast
                    ? 'Generating…'
                    : latest.podcast_status
                      ? 'Regenerate'
                      : 'Create podcast'}
                </Button>
              </div>

              {latest.podcast_status === 'complete' ? (
                <audio
                  src={`/api/lesson-recaps/${latest.id}/podcast`}
                  controls
                  className="h-9 w-full"
                />
              ) : null}

              {podcastError ? (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <div>
                    <div className="font-semibold">{podcastError.title}</div>
                    <div className="mt-0.5">{podcastError.message}</div>
                  </div>
                </div>
              ) : latest.podcast_status === 'failed' && latest.podcast_error ? (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <div>{latest.podcast_error}</div>
                </div>
              ) : null}
            </div>
          </Panel>
        </>
      )}

      {history.length > 0 && (
        <Panel title="Past recaps">
          <ul className="divide-y divide-border">
            {history.map((recap) => (
              <li key={recap.id} className="flex items-center justify-between py-2 text-sm">
                <span className="text-muted-foreground">
                  {formatDate(recap.data.week_start)} – {formatDate(recap.data.week_end)}
                </span>
                <span className="tabular-nums">{recap.data.lessons_completed} lessons</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-surface p-3">
      <h3 className="text-sm font-medium">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function ConceptBars({ items }: { items: LessonRecapConcept[] }) {
  if (items.length === 0) return <EmptyLine />;
  const max = Math.max(...items.map((item) => item.count), 1);
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.concept} className="space-y-1">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="truncate font-medium capitalize">{item.concept}</span>
            <span className="text-muted-foreground tabular-nums">{item.count}</span>
          </div>
          <div className="h-2 overflow-hidden rounded bg-muted">
            <div className="h-full bg-chart-1" style={{ width: `${(item.count / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyLine() {
  return (
    <div className="py-8 text-center text-sm text-muted-foreground">
      No recap yet — finish a lesson this week, then check back or generate one now.
    </div>
  );
}
