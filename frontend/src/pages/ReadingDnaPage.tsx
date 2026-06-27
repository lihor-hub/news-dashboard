import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { CheckCircle, Loader2, Plus, RefreshCw, Trash2, XCircle } from 'lucide-react';
import {
  createGoal,
  deleteGoal,
  fetchGoals,
  fetchLatestQuiz,
  fetchQuizCandidates,
  fetchQuizHistory,
  fetchReadingDna,
  fetchRecommendationPreferences,
  generateQuiz,
  saveRecommendationPreferences,
  submitQuiz,
} from '../api';
import type {
  Quiz,
  QuizCandidate,
  QuizHistoryItem,
  QuizQuestion,
  QuizResult,
  ReadingDna,
  ReadingDnaBucket,
  ReadingGoal,
  RecommendationPreferences,
} from '../types';

const DEFAULT_CATEGORIES = ['tech', 'science', 'business', 'world', 'ai'];

type Tab = 'dna' | 'learning';

interface PageState {
  dna: ReadingDna | null;
  preferences: RecommendationPreferences | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
}

export function ReadingDnaPage() {
  const [tab, setTab] = useState<Tab>('dna');
  const [state, setState] = useState<PageState>({
    dna: null,
    preferences: null,
    loading: true,
    saving: false,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchReadingDna(), fetchRecommendationPreferences()])
      .then(([dna, preferences]) => {
        if (!cancelled) {
          setState({ dna, preferences, loading: false, saving: false, error: null });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load Reading DNA',
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const categories = useMemo(() => {
    const fromStats = state.dna?.categories.map((item) => item.category).filter(Boolean) ?? [];
    return Array.from(new Set([...fromStats, ...DEFAULT_CATEGORIES])).slice(0, 8) as string[];
  }, [state.dna]);

  async function updatePreferences(next: Partial<RecommendationPreferences>) {
    if (!state.preferences) return;
    const optimistic = {
      ...state.preferences,
      ...next,
      category_weights: next.category_weights ?? state.preferences.category_weights,
    };
    setState((s) => ({ ...s, preferences: optimistic, saving: true, error: null }));
    try {
      const preferences = await saveRecommendationPreferences(next);
      const dna = await fetchReadingDna();
      setState((s) => ({ ...s, dna, preferences, saving: false }));
    } catch (err) {
      setState((s) => ({
        ...s,
        saving: false,
        error: err instanceof Error ? err.message : 'Failed to save preferences',
      }));
    }
  }

  const { dna, preferences, loading, saving, error } = state;

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center p-8">
        <Loader2 className="text-muted-foreground size-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl space-y-5 p-4 md:p-5">
      <section>
        <h2 className="text-[22px] font-semibold tracking-tight">Reading DNA</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Your recent reading mix and recommendation controls
        </p>
      </section>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex gap-1 border-b border-border">
        <TabButton active={tab === 'dna'} onClick={() => setTab('dna')}>
          Reading DNA
        </TabButton>
        <TabButton active={tab === 'learning'} onClick={() => setTab('learning')}>
          Learning Center
        </TabButton>
      </div>

      {tab === 'dna' && (
        <>
          <section className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Metric label="Window" value={`${dna?.range_days ?? 30}d`} />
            <Metric label="Avg dwell" value={`${dna?.average_dwell_seconds ?? 0}s`} />
            <Metric
              label="Read"
              value={String(dna?.categories.reduce((sum, item) => sum + item.done, 0) ?? 0)}
            />
            <Metric
              label="Skipped"
              value={String(dna?.categories.reduce((sum, item) => sum + item.skipped, 0) ?? 0)}
            />
          </section>

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Category mix">
              <BucketBars items={dna?.categories ?? []} labelKey="category" />
            </Panel>
            <Panel title="Source mix">
              <BucketBars items={dna?.sources ?? []} labelKey="source" />
            </Panel>
          </section>

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <Panel title="Time on app">
              <div className="flex h-40 items-end gap-2">
                {(dna?.monthly_time ?? []).map((point) => {
                  const max = Math.max(...(dna?.monthly_time ?? []).map((p) => p.minutes), 1);
                  return (
                    <div
                      key={point.month}
                      className="flex h-full flex-1 flex-col justify-end gap-2"
                    >
                      <div
                        className="min-h-1 rounded-t bg-chart-2"
                        style={{ height: `${Math.max(4, (point.minutes / max) * 100)}%` }}
                        title={`${point.minutes} min`}
                      />
                      <div className="truncate text-center text-[10px] text-subtle">
                        {point.month}
                      </div>
                    </div>
                  );
                })}
                {dna?.monthly_time.length === 0 && <EmptyLine />}
              </div>
            </Panel>

            <Panel title="Active nudges">
              <div className="space-y-4">
                {categories.map((category) => {
                  const value = preferences?.category_weights[category] ?? 1;
                  return (
                    <SliderRow
                      key={category}
                      label={category}
                      value={value}
                      onChange={(next) =>
                        void updatePreferences({
                          category_weights: {
                            ...(preferences?.category_weights ?? {}),
                            [category]: next,
                          },
                        })
                      }
                    />
                  );
                })}
                <SliderRow
                  label="novelty"
                  value={preferences?.novelty_weight ?? 1}
                  onChange={(next) => void updatePreferences({ novelty_weight: next })}
                />
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {saving && <RefreshCw className="size-3 animate-spin" />}
                  <span>{saving ? 'Saving and recalculating' : 'Changes save immediately'}</span>
                </div>
              </div>
            </Panel>
          </section>
        </>
      )}

      {tab === 'learning' && <LearningCenter />}
    </div>
  );
}

function LearningCenter() {
  const [goals, setGoals] = useState<ReadingGoal[]>([]);
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [quizHistory, setQuizHistory] = useState<QuizHistoryItem[]>([]);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [loadingGoals, setLoadingGoals] = useState(true);
  const [loadingQuiz, setLoadingQuiz] = useState(true);
  const [generatingQuiz, setGeneratingQuiz] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newDescription, setNewDescription] = useState('');
  const [newKeywords, setNewKeywords] = useState('');
  const [addingGoal, setAddingGoal] = useState(false);
  const [showGoalForm, setShowGoalForm] = useState(false);
  const [candidates, setCandidates] = useState<QuizCandidate[] | null>(null);

  const refreshQuizHistory = async () => {
    try {
      setQuizHistory(await fetchQuizHistory());
    } catch {
      setQuizHistory([]);
    }
  };

  useEffect(() => {
    fetchGoals()
      .then(setGoals)
      .catch(() => setGoals([]))
      .finally(() => setLoadingGoals(false));
    fetchLatestQuiz()
      .then((q) => {
        setQuiz(q);
        if (q?.completed_result) {
          setResult(q.completed_result);
        }
      })
      .catch(() => setQuiz(null))
      .finally(() => setLoadingQuiz(false));
    fetchQuizCandidates()
      .then(setCandidates)
      .catch(() => {
        // leave candidates null so the default UI renders when the endpoint is unavailable
      });
    void refreshQuizHistory();
  }, []);

  async function handleAddGoal() {
    if (!newDescription.trim()) return;
    setAddingGoal(true);
    setError(null);
    try {
      const goal = await createGoal(newDescription.trim(), newKeywords.trim());
      setGoals((prev) => [goal, ...prev]);
      setNewDescription('');
      setNewKeywords('');
      setShowGoalForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add goal');
    } finally {
      setAddingGoal(false);
    }
  }

  async function handleDeleteGoal(goalId: number) {
    try {
      await deleteGoal(goalId);
      setGoals((prev) => prev.filter((g) => g.id !== goalId));
    } catch {
      setError('Failed to delete goal');
    }
  }

  async function handleGenerateQuiz() {
    setGeneratingQuiz(true);
    setError(null);
    setResult(null);
    setAnswers({});
    try {
      const newQuiz = await generateQuiz();
      setQuiz(newQuiz);
      await refreshQuizHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate quiz');
    } finally {
      setGeneratingQuiz(false);
    }
  }

  async function handleSubmitQuiz() {
    if (!quiz) return;
    const answerList = quiz.questions.map((_, i) => answers[i] ?? -1);
    setSubmitting(true);
    setError(null);
    try {
      const quizResult = await submitQuiz(quiz.id, answerList);
      setResult(quizResult);
      await refreshQuizHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit quiz');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Goals section */}
      <Panel title="Learning Goals">
        <div className="space-y-3">
          {loadingGoals ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-3 animate-spin" /> Loading goals…
            </div>
          ) : goals.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No goals yet. Add one to boost relevant articles.
            </p>
          ) : (
            <ul className="space-y-2">
              {goals.map((goal) => (
                <li
                  key={goal.id}
                  className="flex items-start justify-between gap-3 rounded border border-border px-3 py-2 text-sm"
                >
                  <div>
                    <div className="font-medium">{goal.description}</div>
                    {goal.keywords && (
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        Keywords: {goal.keywords}
                      </div>
                    )}
                  </div>
                  <button
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => void handleDeleteGoal(goal.id)}
                    title="Delete goal"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {showGoalForm ? (
            <div className="space-y-2 rounded border border-border p-3">
              <input
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="Goal description (e.g. Understand transformer architectures)"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
              <input
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="Keywords (space-separated, optional)"
                value={newKeywords}
                onChange={(e) => setNewKeywords(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
                  disabled={!newDescription.trim() || addingGoal}
                  onClick={() => void handleAddGoal()}
                >
                  {addingGoal ? 'Saving…' : 'Save goal'}
                </button>
                <button
                  className="rounded border border-border px-3 py-1.5 text-xs"
                  onClick={() => {
                    setShowGoalForm(false);
                    setNewDescription('');
                    setNewKeywords('');
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              className="flex items-center gap-1.5 text-xs text-primary hover:underline"
              onClick={() => setShowGoalForm(true)}
            >
              <Plus className="size-3" /> Add goal
            </button>
          )}
        </div>
      </Panel>

      {/* Quiz section */}
      <Panel title="Weekly Knowledge Quiz">
        {loadingQuiz ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-3 animate-spin" /> Loading quiz…
          </div>
        ) : result ? (
          <QuizResultView result={result} />
        ) : quiz ? (
          <QuizView
            quiz={quiz}
            answers={answers}
            onAnswer={(qi, ai) => setAnswers((prev) => ({ ...prev, [qi]: ai }))}
            onSubmit={() => void handleSubmitQuiz()}
            submitting={submitting}
          />
        ) : candidates !== null && candidates.length === 0 ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              No quiz material yet. Mark articles as done while reading to build up quiz content.
            </p>
            <p className="text-xs text-muted-foreground">
              Quizzes draw from articles you finished in the last 7 days.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {candidates && candidates.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Quiz will draw from
                </p>
                <ul className="space-y-1">
                  {candidates.slice(0, 5).map((c) => (
                    <li key={c.id} className="flex items-start gap-2 text-xs">
                      <span className="mt-0.5 shrink-0 text-muted-foreground">·</span>
                      <span className="min-w-0">
                        <span className="font-medium">{c.title}</span>
                        {(c.source_name ?? c.category) && (
                          <span className="ml-1 text-muted-foreground">
                            {[c.source_name ?? null, c.category ?? null]
                              .filter(Boolean)
                              .join(' · ')}
                          </span>
                        )}
                        {c.goal_matched && <span className="ml-1 text-primary">✓ goal</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-sm text-muted-foreground">
              No quiz yet. Generate one based on your recent reading.
            </p>
            <button
              className="flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
              disabled={generatingQuiz}
              onClick={() => void handleGenerateQuiz()}
            >
              {generatingQuiz && <Loader2 className="size-3 animate-spin" />}
              {generatingQuiz ? 'Generating…' : 'Generate quiz'}
            </button>
          </div>
        )}
        {quiz && !result && (
          <div className="mt-3">
            <button
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              disabled={generatingQuiz}
              onClick={() => void handleGenerateQuiz()}
            >
              {generatingQuiz ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <RefreshCw className="size-3" />
              )}
              Regenerate quiz
            </button>
          </div>
        )}
      </Panel>

      {quizHistory.length > 0 && <QuizHistoryPanel items={quizHistory} />}
    </div>
  );
}

function QuizHistoryPanel({ items }: { items: QuizHistoryItem[] }) {
  const completed = items.filter((item) => item.completed && item.score !== null);
  const average =
    completed.length > 0
      ? Math.round(
          (completed.reduce((sum, item) => sum + (item.score ?? 0) / item.total, 0) /
            completed.length) *
            100
        )
      : null;
  const streak = items.findIndex((item) => !item.completed);
  const currentStreak = streak === -1 ? items.length : streak;

  return (
    <Panel title="Quiz Progress">
      <div className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <ProgressStat label="Attempts" value={String(items.length)} />
          <ProgressStat label="Average" value={average === null ? '—' : `${average}%`} />
          <ProgressStat label="Streak" value={String(currentStreak)} />
        </div>
        <ul className="divide-y divide-border rounded border border-border">
          {items.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">
                  {new Date(item.created_at).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </div>
                <div className="text-xs text-muted-foreground">
                  {item.completed ? 'Completed' : 'Not completed'}
                </div>
              </div>
              <div className="shrink-0 text-sm font-semibold tabular-nums">
                {item.score === null ? `—/${item.total}` : `${item.score}/${item.total}`}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}

function ProgressStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function QuizView({
  quiz,
  answers,
  onAnswer,
  onSubmit,
  submitting,
}: {
  quiz: Quiz;
  answers: Record<number, number>;
  onAnswer: (questionIndex: number, answerIndex: number) => void;
  onSubmit: () => void;
  submitting: boolean;
}) {
  const allAnswered = quiz.questions.every((_, i) => answers[i] !== undefined);

  return (
    <div className="space-y-5">
      {quiz.questions.map((q, qi) => (
        <QuestionCard
          key={qi}
          question={q}
          questionIndex={qi}
          selectedAnswer={answers[qi]}
          onSelect={(ai) => onAnswer(qi, ai)}
        />
      ))}
      <button
        className="flex items-center gap-1.5 rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        disabled={!allAnswered || submitting}
        onClick={onSubmit}
      >
        {submitting && <Loader2 className="size-3.5 animate-spin" />}
        {submitting ? 'Submitting…' : 'Submit answers'}
      </button>
    </div>
  );
}

function QuestionCard({
  question,
  questionIndex,
  selectedAnswer,
  onSelect,
}: {
  question: QuizQuestion;
  questionIndex: number;
  selectedAnswer: number | undefined;
  onSelect: (answerIndex: number) => void;
}) {
  return (
    <div className="rounded border border-border p-3 space-y-2">
      <p className="text-sm font-medium">
        {questionIndex + 1}. {question.question}
      </p>
      <div className="space-y-1.5">
        {question.options.map((opt, ai) => (
          <label
            key={ai}
            className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted"
          >
            <input
              type="radio"
              name={`q-${questionIndex}`}
              checked={selectedAnswer === ai}
              onChange={() => onSelect(ai)}
              className="accent-primary"
            />
            {opt}
          </label>
        ))}
      </div>
    </div>
  );
}

function QuizResultView({ result }: { result: QuizResult }) {
  const pct = Math.round((result.score / result.total) * 100);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="text-3xl font-bold tabular-nums">
          {result.score}/{result.total}
        </div>
        <div className="text-sm text-muted-foreground">{pct}% correct</div>
      </div>
      <div className="space-y-3">
        {result.questions.map((q, qi) => {
          const isCorrect = q.your_answer === q.correct_index;
          return (
            <div
              key={qi}
              className={`rounded border p-3 space-y-1.5 ${isCorrect ? 'border-green-500/40 bg-green-500/5' : 'border-destructive/40 bg-destructive/5'}`}
            >
              <div className="flex items-start gap-2">
                {isCorrect ? (
                  <CheckCircle className="mt-0.5 size-3.5 shrink-0 text-green-500" />
                ) : (
                  <XCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                )}
                <p className="text-sm font-medium">{q.question}</p>
              </div>
              <div className="space-y-1 pl-5">
                {q.options.map((opt, ai) => (
                  <div
                    key={ai}
                    className={`text-xs ${ai === q.correct_index ? 'font-semibold text-green-600' : ai === q.your_answer && !isCorrect ? 'text-destructive line-through' : 'text-muted-foreground'}`}
                  >
                    {opt}
                  </div>
                ))}
              </div>
              {q.explanation && (
                <p className="pl-5 text-xs text-muted-foreground">{q.explanation}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      className={`px-4 py-2 text-sm font-medium transition-colors ${
        active
          ? 'border-b-2 border-primary text-foreground'
          : 'text-muted-foreground hover:text-foreground'
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  );
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

function BucketBars({
  items,
  labelKey,
}: {
  items: ReadingDnaBucket[];
  labelKey: 'category' | 'source';
}) {
  if (items.length === 0) return <EmptyLine />;
  return (
    <div className="space-y-3">
      {items.slice(0, 8).map((item) => {
        const label = item[labelKey] ?? 'unknown';
        return (
          <div key={label} className="space-y-1">
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="truncate font-medium capitalize">{label}</span>
              <span className="text-muted-foreground tabular-nums">{item.percentage}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-muted">
              <div className="h-full bg-chart-1" style={{ width: `${item.percentage}%` }} />
            </div>
            <div className="text-[10px] text-subtle">
              {item.done} read / {item.skipped} skipped
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SliderRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium capitalize">{label}</span>
        <span className="tabular-nums text-muted-foreground">{value.toFixed(1)}x</span>
      </div>
      <input
        className="w-full accent-primary"
        type="range"
        min="0"
        max="3"
        step="0.1"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function EmptyLine() {
  return <div className="py-8 text-center text-sm text-muted-foreground">No activity yet</div>;
}
