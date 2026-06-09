import {
  Archive,
  BarChart2,
  Bookmark,
  Bot,
  BookOpen,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Rss,
  SkipForward,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '../lib/utils';
import { useSummary } from '../hooks/useSummary';
import { ThemeSwitcher } from './ThemeSwitcher';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const CATEGORIES = [
  'python',
  'ai-llm',
  'agents',
  'cloud-infra',
  'engineering',
  'trending',
  'repositories',
] as const;

function Count({ n }: { n: number | undefined }) {
  if (!n) return null;
  return (
    <span className="ml-auto rounded px-1.5 py-0.5 text-[11px] tabular-nums leading-none text-[var(--muted-foreground)] bg-[var(--muted)]">
      {n > 999 ? '999+' : n}
    </span>
  );
}

function NavItem({
  to,
  icon: Icon,
  label,
  count,
  collapsed,
}: {
  to: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  label: string;
  count?: number;
  collapsed: boolean;
}) {
  return (
    <NavLink
      to={to}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2 rounded-md px-2 py-[5px] text-[13px] transition-colors select-none',
          isActive
            ? 'bg-[var(--sidebar-accent)] text-[var(--foreground)]'
            : 'text-[var(--muted-foreground)] hover:bg-[var(--sidebar-accent)] hover:text-[var(--foreground)]'
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            size={15}
            strokeWidth={isActive ? 2 : 1.75}
            className={isActive ? 'text-[var(--foreground)]' : 'text-[var(--muted-foreground)]'}
          />
          {!collapsed && (
            <>
              <span className={cn('truncate', isActive && 'font-medium')}>{label}</span>
              <Count n={count} />
            </>
          )}
        </>
      )}
    </NavLink>
  );
}

function SectionDivider({ collapsed }: { collapsed: boolean }) {
  if (collapsed) {
    return <div className="my-2 h-px bg-[var(--sidebar-border)]" />;
  }
  return <div className="my-1.5 h-px bg-[var(--sidebar-border)]" />;
}

function SectionLabel({ label }: { label: string }) {
  return (
    <p className="mt-3 mb-0.5 px-2 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted-foreground)] opacity-60">
      {label}
    </p>
  );
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { data: summary } = useSummary();
  const byStatus = summary?.byStatus ?? {};
  const byCategory = summary?.byCategory ?? {};

  return (
    <aside
      className={cn(
        'app-sidebar flex h-full flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)]',
        'transition-[width] duration-200 ease-in-out',
        collapsed ? 'w-12' : 'w-52'
      )}
    >
      {/* Header */}
      <div
        className={cn(
          'flex h-11 shrink-0 items-center border-b border-[var(--sidebar-border)]',
          collapsed ? 'justify-center px-0' : 'justify-between px-3'
        )}
      >
        {!collapsed && (
          <span className="text-[13px] font-semibold tracking-tight text-[var(--foreground)]">
            News Dashboard
          </span>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="flex h-6 w-6 items-center justify-center rounded text-[var(--muted-foreground)] hover:bg-[var(--sidebar-accent)] hover:text-[var(--foreground)] transition-colors"
        >
          {collapsed ? <ChevronRight size={13} /> : <ChevronLeft size={13} />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-1.5 py-2 space-y-0.5" aria-label="Main navigation">
        {!collapsed && <SectionLabel label="Views" />}
        {collapsed && <div className="h-1" />}

        <NavItem to="/inbox" icon={Inbox} label="New" count={byStatus.new} collapsed={collapsed} />
        <NavItem
          to="/saved"
          icon={Bookmark}
          label="Saved"
          count={byStatus.saved}
          collapsed={collapsed}
        />
        <NavItem
          to="/read"
          icon={BookOpen}
          label="Read"
          count={byStatus.read}
          collapsed={collapsed}
        />
        <NavItem
          to="/skipped"
          icon={SkipForward}
          label="Skipped"
          count={byStatus.skipped}
          collapsed={collapsed}
        />
        <NavItem
          to="/archived"
          icon={Archive}
          label="Archived"
          count={byStatus.archived}
          collapsed={collapsed}
        />

        {!collapsed && Object.keys(byCategory).length > 0 && (
          <>
            <SectionDivider collapsed={collapsed} />
            <SectionLabel label="Categories" />
            {CATEGORIES.filter((c) => byCategory[c] !== undefined).map((cat) => (
              <div
                key={cat}
                className="flex items-center gap-2 rounded-md px-2 py-[5px] text-[13px] text-[var(--muted-foreground)]"
              >
                <span className="h-1 w-1 shrink-0 rounded-full bg-[var(--muted-foreground)] opacity-50" />
                <span className="truncate">{cat.replace(/-/g, ' ')}</span>
                <span className="ml-auto text-[11px] tabular-nums opacity-70">
                  {byCategory[cat]}
                </span>
              </div>
            ))}
          </>
        )}

        <SectionDivider collapsed={collapsed} />
        {!collapsed && <SectionLabel label="Tools" />}

        <NavItem to="/sources" icon={Rss} label="Sources" collapsed={collapsed} />
        <NavItem to="/scheduler" icon={CalendarClock} label="Scheduler" collapsed={collapsed} />
        <NavItem to="/stats" icon={BarChart2} label="Stats" collapsed={collapsed} />
        <NavItem to="/ask" icon={Bot} label="Ask AI" collapsed={collapsed} />
      </nav>

      {/* Footer — theme switcher */}
      <div
        className={cn(
          'shrink-0 border-t border-[var(--sidebar-border)] px-2 py-2.5',
          collapsed && 'flex justify-center'
        )}
      >
        {collapsed ? (
          <ThemeSwitcher />
        ) : (
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-[var(--muted-foreground)]">Theme</span>
            <ThemeSwitcher />
          </div>
        )}
      </div>
    </aside>
  );
}
