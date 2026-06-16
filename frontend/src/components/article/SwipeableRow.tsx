import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  children: ReactNode;
  onSwipeRight?: () => void;
  onSwipeLeft?: () => void;
  onLongPress?: () => void;
  disableLeft?: boolean;
}

const THRESHOLD = 80;
const LONG_PRESS_MS = 500;
const LONG_PRESS_MOVE_LIMIT = 10;

export function SwipeableRow({
  children,
  onSwipeRight,
  onSwipeLeft,
  onLongPress,
  disableLeft,
}: Props) {
  const [dx, setDx] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [committing, setCommitting] = useState(false);
  const startX = useRef<number | null>(null);

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
      setTimeout(() => {
        action?.();
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
    setDx(0);
    startX.current = null;
  };

  const showRight = dx > 10;
  const showLeft = dx < -10 && !disableLeft;

  return (
    <div className="relative overflow-hidden">
      {showRight && (
        <div
          className={cn(
            'absolute inset-y-0 left-0 flex items-center px-5 text-emerald-500 transition-all duration-150',
            dx > THRESHOLD ? 'bg-emerald-500/25' : 'bg-emerald-500/15'
          )}
        >
          <Check
            className={cn(
              'size-5 transition-transform duration-150',
              dx > THRESHOLD && 'scale-110'
            )}
          />
        </div>
      )}
      {showLeft && (
        <div
          className={cn(
            'absolute inset-y-0 right-0 flex items-center px-5 text-destructive transition-all duration-150',
            dx < -THRESHOLD ? 'bg-destructive/25' : 'bg-destructive/15'
          )}
        >
          <X
            className={cn(
              'size-5 transition-transform duration-150',
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
              : 'transition-transform duration-150'
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
