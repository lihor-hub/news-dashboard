import { useCallback, useRef, useState } from 'react';

export interface Viewport {
  /** SVG translate-x in canvas coordinates */
  tx: number;
  /** SVG translate-y in canvas coordinates */
  ty: number;
  /** Zoom scale factor */
  scale: number;
}

export interface UseInteractiveViewportOptions {
  minScale?: number;
  maxScale?: number;
  /** Canvas width in SVG user units */
  width: number;
  /** Canvas height in SVG user units */
  height: number;
}

export interface UseInteractiveViewportReturn {
  viewport: Viewport;
  /** Ref to attach to the SVG element */
  svgRef: React.RefObject<SVGSVGElement | null>;
  /** Props to spread onto the SVG element */
  svgProps: {
    onMouseDown: (e: React.MouseEvent<SVGSVGElement>) => void;
    onMouseMove: (e: React.MouseEvent<SVGSVGElement>) => void;
    onMouseUp: () => void;
    onMouseLeave: () => void;
    onWheel: (e: React.WheelEvent<SVGSVGElement>) => void;
  };
  /** Panning is active (use to change cursor) */
  isPanning: boolean;
  resetViewport: () => void;
  /** Convert a client-space point to SVG canvas coordinates */
  clientToCanvas: (clientX: number, clientY: number) => { x: number; y: number };
}

const INITIAL: Viewport = { tx: 0, ty: 0, scale: 1 };

export function useInteractiveViewport({
  minScale = 0.2,
  maxScale = 5,
  width,
  height,
}: UseInteractiveViewportOptions): UseInteractiveViewportReturn {
  const [viewport, setViewport] = useState<Viewport>(INITIAL);
  const [isPanning, setIsPanning] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Track pointer during drag
  const dragStart = useRef<{ clientX: number; clientY: number; tx: number; ty: number } | null>(
    null
  );

  // Convert client coords → canvas coords
  const clientToCanvas = useCallback(
    (clientX: number, clientY: number): { x: number; y: number } => {
      const svg = svgRef.current;
      if (!svg) return { x: 0, y: 0 };
      const rect = svg.getBoundingClientRect();
      const scaleX = width / rect.width;
      const scaleY = height / rect.height;
      return {
        x: (clientX - rect.left) * scaleX,
        y: (clientY - rect.top) * scaleY,
      };
    },
    [width, height]
  );

  const onMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    // Only pan on the background (target is the SVG or a <rect> backdrop)
    const tag = (e.target as SVGElement).tagName.toLowerCase();
    if (tag !== 'svg' && tag !== 'rect' && tag !== 'line' && tag !== 'path') return;
    e.preventDefault();
    dragStart.current = {
      clientX: e.clientX,
      clientY: e.clientY,
      tx: 0,
      ty: 0,
    };
    setViewport((v) => {
      dragStart.current = {
        clientX: e.clientX,
        clientY: e.clientY,
        tx: v.tx,
        ty: v.ty,
      };
      return v;
    });
    setIsPanning(true);
  }, []);

  const onMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (!dragStart.current) return;
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const scaleX = width / rect.width;
      const scaleY = height / rect.height;
      const dx = (e.clientX - dragStart.current.clientX) * scaleX;
      const dy = (e.clientY - dragStart.current.clientY) * scaleY;
      setViewport((v) => ({
        ...v,
        tx: dragStart.current!.tx + dx,
        ty: dragStart.current!.ty + dy,
      }));
    },
    [width, height]
  );

  const onMouseUp = useCallback(() => {
    dragStart.current = null;
    setIsPanning(false);
  }, []);

  const onMouseLeave = useCallback(() => {
    dragStart.current = null;
    setIsPanning(false);
  }, []);

  const onWheel = useCallback(
    (e: React.WheelEvent<SVGSVGElement>) => {
      e.preventDefault();
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const scaleX = width / rect.width;
      const scaleY = height / rect.height;
      // Pivot around the cursor position in canvas space
      const pivotX = (e.clientX - rect.left) * scaleX;
      const pivotY = (e.clientY - rect.top) * scaleY;
      const delta = e.deltaY < 0 ? 1.1 : 1 / 1.1;

      setViewport((v) => {
        const newScale = Math.min(maxScale, Math.max(minScale, v.scale * delta));
        const ratio = newScale / v.scale;
        return {
          scale: newScale,
          tx: pivotX - ratio * (pivotX - v.tx),
          ty: pivotY - ratio * (pivotY - v.ty),
        };
      });
    },
    [width, height, minScale, maxScale]
  );

  const resetViewport = useCallback(() => setViewport(INITIAL), []);

  return {
    viewport,
    svgRef,
    svgProps: { onMouseDown, onMouseMove, onMouseUp, onMouseLeave, onWheel },
    isPanning,
    resetViewport,
    clientToCanvas,
  };
}
