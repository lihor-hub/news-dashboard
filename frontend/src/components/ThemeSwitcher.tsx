import { useTranslation } from 'react-i18next';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';
import { cn } from '../lib/utils';
import type { Theme } from '../lib/theme';

const OPTIONS: { value: Theme; labelKey: string; Icon: React.ComponentType<{ size?: number }> }[] =
  [
    { value: 'light', labelKey: 'theme.options.light', Icon: Sun },
    { value: 'system', labelKey: 'theme.options.system', Icon: Monitor },
    { value: 'dark', labelKey: 'theme.options.dark', Icon: Moon },
  ];

export function ThemeSwitcher() {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();

  return (
    <div
      className="flex items-center gap-0.5 rounded-md bg-[var(--muted)] p-0.5"
      role="group"
      aria-label={t('theme.label')}
    >
      {OPTIONS.map(({ value, labelKey, Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => setTheme(value)}
          aria-label={t(labelKey)}
          title={t(labelKey)}
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
