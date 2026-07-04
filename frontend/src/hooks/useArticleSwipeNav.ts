import { useRef, useState } from 'react';

const SWIPE_THRESHOLD = 80;
const VERTICAL_TOLERANCE = 40;

export function useArticleSwipeNav(goPrev: () => void, goNext: () => void) {
  const swipeRef = useRef<{ x: number; y: number } | null>(null);
  const [swipeDx, setSwipeDx] = useState(0);

  const touchHandlers = {
    onTouchStart: (e: React.TouchEvent) => {
      swipeRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    },
    onTouchMove: (e: React.TouchEvent) => {
      if (!swipeRef.current) return;
      const dx = e.touches[0].clientX - swipeRef.current.x;
      const dy = Math.abs(e.touches[0].clientY - swipeRef.current.y);
      if (dy < VERTICAL_TOLERANCE) setSwipeDx(dx);
    },
    onTouchEnd: () => {
      if (swipeDx < -SWIPE_THRESHOLD) goNext();
      else if (swipeDx > SWIPE_THRESHOLD) goPrev();
      setSwipeDx(0);
      swipeRef.current = null;
    },
    onTouchCancel: () => {
      swipeRef.current = null;
      setSwipeDx(0);
    },
  };

  return { swipeDx, touchHandlers };
}
