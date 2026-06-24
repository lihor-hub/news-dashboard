import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchAdminAnalytics } from '../api';
import type { AdminAnalytics } from '../types';

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
const RANGES = [7, 30, 90];
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AdminAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAdminAnalytics(days)
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load analytics');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [days]);

  const s = data?.summary;
  const activeLabelled = useMemo(
    () =>
      (data?.active_over_time ?? []).map((d) => ({
        ...d,
        label: new Date(d.day + 'T00:00:00Z').toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          timeZone: 'UTC',
        }),
      })),
    [data]
  );
  const heatmap = useMemo(() => buildHeatmap(data?.hourly_heatmap ?? []), [data]);

  return (
    <div className="p-4 md:p-5 space-y-6 max-w-5xl">
      <section className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-[22px] font-semibold tracking-tight">User Analytics</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Consumption, engagement, and time spent across all users
          </p>
        </div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setDays(r)}
              className={`rounded-md border px-2.5 py-1 text-xs ${
                days === r
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border bg-card text-muted-foreground'
              }`}
            >
              {r}d
            </button>
          ))}
        </div>
      </section>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <section className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Stat label="DAU" value={fmt(s?.dau, loading)} />
        <Stat label="WAU" value={fmt(s?.wau, loading)} />
        <Stat label="MAU" value={fmt(s?.mau, loading)} accent />
        <Stat
          label="Stickiness"
          value={loading || !s ? '…' : `${Math.round(s.stickiness * 100)}%`}
        />
        <Stat label="Minutes spent" value={fmt(s?.total_minutes, loading)} />
        <Stat label="Sessions" value={fmt(s?.total_sessions, loading)} />
        <Stat label="Avg session" value={loading || !s ? '…' : `${s.avg_session_minutes}m`} />
        <Stat label="Articles read" value={fmt(s?.total_reads, loading)} />
      </section>

      <ChartSection title="Active users & time" sub="Daily active users and minutes spent">
        <div className="h-56 -mx-2">
          <ResponsiveContainer>
            <AreaChart data={activeLabelled} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 3" stroke={GRID_STROKE} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: AXIS_FILL }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                yAxisId="users"
                allowDecimals={false}
                tick={{ fontSize: 10, fill: AXIS_FILL }}
                tickLine={false}
                axisLine={false}
                width={28}
              />
              <YAxis
                yAxisId="minutes"
                orientation="right"
                allowDecimals={false}
                tick={{ fontSize: 10, fill: AXIS_FILL }}
                tickLine={false}
                axisLine={false}
                width={28}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Area
                yAxisId="users"
                type="monotone"
                dataKey="active_users"
                stroke={CHART_COLORS[0]}
                fill={CHART_COLORS[0]}
                fillOpacity={0.15}
                strokeWidth={1.5}
                name="active users"
              />
              <Area
                yAxisId="minutes"
                type="monotone"
                dataKey="minutes"
                stroke={CHART_COLORS[1]}
                fill={CHART_COLORS[1]}
                fillOpacity={0.1}
                strokeWidth={1.5}
                name="minutes"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </ChartSection>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <ChartSection title="Page popularity" sub="Route views in range">
          <SimpleBar data={(data?.route_popularity ?? []).slice(0, 8)} xKey="route" yKey="views" />
        </ChartSection>
        <ChartSection title="Feature usage" sub="Feature events in range">
          <SimpleBar
            data={(data?.feature_usage ?? []).slice(0, 8)}
            xKey="feature"
            yKey="count"
            color={CHART_COLORS[2]}
          />
        </ChartSection>
        <ChartSection title="Top categories read" sub="Completed reads by category">
          <SimpleBar
            data={(data?.category_consumption ?? []).slice(0, 8)}
            xKey="category"
            yKey="reads"
            color={CHART_COLORS[3]}
          />
        </ChartSection>
        <ChartSection title="Top sources read" sub="Completed reads by source">
          <SimpleBar
            data={(data?.source_consumption ?? []).slice(0, 8)}
            xKey="source_name"
            yKey="reads"
            color={CHART_COLORS[4]}
          />
        </ChartSection>
      </div>

      <ChartSection title="Activity heatmap" sub="Events by day of week and hour">
        <div className="overflow-x-auto -mx-1">
          <table className="border-separate border-spacing-[2px]">
            <tbody>
              {heatmap.map((row, dow) => (
                <tr key={dow}>
                  <td className="pr-2 text-[10px] text-subtle text-right">{DOW[dow]}</td>
                  {row.map((value, hour) => (
                    <td key={hour}>
                      <div
                        title={`${DOW[dow]} ${hour}:00 — ${value} events`}
                        className="h-3 w-3 rounded-[2px]"
                        style={{
                          background:
                            value === 0
                              ? 'var(--color-border)'
                              : `color-mix(in srgb, var(--color-chart-1) ${heatIntensity(value, heatmap)}%, transparent)`,
                        }}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartSection>

      <ChartSection title="Per-user engagement" sub="Sorted by time spent">
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-subtle border-b border-border">
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium text-right">Minutes</th>
                <th className="px-3 py-2 font-medium text-right">Reads</th>
                <th className="px-3 py-2 font-medium text-right">Skips</th>
                <th className="px-3 py-2 font-medium text-right">Starred</th>
                <th className="px-3 py-2 font-medium text-right">Briefings</th>
                <th className="px-3 py-2 font-medium text-right">Events</th>
              </tr>
            </thead>
            <tbody>
              {!loading && (data?.users.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-4 text-center text-muted-foreground text-xs">
                    No activity yet
                  </td>
                </tr>
              )}
              {(data?.users ?? []).map((u) => (
                <tr key={u.user_id} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2">{u.username}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-star">{u.minutes}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{u.reads}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {u.skips}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{u.starred}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{u.briefings}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {u.events}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartSection>

      <ChartSection title="Most-read articles" sub="By opens, with average dwell time">
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm min-w-[480px]">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-subtle border-b border-border">
                <th className="px-3 py-2 font-medium">Article</th>
                <th className="px-3 py-2 font-medium text-right">Opens</th>
                <th className="px-3 py-2 font-medium text-right">Avg dwell</th>
              </tr>
            </thead>
            <tbody>
              {!loading && (data?.article_dwell.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-muted-foreground text-xs">
                    No reads tracked yet
                  </td>
                </tr>
              )}
              {(data?.article_dwell ?? []).map((a) => (
                <tr key={a.article_id} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2 truncate max-w-[320px]">{a.title}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{a.opens}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {a.avg_dwell_seconds}s
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartSection>

      {data && (
        <section className="grid grid-cols-3 gap-2">
          <Stat label="Recommended" value={data.recommendation_funnel.recommended} />
          <Stat label="Recs read" value={data.recommendation_funnel.read} accent />
          <Stat label="Recs skipped" value={data.recommendation_funnel.skipped} />
        </section>
      )}
    </div>
  );
}

function fmt(value: number | undefined, loading: boolean): number | string {
  if (loading) return '…';
  return value ?? 0;
}

function buildHeatmap(points: { dow: number; hour: number; events: number }[]): number[][] {
  const grid: number[][] = Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0));
  for (const p of points) {
    if (p.dow >= 0 && p.dow < 7 && p.hour >= 0 && p.hour < 24) {
      grid[p.dow][p.hour] = p.events;
    }
  }
  return grid;
}

function heatIntensity(value: number, grid: number[][]): number {
  const max = Math.max(1, ...grid.flat());
  return Math.round((value / max) * 90) + 10;
}

function Stat({
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

function SimpleBar({
  data,
  xKey,
  yKey,
  color = CHART_COLORS[0],
}: {
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  color?: string;
}) {
  return (
    <div className="h-56 -mx-2">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 40 }}>
          <CartesianGrid strokeDasharray="2 3" stroke={GRID_STROKE} />
          <XAxis
            dataKey={xKey}
            tick={{ fontSize: 10, fill: AXIS_FILL }}
            angle={-30}
            textAnchor="end"
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: string) => String(v).slice(0, 16)}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 10, fill: AXIS_FILL }}
            tickLine={false}
            axisLine={false}
            width={28}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Bar dataKey={yKey} fill={color} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
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
