import {
  Activity,
  Archive,
  BarChart3,
  Bookmark,
  ChartPie,
  Download,
  GraduationCap,
  BrainCircuit,
  Clock,
  Flame,
  History,
  Inbox,
  Library,
  LibraryBig,
  Network,
  Newspaper,
  Podcast,
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
  /** i18next key for the translated label, used by shell surfaces (rail, tabs, sheet menu). */
  labelKey: string;
  icon: LucideIcon;
  commandLabel?: string;
  shortcut?: string;
  adminOnly?: boolean;
}

export type HubId = 'read' | 'library' | 'ask' | 'learn' | 'insights';

/** A top-level destination in the rail / bottom bar that groups related pages as tabs. */
export interface NavigationHub {
  id: HubId;
  label: string;
  labelKey: string;
  icon: LucideIcon;
  items: NavigationItem[];
}

export const BRIEF_ROUTE = '/';
export const TODAY_ROUTE = '/today';

export const navigationHubs: NavigationHub[] = [
  {
    id: 'read',
    label: 'Read',
    labelKey: 'nav.hub_read',
    icon: Newspaper,
    items: [
      { to: BRIEF_ROUTE, label: 'Brief', labelKey: 'nav.brief', icon: Newspaper, shortcut: 'b' },
      { to: TODAY_ROUTE, label: 'Today', labelKey: 'nav.today', icon: Inbox, shortcut: 't' },
      {
        to: '/briefs',
        label: 'Briefing History',
        labelKey: 'nav.briefing_history',
        icon: History,
        shortcut: 'h',
      },
    ],
  },
  {
    id: 'library',
    label: 'Library',
    labelKey: 'nav.hub_library',
    icon: LibraryBig,
    items: [
      { to: '/later', label: 'Later', labelKey: 'nav.later', icon: Clock, shortcut: 'l' },
      { to: '/starred', label: 'Starred', labelKey: 'nav.starred', icon: Star, shortcut: 's' },
      { to: '/shared', label: 'Shared', labelKey: 'nav.shared', icon: Send },
      { to: '/collections', label: 'Collections', labelKey: 'nav.collections', icon: Tag },
      {
        to: '/reading-list',
        label: 'Reading List',
        labelKey: 'nav.reading_list',
        icon: Bookmark,
        shortcut: 'r',
      },
      {
        to: '/offline-saved',
        label: 'Offline Saved',
        labelKey: 'nav.offline_saved',
        icon: Download,
        shortcut: 'o',
      },
      { to: '/archive', label: 'Archive', labelKey: 'nav.archive', icon: Archive },
    ],
  },
  {
    id: 'ask',
    label: 'Ask',
    labelKey: 'nav.hub_ask',
    icon: Sparkles,
    items: [
      {
        to: '/ask',
        label: 'Ask',
        labelKey: 'nav.ask',
        commandLabel: 'Ask AI',
        icon: Sparkles,
        shortcut: 'a',
      },
      { to: '/search', label: 'Search', labelKey: 'nav.search', icon: Search },
    ],
  },
  {
    id: 'learn',
    label: 'Learn',
    labelKey: 'nav.hub_learn',
    icon: GraduationCap,
    items: [
      { to: '/learn', label: 'Learn', labelKey: 'nav.learn', icon: GraduationCap },
      {
        to: '/learn/library',
        label: 'Lesson Library',
        labelKey: 'nav.lesson_library',
        icon: Library,
      },
      {
        to: '/learn/recap',
        label: 'Learning Recap',
        labelKey: 'nav.learning_recap',
        icon: Podcast,
      },
    ],
  },
  {
    id: 'insights',
    label: 'Insights',
    labelKey: 'nav.hub_insights',
    icon: ChartPie,
    items: [
      { to: '/recap', label: 'Weekly Recap', labelKey: 'nav.weekly_recap', icon: Flame },
      {
        to: '/reading-dna',
        label: 'Reading DNA',
        labelKey: 'nav.reading_dna',
        icon: SlidersHorizontal,
      },
      { to: '/topic-map', label: 'Topic Map', labelKey: 'nav.topic_map', icon: Network },
      { to: '/stats', label: 'Stats', labelKey: 'nav.stats', icon: BarChart3, adminOnly: true },
      { to: '/ai-stats', label: 'AI Stats', labelKey: 'nav.ai_stats', icon: BrainCircuit },
    ],
  },
];

