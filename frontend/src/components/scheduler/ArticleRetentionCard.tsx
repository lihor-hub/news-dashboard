import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { fetchArticleRetention, runArticleRetention, updateArticleRetention } from '@/api';
import type { ArticleRetentionPolicy } from '@/types';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

interface ArticleRetentionCardProps {
  onCleanup: () => Promise<void>;
}

const MAX_RETENTION_DAYS = 36_500;

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

export function ArticleRetentionCard({ onCleanup }: ArticleRetentionCardProps) {
  const [policy, setPolicy] = useState<ArticleRetentionPolicy | null>(null);
  const [mode, setMode] = useState<'forever' | 'custom'>('forever');
  const [days, setDays] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const loadPolicy = useCallback(async () => {
    try {
      const next = await fetchArticleRetention();
      setPolicy(next);
      setMode(next.days === null ? 'forever' : 'custom');
      setDays(next.days === null ? '' : String(next.days));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Failed to load article retention');
    }
  }, []);

  useEffect(() => {
    void loadPolicy();
  }, [loadPolicy]);

  async function handleSave() {
    const parsedDays = mode === 'forever' ? null : Number(days);
    if (
      mode === 'custom' &&
      (parsedDays === null ||
        !Number.isSafeInteger(parsedDays) ||
        parsedDays < 1 ||
        parsedDays > MAX_RETENTION_DAYS)
    ) {
      setError(`Retention days must be a whole number from 1 to ${MAX_RETENTION_DAYS}`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const next = await updateArticleRetention(parsedDays);
      setPolicy(next);
      toast.success(
        parsedDays === null ? 'Articles will be kept forever' : 'Retention policy saved'
      );
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Failed to save retention policy';
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }

  async function handleCleanup() {
    setRunning(true);
    setError(null);
    try {
      const result = await runArticleRetention();
      if (result.status === 'skipped') {
        toast.info(result.message);
      } else {
        toast.success(
          `Deleted ${result.deleted_articles} old article${result.deleted_articles === 1 ? '' : 's'}`
        );
      }
      setConfirmOpen(false);
      await Promise.all([loadPolicy(), onCleanup()]);
      if (result.status === 'skipped') setError(result.message);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Article cleanup failed';
      setError(message);
      toast.error(message);
    } finally {
      setRunning(false);
    }
  }

  const preview = policy?.preview;
  const enabled = policy?.days !== null && policy !== null;

  return (
    <div className="rounded-lg border border-border p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Article retention
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Remove unprotected articles a set number of days after ingestion.
      </p>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="grid gap-1 text-xs text-muted-foreground">
          Retention policy
          <select
            aria-label="Retention policy"
            value={mode}
            onChange={(event) => setMode(event.target.value as 'forever' | 'custom')}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
          >
            <option value="forever">Keep forever</option>
            <option value="custom">Keep for a number of days</option>
          </select>
        </label>
        {mode === 'custom' && (
          <label className="grid gap-1 text-xs text-muted-foreground">
            Retention days
            <Input
              aria-label="Retention days"
              type="number"
              min={1}
              max={MAX_RETENTION_DAYS}
              step={1}
              value={days}
              onChange={(event) => setDays(event.target.value)}
              className="w-36"
            />
          </label>
        )}
        <Button type="button" size="sm" onClick={() => void handleSave()} disabled={saving}>
          {saving ? 'Saving…' : 'Save retention'}
        </Button>
      </div>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>{policy?.schedule ?? '03:30 UTC daily'}</span>
        {preview && (
          <>
            <span>{preview.eligible_articles.toLocaleString()} eligible</span>
            <span>{preview.protected_articles.toLocaleString()} protected</span>
            <span>{formatBytes(preview.estimated_payload_bytes)} estimated payload</span>
          </>
        )}
      </div>

      <div className="mt-3">
        <Button
          type="button"
          variant="destructive"
          size="sm"
          disabled={!enabled || running}
          onClick={() => setConfirmOpen(true)}
        >
          {running ? 'Cleaning up…' : 'Run cleanup now'}
        </Button>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete old articles?</DialogTitle>
            <DialogDescription>
              This will permanently delete {preview?.eligible_articles.toLocaleString() ?? 0}{' '}
              eligible articles. Starred, highlighted, tagged, shared, and briefing-linked articles
              remain protected.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={running}>
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="button"
              variant="destructive"
              disabled={running}
              onClick={() => void handleCleanup()}
            >
              {running ? 'Cleaning up…' : 'Confirm cleanup'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
