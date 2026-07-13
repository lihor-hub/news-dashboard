// Dynamic `import()` failures (stale/missing chunk after a new deploy) throw
// browser-specific errors that can't be recovered by re-rendering — only a
// full reload re-fetches the current asset manifest.
const CHUNK_ERROR_PATTERN =
  /fetch dynamically imported module|failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed/i;

export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return CHUNK_ERROR_PATTERN.test(error.message);
}
