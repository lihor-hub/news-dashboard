import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  fetchArticleCounts,
  fetchCategoryMix,
  fetchIngestedVsHandled,
  fetchSourceQuality,
  fetchTriageMetrics,
} from '../api';
import type {
  ArticleCountsResult,
  CategoryMixPoint,
  IngestedVsHandledPoint,
  SourceQualityRow,
  TriageMetrics,
} from '../types';

const CHART_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
];

const TOOLTIP_STYLE = {
  background: 'var(--color-popover)',
  border: '1px solid var(--color-border)',
  borderRadius: 6,
  fontSize: 12,
  color: 'var(--color-foreground)',
};

const GRID_STROKE = 'var(--color-border)';
const AXIS_FILL = 'var(--color-subtle)';

interface StatsState {
  counts: ArticleCountsResult | null;
  triage: TriageMetrics | null;
  overTime: IngestedVsHandledPoint[];
  sourceQuality: SourceQualityRow[];
  categoryMix: CategoryMixPoint[];
  loading: boolean;
  error: string | null;
}

export function StatsPage() {
  const [state, setState] = useState<StatsState>({
    counts: null,
    triage: null,
    overTime: [],
    sourceQuality: [],
    categoryMix: [],
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    Promise.all([
      fetchArticleCounts(),
      fetchTriageMetrics(),
      fetchIngestedVsHandled(),
      fetchSourceQuality(),
      fetchCategoryMix(),
    ])
      .then(([counts, triage, overTime, sourceQuality, categoryMix]) => {
        if (!cancelled) {
          setState({
            counts,
            triage,
            overTime,
            sourceQuality,
            categoryMix,
            loading: false,
            error: null,
          });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load stats',
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { counts, triage, overTime, sourceQuality, categoryMix, loading, error } = state;

  const categories = useMemo(() => {
    if (!categoryMix.length) return [];
    return Object.keys(categoryMix[0]).filter((k) => k !== 'day');
  }, [categoryMix]);

  const overTimeLabelled = useMemo(
    () =>
      overTime.map((d) => ({
        ...d,
        label: new Date(d.day + 'T00:00:00Z').toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          timeZone: 'UTC',
        }),
      })),
    [overTime]
  );

  const categoryMixLabelled = useMemo(
    () =>
      categoryMix.map((d) => ({
        ...d,
        label: new Date(d.day + 'T00:00:00Z').toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          timeZone: 'UTC',
        }),
      })),
    [categoryMix]
  );

  const dash = loading ? '…' : '—';

  return (
    <div className="p-4 md:p-5 space-y-6 max-w-5xl">
      <section>
        <h2 className="text-[22px] font-semibold tracking-tight">Stats</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Habits, source quality, and ingest volume
        </p>
      </section>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Row 1: status counts */}
      <section className="grid grid-cols-3 md:grid-cols-6 gap-2">
        <SmallStat label="Inbox" value={loading ? dash : (counts?.new ?? 0)} />
        <SmallStat label="Saved" value={loading ? dash : (counts?.saved ?? 0)} />
        <SmallStat label="Read" value={loading ? dash : (counts?.read ?? 0)} accent />
        <SmallStat label="Skipped" value={loading ? dash : (counts?.skipped ?? 0)} />
        <SmallStat label="Archived" value={loading ? dash : (counts?.archived ?? 0)} />
        <SmallStat
          label="Total"
          value={
            loading
              ? dash
              : counts
                ? counts.new + counts.saved + counts.read + counts.skipped + counts.archived
                : 0
          }
        />
      </section>

      {/* Row 2: habit metrics */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <BigStat
          label="Articles this week"
          value={loading ? dash : (triage?.articles_this_week ?? '—')}
        />
        <BigStat label="Handled rate" value={loading ? dash : `${triage?.handled_rate ?? '—'}%`} />
        <BigStat
          label="Avg triage time"
          value={loading ? dash : `${triage?.avg_triage_hours ?? '—'}h`}
          sub={loading ? undefined : `${triage?.save_rate ?? '—'}% save rate`}
        />
      </section>

      {/* Articles over time */}
      <ChartSection title="Articles over time" sub="Last 14 days — ingested vs handled">
        <div className="h-56 -mx-2">
          <ResponsiveContainer>
            <AreaChart data={overTimeLabelled} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 3" stroke={GRID_STROKE} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: AXIS_FILL }}
                interval={1}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fontSize: 10, fill: AXIS_FILL }}
                tickLine={false}
                axisLine={false}
                width={28}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Area
                type="monotone"
                dataKey="ingested"
                stroke={CHART_COLORS[2]}
                fill={CHART_COLORS[2]}
                fillOpacity={0.15}
                strokeWidth={1.5}
              />
              <Area
                type="monotone"
                dataKey="handled"
                stroke={CHART_COLORS[1]}
                fill={CHART_COLORS[1]}
                fillOpacity={0.15}
                strokeWidth={1.5}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </ChartSection>

      {/* Per-source volume */}
      <ChartSection title="Per-source volume" sub="Articles inserted (all time)">
        <div className="h-72 -mx-2 overflow-x-auto">
          <div style={{ minWidth: Math.max(sourceQuality.length * 56, 300) }} className="h-full">
            <ResponsiveContainer>
              <BarChart data={sourceQuality} margin={{ left: 0, right: 8, top: 8, bottom: 48 }}>
                <CartesianGrid strokeDasharray="2 3" stroke={GRID_STROKE} />
                <XAxis
                  dataKey="source_name"
                  tick={{ fontSize: 10, fill: AXIS_FILL }}
                  angle={-35}
                  textAnchor="end"
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: string) =>
                    v
                      .replace(/(GitHub|Cloudflare|Engineering|Releases)/g, '')
                      .trim()
                      .slice(0, 18)
                  }
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 10, fill: AXIS_FILL }}
                  tickLine={false}
                  axisLine={false}
                  width={28}
                />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="total" fill={CHART_COLORS[0]} radius={[3, 3, 0, 0]} name="inserted" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </ChartSection>

      {/* Source quality table */}
      <ChartSection title="Source quality" sub="Lower skip + higher save = better signal">
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm min-w-[480px]">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-subtle border-b border-border">
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium text-right">Inserted</th>
                <th className="px-3 py-2 font-medium text-right">Skip rate</th>
                <th className="px-3 py-2 font-medium text-right">Save rate</th>
                <th className="px-3 py-2 font-medium text-right">Handle rate</th>
                <th className="px-3 py-2 font-medium text-right">Errors</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-center text-muted-foreground text-xs">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && sourceQuality.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-center text-muted-foreground text-xs">
                    No data yet
                  </td>
                </tr>
              )}
              {sourceQuality.map((s) => (
                <tr key={s.source_name} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2">{s.source_name}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{s.total}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {s.skip_rate}%
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-star">{s.save_rate}%</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {s.handle_rate.toFixed(1)}%
                  </td>
                  <td
                    className={`px-3 py-2 text-right tabular-nums ${s.error_rate > 0 ? 'text-err' : 'text-muted-foreground'}`}
                  >
                    {s.error_rate > 0 ? `${s.error_rate}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartSection>

      {/* Category mix over time */}
      {categories.length > 0 && (
        <ChartSection title="Category mix over time" sub="Articles per category, last 14 days">
          <div className="h-56 -mx-2">
            <ResponsiveContainer>
              <LineChart
                data={categoryMixLabelled}
                margin={{ left: 0, right: 8, top: 4, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="2 3" stroke={GRID_STROKE} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10, fill: AXIS_FILL }}
                  interval={1}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 10, fill: AXIS_FILL }}
                  tickLine={false}
                  axisLine={false}
                  width={28}
                />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                {categories.map((cat, i) => (
                  <Line
                    key={cat}
                    type="monotone"
                    dataKey={cat}
                    stroke={CHART_COLORS[i % CHART_COLORS.length]}
                    dot={false}
                    strokeWidth={1.5}
                  />
                ))}
                <Legend wrapperStyle={{ fontSize: 10 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ChartSection>
      )}
    </div>
  );
}

function SmallStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">{label}</div>
      <div className={`text-xl font-semibold mt-1 tabular-nums ${accent ? 'text-star' : ''}`}>
        {value}
      </div>
    </div>
  );
}

function BigStat({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">{label}</div>
      <div className="text-3xl font-semibold mt-1 tabular-nums tracking-tight">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

function ChartSection({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2">
        <div className="text-sm font-semibold">{title}</div>
        {sub && <div className="text-[11px] text-subtle">{sub}</div>}
      </div>
      <div className="rounded-lg border border-border bg-card p-3">{children}</div>
    </section>
  );
}
