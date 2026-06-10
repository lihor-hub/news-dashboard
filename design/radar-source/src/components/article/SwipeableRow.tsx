import { useRef, useState, type ReactNode } from "react";
import { Star, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  children: ReactNode;
  onSwipeRight?: () => void;
  onSwipeLeft?: () => void;
  disableLeft?: boolean;
}

export function SwipeableRow({ children, onSwipeRight, onSwipeLeft, disableLeft }: Props) {
  const [dx, setDx] = useState(0);
  const startX = useRef<number | null>(null);
  const dragging = useRef(false);

  const THRESHOLD = 80;

  const onStart = (x: number) => {
    startX.current = x;
    dragging.current = true;
  };
  const onMove = (x: number) => {
    if (!dragging.current || startX.current == null) return;
    const d = x - startX.current;
    setDx(disableLeft && d < 0 ? Math.max(d, -20) : Math.max(Math.min(d, 140), -140));
  };
  const onEnd = () => {
    if (!dragging.current) return;
    dragging.current = false;
    if (dx > THRESHOLD) onSwipeRight?.();
    else if (dx < -THRESHOLD && !disableLeft) onSwipeLeft?.();
    setDx(0);
    startX.current = null;
  };

  const showRight = dx > 10;
  const showLeft = dx < -10 && !disableLeft;

  return (
    <div className="relative overflow-hidden">
      {showRight && (
        <div className="absolute inset-y-0 left-0 flex items-center px-5 bg-star/15 text-star">
          <Star className="size-5 fill-current" />
        </div>
      )}
      {showLeft && (
        <div className="absolute inset-y-0 right-0 flex items-center px-5 bg-destructive/15 text-destructive">
          <X className="size-5" />
        </div>
      )}
      <div
        className={cn("bg-background touch-pan-y", dragging.current ? "" : "transition-transform duration-150")}
        style={{ transform: `translateX(${dx}px)` }}
        onTouchStart={(e) => onStart(e.touches[0].clientX)}
        onTouchMove={(e) => onMove(e.touches[0].clientX)}
        onTouchEnd={onEnd}
      >
        {children}
      </div>
    </div>
  );
}
