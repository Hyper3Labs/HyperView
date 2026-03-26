import type React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { EmbeddingsData } from "@/types";
import type { ScatterLabelsInfo } from "@/lib/labelLegend";
import { getLayoutDimension } from "@/lib/layouts";
import type {
  Dataset,
  Dataset3D,
  GeometryMode,
  GeometryMode3D,
  Modifiers,
  OrbitViewState3D,
  Renderer,
  Renderer3D,
} from "hyper-scatter";

type HyperScatterModule = typeof import("hyper-scatter");
type AnyRenderer = Renderer | Renderer3D;

const MAX_LASSO_VERTS = 512;
const SELECTION_HIGHLIGHT_COLOR = "#f59e0b";

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

function buildCategoryVisibilityMask(labelsInfo: ScatterLabelsInfo, labelFilter: string | null): Uint8Array {
  const mask = new Uint8Array(labelsInfo.uniqueLabels.length);

  if (!labelFilter || !labelsInfo.uniqueLabels.includes(labelFilter)) {
    mask.fill(1);
    return mask;
  }

  for (let i = 0; i < labelsInfo.uniqueLabels.length; i++) {
    mask[i] = labelsInfo.uniqueLabels[i] === labelFilter ? 1 : 0;
  }

  return mask;
}


interface UseHyperScatterArgs {
  embeddings: EmbeddingsData | null;
  labelsInfo: ScatterLabelsInfo | null;
  labelFilter: string | null;
  selectedIds: Set<string>;
  hoveredId: string | null;
  setSelectedIds: (ids: Set<string>, source?: "scatter" | "grid") => void;
  beginLassoSelection: (query: {
    layoutKey: string;
    polygon: number[];
    labelFilter: string | null;
    view3d: {
      yaw: number;
      pitch: number;
      distance: number;
      target_x: number;
      target_y: number;
      target_z: number;
      ortho_scale: number;
    } | null;
    viewportWidth: number | null;
    viewportHeight: number | null;
  }) => void;
  setHoveredId: (id: string | null) => void;
}

function resolveLayoutDimension(embeddings: EmbeddingsData): 2 | 3 {
  try {
    return getLayoutDimension(embeddings.layout_key);
  } catch {
    const first = embeddings.coords[0];
    if (Array.isArray(first) && first.length >= 3) return 3;
    return 2;
  }
}

function toModifiers(e: { shiftKey: boolean; ctrlKey: boolean; altKey: boolean; metaKey: boolean }): Modifiers {
  return {
    shift: e.shiftKey,
    ctrl: e.ctrlKey,
    alt: e.altKey,
    meta: e.metaKey,
  };
}

