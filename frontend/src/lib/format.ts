export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const abs = Math.abs(diff);
  const m = Math.floor(abs / 60000);
  if (m < 1) return diff >= 0 ? 'just now' : 'soon';
  if (m < 60) return diff >= 0 ? `${m}m ago` : `in ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return diff >= 0 ? `${h}h ago` : `in ${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7) return diff >= 0 ? `${d}d ago` : `in ${d}d`;
  const w = Math.floor(d / 7);
  if (w < 5) return diff >= 0 ? `${w}w ago` : `in ${w}w`;
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function signalLabel(s: 'high' | 'mid' | 'low') {
  return s === 'high' ? 'High signal' : s === 'mid' ? 'Maybe' : 'Low signal';
}
