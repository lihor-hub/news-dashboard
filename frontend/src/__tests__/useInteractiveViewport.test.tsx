// @vitest-environment happy-dom
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useInteractiveViewport } from '../lib/useInteractiveViewport';

const OPTIONS = { width: 800, height: 600 };

describe('useInteractiveViewport', () => {
  it('creates a fresh non-null viewport for every mount and reset', () => {
    const first = renderHook(() => useInteractiveViewport(OPTIONS));

    first.result.current.viewport.tx = 42;
    first.result.current.viewport.ty = 24;
    first.result.current.viewport.scale = 2;
    first.unmount();

    const second = renderHook(() => useInteractiveViewport(OPTIONS));
    expect(second.result.current.viewport).toEqual({ tx: 0, ty: 0, scale: 1 });

    second.result.current.viewport.tx = 12;
    act(() => second.result.current.resetViewport());

    expect(second.result.current.viewport).toEqual({ tx: 0, ty: 0, scale: 1 });
  });
});
