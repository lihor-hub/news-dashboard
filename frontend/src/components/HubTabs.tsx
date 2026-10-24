import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink } from './NavLink';
import { getActiveHub, getActiveHubItem, hubItemsFor } from '@/lib/navigation';

interface HubTabsProps {
  pathname: string;
  isAdmin: boolean;
  /** Optional badge counts keyed by route (e.g. `{ '/today': 12 }`). */
  counts?: Partial<Record<string, number | null>>;
}

/**
 * Segmented tab strip for the sub-pages of the hub that owns `pathname`.
 * Scrolls horizontally on narrow screens and keeps the active tab in view.
 */
export function HubTabs({ pathname, isAdmin, counts }: HubTabsProps) {
  const { t } = useTranslation();
  const stripRef = useRef<HTMLDivElement>(null);
  const hub = getActiveHub(pathname);
  const items = hub ? hubItemsFor(hub, isAdmin) : [];
  const activeTo = getActiveHubItem(items, pathname)?.to;

  useEffect(() => {
    const active = stripRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
    active?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [activeTo]);

  if (!hub || items.length < 2) return null;

  return (
    <nav aria-label={t(hub.labelKey)} className="px-4 pt-3 md:px-5 md:pt-4">
      <div
        ref={stripRef}
        className="flex snap-x gap-1 overflow-x-auto overscroll-x-contain rounded-lg bg-surface p-1 [scrollbar-width:none] md:inline-flex md:max-w-full [&::-webkit-scrollbar]:hidden"
      >
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            label={t(item.labelKey)}
            icon={item.icon}
            isActive={item.to === activeTo}
            count={counts?.[item.to]}
            variant="tab"
          />
        ))}
      </div>
    </nav>
  );
}
