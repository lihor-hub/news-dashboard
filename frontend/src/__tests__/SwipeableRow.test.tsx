// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import {
  SwipeableRow,
  SwipeHint,
  SWIPE_HINT_STORAGE_KEY,
} from '../components/article/SwipeableRow';

describe('SwipeableRow — swipe gestures', () => {
  it('fires onSwipeRight when dragged past threshold', () => {
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onSwipeRight={onSwipeRight}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    // Action fires after 180 ms animation window; use fake timers
    vi.useFakeTimers();
    fireEvent.touchStart(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 100, clientY: 0 }] });
    fireEvent.touchEnd(inner);
    void act(() => vi.advanceTimersByTime(200));
    expect(onSwipeRight).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('fires swipe actions immediately on touch end', () => {
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onSwipeRight={onSwipeRight}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    fireEvent.touchStart(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 100, clientY: 0 }] });
    fireEvent.touchEnd(inner);
    expect(onSwipeRight).toHaveBeenCalledOnce();
  });

  it('fires onSwipeLeft when dragged left past threshold', () => {
    const onSwipeLeft = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onSwipeLeft={onSwipeLeft}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    vi.useFakeTimers();
    fireEvent.touchStart(inner, { touches: [{ clientX: 100, clientY: 0 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchEnd(inner);
    void act(() => vi.advanceTimersByTime(200));
    expect(onSwipeLeft).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('does not fire onSwipeLeft when disableLeft=true', () => {
    const onSwipeLeft = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onSwipeLeft={onSwipeLeft} disableLeft>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    vi.useFakeTimers();
    fireEvent.touchStart(inner, { touches: [{ clientX: 100, clientY: 0 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchEnd(inner);
    void act(() => vi.advanceTimersByTime(200));
    expect(onSwipeLeft).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

describe('SwipeableRow — long-press gesture', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fires onLongPress after 500 ms hold without movement', () => {
    const onLongPress = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onLongPress={onLongPress}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    fireEvent.touchStart(inner, { touches: [{ clientX: 50, clientY: 50 }] });
    void act(() => vi.advanceTimersByTime(500));
    expect(onLongPress).toHaveBeenCalledOnce();
  });

  it('does not fire onLongPress if finger moves more than 10 px before 500 ms', () => {
    const onLongPress = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onLongPress={onLongPress}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    fireEvent.touchStart(inner, { touches: [{ clientX: 50, clientY: 50 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 65, clientY: 50 }] }); // 15 px → cancel
    void act(() => vi.advanceTimersByTime(500));
    expect(onLongPress).not.toHaveBeenCalled();
  });

  it('does not fire onLongPress if touch ends before 500 ms', () => {
    const onLongPress = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onLongPress={onLongPress}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    fireEvent.touchStart(inner, { touches: [{ clientX: 50, clientY: 50 }] });
    void act(() => vi.advanceTimersByTime(300));
    fireEvent.touchEnd(inner);
    void act(() => vi.advanceTimersByTime(300));
    expect(onLongPress).not.toHaveBeenCalled();
  });

  it('allows small finger movement (≤10 px) without cancelling long-press', () => {
    const onLongPress = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onLongPress={onLongPress}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    fireEvent.touchStart(inner, { touches: [{ clientX: 50, clientY: 50 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 55, clientY: 52 }] }); // 5 px → keep timer
    void act(() => vi.advanceTimersByTime(500));
    expect(onLongPress).toHaveBeenCalledOnce();
  });

  it('prevents contextmenu event when onLongPress is set', () => {
    const onLongPress = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onLongPress={onLongPress}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    const evt = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    inner.dispatchEvent(evt);
    expect(evt.defaultPrevented).toBe(true);
  });

  it('does not prevent contextmenu event when onLongPress is not set', () => {
    const { getByTestId } = render(
      <SwipeableRow>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    const evt = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    inner.dispatchEvent(evt);
    expect(evt.defaultPrevented).toBe(false);
  });

  it('does not fire swipe action when long-press already fired during the same gesture', () => {
    const onLongPress = vi.fn();
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onLongPress={onLongPress} onSwipeRight={onSwipeRight}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    // Start touch and hold for 500 ms → long-press fires
    fireEvent.touchStart(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    void act(() => vi.advanceTimersByTime(500));
    expect(onLongPress).toHaveBeenCalledOnce();
    // Finger slides right past the swipe threshold while still holding
    fireEvent.touchMove(inner, { touches: [{ clientX: 100, clientY: 0 }] });
    // Lift finger — swipe must NOT fire because long-press already handled the gesture
    fireEvent.touchEnd(inner);
    void act(() => vi.advanceTimersByTime(200));
    expect(onSwipeRight).not.toHaveBeenCalled();
  });

  it('resets gesture state on touchcancel so the next gesture works correctly', () => {
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onSwipeRight={onSwipeRight}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    // First touch is cancelled by the browser (e.g. notification arrives)
    fireEvent.touchStart(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 50, clientY: 0 }] });
    fireEvent(inner, new TouchEvent('touchcancel', { bubbles: true }));
    // Second touch should behave normally — swipe right works
    fireEvent.touchStart(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 100, clientY: 0 }] });
    fireEvent.touchEnd(inner);
    void act(() => vi.advanceTimersByTime(200));
    expect(onSwipeRight).toHaveBeenCalledOnce();
  });

  it('does not fire swipe action when touchcancel arrives even if dx exceeds threshold', () => {
    // Regression: onTouchCancel={onEnd} would invoke onEnd which fires the swipe if dx > 80.
    // A browser cancel (e.g. scroll taking over) must never trigger an article action.
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(
      <SwipeableRow onSwipeRight={onSwipeRight}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    fireEvent.touchStart(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 100, clientY: 0 }] }); // dx=100 > THRESHOLD
    fireEvent(inner, new TouchEvent('touchcancel', { bubbles: true }));
    void act(() => vi.advanceTimersByTime(200));
    expect(onSwipeRight).not.toHaveBeenCalled();
  });

  it('does not fire long-press action when component unmounts mid-gesture', () => {
    // Regression: without useEffect cleanup the 500ms timer fires after unmount and
    // calls onLongPress() — starring an article the user never intended to star.
    const onLongPress = vi.fn();
    const { getByTestId, unmount } = render(
      <SwipeableRow onLongPress={onLongPress}>
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    fireEvent.touchStart(inner, { touches: [{ clientX: 50, clientY: 50 }] });
    // 300 ms in — timer is running but not yet fired
    void act(() => vi.advanceTimersByTime(300));
    // Component navigates away (unmounts) while finger is still down
    unmount();
    // The remaining 200 ms pass — timer must NOT fire after unmount
    void act(() => vi.advanceTimersByTime(200));
    expect(onLongPress).not.toHaveBeenCalled();
  });
});

describe('SwipeableRow — action reveal', () => {
  it('shows the right-swipe label while dragging right', () => {
    const { getByTestId, getByText } = render(
      <SwipeableRow onSwipeRight={vi.fn()} rightLabel="Done" leftLabel="Skip">
        <div data-testid="inner">content</div>
      </SwipeableRow>
    );
    const inner = getByTestId('inner');
    fireEvent.touchStart(inner, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(inner, { touches: [{ clientX: 40, clientY: 0 }] });
    expect(getByText('Done')).toBeTruthy();
  });
});

describe('SwipeHint', () => {
  beforeEach(() => localStorage.removeItem(SWIPE_HINT_STORAGE_KEY));

  it('renders the hint until dismissed and remembers the dismissal', () => {
    const { getByRole, queryByRole, unmount } = render(
      <SwipeHint message="Swipe right to mark done" dismissLabel="Dismiss tip" />
    );
    expect(getByRole('note').textContent).toContain('Swipe right to mark done');
    fireEvent.click(getByRole('button', { name: 'Dismiss tip' }));
    expect(queryByRole('note')).toBeNull();
    expect(localStorage.getItem(SWIPE_HINT_STORAGE_KEY)).toBe('1');
    unmount();

    const again = render(
      <SwipeHint message="Swipe right to mark done" dismissLabel="Dismiss tip" />
    );
    expect(again.queryByRole('note')).toBeNull();
  });

  it('gives the dismiss button a 44px tap target', () => {
    const { getByRole } = render(<SwipeHint message="Tip" dismissLabel="Dismiss tip" />);
    expect(getByRole('button', { name: 'Dismiss tip' }).className).toContain('size-11');
  });
});
