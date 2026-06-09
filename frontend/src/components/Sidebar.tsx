import {
  Archive,
  BookOpen,
  Bot,
  BarChart2,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Bookmark,
  SkipForward,
  Rss,
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

function NavCount({ n }: { n: number | undefined }) {
  if (n === undefined || n === 0) return null;
  return (
    <span className="ml-auto min-w-[1.25rem] rounded-full bg-[var(--primary)] px-1 text-center text-[10px] font-medium leading-5 text-[var(--primary-foreground)]">
      {n > 999 ? '999+' : n}
    </span>
  );
}

function SidebarLink({
  to,
  icon: Icon,
  label,
  count,
  collapsed,
}: {
  to: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
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
          'group flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors',
          'text-[var(--sidebar-foreground)] hover:bg-[var(--sidebar-accent)]',
          isActive && 'bg-[var(--sidebar-accent)] font-medium'
        )
      }
    >
      <Icon size={16} strokeWidth={1.75} />
      {!collapsed && (
        <>
          <span className="truncate">{label}</span>
          <NavCount n={count} />
        </>
      )}
    </NavLink>
  );
}

function SectionLabel({ children, collapsed }: { children: React.ReactNode; collapsed: boolean }) {
  if (collapsed) return <div className="my-1 h-px bg-[var(--sidebar-border)]" />;
  return (
    <p className="mt-4 mb-1 px-2 text-[11px] font-semibold tracking-wider text-[var(--muted-foreground)] uppercase">
      {children}
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
        'flex h-full flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] transition-all duration-200',
        collapsed ? 'w-12' : 'w-56'
      )}
    >
      {/* Logo row */}
      <div
        className={cn(
          'flex h-12 shrink-0 items-center border-b border-[var(--sidebar-border)] px-3',
          collapsed ? 'justify-center' : 'justify-between'
        )}
      >
        {!collapsed && (
          <span className="text-sm font-semibold tracking-tight text-[var(--foreground)]">
            News Dashboard
          </span>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="flex h-6 w-6 items-center justify-center rounded text-[var(--muted-foreground)] hover:bg-[var(--sidebar-accent)] hover:text-[var(--foreground)]"
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Main navigation">
        <SectionLabel collapsed={collapsed}>Views</SectionLabel>

        <SidebarLink
          to="/inbox"
          icon={Inbox}
          label="New"
          count={byStatus.new}
          collapsed={collapsed}
        />
        <SidebarLink
          to="/saved"
          icon={Bookmark}
          label="Saved"
          count={byStatus.saved}
          collapsed={collapsed}
        />
        <SidebarLink
          to="/read"
          icon={BookOpen}
          label="Read"
          count={byStatus.read}
          collapsed={collapsed}
        />
        <SidebarLink
          to="/skipped"
          icon={SkipForward}
          label="Skipped"
          count={byStatus.skipped}
          collapsed={collapsed}
        />
        <SidebarLink
          to="/archived"
          icon={Archive}
          label="Archived"
          count={byStatus.archived}
          collapsed={collapsed}
        />

        {!collapsed && Object.keys(byCategory).length > 0 && (
          <>
            <SectionLabel collapsed={collapsed}>Categories</SectionLabel>
            {CATEGORIES.filter((c) => byCategory[c] !== undefined).map((cat) => (
              <div
                key={cat}
                className="flex items-center gap-2.5 rounded-md px-2 py-1 text-sm text-[var(--muted-foreground)]"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--muted-foreground)]" />
                <span className="truncate">{cat.replace(/-/g, ' ')}</span>
                <span className="ml-auto text-xs">{byCategory[cat]}</span>
              </div>
            ))}
          </>
        )}

        <SectionLabel collapsed={collapsed}>Tools</SectionLabel>

        <SidebarLink to="/sources" icon={Rss} label="Sources" collapsed={collapsed} />
        <SidebarLink to="/scheduler" icon={CalendarClock} label="Scheduler" collapsed={collapsed} />
        <SidebarLink to="/stats" icon={BarChart2} label="Stats" collapsed={collapsed} />
        <SidebarLink to="/ask" icon={Bot} label="Ask AI" collapsed={collapsed} />
      </nav>

      {/* Footer */}
      <div
        className={cn(
          'shrink-0 border-t border-[var(--sidebar-border)] px-2 py-3',
          collapsed ? 'flex justify-center' : ''
        )}
      >
        {collapsed ? (
          <ThemeSwitcher />
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--muted-foreground)]">Theme</span>
            <ThemeSwitcher />
          </div>
        )}
      </div>
    </aside>
  );
}
