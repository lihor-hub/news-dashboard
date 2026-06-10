import { useSearchParams } from 'react-router-dom';
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
  const [searchParams, setSearchParams] = useSearchParams();
  const active = searchParams.get('category') ?? '';

  function select(value: string) {
    setSearchParams(value ? { category: value } : {}, { replace: true });
  }

  return (
    <div className="flex gap-1.5 px-4 md:px-5 pb-2 overflow-x-auto scrollbar-none">
      {CATEGORIES.map((c) => (
        <button
          key={c.value}
          onClick={() => select(c.value)}
          className={cn(
            'shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors',
            active === c.value
              ? 'bg-foreground text-background'
              : 'bg-surface-2 text-muted-foreground hover:text-foreground'
          )}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}
