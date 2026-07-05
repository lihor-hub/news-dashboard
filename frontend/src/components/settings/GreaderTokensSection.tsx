import { useEffect, useState } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
import { createGreaderToken, fetchGreaderTokens, revokeGreaderToken } from '@/api';
import type { GreaderToken } from '@/types';

type GreaderTokenState = 'idle' | 'loading' | 'creating' | 'error';

export function GreaderTokensSection() {
  const [tokens, setTokens] = useState<GreaderToken[]>([]);
  const [newName, setNewName] = useState('');
  const [mintedToken, setMintedToken] = useState<string | null>(null);
  const [state, setState] = useState<GreaderTokenState>('loading');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await fetchGreaderTokens();
        if (!cancelled) {
          setTokens(data.items);
          setState('idle');
        }
      } catch {
        if (!cancelled) setState('error');
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const create = async () => {
    const name = newName.trim();
    if (!name) return;
    setState('creating');
    try {
      const token = await createGreaderToken(name);
      setTokens((current) => [token, ...current]);
      setMintedToken(token.token ?? null);
      setNewName('');
      setState('idle');
    } catch {
      setState('error');
    }
  };

  const revoke = async (tokenId: number) => {
    setState('creating');
    try {
      const updated = await revokeGreaderToken(tokenId);
      setTokens((current) => current.map((t) => (t.id === tokenId ? updated : t)));
      setState('idle');
    } catch {
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        RSS Client Sync (Google Reader API)
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <p className="text-xs text-muted-foreground">
          Create a token to subscribe with a third-party RSS reader (NetNewsWire, Reeder, Unread,
          ...). Enter your username as the email and this token as the password when adding the
          account.
        </p>

        {mintedToken && (
          <div className="rounded-md border border-border bg-surface p-3 space-y-1">
            <p className="text-xs font-medium text-foreground">
              Copy this token now — it will not be shown again:
            </p>
            <code className="block break-all text-xs text-foreground">{mintedToken}</code>
            <button
              onClick={() => setMintedToken(null)}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Dismiss
            </button>
          </div>
        )}

        <div className="flex gap-2">
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="Token name (e.g. NetNewsWire)"
            aria-label="New RSS sync token name"
            className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            onClick={() => void create()}
            disabled={state === 'creating' || !newName.trim()}
            className="flex shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
          >
            {state === 'creating' ? <RefreshCw className="size-3 animate-spin" /> : null}
            Create token
          </button>
        </div>

        {state === 'error' && (
          <p className="text-xs text-destructive" role="alert">
            Could not update RSS sync tokens.
          </p>
        )}

        <div className="space-y-2">
          {tokens.map((token) => (
            <div
              key={token.id}
              className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface p-3"
            >
              <div className="min-w-0 space-y-1">
                <p className="truncate text-sm text-foreground">{token.name}</p>
                <p className="text-[11px] text-muted-foreground">
                  {token.token_prefix}…{token.revoked_at ? ' · revoked' : ''}
                  {token.last_used_at ? ` · last used ${token.last_used_at}` : ' · never used'}
                </p>
              </div>
              {!token.revoked_at && (
                <button
                  onClick={() => void revoke(token.id)}
                  aria-label="Revoke RSS sync token"
                  className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-card hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </div>
          ))}
          {state !== 'loading' && tokens.length === 0 && (
            <p className="text-xs text-muted-foreground">No RSS sync tokens yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}