// Pages that belong to no hub; they live in the "You" / avatar menu.
export const accountNavigationItems: NavigationItem[] = [
  { to: '/feeds', label: 'Feeds', labelKey: 'nav.feeds', icon: Radio, shortcut: 'f' },
  { to: '/settings', label: 'Settings', labelKey: 'nav.settings', icon: Settings },
  {
    to: '/analytics',
    label: 'Analytics',
    labelKey: 'nav.analytics',
    icon: Activity,
    adminOnly: true,
  },
  { to: '/admin', label: 'Users', labelKey: 'nav.users', icon: Users, adminOnly: true },
];

const visibleFor = (isAdmin: boolean) => (item: NavigationItem) => isAdmin || !item.adminOnly;

export function hubItemsFor(hub: NavigationHub, isAdmin: boolean): NavigationItem[] {
  return hub.items.filter(visibleFor(isAdmin));
}

export function accountNavigationItemsFor(isAdmin: boolean): NavigationItem[] {
  return accountNavigationItems.filter(visibleFor(isAdmin));
}

const allNavigationItems = [
  ...navigationHubs.flatMap((hub) => hub.items),
  ...accountNavigationItems,
];

/** Every page reachable from the shell, in hub order, filtered by role. */
export function navigationItemsFor(isAdmin: boolean): NavigationItem[] {
  return allNavigationItems.filter(visibleFor(isAdmin));
}

export function commandNavigationItemsFor(isAdmin: boolean): NavigationItem[] {
  return navigationItemsFor(isAdmin).map((item) => ({
    ...item,
    label: item.commandLabel ?? item.label,
  }));
}

/** Where a hub's rail / bottom-bar button leads: its first page visible to everyone. */
export function hubTarget(hub: NavigationHub): string {
  return (hub.items.find((item) => !item.adminOnly) ?? hub.items[0]).to;
}

const hubById = new Map(navigationHubs.map((hub) => [hub.id, hub]));

// The mobile bottom bar shows four hubs plus the "You" sheet, with Ask raised in
// the centre. Insights lives inside the "You" sheet on small screens.
export const mobileBarHubs: NavigationHub[] = (['read', 'library', 'ask', 'learn'] as const).map(
  (id) => hubById.get(id)!
);
export const insightsHub: NavigationHub = hubById.get('insights')!;

function matchesRoute(to: string, pathname: string): boolean {
  if (to === '/') return pathname === '/';
  return pathname === to || pathname.startsWith(`${to}/`);
}

/** The hub that owns the current page, or null for account/admin pages and unknown routes. */
export function getActiveHub(pathname: string): NavigationHub | null {
  return (
    navigationHubs.find((hub) => hub.items.some((item) => matchesRoute(item.to, pathname))) ?? null
  );
}

/** The tab for the current page: the longest of `items` whose route contains it. */
export function getActiveHubItem(items: NavigationItem[], pathname: string): NavigationItem | null {
  return items.reduce<NavigationItem | null>(
    (best, item) =>
      matchesRoute(item.to, pathname) && item.to.length > (best?.to.length ?? -1) ? item : best,
    null
  );
}

/** True for account pages (Feeds, Settings, admin) that live only in the "You" / avatar menu. */
export function isAccountRoute(pathname: string): boolean {
  return accountNavigationItems.some((item) => matchesRoute(item.to, pathname));
}

export const navigationShortcutRows: [string, string][] = [
  ['j / k', 'shortcuts.navigation.move'],
  ['Enter', 'shortcuts.navigation.open'],
  ['g b / g t', 'shortcuts.navigation.briefToday'],
  ['g l / g s', 'shortcuts.navigation.laterStarred'],
  ['g a / g f', 'shortcuts.navigation.askFeeds'],
  ['g h', 'shortcuts.navigation.history'],
];

const shortcutTargets = new Map(
  allNavigationItems.filter((item) => item.shortcut).map((item) => [item.shortcut!, item.to])
);

export function getShortcutTarget(key: string): string | null {
  return shortcutTargets.get(key.toLowerCase()) ?? null;
}

// Hub roots whose sub-routes are separate pages (or detail views) of their own.
const exactMatchRoutes = new Set(['/', '/today', '/learn']);

export function isNavigationItemActive(to: string, pathname: string): boolean {
  return exactMatchRoutes.has(to) ? pathname === to : matchesRoute(to, pathname);
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
    test: (p) => p.startsWith('/learn/library'),
    en: 'Lesson Library',
    key: 'page_title.lesson_library',
  },
  {
    test: (p) => p.startsWith('/learn/recap'),
    en: 'Learning Recap',
    key: 'page_title.learning_recap',
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