function toServerView3D(view: OrbitViewState3D): {
  yaw: number;
  pitch: number;
  distance: number;
  target_x: number;
  target_y: number;
  target_z: number;
  ortho_scale: number;
} {
  return {
    yaw: view.yaw,
    pitch: view.pitch,
    distance: view.distance,
    target_x: view.targetX,
    target_y: view.targetY,
    target_z: view.targetZ,
    ortho_scale: view.orthoScale,
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
  labelFilter,
  selectedIds,
  hoveredId,
  setSelectedIds,
  beginLassoSelection,
  setHoveredId,
}: UseHyperScatterArgs) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const rendererRef = useRef<AnyRenderer | null>(null);

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
  const persistentLassoRef = useRef<number[] | null>(null);

  const hoveredIndexRef = useRef<number>(-1);

  const idToIndex = useMemo(() => {
    if (!embeddings) return null;
    const m = new Map<string, number>();
    for (let i = 0; i < embeddings.ids.length; i++) {
      m.set(embeddings.ids[i], i);
    }
    return m;
  }, [embeddings]);

  const layoutDimension = useMemo(() => {
    if (!embeddings) return 2;
    return resolveLayoutDimension(embeddings);
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

  const redrawOverlay = useCallback(() => {
    if (!overlayCanvasRef.current) return;
    clearOverlay(overlayCanvasRef.current);
    const persistent = persistentLassoRef.current;
    if (persistent && persistent.length >= 6) {
      drawLassoOverlay(overlayCanvasRef.current, persistent);
    }
  }, []);

  const clearPersistentLasso = useCallback(() => {
    persistentLassoRef.current = null;
    clearOverlay(overlayCanvasRef.current);
  }, []);

  const stopInteraction = useCallback(() => {
    isPanningRef.current = false;
    isLassoingRef.current = false;
    lassoPointsRef.current = [];
    if (persistentLassoRef.current) {
      redrawOverlay();
      return;
    }
    clearOverlay(overlayCanvasRef.current);
  }, [redrawOverlay]);

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
          redrawOverlay();
        }

        // Use coords from embeddings response directly.
        const coords = embeddings.coords;
        const resolvedLayoutDimension = resolveLayoutDimension(embeddings);

        const rendererOpts = {
          width,
          height,
          devicePixelRatio: window.devicePixelRatio,
          pointRadius: 4,
          colors: labelsInfo.palette,
          backgroundColor: "#161b22", // Match HyperView theme: --card is #161b22
        };

        let renderer: AnyRenderer;

        if (resolvedLayoutDimension === 3) {
          const positions = new Float32Array(coords.length * 3);
          for (let i = 0; i < coords.length; i++) {
            if (coords[i].length < 3) {
              throw new Error(`3D layout coords must have at least 3 components (row ${i}).`);
            }
            positions[i * 3] = coords[i][0];
            positions[i * 3 + 1] = coords[i][1];
            positions[i * 3 + 2] = coords[i][2];
          }

          const geometry: GeometryMode3D =
            embeddings.geometry === "spherical" ? "sphere" : "euclidean3d";
          const dataset: Dataset3D = viz.createDataset3D(geometry, positions, labelsInfo.categories);

          renderer =
            geometry === "sphere"
              ? new viz.Spherical3DWebGLCandidate()
              : new viz.Euclidean3DWebGLCandidate();

          renderer.init(canvas, {
            ...rendererOpts,
            sphereGuideColor: "#94a3b8",
            sphereGuideOpacity: 0.2,
          });
          renderer.setDataset(dataset);
        } else {
          const positions = new Float32Array(coords.length * 2);
          for (let i = 0; i < coords.length; i++) {
            if (coords[i].length < 2) {
              throw new Error(`Layout coords must have at least 2 components (row ${i}).`);
            }
            positions[i * 2] = coords[i][0];
            positions[i * 2 + 1] = coords[i][1];
          }

          // Spherical 2D layouts currently use the planar renderer interaction model.
          const geometry: GeometryMode =
            embeddings.geometry === "poincare" ? "poincare" : "euclidean";
          const dataset: Dataset = viz.createDataset(geometry, positions, labelsInfo.categories);

          renderer =
            geometry === "euclidean" ? new viz.EuclideanWebGLCandidate() : new viz.HyperbolicWebGLCandidate();

          renderer.init(canvas, rendererOpts);
          renderer.setDataset(dataset);
        }

        rendererRef.current = renderer;

        // Apply mutable display-state contract at init so label filtering does
        // not rely on renderer recreation.
        renderer.setPalette(labelsInfo.palette);
        renderer.setCategoryVisibility(buildCategoryVisibilityMask(labelsInfo, null));
        renderer.setCategoryAlpha(1);
        renderer.setInteractionStyle({
          selectionColor: SELECTION_HIGHLIGHT_COLOR,
          hoverColor: "#ffffff",
          hoverFillColor: null,
        });

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
  }, [embeddings, labelsInfo, redrawOverlay, requestRender, stopInteraction]);

  // Runtime display-state sync (no renderer re-init).
  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer || !labelsInfo) return;

    renderer.setPalette(labelsInfo.palette);
    renderer.setCategoryVisibility(buildCategoryVisibilityMask(labelsInfo, labelFilter));
    renderer.setCategoryAlpha(1);
    renderer.setInteractionStyle({
      selectionColor: SELECTION_HIGHLIGHT_COLOR,
      hoverColor: "#ffffff",
      hoverFillColor: null,
    });

    requestRender();
  }, [labelFilter, labelsInfo, requestRender]);

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
        redrawOverlay();
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
  }, [redrawOverlay, requestRender]);

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

      if (persistentLassoRef.current) {
        clearPersistentLasso();
      }

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
    [clearPersistentLasso, getCanvasPos]
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
        const pts = lassoPointsRef.current.slice();
        persistentLassoRef.current = pts.length >= 6 ? pts : null;
        stopInteraction();
        redrawOverlay();

        if (pts.length >= 6) {
          try {
            if (layoutDimension === 3) {
              const renderer3d = renderer as Renderer3D;
              const view = renderer3d.getView();
              const rect = containerRef.current?.getBoundingClientRect();
              const viewportWidth = rect
                ? Math.max(1, Math.floor(rect.width))
                : Math.max(
                    1,
                    overlayCanvasRef.current?.clientWidth ??
                      canvasRef.current?.clientWidth ??
                      overlayCanvasRef.current?.width ??
                      canvasRef.current?.width ??
                      0
                  );
              const viewportHeight = rect
                ? Math.max(1, Math.floor(rect.height))
                : Math.max(
                    1,
                    overlayCanvasRef.current?.clientHeight ??
                      canvasRef.current?.clientHeight ??
                      overlayCanvasRef.current?.height ??
                      canvasRef.current?.height ??
                      0
                  );

              // Clear any existing manual selection highlights immediately.
              renderer.setSelection(new Set());

              // Cap vertex count to keep request payload + backend runtime bounded.
              const polygon = capInterleavedXY(pts, MAX_LASSO_VERTS);
              if (polygon.length < 6) return;

              beginLassoSelection({
                layoutKey: embeddings.layout_key,
                polygon,
                labelFilter: labelFilter ?? null,
                view3d: toServerView3D(view),
                viewportWidth,
                viewportHeight,
              });
            } else {
              const polyline = new Float32Array(pts);
              const result = renderer.lassoSelect(polyline);

              // Enter server-driven lasso mode by sending a data-space polygon.
              // Backend selection runs in the same coordinate system returned by /api/embeddings.
              const dataCoords = (result as { geometry?: { coords?: Float32Array } }).geometry?.coords;
              if (!dataCoords || dataCoords.length < 6) return;

              // Clear any existing manual selection highlights immediately.
              renderer.setSelection(new Set());

              // Cap vertex count to keep request payload + backend runtime bounded.
              const polygon = capInterleavedXY(dataCoords, MAX_LASSO_VERTS);
              if (polygon.length < 6) return;

              beginLassoSelection({
                layoutKey: embeddings.layout_key,
                polygon,
                labelFilter: labelFilter ?? null,
                view3d: null,
                viewportWidth: null,
                viewportHeight: null,
              });
            }
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
    [
      beginLassoSelection,
      embeddings,
      getCanvasPos,
      redrawOverlay,
      requestRender,
      selectedIds,
      setSelectedIds,
      stopInteraction,
      layoutDimension,
      labelFilter,
    ]
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
      clearPersistentLasso();
      stopInteraction();

      renderer.setSelection(new Set());
      setSelectedIds(new Set<string>(), "scatter");

      requestRender();
    },
    [clearPersistentLasso, requestRender, setSelectedIds, stopInteraction]
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
