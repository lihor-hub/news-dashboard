import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
  Star,
  Check,
  Clock,
  X as XIcon,
  Archive,
  Loader2,
  Volume2,
  Square,
  Share2,
  Sparkles,
  MoreHorizontal,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AudioState } from '@/hooks/useArticleAudio';

export type ArticleActionBarLayout = 'floating' | 'inline';

type Icon = React.ComponentType<{ className?: string; strokeWidth?: number }>;

function ActionBtn({
  onClick,
  icon: Icon,
  label,
  active,
  disabled,
  compactLabel,
  className,
  expanded,
}: {
  onClick: () => void;
  icon: Icon;
  label: string;
  active?: boolean;
  disabled?: boolean;
  /** Floating layout: icon-only on mobile, label visible from md up. */
  compactLabel?: boolean;
  className?: string;
  expanded?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-expanded={expanded}
      aria-haspopup={expanded === undefined ? undefined : 'menu'}
      title={compactLabel ? label : undefined}
      className={cn(
        'inline-flex min-h-touch min-w-touch shrink-0 items-center justify-center gap-1.5 rounded-full px-2 text-sm font-medium transition-colors md:min-h-9 md:px-3 md:text-xs',
        active ? 'text-star' : 'text-muted-foreground hover:bg-surface hover:text-foreground',
        disabled && 'cursor-not-allowed opacity-30 hover:bg-transparent',
        className
      )}
    >
      <Icon
        className={cn(
          'size-5 md:size-4',
          active && 'fill-current',
          Icon === Loader2 && 'animate-spin motion-reduce:animate-none'
        )}
        strokeWidth={1.75}
      />
      <span className={cn(compactLabel && 'sr-only md:not-sr-only')}>{label}</span>
    </button>
  );
}

function MenuItem({
  onClick,
  icon: Icon,
  label,
  disabled,
}: {
  onClick: () => void;
  icon: Icon;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      disabled={disabled}
      className="flex min-h-touch w-full items-center gap-3 rounded-lg px-3 text-start text-[15px] font-medium text-foreground transition-colors hover:bg-surface disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
    >
      <Icon className="size-5 text-muted-foreground" strokeWidth={1.75} />
      {label}
    </button>
  );
}

export function ArticleActionBar({
  starred,
  onStar,
  onDone,
  onLater,
  onSkip,
  onArchive,
  onShare,
  onAsk,
  audioState,
  onListen,
  layout = 'floating',
}: {
  starred: boolean;
  onStar: () => void;
  onDone: () => void;
  onLater: () => void;
  onSkip: () => void;
  onArchive: () => void;
  onShare: () => void;
  onAsk: () => void;
  audioState: AudioState;
  onListen: () => void;
  /**
   * `floating` (full-page reader): portal-mounted, a rounded bar in thumb reach
   * on mobile and a compact labelled bar on desktop.
   * `inline` (reading pane): in-flow bar that sticks to the top of the pane.
   */
  layout?: ArticleActionBarLayout;
}) {
  const { t } = useTranslation();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  const floating = layout === 'floating';

  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      // Close the menu without also triggering the reader's Esc → back.
      e.stopImmediatePropagation();
      setMoreOpen(false);
    };
    const onPointer = (e: PointerEvent) => {
      if (!moreRef.current?.contains(e.target as Node)) setMoreOpen(false);
    };
    window.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      window.removeEventListener('keydown', onKey, true);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [moreOpen]);

  const listenIcon =
    audioState === 'loading' ? Loader2 : audioState === 'playing' ? Square : Volume2;
  const listenLabel =
    audioState === 'loading'
      ? 'Loading…'
      : audioState === 'playing'
        ? 'Stop'
        : audioState === 'paused'
          ? 'Resume'
          : 'Listen';
  const closeThen = (fn: () => void) => () => {
    setMoreOpen(false);
    fn();
  };

  // On the floating bar Done/Skip/Archive move into the More menu below md so
  // the mobile bar keeps five thumb-sized primary actions.
  const secondaryClass = floating ? 'hidden md:inline-flex' : undefined;

  const actions = (
    <>
      <ActionBtn
        onClick={onStar}
        icon={Star}
        label={starred ? 'Unstar' : 'Star'}
        active={starred}
        compactLabel={floating}
      />
      <ActionBtn
        onClick={onDone}
        icon={Check}
        label="Done"
        compactLabel={floating}
        className={secondaryClass}
      />
      <ActionBtn onClick={onLater} icon={Clock} label="Later" compactLabel={floating} />
      <ActionBtn
        onClick={onSkip}
        icon={XIcon}
        label="Skip"
        disabled={starred}
        compactLabel={floating}
        className={secondaryClass}
      />
      <ActionBtn
        onClick={onArchive}
        icon={Archive}
        label="Archive"
        compactLabel={floating}
        className={secondaryClass}
      />
      <ActionBtn
        onClick={onListen}
        icon={listenIcon}
        label={listenLabel}
        disabled={audioState === 'loading'}
        compactLabel={floating}
      />
      <ActionBtn
        onClick={onAsk}
        icon={Sparkles}
        label={t('reader.ask', 'Ask')}
        compactLabel={floating}
      />
      <ActionBtn onClick={onShare} icon={Share2} label="Share" compactLabel={floating} />
      {floating && (
        <div ref={moreRef} className="relative md:hidden">
          <ActionBtn
            onClick={() => setMoreOpen((v) => !v)}
            icon={MoreHorizontal}
            label={t('reader.more_actions', 'More actions')}
            compactLabel
            expanded={moreOpen}
          />
          {moreOpen && (
            <div
              role="menu"
              data-testid="more-actions"
              aria-label={t('reader.more_actions', 'More actions')}
              className="absolute bottom-full end-0 mb-3 w-48 rounded-xl border border-border bg-background p-1 shadow-elevation-3"
            >
              <MenuItem onClick={closeThen(onDone)} icon={Check} label="Done" />
              <MenuItem onClick={closeThen(onSkip)} icon={XIcon} label="Skip" disabled={starred} />
              <MenuItem onClick={closeThen(onArchive)} icon={Archive} label="Archive" />
            </div>
          )}
        </div>
      )}
    </>
  );

  if (!floating) {
    return (
      <div
        data-testid="action-bar"
        className="sticky top-14 z-10 md:top-12 -mx-1 mt-4 flex items-center gap-0.5 overflow-x-auto rounded-full border border-border bg-background/95 p-1 backdrop-blur"
      >
        {actions}
      </div>
    );
  }

  // Rendered via portal so its position:fixed always resolves against the
  // viewport regardless of any CSS transform that may exist on an ancestor or
  // sibling of the reader root during the entry animation
  // (motion-slide-in-right carries transform:translateX in its from-keyframe;
  // even as a sibling, some mobile browser compositors bleed this transform
  // onto nearby fixed elements for the first paint). The bar floats above the
  // safe area and above any host bottom chrome (see useBottomObstruction).
  return createPortal(
    <div
      data-testid="action-bar"
      data-reader-floating=""
      className="pointer-events-none fixed inset-x-0 bottom-[calc(max(env(safe-area-inset-bottom),var(--reader-bottom-offset,0px))+0.75rem)] z-20 flex justify-center px-3 md:bottom-[calc(max(env(safe-area-inset-bottom),var(--reader-bottom-offset,0px))+1.25rem)]"
    >
      <div className="pointer-events-auto flex max-w-full items-center gap-0.5 rounded-full border border-border bg-background/95 p-1 shadow-elevation-2 backdrop-blur">
        {actions}
      </div>
    </div>,
    document.body
  );
}
