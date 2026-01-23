import type React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { EmbeddingsData } from "@/types";
import type { Dataset, GeometryMode, Modifiers, Renderer } from "hyper-scatter";

type HyperScatterModule = typeof import("hyper-scatter");

export interface ScatterLabelsInfo {
  uniqueLabels: string[];
  categories: Uint16Array;
  palette: string[];
}

const MAX_LASSO_VERTS = 512;

function supportsWebGL2(): boolean {
  try {
    if (typeof document === "undefined") return false;
    const canvas = document.createElement("canvas");
    return !!canvas.getContext("webgl2");
  } catch {
    return false;
  }
}

function capInterleavedXY(points: ArrayLike<number>, maxVerts: number): number[] {
  const n = Math.floor(points.length / 2);
  if (n <= maxVerts) return Array.from(points as ArrayLike<number>);

  const out = new Array<number>(maxVerts * 2);
  for (let i = 0; i < maxVerts; i++) {
    const src = Math.floor((i * n) / maxVerts);
    out[i * 2] = points[src * 2];
    out[i * 2 + 1] = points[src * 2 + 1];
  }
  return out;
}


interface UseHyperScatterArgs {
  embeddings: EmbeddingsData | null;
  labelsInfo: ScatterLabelsInfo | null;
  selectedIds: Set<string>;
  hoveredId: string | null;
  setSelectedIds: (ids: Set<string>, source?: "scatter" | "grid") => void;
  beginLassoSelection: (query: { layoutKey: string; polygon: number[] }) => void;
  setHoveredId: (id: string | null) => void;
}

function toModifiers(e: { shiftKey: boolean; ctrlKey: boolean; altKey: boolean; metaKey: boolean }): Modifiers {
  return {
    shift: e.shiftKey,
    ctrl: e.ctrlKey,
    alt: e.altKey,
    meta: e.metaKey,
  };
}

