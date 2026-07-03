/** Extract the first http(s) URL from OS share-sheet `url`/`text` fields. */
export function extractSharedUrl(url: string | null, text: string | null): string | null {
  const candidates = [url, text].filter((v): v is string => Boolean(v?.trim()));
  for (const candidate of candidates) {
    const match = /https?:\/\/\S+/.exec(candidate);
    if (match) return match[0];
    try {
      const parsed = new URL(candidate.trim());
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') return parsed.toString();
    } catch {
      // not a bare URL, keep looking
    }
  }
  return null;
}
