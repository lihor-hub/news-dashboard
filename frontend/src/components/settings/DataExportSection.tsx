import { useState } from 'react';
import { RefreshCw, Download, Upload } from 'lucide-react';
import { downloadUserExport, importUserArchive } from '@/api';
import type { ArchiveImportResult } from '@/types';

type ExportState = 'idle' | 'running' | 'done' | 'error';
type ImportState = 'idle' | 'running' | 'done' | 'error';

function formatCounts(counts: { added: number; updated?: number; skipped: number }): string {
  const parts = [`${counts.added} added`];
  if (counts.updated !== undefined) parts.push(`${counts.updated} updated`);
  parts.push(`${counts.skipped} skipped`);
  return parts.join(', ');
}

export function DataExportSection() {
  const [state, setState] = useState<ExportState>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [importState, setImportState] = useState<ImportState>('idle');
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ArchiveImportResult | null>(null);

  const handleExport = async () => {
    setState('running');
    setErrorMsg(null);
    try {
      await downloadUserExport();
      setState('done');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Export failed.');
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Data Export
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Download a personal archive of your reading history, starred articles, workflow state,
          daily briefings, source subscriptions, and preferences (recommendation weights, onboarding
          interests, notification settings) as a JSON file. Cached article body text and secrets are
          not included.
        </p>
        <button
          onClick={() => void handleExport()}
          disabled={state === 'running'}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
        >
          {state === 'running' ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <Download className="size-3" />
          )}
          {state === 'running' ? 'Preparing…' : 'Download archive'}
        </button>

        {state === 'done' && (
          <p className="text-xs text-green-600 dark:text-green-400">Archive downloaded.</p>
        )}
        {state === 'error' && (
          <p className="text-xs text-destructive">
            {errorMsg ?? 'Export failed. Please try again.'}
          </p>
        )}

        <div className="border-t border-border pt-3">
          <p className="text-xs text-muted-foreground mb-2">
            Restore a previously downloaded archive into this account. Existing articles, briefings,
            AI memories, source subscriptions, and preferences are matched and updated rather than
            duplicated.
          </p>
          <button
            onClick={() => document.getElementById('archive-import-input')?.click()}
            disabled={importState === 'running'}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted transition-colors disabled:opacity-60"
          >
            {importState === 'running' ? (
              <RefreshCw className="size-3 animate-spin" />
            ) : (
              <Upload className="size-3" />
            )}
            {importState === 'running' ? 'Restoring…' : 'Restore archive'}
          </button>
          <input
            id="archive-import-input"
            aria-label="Restore archive"
            type="file"
            accept=".json,application/json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const input = e.target;
              setImportState('running');
              setImportError(null);
              setImportResult(null);
              void (async () => {
                try {
                  const result = await importUserArchive(file);
                  setImportResult(result);
                  setImportState('done');
                } catch (err) {
                  setImportError(err instanceof Error ? err.message : 'Import failed.');
                  setImportState('error');
                } finally {
                  input.value = '';
                }
              })();
            }}
          />

          {importState === 'done' && importResult && (
            <ul className="mt-2 text-xs text-green-600 dark:text-green-400 space-y-0.5">
              <li>Articles: {formatCounts(importResult.articles)}</li>
              <li>Briefings: {formatCounts(importResult.briefings)}</li>
              <li>AI memories: {formatCounts(importResult.ai_memories)}</li>
              <li>Source subscriptions: {formatCounts(importResult.source_subscriptions)}</li>
              <li>Preferences: {formatCounts(importResult.preferences)}</li>
            </ul>
          )}
          {importState === 'error' && (
            <p className="mt-2 text-xs text-destructive">
              {importError ?? 'Import failed. Please try again.'}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
