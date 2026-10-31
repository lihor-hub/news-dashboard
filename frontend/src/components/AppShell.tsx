import { useLocation, useNavigate, Outlet, Link } from 'react-router';
import { useState, useEffect, lazy, Suspense, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { CircleUser, LogOut, Search, UserRound, WifiOff } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { AppLogo } from './AppLogo';
import { ErrorBoundary } from './ErrorBoundary';
import { ListenQueuePlayer } from './ListenQueuePlayer';
import { DifyChatWidget } from './DifyChatWidget';
import { HubTabs } from './HubTabs';
import { NavLink } from './NavLink';
import { ThemeSwitcher } from './ThemeSwitcher';

import { useElectronBriefNotifier } from '@/hooks/useElectronBriefNotifier';
import { useLogout } from '@/hooks/useLogout';
import { cn } from '@/lib/utils';
import { fetchSummary, fetchSharesUnreadCount, fetchAnalyticsSettings } from '@/api';
import { startAnalytics, stopAnalytics, trackRoute, setAnalyticsAllowed } from '@/lib/analytics';
import { useAuth } from '@/contexts/auth';
import {
  accountNavigationItemsFor,
  getActiveHub,
  getPageTitleKey,
  getShortcutTarget,
  hubItemsFor,
  hubTarget,
  isAccountRoute,
  isNavigationItemActive,
  insightsHub,
  mobileBarHubs,
  navigationHubs,
  type NavigationHub,
} from '@/lib/navigation';

const CommandPalette = lazy(() =>
  import('./CommandPalette').then((m) => ({ default: m.CommandPalette }))
);
const ShortcutOverlay = lazy(() =>
  import('./ShortcutOverlay').then((m) => ({ default: m.ShortcutOverlay }))
);

type RouteCounts = Partial<Record<string, number | null>>;

/** Badge counts keyed by route, shared by the rail and the hub tab strip. */
function useCountsByRoute(): RouteCounts {
  const { data } = useQuery({
    queryKey: ['summary'],
    queryFn: fetchSummary,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
  const { data: sharesUnread } = useQuery({
    queryKey: ['shares-unread'],
    queryFn: fetchSharesUnreadCount,
    staleTime: 30_000,
  });
  return {
    '/today': data?.byStatus?.new ?? null,
    '/starred': data?.byStatus?.saved ?? null,
    '/shared': sharesUnread ?? null,
  };
}

function useOnlineStatus() {
  const [online, setOnline] = useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine
  );
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);
  return online;
}

// Badge shown on a hub button: Read surfaces new arrivals, Library surfaces unread shares.
function hubCount(hub: NavigationHub, counts: RouteCounts) {
  if (hub.id === 'read') return counts['/today'];
  if (hub.id === 'library') return counts['/shared'];
  return null;
}

function UserAvatar({ name, className }: { name: string | undefined; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 font-semibold uppercase text-foreground',
        className
      )}
    >
      {name ? name.charAt(0) : <UserRound className="size-4" />}
    </span>
  );
}

/** Pages behind the avatar / "You" menu: Insights (mobile), account pages, theme, log out. */
function AccountMenuContent({
  pathname,
  includeInsights,
  onNavigate,
}: {
  pathname: string;
  includeInsights: boolean;
  onNavigate: () => void;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const handleLogout = useLogout();
  const isAdmin = Boolean(user?.is_admin);

  return (
    <>
      <SheetHeader className="flex-row items-center gap-3 space-y-0 px-5 pt-5 pb-3 pe-12 text-start">
        <UserAvatar name={user?.username} className="size-10 text-sm" />
        <div className="min-w-0">
          <SheetTitle className="truncate text-sm">{user?.username ?? t('nav.you')}</SheetTitle>
          {user?.email && (
            <SheetDescription className="truncate text-meta">{user.email}</SheetDescription>
          )}
        </div>
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-3">
        {includeInsights && (
          <nav aria-label={t(insightsHub.labelKey)} className="pb-2">
            <div className="px-3 pt-1 pb-1.5 text-xs font-medium uppercase tracking-wider text-subtle">
              {t(insightsHub.labelKey)}
            </div>
            {hubItemsFor(insightsHub, isAdmin).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                label={t(item.labelKey)}
                icon={item.icon}
                isActive={isNavigationItemActive(item.to, pathname)}
                variant="sheet"
                onClick={onNavigate}
              />
            ))}
            <div className="mx-1 mt-2 h-px bg-border" />
          </nav>
        )}
        <nav aria-label={t('shell.account_menu')}>
          {accountNavigationItemsFor(isAdmin).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              label={t(item.labelKey)}
              icon={item.icon}
              isActive={isNavigationItemActive(item.to, pathname)}
              variant="sheet"
              onClick={onNavigate}
            />
          ))}
        </nav>
        <div className="mx-1 my-2 h-px bg-border" />
        <div className="flex min-h-touch items-center justify-between gap-3 px-3">
          <span className="text-sm text-muted-foreground">{t('theme.label')}</span>
          <ThemeSwitcher />
        </div>
        <button
          type="button"
          onClick={() => void handleLogout()}
          className="flex min-h-touch w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm text-muted-foreground hover:bg-surface hover:text-foreground"
        >
          <LogOut className="size-4" aria-hidden="true" />
          {t('shell.log_out')}
        </button>
      </div>
    </>
  );
}

