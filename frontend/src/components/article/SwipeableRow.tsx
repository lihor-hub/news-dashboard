import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Check, Hand, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  children: ReactNode;
  onSwipeRight?: () => void;
  onSwipeLeft?: () => void;
  onLongPress?: () => void;
  disableLeft?: boolean;
  /** Visible name of the swipe-right action, shown in the colour reveal. */
  rightLabel?: string;
  /** Visible name of the swipe-left action, shown in the colour reveal. */
  leftLabel?: string;
}

export const SWIPE_HINT_STORAGE_KEY = 'nd.swipeHintDismissed';

const THRESHOLD = 80;
const LONG_PRESS_MS = 500;
const LONG_PRESS_MOVE_LIMIT = 10;

export function SwipeableRow({
  children,
  onSwipeRight,
  onSwipeLeft,
  onLongPress,
  disableLeft,
  rightLabel,
  leftLabel,
}: Props) {
  const [dx, setDx] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [committing, setCommitting] = useState(false);
  const startX = useRef<number | null>(null);
  const commitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Long-press state
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressOrigin = useRef<{ x: number; y: number } | null>(null);
  const longPressFired = useRef(false);

  const clearLongPress = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  // Cancel the long-press timer if the component unmounts mid-gesture (e.g.
  // programmatic navigation from a keyboard shortcut while a finger is down).
  // Without this, the timer fires after unmount and calls onLongPress() —
  // triggering a star mutation against an article that the user never intended.
  useEffect(() => {
    return () => {
      if (longPressTimer.current) clearTimeout(longPressTimer.current);
      if (commitTimer.current) clearTimeout(commitTimer.current);
    };
  }, []);

  const onStart = (x: number) => {
    startX.current = x;
    setIsDragging(true);
  };

  const onMove = (x: number, y: number) => {
    if (!isDragging || startX.current == null) return;
    const d = x - startX.current;
    setDx(disableLeft && d < 0 ? Math.max(d, -20) : Math.max(Math.min(d, 140), -140));

    // Cancel long-press if finger moved too far
    if (longPressOrigin.current) {
      const moveX = Math.abs(x - longPressOrigin.current.x);
      const moveY = Math.abs(y - longPressOrigin.current.y);
      if (moveX > LONG_PRESS_MOVE_LIMIT || moveY > LONG_PRESS_MOVE_LIMIT) {
        clearLongPress();
      }
    }
  };

  const onEnd = () => {
    clearLongPress();
    longPressOrigin.current = null;
    if (!isDragging) return;
    setIsDragging(false);
    // Suppress swipe if a long-press already fired — the two actions must be mutually exclusive.
    // Before PR #162, Chrome's contextmenu dialog consumed touchend so this was never reached;
    // preventing the default unblocked touchend and exposed the race.
    const willFire =
      !longPressFired.current &&
      ((dx > THRESHOLD && !!onSwipeRight) || (dx < -THRESHOLD && !disableLeft && !!onSwipeLeft));
    if (willFire) {
      setCommitting(true);
      const action = dx > THRESHOLD ? onSwipeRight : onSwipeLeft;
      action?.();
      if (commitTimer.current) clearTimeout(commitTimer.current);
      commitTimer.current = setTimeout(() => {
        setCommitting(false);
      }, 180);
    }
    setDx(0);
    startX.current = null;
  };

  // Browser-cancelled touch (scroll takeover, notification, etc.) — reset state only, no action.
  const onCancel = () => {
    clearLongPress();
    longPressOrigin.current = null;
    longPressFired.current = false;
    if (!isDragging) return;
    setIsDragging(false);
    setCommitting(false);
    setDx(0);
    startX.current = null;
  };

  // RTL exception: these reveal edges follow physical pointer dx and onSwipeRight/onSwipeLeft.
  const showRight = dx > 10;
  const showLeft = dx < -10 && !disableLeft;

  return (
    <div className="relative overflow-hidden">
      {showRight && (
        <div
          className={cn(
            'absolute inset-y-0 left-0 flex items-center gap-2 px-5 text-sm font-semibold text-ok transition-colors duration-150',
            dx > THRESHOLD ? 'bg-ok/25' : 'bg-ok/15'
          )}
        >
          <Check
            aria-hidden="true"
            className={cn(
              'size-5 transition-transform duration-150 motion-reduce:transition-none',
              dx > THRESHOLD && 'scale-110'
            )}
          />
          {rightLabel && <span>{rightLabel}</span>}
        </div>
      )}
      {showLeft && (
        <div
          className={cn(
            'absolute inset-y-0 right-0 flex items-center gap-2 px-5 text-sm font-semibold text-destructive transition-colors duration-150',
            dx < -THRESHOLD ? 'bg-destructive/25' : 'bg-destructive/15'
          )}
        >
          {leftLabel && <span>{leftLabel}</span>}
          <X
            aria-hidden="true"
            className={cn(
              'size-5 transition-transform duration-150 motion-reduce:transition-none',
              dx < -THRESHOLD && 'scale-110'
            )}
          />
        </div>
      )}
      <div
        className={cn(
          'bg-background touch-pan-y',
          committing
            ? 'motion-swipe-confirm'
            : isDragging
              ? ''
              : 'transition-transform duration-150 motion-reduce:transition-none'
        )}
        style={committing ? undefined : { transform: `translateX(${dx}px)` }}
        onClickCapture={(e) => {
          // Prevent navigation click from firing after a long-press
          if (longPressFired.current) {
            e.preventDefault();
            e.stopPropagation();
            longPressFired.current = false;
          }
        }}
        onContextMenu={(e) => {
          // Suppress Chrome's native link context menu during long-press
          if (onLongPress) e.preventDefault();
        }}
        onTouchStart={(e) => {
          const touch = e.touches[0];
          onStart(touch.clientX);
          if (onLongPress) {
            longPressOrigin.current = { x: touch.clientX, y: touch.clientY };
            longPressFired.current = false;
            longPressTimer.current = setTimeout(() => {
              longPressFired.current = true;
              longPressTimer.current = null;
              onLongPress();
            }, LONG_PRESS_MS);
          }
        }}
        onTouchMove={(e) => {
          const touch = e.touches[0];
          onMove(touch.clientX, touch.clientY);
        }}
        onTouchEnd={onEnd}
        onTouchCancel={onCancel}
      >
        {children}
      </div>
    </div>
  );
}

function readHintDismissed(): boolean {
  try {
    return localStorage.getItem(SWIPE_HINT_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

/**
 * One-time tip that teaches the row gestures. Only rendered for coarse
 * (touch) pointers; dismissal is remembered in localStorage.
 */
export function SwipeHint({ message, dismissLabel }: { message: string; dismissLabel: string }) {
  const [dismissed, setDismissed] = useState(readHintDismissed);
  if (dismissed) return null;

  const dismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(SWIPE_HINT_STORAGE_KEY, '1');
    } catch {
      // Storage unavailable (private mode): the tip just reappears next visit.
    }
  };

  return (
    <div
      role="note"
      className="mx-4 my-2 hidden items-center gap-3 rounded-xl border border-border bg-surface ps-3 text-[13px] leading-snug text-muted-foreground pointer-coarse:flex md:mx-5"
    >
      <Hand className="size-5 shrink-0 text-accent" aria-hidden="true" />
      <p className="flex-1 py-2.5">{message}</p>
      <button
        type="button"
        aria-label={dismissLabel}
        onClick={dismiss}
        className="grid size-11 shrink-0 place-items-center rounded-xl text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
      >
        <X className="size-4" aria-hidden="true" />
      </button>
    </div>
  );
}
