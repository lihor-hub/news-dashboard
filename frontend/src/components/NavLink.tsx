import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface NavLinkProps {
  to: string;
  label: string;
  icon: LucideIcon;
  isActive: boolean;
  variant: 'rail' | 'sheet';
  count?: number | null;
  onClick?: () => void;
}

const variantClasses: Record<NavLinkProps['variant'], { base: string; active: string }> = {
  rail: {
    base: 'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm',
    active: 'bg-surface-2 text-foreground font-medium',
  },
  sheet: {
    base: 'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm',
    active: 'bg-surface-2 text-foreground',
  },
};

const inactiveClasses = 'text-muted-foreground hover:bg-surface hover:text-foreground';

export function NavLink({
  to,
  label,
  icon: Icon,
  isActive,
  variant,
  count,
  onClick,
}: NavLinkProps) {
  const { base, active } = variantClasses[variant];
  return (
    <Link to={to} onClick={onClick} className={cn(base, isActive ? active : inactiveClasses)}>
      <Icon className="size-4" />
      <span className={variant === 'rail' ? 'flex-1' : undefined}>{label}</span>
      {count != null && count > 0 && (
        <span className="text-[10px] font-medium tabular-nums text-muted-foreground">{count}</span>
      )}
    </Link>
  );
}
