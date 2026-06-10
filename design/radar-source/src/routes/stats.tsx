import { createFileRoute } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { CATEGORIES } from "@/lib/types";
import { useMemo } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const Route = createFileRoute("/stats")({
  head: () => ({ meta: [{ title: "Stats — Radar" }] }),
  component: StatsPage,
});

function StatsPage() {
  const articles = useApp((s) => s.articles);
  const sources = useApp((s) => s.sources);

  const counts = useMemo(() => ({
    today: articles.filter((a) => a.state === "today").length,
    later: articles.filter((a) => a.state === "later").length,
    starred: articles.filter((a) => a.starred).length,
    done: articles.filter((a) => a.state === "done").length,
    skipped: articles.filter((a) => a.state === "skipped").length,
    archived: articles.filter((a) => a.state === "archived").length,
  }), [articles]);

  const weekArticles = useMemo(
    () => articles.filter((a) => Date.now() - +new Date(a.publishedAt) < 7 * 86400e3),
    [articles],
  );
  const handled = weekArticles.filter((a) => a.state !== "today").length;
  const handleRate = weekArticles.length ? Math.round((handled / weekArticles.length) * 100) : 0;
  const starRate = weekArticles.length ? Math.round((weekArticles.filter((a) => a.starred).length / weekArticles.length) * 100) : 0;

  const avgTriageHours = useMemo(() => {
    const ts = articles
      .filter((a) => a.done_at || a.skipped_at || a.later_until)
      .map((a) => {
        const end = a.done_at || a.skipped_at || a.later_until!;
        return (+new Date(end) - +new Date(a.ingestedAt)) / 3600e3;
      });
    if (!ts.length) return 0;
    return Math.round((ts.reduce((s, x) => s + x, 0) / ts.length) * 10) / 10;
  }, [articles]);

  const overTime = useMemo(() => {
    const days: { day: string; ingested: number; handled: number }[] = [];
    for (let i = 13; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400e3);
      const key = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      const dayStart = new Date(d).setHours(0, 0, 0, 0);
      const dayEnd = dayStart + 86400e3;
      const ingested = articles.filter((a) => {
        const t = +new Date(a.ingestedAt);
        return t >= dayStart && t < dayEnd;
      }).length;
      const handled = articles.filter((a) => {
        const end = a.done_at || a.skipped_at;
        if (!end) return false;
        const t = +new Date(end);
        return t >= dayStart && t < dayEnd;
      }).length;
      days.push({ day: key, ingested, handled });
    }
    return days;
  }, [articles]);

  const perSource = useMemo(() => {
    return sources
      .map((s) => {
        const arts = articles.filter((a) => a.sourceId === s.id);
        const inserted = arts.length;
        const skipped = arts.filter((a) => a.state === "skipped").length;
        const starred = arts.filter((a) => a.starred).length;
        return {
          name: s.name.replace(/(GitHub|Cloudflare|Engineering|Releases)/g, "").trim().slice(0, 18),
          full: s.name,
          inserted,
          skipped,
          starred,
          skipRate: inserted ? Math.round((skipped / inserted) * 100) : 0,
          starRate: inserted ? Math.round((starred / inserted) * 100) : 0,
          errorRate: s.health === "error" ? 100 : s.health === "stale" ? 30 : 0,
        };
      })
      .sort((a, b) => b.inserted - a.inserted);
  }, [articles, sources]);

  const categoryMix = useMemo(() => {
    return overTime.map((d, i) => {
      const slice: any = { day: d.day };
      CATEGORIES.forEach((c) => {
        // synthetic mix derived from id distribution + day index, deterministic
        slice[c] = articles.filter((a) => a.category === c).length / 14 + (i % 3) * 0.3;
        slice[c] = Math.max(0, Math.round(slice[c]));
      });
      return slice;
    });
  }, [overTime, articles]);

  return (
    <div className="p-4 md:p-5 space-y-6 max-w-5xl">
      <section>
        <h2 className="text-[22px] font-semibold tracking-tight">Stats</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Habits, source quality, and ingest volume</p>
      </section>

      <section className="grid grid-cols-3 md:grid-cols-6 gap-2">
        <Stat label="Today" value={counts.today} />
        <Stat label="Later" value={counts.later} />
        <Stat label="Starred" value={counts.starred} accent />
        <Stat label="Done" value={counts.done} />
        <Stat label="Skipped" value={counts.skipped} />
        <Stat label="Archived" value={counts.archived} />
      </section>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <BigStat label="Articles this week" value={weekArticles.length} />
        <BigStat label="Handled rate" value={`${handleRate}%`} />
        <BigStat label="Avg triage time" value={`${avgTriageHours}h`} sub={`${starRate}% star rate`} />
      </section>

      <Section title="Articles over time" sub="Last 14 days">
        <div className="h-56 -mx-2">
          <ResponsiveContainer>
            <AreaChart data={overTime} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 3" stroke="var(--color-border)" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: "var(--color-subtle)" }} interval={1} />
              <YAxis tick={{ fontSize: 10, fill: "var(--color-subtle)" }} width={28} />
              <Tooltip contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 6, fontSize: 12 }} />
              <Area type="monotone" dataKey="ingested" stroke="var(--color-chart-3)" fill="var(--color-chart-3)" fillOpacity={0.15} strokeWidth={1.5} />
              <Area type="monotone" dataKey="handled" stroke="var(--color-chart-2)" fill="var(--color-chart-2)" fillOpacity={0.15} strokeWidth={1.5} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Section>

      <Section title="Per-source volume" sub="Articles inserted (lifetime, mock)">
        <div className="h-72 -mx-2 overflow-x-auto">
          <div style={{ minWidth: perSource.length * 56 }} className="h-full">
            <ResponsiveContainer>
              <BarChart data={perSource} margin={{ left: 0, right: 8, top: 8, bottom: 40 }}>
                <CartesianGrid strokeDasharray="2 3" stroke="var(--color-border)" />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--color-subtle)" }} angle={-30} textAnchor="end" />
                <YAxis tick={{ fontSize: 10, fill: "var(--color-subtle)" }} width={28} />
                <Tooltip contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 6, fontSize: 12 }} />
                <Bar dataKey="inserted" fill="var(--color-chart-1)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </Section>

      <Section title="Source quality" sub="Lower skip + higher star = better signal">
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-subtle border-b border-border">
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium text-right">Inserted</th>
                <th className="px-3 py-2 font-medium text-right">Skip rate</th>
                <th className="px-3 py-2 font-medium text-right">Star rate</th>
                <th className="px-3 py-2 font-medium text-right">Errors</th>
              </tr>
            </thead>
            <tbody>
              {perSource.map((s) => (
                <tr key={s.full} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2">{s.full}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{s.inserted}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{s.skipRate}%</td>
                  <td className="px-3 py-2 text-right tabular-nums text-star">{s.starRate}%</td>
                  <td className="px-3 py-2 text-right tabular-nums text-err">{s.errorRate}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Category mix over time">
        <div className="h-56 -mx-2">
          <ResponsiveContainer>
            <LineChart data={categoryMix} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 3" stroke="var(--color-border)" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: "var(--color-subtle)" }} interval={1} />
              <YAxis tick={{ fontSize: 10, fill: "var(--color-subtle)" }} width={28} />
              <Tooltip contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 6, fontSize: 12 }} />
              {CATEGORIES.map((c, i) => (
                <Line key={c} type="monotone" dataKey={c} stroke={`var(--color-chart-${(i % 5) + 1})`} dot={false} strokeWidth={1.5} />
              ))}
              <Legend wrapperStyle={{ fontSize: 10 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Section>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">{label}</div>
      <div className={`text-xl font-semibold mt-1 tabular-nums ${accent ? "text-star" : ""}`}>{value}</div>
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
function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
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
