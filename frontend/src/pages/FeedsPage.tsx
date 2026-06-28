import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useAuth } from '@/contexts/auth';

const ALL_TABS = [
  { to: '/feeds', label: 'Sources', exact: true, adminOnly: false },
  { to: '/feeds/schedule', label: 'Schedule', adminOnly: true },
  { to: '/feeds/runs', label: 'Runs', adminOnly: true },
  { to: '/feeds/logs', label: 'Logs', adminOnly: true },
];

export function FeedsPage() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const tabs = ALL_TABS.filter((t) => !t.adminOnly || user?.is_admin);
  return (
    <div>
      <div className="px-4 md:px-5 pt-4">
        <h2 className="text-[22px] font-semibold tracking-tight">Feeds</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Sources, schedule, and ingest history
        </p>
      </div>
      <div className="px-4 md:px-5 mt-3 border-b border-border overflow-x-auto">
        <div className="flex gap-1">
          {tabs.map((t) => {
            const active = t.exact ? pathname === t.to : pathname === t.to;
            return (
              <NavLink
                key={t.to}
                to={t.to}
                className={cn(
                  'px-3 py-2 text-[13px] font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
                  active
                    ? 'border-foreground text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                )}
              >
                {t.label}
              </NavLink>
            );
          })}
        </div>
      </div>
      <Outlet />
    </div>
  );
}
