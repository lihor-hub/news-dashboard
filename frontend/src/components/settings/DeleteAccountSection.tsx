import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw, Trash2 } from 'lucide-react';
import { useAuth } from '@/contexts/auth';
import { deleteOwnAccount } from '@/api';

type DeleteAccountState = 'idle' | 'confirming' | 'deleting' | 'error';

export function DeleteAccountSection() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<DeleteAccountState>('idle');
  const [confirmation, setConfirmation] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!user) return null;

  const canDelete = confirmation === user.username;

  const handleDelete = async () => {
    if (!canDelete) return;
    setState('deleting');
    setErrorMsg(null);
    try {
      await deleteOwnAccount(confirmation);
      setUser(null);
      void navigate('/login', { replace: true });
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Could not delete account.');
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Danger Zone
      </div>
      <div className="rounded-lg border border-destructive/40 bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Permanently delete your account and all associated data — reading history, starred
          articles, highlights, shares, and preferences. This cannot be undone.
        </p>

        {state === 'idle' && (
          <button
            onClick={() => setState('confirming')}
            className="flex items-center gap-1.5 rounded-md border border-destructive px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors"
          >
            <Trash2 className="size-3" />
            Delete my account
          </button>
        )}

        {(state === 'confirming' || state === 'deleting' || state === 'error') && (
          <div className="space-y-2">
            <label
              className="text-xs font-medium text-foreground"
              htmlFor="delete-account-confirmation"
            >
              Type <span className="font-mono">{user.username}</span> to confirm
            </label>
            <input
              id="delete-account-confirmation"
              type="text"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
              disabled={state === 'deleting'}
              className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              autoComplete="off"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={() => void handleDelete()}
                disabled={!canDelete || state === 'deleting'}
                className="flex items-center gap-1.5 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-60"
              >
                {state === 'deleting' ? (
                  <RefreshCw className="size-3 animate-spin" />
                ) : (
                  <Trash2 className="size-3" />
                )}
                {state === 'deleting' ? 'Deleting…' : 'Permanently delete account'}
              </button>
              <button
                onClick={() => {
                  setState('idle');
                  setConfirmation('');
                  setErrorMsg(null);
                }}
                disabled={state === 'deleting'}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-60"
              >
                Cancel
              </button>
            </div>
            {state === 'error' && (
              <p className="text-xs text-destructive" role="alert">
                {errorMsg ?? 'Could not delete account. Please try again.'}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
