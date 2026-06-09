import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';
import { cn } from '../lib/utils';
import type { Theme } from '../lib/theme';

const OPTIONS: { value: Theme; label: string; Icon: React.ComponentType<{ size?: number }> }[] = [
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'system', label: 'System', Icon: Monitor },
  { value: 'dark', label: 'Dark', Icon: Moon },
];

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();

  return (
    <div
      className="flex items-center gap-0.5 rounded-md bg-[var(--muted)] p-0.5"
      role="group"
      aria-label="Theme"
    >
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => setTheme(value)}
          aria-label={label}
          title={label}
          aria-pressed={theme === value}
          className={cn(
            'flex items-center justify-center rounded p-1.5 transition-colors',
            theme === value
              ? 'bg-[var(--background)] text-[var(--foreground)] shadow-xs'
              : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
          )}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  );
}