function DesktopRail({ pathname, counts }: { pathname: string; counts: RouteCounts }) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const [accountOpen, setAccountOpen] = useState(false);
  const activeHub = getActiveHub(pathname);
  const accountActive = isAccountRoute(pathname);
  // Sheet sides are physical; open the account drawer from the rail's (start) edge.
  const side = i18n?.dir?.() === 'rtl' ? 'right' : 'left';

  return (
    <aside className="hidden md:sticky md:top-0 md:z-20 md:flex md:h-dvh md:w-[76px] md:shrink-0 md:flex-col md:border-e md:border-border md:bg-background">
      <div className="flex h-12 shrink-0 items-center justify-center">
        <AppLogo className="size-7 rounded-md" />
      </div>
      <nav aria-label={t('shell.main_navigation')} className="flex flex-col gap-1 px-2 pt-2">
        {navigationHubs.map((hub) => (
          <NavLink
            key={hub.id}
            to={hubTarget(hub)}
            label={t(hub.labelKey)}
            icon={hub.icon}
            isActive={activeHub?.id === hub.id}
            count={hubCount(hub, counts)}
            variant="rail"
          />
        ))}
      </nav>
      <div className="mt-auto px-2 pb-3">
        <Sheet open={accountOpen} onOpenChange={setAccountOpen}>
          <SheetTrigger asChild>
            <button
              type="button"
              title={t('shell.account_menu')}
              className={cn(
                'flex min-h-touch w-full flex-col items-center justify-center gap-1 rounded-lg px-1 py-2 text-xs font-medium leading-tight transition-colors motion-reduce:transition-none',
                'outline-none focus-visible:ring-2 focus-visible:ring-ring',
                accountActive
                  ? 'bg-surface-2 text-foreground'
                  : 'text-muted-foreground hover:bg-surface hover:text-foreground'
              )}
            >
              <UserAvatar name={user?.username} className="size-8 text-xs" />
              <span className="max-w-full truncate">{user?.username ?? t('nav.you')}</span>
            </button>
          </SheetTrigger>
          <SheetContent side={side} className="flex w-[300px] flex-col gap-0 p-0">
            <AccountMenuContent
              pathname={pathname}
              includeInsights={false}
              onNavigate={() => setAccountOpen(false)}
            />
          </SheetContent>
        </Sheet>
      </div>
    </aside>
  );
}

function MobileBottomBar({ pathname }: { pathname: string }) {
  const { t } = useTranslation();
  const [youOpen, setYouOpen] = useState(false);
  const activeHub = getActiveHub(pathname);
  const youActive = activeHub?.id === 'insights' || isAccountRoute(pathname);
  const slotClass =
    'flex min-h-touch flex-col items-center justify-center gap-0.5 px-1 pt-1.5 pb-1 text-meta font-medium tracking-tight transition-colors motion-reduce:transition-none outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring';

  return (
    <nav
      aria-label={t('shell.main_navigation')}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/95 ps-[env(safe-area-inset-left)] pe-[env(safe-area-inset-right)] pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      <div className="grid h-mobile-nav grid-cols-5 items-end">
        {mobileBarHubs.map((hub) => {
          const Icon = hub.icon;
          const active = activeHub?.id === hub.id;
          const raised = hub.id === 'ask';
          return (
            <Link
              key={hub.id}
              to={hubTarget(hub)}
              aria-current={active ? 'true' : undefined}
              className={cn(
                slotClass,
                active ? 'text-foreground' : 'text-subtle hover:text-muted-foreground'
              )}
            >
              {raised ? (
                <span
                  className={cn(
                    '-mt-3 flex size-touch items-center justify-center rounded-full bg-accent text-accent-foreground shadow-elevation-2 ring-4 ring-background',
                    active && 'ring-surface-2'
                  )}
                >
                  <Icon className="size-6" aria-hidden="true" />
                </span>
              ) : (
                <Icon className={cn('size-5', active && 'stroke-[2.25]')} aria-hidden="true" />
              )}
              {t(hub.labelKey)}
            </Link>
          );
        })}
        <Sheet open={youOpen} onOpenChange={setYouOpen}>
          <SheetTrigger asChild>
            <button
              type="button"
              data-active={youActive ? 'true' : undefined}
              className={cn(
                slotClass,
                youActive ? 'text-foreground' : 'text-subtle hover:text-muted-foreground'
              )}
            >
              <CircleUser
                className={cn('size-5', youActive && 'stroke-[2.25]')}
                aria-hidden="true"
              />
              {t('nav.you')}
            </button>
          </SheetTrigger>
          <SheetContent side="bottom" className="gap-0 px-0 sm:px-0">
            <AccountMenuContent
              pathname={pathname}
              includeInsights
              onNavigate={() => setYouOpen(false)}
            />
          </SheetContent>
        </Sheet>
      </div>
    </nav>
  );
}

