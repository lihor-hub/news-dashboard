// @vitest-environment happy-dom
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useInteractiveViewport } from '../lib/useInteractiveViewport';

const OPTIONS = { width: 800, height: 600 };

function makeSvg(): SVGSVGElement {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: OPTIONS.width, height: OPTIONS.height }) as DOMRect;
  return svg;
}

function mouseEvent(
  target: SVGSVGElement,
  clientX: number,
  clientY: number
): React.MouseEvent<SVGSVGElement> {
  return {
    target,
    clientX,
    clientY,
    preventDefault: () => undefined,
  } as unknown as React.MouseEvent<SVGSVGElement>;
}

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

  it('pans without crashing when mouseup lands in the same batch as mousemove', () => {
    const { result } = renderHook(() => useInteractiveViewport(OPTIONS));
    const svg = makeSvg();
    result.current.svgRef.current = svg;

    act(() => {
      result.current.svgProps.onMouseDown(mouseEvent(svg, 100, 100));
    });

    // React 18 batches both updates: the mousemove queues a viewport updater
    // and the mouseup clears the drag ref before that updater runs.
    act(() => {
      result.current.svgProps.onMouseMove(mouseEvent(svg, 130, 120));
      result.current.svgProps.onMouseUp();
    });

    expect(result.current.viewport).toEqual({ tx: 30, ty: 20, scale: 1 });
    expect(result.current.isPanning).toBe(false);
  });

  it('starts each pan from the current viewport position', () => {
    const { result } = renderHook(() => useInteractiveViewport(OPTIONS));
    const svg = makeSvg();
    result.current.svgRef.current = svg;

    act(() => {
      result.current.svgProps.onMouseDown(mouseEvent(svg, 100, 100));
    });
    act(() => {
      result.current.svgProps.onMouseMove(mouseEvent(svg, 130, 120));
    });
    act(() => {
      result.current.svgProps.onMouseUp();
    });
    expect(result.current.viewport).toEqual({ tx: 30, ty: 20, scale: 1 });

    act(() => {
      result.current.svgProps.onMouseDown(mouseEvent(svg, 200, 200));
    });
    act(() => {
      result.current.svgProps.onMouseMove(mouseEvent(svg, 210, 205));
    });
    act(() => {
      result.current.svgProps.onMouseUp();
    });
    expect(result.current.viewport).toEqual({ tx: 40, ty: 25, scale: 1 });
  });
});
