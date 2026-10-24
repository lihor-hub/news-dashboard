import { Link } from 'react-router';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

type NavLinkVariant = 'rail' | 'sheet' | 'tab';

interface NavLinkProps {
  to: string;
  label: string;
  icon: LucideIcon;
  isActive: boolean;
  /** rail: stacked icon + label hub button; sheet: full-width menu row; tab: hub tab-strip segment. */
  variant: NavLinkVariant;
  count?: number | null;
  onClick?: () => void;
}

const focusRing =
  'outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background';

const variantClasses: Record<NavLinkVariant, { base: string; active: string; inactive: string }> = {
  rail: {
    base: 'relative flex min-h-11 w-full flex-col items-center justify-center gap-1 rounded-lg px-1 py-2 text-xs font-medium leading-tight transition-colors motion-reduce:transition-none',
    active: 'bg-surface-2 text-foreground',
    inactive: 'text-muted-foreground hover:bg-surface hover:text-foreground',
  },
  sheet: {
    base: 'flex min-h-11 items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors motion-reduce:transition-none',
    active: 'bg-surface-2 text-foreground font-medium',
    inactive: 'text-muted-foreground hover:bg-surface hover:text-foreground',
  },
  tab: {
    base: 'inline-flex min-h-11 shrink-0 snap-start items-center gap-1.5 whitespace-nowrap rounded-md px-3 text-sm transition-colors motion-reduce:transition-none md:min-h-9',
    active: 'bg-background text-foreground font-medium shadow-xs',
    inactive: 'text-muted-foreground hover:text-foreground',
  },
};

export function NavLink({
  to,
  label,
  icon: Icon,
  isActive,
  variant,
  count,
  onClick,
}: NavLinkProps) {
  const { base, active, inactive } = variantClasses[variant];
  const showCount = count != null && count > 0;
  // A hub button marks the current section; sheet rows and tabs mark the exact page.
  const current = isActive ? (variant === 'rail' ? 'true' : 'page') : undefined;

  return (
    <Link
      to={to}
      onClick={onClick}
      aria-current={current}
      className={cn(base, focusRing, isActive ? active : inactive)}
    >
      <Icon
        className={cn(
          variant === 'rail' ? 'size-5' : 'size-4',
          variant === 'tab' && 'hidden sm:block',
          variant === 'rail' && isActive && 'stroke-[2.25]'
        )}
        aria-hidden="true"
      />
      <span
        className={cn(variant === 'sheet' && 'flex-1', variant === 'rail' && 'max-w-full truncate')}
      >
        {label}
      </span>
      {showCount &&
        (variant === 'rail' ? (
          <span className="absolute top-1 end-1.5 min-w-5 rounded-full border border-border bg-background px-1 text-center text-xs font-medium leading-4 tabular-nums text-foreground">
            {count}
          </span>
        ) : (
          <span className="text-xs font-medium tabular-nums text-muted-foreground">{count}</span>
        ))}
    </Link>
  );
}
