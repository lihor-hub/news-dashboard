import { useRef, useState, type ReactNode } from 'react';
import { Star, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  children: ReactNode;
  onSwipeRight?: () => void;
  onSwipeLeft?: () => void;
  disableLeft?: boolean;
}

const THRESHOLD = 80;

export function SwipeableRow({ children, onSwipeRight, onSwipeLeft, disableLeft }: Props) {
  const [dx, setDx] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [committing, setCommitting] = useState(false);
  const startX = useRef<number | null>(null);

  const onStart = (x: number) => {
    startX.current = x;
    setIsDragging(true);
  };

  const onMove = (x: number) => {
    if (!isDragging || startX.current == null) return;
    const d = x - startX.current;
    setDx(disableLeft && d < 0 ? Math.max(d, -20) : Math.max(Math.min(d, 140), -140));
  };

  const onEnd = () => {
    if (!isDragging) return;
    setIsDragging(false);
    const willFire =
      (dx > THRESHOLD && !!onSwipeRight) || (dx < -THRESHOLD && !disableLeft && !!onSwipeLeft);
    if (willFire) {
      setCommitting(true);
      const action = dx > THRESHOLD ? onSwipeRight : onSwipeLeft;
      // Fire action after brief animation window
      setTimeout(() => {
        action?.();
        setCommitting(false);
      }, 180);
    }
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
            'absolute inset-y-0 left-0 flex items-center px-5 text-star transition-all duration-150',
            dx > THRESHOLD ? 'bg-star/25' : 'bg-star/15'
          )}
        >
          <Star
            className={cn(
              'size-5 fill-current transition-transform duration-150',
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
        onTouchStart={(e) => onStart(e.touches[0].clientX)}
        onTouchMove={(e) => onMove(e.touches[0].clientX)}
        onTouchEnd={onEnd}
      >
        {children}
      </div>
    </div>
  );
}
