import {
  Activity,
  Archive,
  BarChart3,
  Bookmark,
  Download,
  GraduationCap,
  BrainCircuit,
  Clock,
  Flame,
  History,
  Inbox,
  Network,
  Newspaper,
  Radio,
  Search,
  Send,
  Settings,
  Sparkles,
  Star,
  SlidersHorizontal,
  Tag,
  Users,
  type LucideIcon,
} from 'lucide-react';

export interface NavigationItem {
  to: string;
  label: string;
  /** i18next key for the translated label, used by shell surfaces (rail, mobile nav, sheet menu). */
  labelKey: string;
  icon: LucideIcon;
  commandLabel?: string;
  shortcut?: string;
  adminOnly?: boolean;
}

export const primaryNavigationItems: NavigationItem[] = [
  { to: '/', label: 'Brief', labelKey: 'nav.brief', icon: Newspaper, shortcut: 'b' },
  { to: '/today', label: 'Today', labelKey: 'nav.today', icon: Inbox, shortcut: 't' },
  { to: '/later', label: 'Later', labelKey: 'nav.later', icon: Clock, shortcut: 'l' },
  { to: '/starred', label: 'Starred', labelKey: 'nav.starred', icon: Star, shortcut: 's' },
  { to: '/shared', label: 'Shared', labelKey: 'nav.shared', icon: Send },
  { to: '/search', label: 'Search', labelKey: 'nav.search', icon: Search },
  {
    to: '/ask',
    label: 'Ask',
    labelKey: 'nav.ask',
    commandLabel: 'Ask AI',
    icon: Sparkles,
    shortcut: 'a',
  },
];

export const secondaryNavigationItems: NavigationItem[] = [
  {
    to: '/reading-list',
    label: 'Reading List',
    labelKey: 'nav.reading_list',
    icon: Bookmark,
    shortcut: 'r',
  },
  {
    to: '/learn',
    label: 'Learn',
    labelKey: 'nav.learn',
    icon: GraduationCap,
  },
  {
    to: '/offline-saved',
    label: 'Offline Saved',
    labelKey: 'nav.offline_saved',
    icon: Download,
    shortcut: 'o',
  },
  {
    to: '/briefs',
    label: 'Briefing History',
    labelKey: 'nav.briefing_history',
    icon: History,
    shortcut: 'h',
  },
  { to: '/topic-map', label: 'Topic Map', labelKey: 'nav.topic_map', icon: Network },
  { to: '/ai-stats', label: 'AI Stats', labelKey: 'nav.ai_stats', icon: BrainCircuit },
  { to: '/feeds', label: 'Feeds', labelKey: 'nav.feeds', icon: Radio, shortcut: 'f' },
  {
    to: '/reading-dna',
    label: 'Reading DNA',
    labelKey: 'nav.reading_dna',
    icon: SlidersHorizontal,
  },
  { to: '/recap', label: 'Weekly Recap', labelKey: 'nav.weekly_recap', icon: Flame },
  { to: '/archive', label: 'Archive', labelKey: 'nav.archive', icon: Archive },
  { to: '/collections', label: 'Collections', labelKey: 'nav.collections', icon: Tag },
  { to: '/settings', label: 'Settings', labelKey: 'nav.settings', icon: Settings },
];

// Shown in the secondary nav only for admin users.
export const adminNavigationItems: NavigationItem[] = [
  { to: '/stats', label: 'Stats', labelKey: 'nav.stats', icon: BarChart3 },
  { to: '/analytics', label: 'Analytics', labelKey: 'nav.analytics', icon: Activity },
  { to: '/admin', label: 'Users', labelKey: 'nav.users', icon: Users },
];

export function secondaryNavigationItemsFor(isAdmin: boolean): NavigationItem[] {
  return isAdmin
    ? [...secondaryNavigationItems, ...adminNavigationItems]
    : secondaryNavigationItems;
}

// The mobile bottom bar is a fixed 5-column grid. List the five destinations in
// display order so adding desktop-only items does not silently push one off the
// bar. Mobile surfaces Shared (articles sent to you by other people) here in
// place of Later, which remains reachable on desktop.
const mobileNavigationOrder = ['/', '/today', '/shared', '/starred', '/search'];
const mobileNavigationSet = new Set(mobileNavigationOrder);
const primaryNavigationByTo = new Map(primaryNavigationItems.map((item) => [item.to, item]));
export const mobileNavigationItems = mobileNavigationOrder.flatMap((to) => {
  const item = primaryNavigationByTo.get(to);
  return item ? [item] : [];
});

