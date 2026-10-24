import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';
import { cn } from '@/lib/utils';

const CATEGORIES = [
  { value: '', label: 'All' },
  { value: 'python', label: 'Python' },
  { value: 'ai-llm', label: 'AI/LLM' },
  { value: 'agents', label: 'Agents' },
  { value: 'cloud-infra', label: 'Cloud/Infra' },
  { value: 'engineering', label: 'Engineering' },
  { value: 'trending', label: 'Trending' },
  { value: 'repositories', label: 'Repos' },
];

export function CategoryFilter() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const active = searchParams.get('category') ?? '';

  function select(value: string) {
    setSearchParams(value ? { category: value } : {}, { replace: true });
  }

  return (
    // Sticks just below the app shell's h-12 sticky header while the list scrolls.
    <div
      role="group"
      aria-label={t('articleList.filterByCategory')}
      className="sticky top-12 z-20 border-b border-border bg-background/90 backdrop-blur"
    >
      <div className="flex gap-2 overflow-x-auto overscroll-x-contain scroll-px-4 snap-x px-4 py-2 scrollbar-none md:px-5">
        {CATEGORIES.map((c) => (
          <button
            key={c.value}
            type="button"
            aria-pressed={active === c.value}
            onClick={() => select(c.value)}
            className={cn(
              'inline-flex min-h-11 shrink-0 snap-start items-center rounded-full border px-4 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring md:min-h-8 md:px-3 md:text-xs',
              active === c.value
                ? 'border-foreground bg-foreground text-background'
                : 'border-border bg-surface text-muted-foreground hover:bg-surface-2 hover:text-foreground'
            )}
          >
            {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}
