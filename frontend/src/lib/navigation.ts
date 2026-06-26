import {
  Activity,
  Archive,
  BarChart3,
  Clock,
  History,
  Inbox,
  Newspaper,
  Radio,
  Search,
  Send,
  Settings,
  Sparkles,
  Star,
  Users,
  type LucideIcon,
} from 'lucide-react';

export interface NavigationItem {
  to: string;
  label: string;
  icon: LucideIcon;
  commandLabel?: string;
  shortcut?: string;
}

export const primaryNavigationItems: NavigationItem[] = [
  { to: '/', label: 'Brief', icon: Newspaper, shortcut: 'b' },
  { to: '/today', label: 'Today', icon: Inbox, shortcut: 't' },
  { to: '/later', label: 'Later', icon: Clock, shortcut: 'l' },
  { to: '/starred', label: 'Starred', icon: Star, shortcut: 's' },
  { to: '/shared', label: 'Shared', icon: Send },
  { to: '/search', label: 'Search', icon: Search },
  { to: '/ask', label: 'Ask', commandLabel: 'Ask AI', icon: Sparkles, shortcut: 'a' },
];

export const secondaryNavigationItems: NavigationItem[] = [
  { to: '/briefs', label: 'Briefing History', icon: History, shortcut: 'h' },
  { to: '/feeds', label: 'Feeds', icon: Radio, shortcut: 'f' },
  { to: '/stats', label: 'Stats', icon: BarChart3 },
  { to: '/archive', label: 'Archive', icon: Archive },
  { to: '/settings', label: 'Settings', icon: Settings },
];

// Shown in the secondary nav only for admin users.
export const adminNavigationItems: NavigationItem[] = [
  { to: '/analytics', label: 'Analytics', icon: Activity },
  { to: '/admin', label: 'Users', icon: Users },
];

export function secondaryNavigationItemsFor(isAdmin: boolean): NavigationItem[] {
  return isAdmin
    ? [...secondaryNavigationItems, ...adminNavigationItems]
    : secondaryNavigationItems;
}

// The mobile bottom bar is a fixed 5-column grid. Keep the five most-used
// destinations here explicitly so adding desktop-only items (e.g. Shared) does
// not silently push one off the bar.
export const mobileNavigationItems = primaryNavigationItems.filter((item) =>
  ['/', '/today', '/later', '/starred', '/search'].includes(item.to)
);

export const commandNavigationItems = [...primaryNavigationItems, ...secondaryNavigationItems].map(
  (item) => ({
    ...item,
    label: item.commandLabel ?? item.label,
  })
);

export const navigationShortcutRows: [string, string][] = [
  ['j / k', 'Move down / up in list'],
  ['Enter', 'Open selected article'],
  ['g b / g t', 'Go to Brief / Today'],
  ['g l / g s', 'Go to Later / Starred'],
  ['g a / g f', 'Go to Ask / Feeds'],
  ['g h', 'Go to Briefing History'],
];

const shortcutTargets = new Map(
  [...primaryNavigationItems, ...secondaryNavigationItems]
    .filter((item) => item.shortcut)
    .map((item) => [item.shortcut!, item.to])
);

export function getShortcutTarget(key: string): string | null {
  return shortcutTargets.get(key.toLowerCase()) ?? null;
}

export function isNavigationItemActive(to: string, pathname: string): boolean {
  if (to === '/' || to === '/today') return pathname === to;
  return pathname.startsWith(to);
}

export function getPageTitle(pathname: string): string {
  if (pathname === '/') return 'Brief';
  if (pathname === '/today') return 'Today';
  if (pathname.startsWith('/later')) return 'Later';
  if (pathname.startsWith('/starred')) return 'Starred';
  if (pathname.startsWith('/shared')) return 'Shared';
  if (pathname.startsWith('/search')) return 'Search';
  if (pathname.startsWith('/ask')) return 'Ask AI';
  if (pathname.startsWith('/briefs')) return 'Briefs';
  if (pathname.startsWith('/feeds')) return 'Feeds';
  if (pathname.startsWith('/stats')) return 'Stats';
  if (pathname.startsWith('/archive')) return 'Archive';
  if (pathname.startsWith('/settings')) return 'Settings';
  if (pathname.startsWith('/analytics')) return 'Analytics';
  if (pathname.startsWith('/admin')) return 'Users';
  return 'Radar';
}
