import { useLocation, useNavigate, Outlet, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Newspaper,
  Inbox,
  Clock,
  Star,
  Search,
  Sparkles,
  MoreHorizontal,
  Radio,
  BarChart3,
  Archive,
  Settings,
  History,
  LogOut,
} from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { CommandPalette } from './CommandPalette';
import { ShortcutOverlay } from './ShortcutOverlay';
import { cn } from '@/lib/utils';
import { fetchSummary, logoutUser } from '@/api';
import { useAuth } from '@/contexts/auth';

function useNavCounts() {
  const { data } = useQuery({
    queryKey: ['summary'],
    queryFn: fetchSummary,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
  return {
    today: data?.byStatus?.new ?? null,
    starred: data?.byStatus?.saved ?? null,
  };
}

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

// Desktop rail shows all primary + ask; mobile nav shows only the first 5.
const navItems: NavItem[] = [
  { to: '/', label: 'Brief', icon: Newspaper },
  { to: '/today', label: 'Today', icon: Inbox },
  { to: '/later', label: 'Later', icon: Clock },
  { to: '/starred', label: 'Starred', icon: Star },
  { to: '/search', label: 'Search', icon: Search },
  { to: '/ask', label: 'Ask', icon: Sparkles },
];

const mobileNavItems = navItems.slice(0, 5);

const moreItems = [
  { to: '/briefs', label: 'Brief History', icon: History },
  { to: '/feeds', label: 'Feeds', icon: Radio },
  { to: '/stats', label: 'Stats', icon: BarChart3 },
  { to: '/archive', label: 'Archive', icon: Archive },
  { to: '/settings', label: 'Settings', icon: Settings },
];

function isNavActive(to: string, pathname: string): boolean {
  if (to === '/' || to === '/today') return pathname === to;
  return pathname.startsWith(to);
}

function currentTitle(p: string) {
  if (p === '/') return 'Brief';
  if (p === '/today') return 'Today';
  if (p.startsWith('/later')) return 'Later';
  if (p.startsWith('/starred')) return 'Starred';
  if (p.startsWith('/search')) return 'Search';
  if (p.startsWith('/ask')) return 'Ask AI';
  if (p.startsWith('/briefs')) return 'Briefs';
  if (p.startsWith('/feeds')) return 'Feeds';
  if (p.startsWith('/stats')) return 'Stats';
  if (p.startsWith('/archive')) return 'Archive';
  if (p.startsWith('/settings')) return 'Settings';
  return 'Radar';
}

function DesktopRail({ pathname }: { pathname: string }) {
  const counts = useNavCounts();
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const countFor = (to: string): number | null =>
    to === '/today' ? counts.today : to === '/starred' ? counts.starred : null;

  async function handleLogout() {
    await logoutUser();
    setUser(null);
    navigate('/login', { replace: true });
  }

  return (
    <aside className="hidden md:flex md:flex-col md:w-[200px] md:shrink-0 md:border-r md:border-border md:min-h-[calc(100vh-3rem)] md:sticky md:top-12 md:self-start">
      <nav className="flex flex-col p-2 gap-0.5">
        {navItems.map((n) => {
          const Icon = n.icon;
          const active = isNavActive(n.to, pathname);
          const count = countFor(n.to);
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
        {moreItems.map((m) => {
          const Icon = m.icon;
          const active = pathname.startsWith(m.to);
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

  async function handleLogout() {
    await logoutUser();
    setUser(null);
    navigate('/login', { replace: true });
  }

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
          const k = e2.key.toLowerCase();
          if (k === 'b') navigate('/');
          else if (k === 't') navigate('/today');
          else if (k === 'l') navigate('/later');
          else if (k === 's') navigate('/starred');
          else if (k === 'a') navigate('/ask');
          else if (k === 'f') navigate('/feeds');
          else if (k === 'h') navigate('/briefs');
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

  const title = currentTitle(pathname);

  return (
    <div className="app-shell min-h-screen flex flex-col bg-background text-foreground">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto max-w-6xl flex h-12 items-center justify-between px-4">
          <div className="flex items-center gap-2 min-w-0">
            <div className="size-6 rounded-md bg-foreground/90 grid place-items-center text-background text-[10px] font-bold tracking-tight">
              RD
            </div>
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
                  {moreItems.map((m) => {
                    const Icon = m.icon;
                    const active = pathname.startsWith(m.to);
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
          {mobileNavItems.map((n) => {
            const Icon = n.icon;
            const active = isNavActive(n.to, pathname);
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
    </div>
  );
}