function clearOverlay(canvas: HTMLCanvasElement | null): void {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function drawLassoOverlay(canvas: HTMLCanvasElement | null, points: number[]): void {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  clearOverlay(canvas);
  if (points.length < 6) return;

  ctx.save();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(79,70,229,0.9)"; // indigo-ish
  ctx.fillStyle = "rgba(79,70,229,0.15)";

  ctx.beginPath();
  ctx.moveTo(points[0], points[1]);
  for (let i = 2; i < points.length; i += 2) {
    ctx.lineTo(points[i], points[i + 1]);
  }
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

export function useHyperScatter({
  embeddings,
  labelsInfo,
  selectedIds,
  hoveredId,
  setSelectedIds,
  beginLassoSelection,
  setHoveredId,
}: UseHyperScatterArgs) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const rendererRef = useRef<Renderer | null>(null);

  const [rendererError, setRendererError] = useState<string | null>(null);

  const rafPendingRef = useRef(false);

  // Interaction state (refs to avoid rerender churn)
  const isPanningRef = useRef(false);
  const isLassoingRef = useRef(false);
  const pointerDownXRef = useRef(0);
  const pointerDownYRef = useRef(0);
  const lastPointerXRef = useRef(0);
  const lastPointerYRef = useRef(0);
  const lassoPointsRef = useRef<number[]>([]);

  const hoveredIndexRef = useRef<number>(-1);

  const idToIndex = useMemo(() => {
    if (!embeddings) return null;
    const m = new Map<string, number>();
    for (let i = 0; i < embeddings.ids.length; i++) {
      m.set(embeddings.ids[i], i);
    }
    return m;
  }, [embeddings]);

  const requestRender = useCallback(() => {
    if (rafPendingRef.current) return;
    rafPendingRef.current = true;

    requestAnimationFrame(() => {
      rafPendingRef.current = false;
      const renderer = rendererRef.current;
      if (!renderer) return;

      try {
        renderer.render();
      } catch (err) {
        // Avoid an exception storm that would permanently prevent the UI from updating.
        console.error("hyper-scatter renderer.render() failed:", err);
        try {
          renderer.destroy();
        } catch {
          // ignore
        }
        rendererRef.current = null;
        setRendererError(
          "This browser can't render the scatter plot (WebGL2 is required). Please use Chrome/Edge/Firefox."
        );
        clearOverlay(overlayCanvasRef.current);
        return;
      }

      if (isLassoingRef.current) {
        drawLassoOverlay(overlayCanvasRef.current, lassoPointsRef.current);
      }
    });
  }, []);

  const getCanvasPos = useCallback((e: { clientX: number; clientY: number }) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  }, []);

  const stopInteraction = useCallback(() => {
    isPanningRef.current = false;
    isLassoingRef.current = false;
    lassoPointsRef.current = [];
    clearOverlay(overlayCanvasRef.current);
  }, []);

  // Initialize renderer when embeddings change.
  useEffect(() => {
    if (!embeddings || !labelsInfo) return;
    if (!canvasRef.current || !containerRef.current) return;

    let cancelled = false;

    const init = async () => {
      // Clear any previous renderer errors when we attempt to re-init.
      setRendererError(null);

      if (!supportsWebGL2()) {
        setRendererError(
          "This browser doesn't support WebGL2, so the scatter plot can't be displayed. Please use Chrome/Edge/Firefox."
        );
        return;
      }

      try {
        const viz = (await import("hyper-scatter")) as HyperScatterModule;
        if (cancelled) return;

        const container = containerRef.current;
        const canvas = canvasRef.current;
        if (!container || !canvas) return;

        // Destroy existing renderer (if any)
        if (rendererRef.current) {
          rendererRef.current.destroy();
          rendererRef.current = null;
        }

        const rect = container.getBoundingClientRect();
        const width = Math.floor(rect.width);
        const height = Math.floor(rect.height);
        if (overlayCanvasRef.current) {
          overlayCanvasRef.current.width = Math.max(1, width);
          overlayCanvasRef.current.height = Math.max(1, height);
          overlayCanvasRef.current.style.width = `${width}px`;
          overlayCanvasRef.current.style.height = `${height}px`;
          clearOverlay(overlayCanvasRef.current);
        }

        // Use coords from embeddings response directly
        const coords = embeddings.coords;
        const positions = new Float32Array(coords.length * 2);
        for (let i = 0; i < coords.length; i++) {
          positions[i * 2] = coords[i][0];
          positions[i * 2 + 1] = coords[i][1];
        }

        const geometry = embeddings.geometry as GeometryMode;
        const dataset: Dataset = viz.createDataset(geometry, positions, labelsInfo.categories);

        const opts = {
          width,
          height,
          devicePixelRatio: window.devicePixelRatio,
          pointRadius: 4,
          colors: labelsInfo.palette,
          backgroundColor: "#161b22", // Match HyperView theme: --card is #161b22
        };

        const renderer: Renderer =
          geometry === "euclidean" ? new viz.EuclideanWebGLCandidate() : new viz.HyperbolicWebGLCandidate();

        renderer.init(canvas, opts);

        renderer.setDataset(dataset);
        rendererRef.current = renderer;

        // Force a first render to surface WebGL2 context creation failures early.
        try {
          renderer.render();
        } catch (err) {
          console.error("hyper-scatter initial render failed:", err);
          rendererRef.current = null;
          try {
            renderer.destroy();
          } catch {
            // ignore
          }
          setRendererError(
            "This browser can't render the scatter plot (WebGL2 is required). Please use Chrome/Edge/Firefox."
          );
          return;
        }

        hoveredIndexRef.current = -1;
        renderer.setHovered(-1);

        requestRender();
      } catch (err) {
        console.error("Failed to initialize hyper-scatter renderer:", err);
        setRendererError(
          "Failed to initialize the scatter renderer in this browser. Please use Chrome/Edge/Firefox."
        );
      }
    };

    init();

    return () => {
      cancelled = true;
      stopInteraction();
      if (rendererRef.current) {
        rendererRef.current.destroy();
        rendererRef.current = null;
      }
    };
  }, [embeddings, labelsInfo, requestRender, stopInteraction]);

  // Store -> renderer sync
  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer || !embeddings || !idToIndex) return;

    const indices = new Set<number>();
    for (const id of selectedIds) {
      const idx = idToIndex.get(id);
      if (typeof idx === "number") indices.add(idx);
    }

    renderer.setSelection(indices);

    const hoveredIdx = hoveredId ? (idToIndex.get(hoveredId) ?? -1) : -1;
    renderer.setHovered(hoveredIdx);
    hoveredIndexRef.current = hoveredIdx;

    requestRender();
  }, [embeddings, hoveredId, idToIndex, requestRender, selectedIds]);

  // Resize handling
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resize = () => {
      const rect = container.getBoundingClientRect();
      const width = Math.floor(rect.width);
      const height = Math.floor(rect.height);
      if (!(width > 0) || !(height > 0)) return;

      if (overlayCanvasRef.current) {
        overlayCanvasRef.current.width = Math.max(1, width);
        overlayCanvasRef.current.height = Math.max(1, height);
        overlayCanvasRef.current.style.width = `${width}px`;
        overlayCanvasRef.current.style.height = `${height}px`;
      }

      const renderer = rendererRef.current;
      if (renderer) {
        renderer.resize(width, height);
        requestRender();
      }
    };

    resize();

    const ro = new ResizeObserver(resize);
    ro.observe(container);
    return () => ro.disconnect();
  }, [requestRender]);

  // Wheel zoom (native listener so we can set passive:false)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onWheel = (e: WheelEvent) => {
      const renderer = rendererRef.current;
      if (!renderer) return;
      e.preventDefault();

      const pos = getCanvasPos(e);
      const delta = -e.deltaY / 100;
      renderer.zoom(pos.x, pos.y, delta, toModifiers(e));
      requestRender();
    };

    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [getCanvasPos, requestRender]);

  // Pointer interactions
  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const renderer = rendererRef.current;
      if (!renderer) return;

      // Left button only
      if (typeof e.button === "number" && e.button !== 0) return;

      const pos = getCanvasPos(e);
      pointerDownXRef.current = pos.x;
      pointerDownYRef.current = pos.y;
      lastPointerXRef.current = pos.x;
      lastPointerYRef.current = pos.y;

      // Shift-drag = lasso, otherwise pan.
      if (e.shiftKey) {
        isLassoingRef.current = true;
        isPanningRef.current = false;
        lassoPointsRef.current = [pos.x, pos.y];
        drawLassoOverlay(overlayCanvasRef.current, lassoPointsRef.current);
      } else {
        isPanningRef.current = true;
        isLassoingRef.current = false;
      }

      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        // ignore
      }

      e.preventDefault();
    },
    [getCanvasPos]
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const renderer = rendererRef.current;
      if (!renderer) return;

      const pos = getCanvasPos(e);

      if (isPanningRef.current) {
        const dx = pos.x - lastPointerXRef.current;
        const dy = pos.y - lastPointerYRef.current;
        lastPointerXRef.current = pos.x;
        lastPointerYRef.current = pos.y;

        renderer.pan(dx, dy, toModifiers(e));
        requestRender();
        return;
      }

      if (isLassoingRef.current) {
        const pts = lassoPointsRef.current;
        const lastX = pts[pts.length - 2] ?? pos.x;
        const lastY = pts[pts.length - 1] ?? pos.y;
        const ddx = pos.x - lastX;
        const ddy = pos.y - lastY;
        const distSq = ddx * ddx + ddy * ddy;

        // Sample at ~2px spacing
        if (distSq >= 4) {
          pts.push(pos.x, pos.y);
          drawLassoOverlay(overlayCanvasRef.current, pts);
        }
        return;
      }

      // Hover
      const hit = renderer.hitTest(pos.x, pos.y);
      const nextIndex = hit ? hit.index : -1;
      if (nextIndex === hoveredIndexRef.current) return;
      hoveredIndexRef.current = nextIndex;
      renderer.setHovered(nextIndex);

      if (!embeddings) return;
      if (nextIndex >= 0 && nextIndex < embeddings.ids.length) {
        setHoveredId(embeddings.ids[nextIndex]);
      } else {
        setHoveredId(null);
      }

      requestRender();
    },
    [embeddings, getCanvasPos, requestRender, setHoveredId]
  );

  const handlePointerUp = useCallback(
    async (e: React.PointerEvent<HTMLCanvasElement>) => {
      const renderer = rendererRef.current;
      if (!renderer || !embeddings) {
        stopInteraction();
        return;
      }

      if (isLassoingRef.current) {
        const pts = lassoPointsRef.current;
        stopInteraction();

        if (pts.length >= 6) {
          try {
            const polyline = new Float32Array(pts);
            const result = renderer.lassoSelect(polyline);

            // Enter server-driven lasso mode by sending a data-space polygon.
            // Backend selection runs in the same coordinate system returned by /api/embeddings.
            const dataCoords = result.geometry?.coords;
            if (!dataCoords || dataCoords.length < 6) return;

            // Clear any existing manual selection highlights immediately.
            renderer.setSelection(new Set());

            // Cap vertex count to keep request payload + backend runtime bounded.
            const polygon = capInterleavedXY(dataCoords, MAX_LASSO_VERTS);
            if (polygon.length < 6) return;

            beginLassoSelection({ layoutKey: embeddings.layout_key, polygon });
          } catch (err) {
            console.error("Lasso selection failed:", err);
          }
        }

        requestRender();
        return;
      }

      // Click-to-select (scatter -> image grid)
      // Only treat as a click if the pointer didn't move much (otherwise it's a pan).
      const pos = getCanvasPos(e);
      const dx = pos.x - pointerDownXRef.current;
      const dy = pos.y - pointerDownYRef.current;
      const CLICK_MAX_DIST_SQ = 36; // ~6px
      const isClick = dx * dx + dy * dy <= CLICK_MAX_DIST_SQ;

      if (isClick) {
        const hit = renderer.hitTest(pos.x, pos.y);
        const idx = hit ? hit.index : -1;

        if (idx >= 0 && idx < embeddings.ids.length) {
          const id = embeddings.ids[idx];

          if (e.metaKey || e.ctrlKey) {
            const next = new Set(selectedIds);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            setSelectedIds(next, "scatter");
          } else {
            setSelectedIds(new Set([id]), "scatter");
          }
        }
      }

      stopInteraction();
      requestRender();
    },
    [beginLassoSelection, embeddings, getCanvasPos, requestRender, selectedIds, setSelectedIds, stopInteraction]
  );

  const handlePointerLeave = useCallback(
    (_e: React.PointerEvent<HTMLCanvasElement>) => {
      const renderer = rendererRef.current;
      if (renderer) {
        hoveredIndexRef.current = -1;
        setHoveredId(null);
        renderer.setHovered(-1);
        requestRender();
      }
      stopInteraction();
    },
    [requestRender, setHoveredId, stopInteraction]
  );

  const handleDoubleClick = useCallback(
    (_e: React.MouseEvent<HTMLCanvasElement>) => {
      const renderer = rendererRef.current;
      if (!renderer) return;
      stopInteraction();

      renderer.setSelection(new Set());
      setSelectedIds(new Set<string>(), "scatter");

      requestRender();
    },
    [requestRender, setSelectedIds, stopInteraction]
  );

  return {
    canvasRef,
    overlayCanvasRef,
    containerRef,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerLeave,
    handleDoubleClick,
    rendererError,
  };
}
