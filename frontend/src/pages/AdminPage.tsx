import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, ShieldAlert, Trash2, UserPlus } from 'lucide-react';
import {
  deleteAdminUser,
  fetchAdminUsers,
  fetchAuthConfig,
  generateAdminUser,
  type GeneratedUser,
} from '@/api';
import { useAuth } from '@/contexts/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      aria-label={`Copy ${label}`}
    >
      {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function CredentialsCard({ user }: { user: GeneratedUser }) {
  return (
    <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-4 space-y-3">
      <div className="text-sm font-medium text-foreground">
        User <span className="font-semibold">{user.username}</span> created
      </div>
      <p className="text-xs text-muted-foreground">
        Copy these credentials now — the password is shown only once and cannot be retrieved later.
        {user.temporary
          ? ' The user will be asked to set a new password the first time they sign in.'
          : ''}
      </p>
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3 rounded-md bg-background px-3 py-2">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-subtle">Username</div>
            <div className="truncate font-mono text-sm text-foreground">{user.username}</div>
          </div>
          <CopyButton value={user.username} label="username" />
        </div>
        <div className="flex items-center justify-between gap-3 rounded-md bg-background px-3 py-2">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-subtle">Password</div>
            <div className="truncate font-mono text-sm text-foreground">{user.password}</div>
          </div>
          <CopyButton value={user.password} label="password" />
        </div>
      </div>
    </div>
  );
}

export function AdminPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [created, setCreated] = useState<GeneratedUser | null>(null);

  const usersQuery = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: fetchAdminUsers,
    enabled: Boolean(user?.is_admin),
  });

  const authConfigQuery = useQuery({
    queryKey: ['auth', 'config'],
    queryFn: fetchAuthConfig,
    enabled: Boolean(user?.is_admin),
  });
  const isKeycloak = authConfigQuery.data?.provider === 'keycloak';

  const createMutation = useMutation({
    mutationFn: (name: string) => generateAdminUser(name, { is_admin: isAdmin }),
    onSuccess: (newUser) => {
      setCreated(newUser);
      setUsername('');
      setIsAdmin(false);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAdminUser(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });

  if (!user?.is_admin) {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center gap-3 text-center">
        <ShieldAlert className="size-8 text-muted-foreground" />
        <h1 className="text-lg font-semibold text-foreground">Admins only</h1>
        <p className="text-sm text-muted-foreground">
          You need an administrator account to manage users.
        </p>
      </div>
    );
  }

  const trimmed = username.trim();

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-4">
      <header>
        <h1 className="text-xl font-semibold text-foreground">User management</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Create a new user account. A secure password is generated automatically and shown once.
        </p>
        {isKeycloak && (
          <p className="mt-2 text-xs text-muted-foreground">
            This deployment uses Keycloak for sign-in, so the account is created in Keycloak with a
            temporary password. Administrator access is managed via the configured Keycloak admin
            usernames, not here.
          </p>
        )}
      </header>

      <section className="space-y-4">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (trimmed) createMutation.mutate(trimmed);
          }}
        >
          <div className="space-y-1">
            <label htmlFor="new-username" className="text-sm font-medium text-foreground">
              Username
            </label>
            <Input
              id="new-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. maria"
              autoComplete="off"
            />
          </div>
          {!isKeycloak && (
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={isAdmin}
                onChange={(e) => setIsAdmin(e.target.checked)}
                className="size-4 rounded border-input"
              />
              Grant administrator access
            </label>
          )}
          <Button type="submit" disabled={!trimmed || createMutation.isPending}>
            <UserPlus className="size-4" />
            {createMutation.isPending ? 'Creating…' : 'Create user'}
          </Button>
          {createMutation.isError && (
            <p className="text-sm text-destructive">
              Could not create user: {createMutation.error.message}
            </p>
          )}
        </form>

        {created && <CredentialsCard user={created} />}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-foreground">Existing users</h2>
        {isKeycloak && (
          <p className="text-xs text-muted-foreground">
            Shows app users who have signed in at least once. Newly created Keycloak users appear
            here after their first login. Manage Keycloak accounts in the Keycloak admin console.
          </p>
        )}
        {usersQuery.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {usersQuery.data && (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {usersQuery.data.map((u) => (
              <li key={u.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm text-foreground">{u.username}</span>
                    {u.is_admin && (
                      <span className="rounded bg-secondary px-1.5 py-0.5 text-xs uppercase tracking-wider text-secondary-foreground">
                        Admin
                      </span>
                    )}
                  </div>
                  {u.email && (
                    <div className="truncate text-xs text-muted-foreground">{u.email}</div>
                  )}
                </div>
                {!isKeycloak && u.id !== user.id && (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete ${u.username}`}
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (window.confirm(`Delete user "${u.username}"? This cannot be undone.`)) {
                        deleteMutation.mutate(u.id);
                      }
                    }}
                  >
                    <Trash2 className="size-4 text-destructive" />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
