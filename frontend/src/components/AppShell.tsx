import { useLocation, useNavigate, Outlet, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LogOut, MoreHorizontal, Search } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { AppLogo } from './AppLogo';
import { CommandPalette } from './CommandPalette';
import { ShortcutOverlay } from './ShortcutOverlay';
import { WhatsNewDialog } from './WhatsNewDialog';
import { OnboardingWizard } from './OnboardingWizard';
import { useWhatsNew } from '@/hooks/useWhatsNew';
import { useOnboardingWizard } from '@/hooks/useOnboardingWizard';
import { useElectronBriefNotifier } from '@/hooks/useElectronBriefNotifier';
import { cn } from '@/lib/utils';
import { fetchSummary, fetchSharesUnreadCount, logoutUser } from '@/api';
import { startAnalytics, stopAnalytics, trackRoute } from '@/lib/analytics';
import { useAuth } from '@/contexts/auth';
import {
  getPageTitle,
  getShortcutTarget,
  isNavigationItemActive,
  mobilePrimaryOverflowItems,
  mobileNavigationItems,
  primaryNavigationItems,
  secondaryNavigationItemsFor,
  type NavigationItem,
} from '@/lib/navigation';

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

function DesktopRail({ pathname }: { pathname: string }) {
  const counts = useNavCounts();
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const countFor = (item: NavigationItem): number | null =>
    item.to === '/today'
      ? counts.today
      : item.to === '/starred'
        ? counts.starred
        : item.to === '/shared'
          ? counts.shared
          : null;

  async function handleLogout() {
    await logoutUser();
    setUser(null);
    void navigate('/login', { replace: true });
  }

  return (
    <aside className="hidden md:flex md:flex-col md:w-[200px] md:shrink-0 md:border-r md:border-border md:min-h-[calc(100vh-3rem)] md:sticky md:top-12 md:self-start">
      <nav className="flex flex-col p-2 gap-0.5">
        {primaryNavigationItems.map((n) => {
          const Icon = n.icon;
          const active = isNavigationItemActive(n.to, pathname);
          const count = countFor(n);
          return (
            <Link
              key={n.to}
              to={n.to}
              className={cn(
                'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm',
                active
                  ? 'bg-surface-2 text-foreground font-medium'
                  : 'text-muted-foreground hover:bg-surface hover:text-foreground'
              )}
            >
              <Icon className="size-4" />
              <span className="flex-1">{n.label}</span>
              {count != null && count > 0 && (
                <span className="text-[10px] font-medium tabular-nums text-muted-foreground">
                  {count}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="mx-2 my-2 h-px bg-border" />
      <nav className="flex flex-col p-2 gap-0.5">
        {secondaryNavigationItemsFor(Boolean(user?.is_admin)).map((m) => {
          const Icon = m.icon;
          const active = isNavigationItemActive(m.to, pathname);
          return (
            <Link
              key={m.to}
              to={m.to}
              className={cn(
                'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm',
                active
                  ? 'bg-surface-2 text-foreground font-medium'
                  : 'text-muted-foreground hover:bg-surface hover:text-foreground'
              )}
            >
              <Icon className="size-4" />
              {m.label}
            </Link>
          );
        })}
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
          Log out
        </button>
      </div>
    </aside>
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, setUser } = useAuth();
  const [moreOpen, setMoreOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const whatsNew = useWhatsNew();
  const onboarding = useOnboardingWizard();
  useElectronBriefNotifier((path) => void navigate(path));

  async function handleLogout() {
    await logoutUser();
    setUser(null);
    void navigate('/login', { replace: true });
  }

  useEffect(() => {
    startAnalytics();
    return () => stopAnalytics();
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
        <Outlet />
        <CommandPalette
          open={paletteOpen}
          onOpenChange={setPaletteOpen}
          onShortcuts={() => {
            setPaletteOpen(false);
            setShortcutsOpen(true);
          }}
        />
        <ShortcutOverlay open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
      </>
    );
  }

  const title = getPageTitle(pathname);

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
            <button
              onClick={() => setPaletteOpen(true)}
              className="hidden md:inline-flex items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground hover:border-border-strong transition-colors"
            >
              <Search className="size-3.5" />
              <span>Command</span>
              <kbd className="font-mono text-[10px] text-subtle">⌘K</kbd>
            </button>
            <Sheet open={moreOpen} onOpenChange={setMoreOpen}>
              <SheetTrigger asChild>
                <button
                  className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="More"
                >
                  <MoreHorizontal className="size-5" />
                </button>
              </SheetTrigger>
              <SheetContent side="right" className="w-[280px] p-0">
                <SheetHeader className="px-5 pt-5 pb-3">
                  <SheetTitle className="text-sm">Menu</SheetTitle>
                  {user && (
                    <p className="text-xs text-muted-foreground truncate">{user.username}</p>
                  )}
                </SheetHeader>
                <nav className="p-2">
                  {mobilePrimaryOverflowItems.map((m) => {
                    const Icon = m.icon;
                    const active = isNavigationItemActive(m.to, pathname);
                    return (
                      <Link
                        key={m.to}
                        to={m.to}
                        onClick={() => setMoreOpen(false)}
                        className={cn(
                          'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm',
                          active
                            ? 'bg-surface-2 text-foreground'
                            : 'text-muted-foreground hover:bg-surface hover:text-foreground'
                        )}
                      >
                        <Icon className="size-4" />
                        {m.label}
                      </Link>
                    );
                  })}
                  {mobilePrimaryOverflowItems.length > 0 && (
                    <div className="mx-1 my-1 h-px bg-border" />
                  )}
                  {secondaryNavigationItemsFor(Boolean(user?.is_admin)).map((m) => {
                    const Icon = m.icon;
                    const active = isNavigationItemActive(m.to, pathname);
                    return (
                      <Link
                        key={m.to}
                        to={m.to}
                        onClick={() => setMoreOpen(false)}
                        className={cn(
                          'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm',
                          active
                            ? 'bg-surface-2 text-foreground'
                            : 'text-muted-foreground hover:bg-surface hover:text-foreground'
                        )}
                      >
                        <Icon className="size-4" />
                        {m.label}
                      </Link>
                    );
                  })}
                  <button
                    onClick={() => void handleLogout()}
                    className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm text-muted-foreground hover:bg-surface hover:text-foreground"
                  >
                    <LogOut className="size-4" />
                    Log out
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
            <Outlet />
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
                {n.label}
              </Link>
            );
          })}
        </div>
      </nav>

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
    </div>
  );
}
