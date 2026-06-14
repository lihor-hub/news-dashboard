export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export function formatWindow(sinceAt: string, untilAt: string): string {
  const since = new Date(sinceAt);
  const until = new Date(untilAt);
  const sameDay = since.toDateString() === until.toDateString();
  if (sameDay) {
    return since.toLocaleDateString(undefined, { dateStyle: 'medium' });
  }
  return `${since.toLocaleDateString(undefined, { dateStyle: 'medium' })} – ${until.toLocaleDateString(undefined, { dateStyle: 'medium' })}`;
}
