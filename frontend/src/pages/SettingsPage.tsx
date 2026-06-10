import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';
import type { Theme } from '@/lib/theme';

const THEME_OPTS: { v: Theme; label: string; Icon: React.ComponentType<{ className?: string }> }[] =
  [
    { v: 'light', label: 'Light', Icon: Sun },
    { v: 'dark', label: 'Dark', Icon: Moon },
    { v: 'system', label: 'System', Icon: Monitor },
  ];

export function SettingsPage() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="p-4 md:p-5 max-w-2xl space-y-6">
      <div>
        <h2 className="text-[22px] font-semibold tracking-tight">Settings</h2>
      </div>

      <section>
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
          Theme
        </div>
        <div className="grid grid-cols-3 gap-2">
          {THEME_OPTS.map(({ v, label, Icon }) => {
            const active = theme === v;
            return (
              <button
                key={v}
                onClick={() => setTheme(v)}
                className={cn(
                  'flex flex-col items-center gap-1.5 rounded-md border p-3 text-xs font-medium transition-colors',
                  active
                    ? 'border-foreground bg-surface-2'
                    : 'border-border bg-card hover:bg-surface'
                )}
              >
                <Icon className="size-5" />
                {label}
              </button>
            );
          })}
        </div>
      </section>

      <section className="text-xs text-muted-foreground space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">About</div>
        <p>Radar is a private technical news triage tool. State is stored on the server.</p>
        <p>
          Press{' '}
          <kbd className="font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
            ?
          </kbd>{' '}
          anywhere for keyboard shortcuts.
        </p>
      </section>
    </div>
  );
}
