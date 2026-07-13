import { useLocation, useNavigate, Outlet, Link } from 'react-router-dom';
import { useState, useEffect, lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { LogOut, MoreHorizontal, Search, WifiOff } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { AppLogo } from './AppLogo';
import { ErrorBoundary } from './ErrorBoundary';
import { ListenQueuePlayer } from './ListenQueuePlayer';
import { NavLink } from './NavLink';
import { useWhatsNew } from '@/hooks/useWhatsNew';
import { useOnboardingWizard } from '@/hooks/useOnboardingWizard';
import { useElectronBriefNotifier } from '@/hooks/useElectronBriefNotifier';
import { useLogout } from '@/hooks/useLogout';
import { cn } from '@/lib/utils';
import { fetchSummary, fetchSharesUnreadCount, fetchAnalyticsSettings } from '@/api';
import { startAnalytics, stopAnalytics, trackRoute, setAnalyticsAllowed } from '@/lib/analytics';
import { useAuth } from '@/contexts/auth';
import {
  getPageTitleKey,
  getShortcutTarget,
  isNavigationItemActive,
  mobilePrimaryOverflowItems,
  mobileNavigationItems,
  primaryNavigationItems,
  secondaryNavigationItemsFor,
  type NavigationItem,
} from '@/lib/navigation';

const CommandPalette = lazy(() =>
  import('./CommandPalette').then((m) => ({ default: m.CommandPalette }))
);
const ShortcutOverlay = lazy(() =>
  import('./ShortcutOverlay').then((m) => ({ default: m.ShortcutOverlay }))
);
const WhatsNewDialog = lazy(() =>
  import('./WhatsNewDialog').then((m) => ({ default: m.WhatsNewDialog }))
);
const OnboardingWizard = lazy(() =>
  import('./OnboardingWizard').then((m) => ({ default: m.OnboardingWizard }))
);

function useNavCounts() {
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
    today: data?.byStatus?.new ?? null,
    starred: data?.byStatus?.saved ?? null,
    shared: sharesUnread ?? null,
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

function DesktopRail({ pathname }: { pathname: string }) {
  const { t } = useTranslation();
  const counts = useNavCounts();
  const { user } = useAuth();
  const handleLogout = useLogout();
  const countFor = (item: NavigationItem): number | null =>
    item.to === '/today'
      ? counts.today
      : item.to === '/starred'
        ? counts.starred
        : item.to === '/shared'
          ? counts.shared
          : null;

  return (
    <aside className="hidden md:flex md:flex-col md:w-[200px] md:shrink-0 md:border-r md:border-border md:min-h-[calc(100vh-3rem)] md:sticky md:top-12 md:self-start">
      <nav className="flex flex-col p-2 gap-0.5">
        {primaryNavigationItems.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            label={t(n.labelKey)}
            icon={n.icon}
            isActive={isNavigationItemActive(n.to, pathname)}
            count={countFor(n)}
            variant="rail"
          />
        ))}
      </nav>
      <div className="mx-2 my-2 h-px bg-border" />
      <nav className="flex flex-col p-2 gap-0.5">
        {secondaryNavigationItemsFor(Boolean(user?.is_admin)).map((m) => (
          <NavLink
            key={m.to}
            to={m.to}
            label={t(m.labelKey)}
            icon={m.icon}
            isActive={isNavigationItemActive(m.to, pathname)}
            variant="rail"
          />
        ))}
      </nav>
      <div className="mt-auto mx-2 mb-2 pt-2 border-t border-border">
        {user && (
          <div className="px-2.5 py-1 text-[11px] text-subtle truncate">{user.username}</div>
        )}
        <button
          onClick={() => void handleLogout()}
          className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-surface hover:text-foreground"
        >
          <LogOut className="size-4" />
          {t('shell.log_out')}
        </button>
      </div>
    </aside>
  );
}