// Primary destinations omitted from the mobile bottom bar (e.g. Later, Ask).
// Rendered in the mobile More sheet so they remain reachable on small screens.
export const mobilePrimaryOverflowItems = primaryNavigationItems.filter(
  (item) => !mobileNavigationSet.has(item.to)
);

export const commandNavigationItems = [...primaryNavigationItems, ...secondaryNavigationItems].map(
  (item) => ({
    ...item,
    label: item.commandLabel ?? item.label,
  })
);

export function commandNavigationItemsFor(isAdmin: boolean): NavigationItem[] {
  const baseItems = [...primaryNavigationItems, ...secondaryNavigationItems];
  if (isAdmin) {
    return [...baseItems, ...adminNavigationItems].map((item) => ({
      ...item,
      label: item.commandLabel ?? item.label,
    }));
  }
  return baseItems.map((item) => ({
    ...item,
    label: item.commandLabel ?? item.label,
  }));
}

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

// Single source of truth for page titles: each rule pairs a route match with
// its English label and i18next key, so the two can never drift out of sync.
const pageTitleRules: { test: (pathname: string) => boolean; en: string; key: string }[] = [
  { test: (p) => p === '/', en: 'Brief', key: 'page_title.brief' },
  { test: (p) => p === '/today', en: 'Today', key: 'page_title.today' },
  { test: (p) => p.startsWith('/later'), en: 'Later', key: 'page_title.later' },
  { test: (p) => p.startsWith('/starred'), en: 'Starred', key: 'page_title.starred' },
  { test: (p) => p.startsWith('/shared'), en: 'Shared', key: 'page_title.shared' },
  { test: (p) => p.startsWith('/search'), en: 'Search', key: 'page_title.search' },
  { test: (p) => p.startsWith('/ask'), en: 'Ask AI', key: 'page_title.ask' },
  { test: (p) => p.startsWith('/topic-map'), en: 'Topic Map', key: 'page_title.topic_map' },
  { test: (p) => p.startsWith('/ai-stats'), en: 'AI Stats', key: 'page_title.ai_stats' },
  { test: (p) => p.startsWith('/briefs'), en: 'Briefs', key: 'page_title.briefs' },
  { test: (p) => p.startsWith('/feeds'), en: 'Feeds', key: 'page_title.feeds' },
  { test: (p) => p.startsWith('/stats'), en: 'Stats', key: 'page_title.stats' },
  { test: (p) => p.startsWith('/reading-dna'), en: 'Reading DNA', key: 'page_title.reading_dna' },
  {
    test: (p) => p.startsWith('/reading-list'),
    en: 'Reading List',
    key: 'page_title.reading_list',
  },
  {
    test: (p) => p.startsWith('/learn'),
    en: 'Learn',
    key: 'page_title.learn',
  },
  {
    test: (p) => p.startsWith('/offline-saved'),
    en: 'Offline Saved',
    key: 'page_title.offline_saved',
  },
  { test: (p) => p.startsWith('/recap'), en: 'Weekly Recap', key: 'page_title.weekly_recap' },
  { test: (p) => p.startsWith('/archive'), en: 'Archive', key: 'page_title.archive' },
  { test: (p) => p.startsWith('/collections'), en: 'Collections', key: 'page_title.collections' },
  { test: (p) => p.startsWith('/settings'), en: 'Settings', key: 'page_title.settings' },
  { test: (p) => p.startsWith('/analytics'), en: 'Analytics', key: 'page_title.analytics' },
  { test: (p) => p.startsWith('/admin'), en: 'Users', key: 'page_title.users' },
];
const defaultPageTitle = { en: 'Radar', key: 'page_title.default' };

function resolvePageTitle(pathname: string): { en: string; key: string } {
  return pageTitleRules.find((rule) => rule.test(pathname)) ?? defaultPageTitle;
}

export function getPageTitle(pathname: string): string {
  return resolvePageTitle(pathname).en;
}

/** i18next key for the page title, for shell surfaces that render translated text. */
export function getPageTitleKey(pathname: string): string {
  return resolvePageTitle(pathname).key;
}