export function AppShell() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const countsByRoute = useCountsByRoute();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const online = useOnlineStatus();
  useElectronBriefNotifier((path) => void navigate(path));

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const settings = await fetchAnalyticsSettings();
        if (!cancelled) setAnalyticsAllowed(settings.enabled && settings.global_enabled);
      } catch {
        // Analytics preference unknown — stay disabled rather than send by default.
        return;
      }
      if (!cancelled) startAnalytics();
    })();
    return () => {
      cancelled = true;
      stopAnalytics();
    };
  }, []);

  useEffect(() => {
    trackRoute(pathname);
  }, [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // ⌘K/Ctrl+K toggles the palette even when an input is focused (e.g. to close it)
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      const target = e.target as HTMLElement;
      if (
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA' ||
        target?.isContentEditable
      )
        return;
      if (e.key === '?') {
        setShortcutsOpen((v) => !v);
      } else if (e.key === 'g') {
        const handler2 = (e2: KeyboardEvent) => {
          const target = getShortcutTarget(e2.key);
          if (target) void navigate(target);
          window.removeEventListener('keydown', handler2);
        };
        window.addEventListener('keydown', handler2, { once: true });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [navigate]);

  const isReader = pathname.startsWith('/a/');
  if (isReader) {
    return (
      <>
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
        <Suspense fallback={null}>
          <CommandPalette
            open={paletteOpen}
            onOpenChange={setPaletteOpen}
            onShortcuts={() => {
              setPaletteOpen(false);
              setShortcutsOpen(true);
            }}
          />
          <ShortcutOverlay open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
        </Suspense>
        {user && <DifyChatWidget key={user.id} />}
      </>
    );
  }

  const title = t(getPageTitleKey(pathname));

  return (
    // --shell-content-max caps the reading column. A desktop list + reading
    // pane ([data-split-pane]) instead gets the full width and a viewport-tall
    // column so each pane scrolls on its own.
    <div
      className="app-shell group/shell flex min-h-dvh bg-background text-foreground lg:has-[[data-split-pane]]:h-dvh lg:has-[[data-split-pane]]:overflow-hidden"
      style={{ '--shell-content-max': '72rem' } as CSSProperties}
    >
      <DesktopRail pathname={pathname} counts={countsByRoute} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur">
          <div className="flex h-12 items-center justify-between gap-2 ps-[max(1rem,env(safe-area-inset-left))] pe-[max(1rem,env(safe-area-inset-right))] md:px-5">
            <div className="flex min-w-0 items-center gap-2">
              <AppLogo className="size-6 rounded-md md:hidden" />
              <h1 className="truncate text-sm font-semibold tracking-tight">{title}</h1>
            </div>
            <div className="flex items-center gap-1">
              {!online && (
                <div className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs font-medium text-muted-foreground">
                  <WifiOff className="size-4" aria-hidden="true" />
                  {t('shell.offline')}
                </div>
              )}
              <button
                type="button"
                onClick={() => setPaletteOpen(true)}
                className="hidden md:inline-flex items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:border-border-strong transition-colors motion-reduce:transition-none"
              >
                <Search className="size-4" aria-hidden="true" />
                <span>{t('shell.command')}</span>
                <kbd className="font-mono text-xs text-subtle">⌘K</kbd>
              </button>
            </div>
          </div>
        </header>

        <main className="flex-1 pb-(--mobile-nav-h) max-md:group-has-[[data-listen-player]]/shell:pb-[calc(var(--mobile-nav-h)+var(--listen-player-h))] md:pb-0 lg:has-[[data-split-pane]]:flex lg:has-[[data-split-pane]]:min-h-0 lg:has-[[data-split-pane]]:flex-col">
          <div className="mx-auto w-full max-w-(--shell-content-max) lg:has-[[data-split-pane]]:flex lg:has-[[data-split-pane]]:min-h-0 lg:has-[[data-split-pane]]:max-w-none lg:has-[[data-split-pane]]:flex-1 lg:has-[[data-split-pane]]:flex-col">
            <HubTabs pathname={pathname} isAdmin={Boolean(user?.is_admin)} counts={countsByRoute} />
            <ErrorBoundary resetKey={pathname} compact>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <MobileBottomBar pathname={pathname} />

      <ErrorBoundary silent resetKey={pathname}>
        <Suspense fallback={null}>
          <CommandPalette
            open={paletteOpen}
            onOpenChange={setPaletteOpen}
            onShortcuts={() => {
              setPaletteOpen(false);
              setShortcutsOpen(true);
            }}
          />
          <ShortcutOverlay open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
        </Suspense>
      </ErrorBoundary>
      <ListenQueuePlayer />
      {user && <DifyChatWidget key={user.id} />}
    </div>
  );
}
