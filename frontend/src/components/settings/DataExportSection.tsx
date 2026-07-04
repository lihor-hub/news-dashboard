import { useState } from 'react';
import { RefreshCw, Download } from 'lucide-react';
import { downloadUserExport } from '@/api';

type ExportState = 'idle' | 'running' | 'done' | 'error';

export function DataExportSection() {
  const [state, setState] = useState<ExportState>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

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
          interests, notification settings) as a JSON file. Cached article body text is included
          when available; secrets are never included.
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
      </div>
    </section>
  );
}
