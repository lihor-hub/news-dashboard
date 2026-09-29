import { useEffect, useMemo, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { fetchDatasetStats } from '@/api';
import type { DatasetRange, DatasetStats } from '@/types';
import { Button } from '@/components/ui/button';

const RANGES: Array<{ value: DatasetRange; label: string }> = [
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: '1y', label: '1 year' },
  { value: 'all', label: 'All time' },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)} ${unit}`;
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function DatasetOverview() {
  const [range, setRange] = useState<DatasetRange>('30d');
  const [data, setData] = useState<DatasetStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDatasetStats(range)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : 'Failed to load dataset statistics');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range]);

  const trend = useMemo(
    () =>
      (data?.trend ?? []).map((point) => ({
        ...point,
        label: new Date(`${point.bucket}T00:00:00Z`).toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          timeZone: 'UTC',
        }),
      })),
    [data]
  );

  return (
    <section className="space-y-3" aria-labelledby="dataset-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 id="dataset-heading" className="text-lg font-semibold">
            Dataset
          </h3>
          <p className="text-xs text-muted-foreground">Coverage, growth, and PostgreSQL storage</p>
        </div>
        <div className="flex flex-wrap gap-1" aria-label="Dataset trend range">
          {RANGES.map((option) => (
            <Button
              key={option.value}
              type="button"
              size="sm"
              variant={range === option.value ? 'default' : 'outline'}
              aria-pressed={range === option.value}
              onClick={() => setRange(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {!data && loading && (
        <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
          Loading dataset statistics…
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Metric label="News entries" value={data.summary.article_count.toLocaleString()} />
            <Metric
              label="Coverage"
              value={`${data.summary.coverage_days.toLocaleString()} days`}
            />
            <Metric label="Database" value={formatBytes(data.storage.database_bytes)} />
            <Metric label="Articles total" value={formatBytes(data.storage.article_total_bytes)} />
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.3fr_1fr]">
            <div className="rounded-lg border border-border bg-card p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold">Dataset growth</div>
                  <div className="text-[11px] text-subtle">
                    New entries per {data.trend_granularity}
                  </div>
                </div>
                {loading && <span className="text-xs text-muted-foreground">Refreshing…</span>}
              </div>
              <div className="h-44">
                <ResponsiveContainer>
                  <LineChart data={trend} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      width={28}
                    />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="articles"
                      stroke="var(--color-chart-1)"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-lg border border-border bg-card p-3">
              <div className="text-sm font-semibold">Storage breakdown</div>
              <dl className="mt-2 space-y-1.5 text-sm">
                <StorageRow label="Table data" bytes={data.storage.article_heap_bytes} />
                <StorageRow
                  label="TOAST & auxiliary"
                  bytes={data.storage.article_auxiliary_bytes}
                />
                <StorageRow label="Indexes" bytes={data.storage.article_index_bytes} />
                <StorageRow label="Median entry" bytes={data.storage.median_article_bytes} />
                <StorageRow
                  label="Amortized per entry"
                  bytes={data.storage.amortized_article_bytes}
                />
              </dl>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Space from deleted rows is reused by PostgreSQL
              </p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Median entry estimates row payload; amortized storage includes table, auxiliary, and
                index overhead per article.
              </p>
            </div>
          </div>

          {data.retention_preview.enabled && data.retention_preview.retention_days !== null && (
            <div className="rounded-lg border border-border bg-card p-3 text-sm">
              <div className="font-semibold">
                {data.retention_preview.retention_days}-day retention preview
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {data.retention_preview.eligible_articles.toLocaleString()} eligible ·{' '}
                {data.retention_preview.protected_articles.toLocaleString()} protected ·{' '}
                {formatBytes(data.retention_preview.estimated_payload_bytes)} estimated payload
              </div>
            </div>
          )}

          <div className="text-xs text-muted-foreground">
            {data.summary.article_count === 0 ? (
              'No articles yet'
            ) : (
              <>
                Ingested from {formatDate(data.summary.oldest_discovered_at)} to{' '}
                {formatDate(data.summary.newest_discovered_at)}
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="text-[10px] font-medium uppercase tracking-wider text-subtle">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function StorageRow({ label, bytes }: { label: string; bytes: number }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{formatBytes(bytes)}</dd>
    </div>
  );
}
