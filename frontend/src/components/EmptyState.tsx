import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface EmptyStateAction {
  label: string;
  /** Route to navigate to. Rendered as a link when set. */
  to?: string;
  onClick?: () => void;
  icon?: LucideIcon;
}

export interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  /** One-line explanation of why the view is empty and what to do next. */
  subtitle?: string;
  /** Replaces the icon tile with a custom illustration. */
  illustration?: ReactNode;
  /** The first action is primary; any others render as secondary buttons. */
  actions?: EmptyStateAction[];
  className?: string;
}

const ACTION_CLASS = 'h-11 min-w-11 gap-2 px-4 text-sm md:h-9';

function ActionButton({ action, primary }: { action: EmptyStateAction; primary: boolean }) {
  const Icon = action.icon;
  const content = (
    <>
      {Icon && <Icon className="size-4" aria-hidden="true" />}
      {action.label}
    </>
  );
  const variant = primary ? 'default' : 'outline';
  if (action.to) {
    return (
      <Button asChild variant={variant} className={ACTION_CLASS}>
        <Link to={action.to} onClick={action.onClick}>
          {content}
        </Link>
      </Button>
    );
  }
  return (
    <Button type="button" variant={variant} className={ACTION_CLASS} onClick={action.onClick}>
      {content}
    </Button>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  subtitle,
  illustration,
  actions = [],
  className,
}: EmptyStateProps) {
  return (
    <section
      aria-label={title}
      className={cn(
        'flex flex-col items-center justify-center px-6 py-16 text-center text-muted-foreground md:py-20',
        className
      )}
    >
      {illustration ?? (
        <div className="mb-4 flex size-16 items-center justify-center rounded-2xl bg-muted">
          <Icon className="size-8 text-subtle" strokeWidth={1.5} aria-hidden="true" />
        </div>
      )}
      <h3 className="text-base font-semibold text-foreground">{title}</h3>
      {subtitle && (
        <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed md:text-sm">{subtitle}</p>
      )}
      {actions.length > 0 && (
        <div className="mt-5 flex w-full max-w-sm flex-col items-stretch gap-2 sm:w-auto sm:max-w-none sm:flex-row sm:flex-wrap sm:justify-center">
          {actions.map((action, index) => (
            <ActionButton key={action.label} action={action} primary={index === 0} />
          ))}
        </div>
      )}
    </section>
  );
}