export function AppShell() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const handleLogout = useLogout();
  const [moreOpen, setMoreOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const whatsNew = useWhatsNew();
  const onboarding = useOnboardingWizard();
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
      </>
    );
  }

  const title = t(getPageTitleKey(pathname));

  return (
    <div className="app-shell min-h-screen flex flex-col bg-background text-foreground">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto max-w-6xl flex h-12 items-center justify-between px-4">
          <div className="flex items-center gap-2 min-w-0">
            <AppLogo className="size-6 rounded-md" />
            <h1 className="text-[13px] font-semibold tracking-tight truncate">{title}</h1>
          </div>
          <div className="flex items-center gap-1">
            {!online && (
              <div className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs font-medium text-muted-foreground">
                <WifiOff className="size-3.5" />
                {t('shell.offline')}
              </div>
            )}
            <button
              onClick={() => setPaletteOpen(true)}
              className="hidden md:inline-flex items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground hover:border-border-strong transition-colors"
            >
              <Search className="size-3.5" />
              <span>{t('shell.command')}</span>
              <kbd className="font-mono text-[10px] text-subtle">⌘K</kbd>
            </button>
            <Sheet open={moreOpen} onOpenChange={setMoreOpen}>
              <SheetTrigger asChild>
                <button
                  className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label={t('shell.more')}
                >
                  <MoreHorizontal className="size-5" />
                </button>
              </SheetTrigger>
              <SheetContent side="right" className="w-[280px] p-0">
                <SheetHeader className="px-5 pt-5 pb-3">
                  <SheetTitle className="text-sm">{t('shell.menu')}</SheetTitle>
                  {user && (
                    <p className="text-xs text-muted-foreground truncate">{user.username}</p>
                  )}
                </SheetHeader>
                <nav className="p-2">
                  {mobilePrimaryOverflowItems.map((m) => (
                    <NavLink
                      key={m.to}
                      to={m.to}
                      label={t(m.labelKey)}
                      icon={m.icon}
                      isActive={isNavigationItemActive(m.to, pathname)}
                      variant="sheet"
                      onClick={() => setMoreOpen(false)}
                    />
                  ))}
                  {mobilePrimaryOverflowItems.length > 0 && (
                    <div className="mx-1 my-1 h-px bg-border" />
                  )}
                  {secondaryNavigationItemsFor(Boolean(user?.is_admin)).map((m) => (
                    <NavLink
                      key={m.to}
                      to={m.to}
                      label={t(m.labelKey)}
                      icon={m.icon}
                      isActive={isNavigationItemActive(m.to, pathname)}
                      variant="sheet"
                      onClick={() => setMoreOpen(false)}
                    />
                  ))}
                  <button
                    onClick={() => void handleLogout()}
                    className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm text-muted-foreground hover:bg-surface hover:text-foreground"
                  >
                    <LogOut className="size-4" />
                    {t('shell.log_out')}
                  </button>
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      {/* Main content + desktop rail */}
      <main className="flex-1 pb-[68px] md:pb-0">
        <div className="md:flex md:max-w-6xl md:mx-auto md:gap-0">
          <DesktopRail pathname={pathname} />
          <div className="flex-1 min-w-0">
            <ErrorBoundary resetKey={pathname} compact>
              <Outlet />
            </ErrorBoundary>
          </div>
        </div>
      </main>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 border-t border-border bg-background/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
        <div className="grid grid-cols-5">
          {mobileNavigationItems.map((n) => {
            const Icon = n.icon;
            const active = isNavigationItemActive(n.to, pathname);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={cn(
                  'flex flex-col items-center justify-center gap-0.5 py-2.5 text-[10px] font-medium tracking-tight transition-colors',
                  active ? 'text-foreground' : 'text-subtle hover:text-muted-foreground'
                )}
              >
                <Icon className={cn('size-5', active && 'stroke-[2.25]')} />
                {t(n.labelKey)}
              </Link>
            );
          })}
        </div>
      </nav>

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
          <WhatsNewDialog state={whatsNew} />
          <OnboardingWizard open={onboarding.open} onClose={onboarding.skip} />
        </Suspense>
      </ErrorBoundary>
      <ListenQueuePlayer />
    </div>
  );
}
