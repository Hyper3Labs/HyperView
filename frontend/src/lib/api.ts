import type {
  DatasetInfo,
  EmbeddingsData,
  RuntimeCollection,
  RuntimePanelDirection,
  RuntimePanelPosition,
  RuntimeSnapshot,
  Sample,
  SamplesResponse,
  SimilaritySearchResponse,
} from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_HYPERVIEW_API_BASE ??
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:6262" : "");
const MISSING_LABEL_SENTINEL = "undefined";
const READ_ONLY_DEMO_NOTICE = "Read-only demo — pip install hyperview for the full workbench";
const RUNTIME_CLIENT_ID = `hv-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
const SAMPLE_BATCH_SIZE = 1000;

declare global {
  interface Window {
    __HYPERVIEW_STATIC__?: boolean;
  }
}

export function apiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}/api${normalizedPath}`;
}

export function backendUrl(pathOrUrl: string | null | undefined): string | null {
  if (!pathOrUrl) return null;
  if (/^https?:\/\//.test(pathOrUrl)) return pathOrUrl;
  if (isStaticBundle() && pathOrUrl.startsWith("/api/")) {
    return staticAssetUrl(pathOrUrl.slice(1).split("?")[0]);
  }
  if (pathOrUrl.startsWith("/api/")) return `${API_BASE}${pathOrUrl}`;
  return pathOrUrl;
}

export function isStaticBundle(): boolean {
  return typeof window !== "undefined" && window.__HYPERVIEW_STATIC__ === true;
}

export function showReadOnlyNotice(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent("hyperview-readonly-notice", {
      detail: { message: READ_ONLY_DEMO_NOTICE },
    })
  );
}

function staticAssetUrl(path: string): string {
  const normalized = path.replace(/^\/+/, "");
  return new URL(normalized, window.location.href).toString();
}

async function fetchStaticJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(staticAssetUrl(path), signal ? { signal } : undefined);
  if (!res.ok) {
    await throwApiError(res, `Failed to fetch static asset ${path}`);
  }
  return (await res.json()) as T;
}

function toApiLabel(label: string | null | undefined): string | null {
  if (!label || label === MISSING_LABEL_SENTINEL) {
    return null;
  }
  return label;
}

function isMissingLabelFilter(label: string | null | undefined): boolean {
  return label === MISSING_LABEL_SENTINEL;
}

export class ApiError extends Error {
  status: number;
  detail: string | null;

  constructor(message: string, status: number, detail: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function isLayoutNotFoundError(error: unknown): error is ApiError {
  return (
    error instanceof ApiError &&
    error.status === 404 &&
    typeof error.detail === "string" &&
    error.detail.includes("Layout not found")
  );
}

async function readErrorDetail(res: Response): Promise<string | null> {
  try {
    const contentType = res.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const payload = await res.json();
      if (typeof payload?.detail === "string") return payload.detail;
      return JSON.stringify(payload);
    }

    const text = await res.text();
    return text.trim() || null;
  } catch {
    return null;
  }
}

async function throwApiError(res: Response, context: string): Promise<never> {
  const detail = await readErrorDetail(res);
  const suffix = detail ? ` (${detail})` : "";
  throw new ApiError(`${context}: ${res.status} ${res.statusText}${suffix}`.trim(), res.status, detail);
}

export function getRuntimeClientId(): string {
  return RUNTIME_CLIENT_ID;
}

export function getRuntimeEventsUrl(): string {
  return `${apiUrl("/events")}?client_id=${encodeURIComponent(RUNTIME_CLIENT_ID)}`;
}

export interface ControlCommandResult {
  ok: boolean;
  command: string;
  result?: {
    panel_id?: string;
    collection_id?: string | null;
    collection?: RuntimeCollection | null;
    [key: string]: unknown;
  };
  workspace?: RuntimeSnapshot["workspace"];
  snapshot?: RuntimeSnapshot;
  revision?: number;
  error?: {
    code: string;
    message: string;
  };
}

export async function runControlCommand(args: {
  command: string;
  target?: Record<string, unknown>;
  args?: Record<string, unknown>;
}): Promise<ControlCommandResult> {
  if (isStaticBundle()) {
    return runStaticControlCommand(args);
  }
  const res = await fetch(apiUrl("/control/commands/run"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      command: args.command,
      target: args.target ?? {},
      args: args.args ?? {},
    }),
  });
  if (!res.ok) {
    await throwApiError(res, `Failed to run command ${args.command}`);
  }
  const payload = (await res.json()) as ControlCommandResult;
  if (payload.ok === false) {
    const message = payload.error?.message ?? "Command failed";
    const code = payload.error?.code ?? "unknown_error";
    throw new ApiError(`Command ${args.command} failed: ${code}: ${message}`, 400, message);
  }
  return payload;
}

export function runtimeSnapshotFromCommandResult(
  payload: ControlCommandResult,
  context: string = "Command did not return a runtime snapshot"
): RuntimeSnapshot {
  if (payload.snapshot) return payload.snapshot;
  throw new ApiError(context, 500, context);
}

export async function fetchDataset(signal?: AbortSignal): Promise<DatasetInfo> {
  if (isStaticBundle()) {
    return fetchStaticJson<DatasetInfo>("api/dataset.json", signal);
  }
  const res = await fetch(apiUrl("/dataset"), signal ? { signal } : undefined);
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch dataset");
  }
  return res.json();
}

export async function fetchRuntimeState(workspaceId?: string | null): Promise<RuntimeSnapshot> {
  if (isStaticBundle()) {
    const snapshot = await fetchStaticJson<RuntimeSnapshot>("api/runtime.json");
    staticRuntimeSnapshot = snapshot;
    return snapshot;
  }
  const params = new URLSearchParams();
  if (workspaceId) {
    params.set("workspace_id", workspaceId);
  }
  const query = params.toString();
  const res = await fetch(`${apiUrl("/runtime")}${query ? `?${query}` : ""}`);
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch runtime state");
  }
  return res.json();
}

export async function setLabelFilterCollection(args: {
  workspaceId: string;
  field?: string;
  value?: string | null;
  clear?: boolean;
}): Promise<RuntimeSnapshot> {
  const payload = await runControlCommand({
    command: "collection.filter.set",
    target: { workspace_id: args.workspaceId },
    args: {
      field: args.field ?? "label",
      ...(args.clear ? { clear: true } : { value: toApiLabel(args.value) }),
      source: "frontend",
    },
  });
  return runtimeSnapshotFromCommandResult(payload, "Label filter command did not return a runtime snapshot");
}

export async function setActiveWorkspace(workspaceId: string): Promise<RuntimeSnapshot> {
  if (isStaticBundle()) {
    showReadOnlyNotice();
    return fetchRuntimeState(workspaceId);
  }
  const res = await fetch(apiUrl("/control/workspaces/set-active"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to set active workspace");
  }
  return fetchRuntimeState();
}

export async function addRuntimePanel(args: {
  workspaceId: string;
  panelId: string;
  title?: string | null;
  kind?: "extension" | "scatter" | "builtin";
  builtinPanel?: string | null;
  extension?: string | null;
  extensionPanel?: string | null;
  layoutKey?: string | null;
  position?: RuntimePanelPosition;
  referencePanelId?: string | null;
  direction?: RuntimePanelDirection | null;
  width?: number | null;
  height?: number | null;
  minWidth?: number | null;
  minHeight?: number | null;
  maxWidth?: number | null;
  maxHeight?: number | null;
  visible?: boolean;
  props?: Record<string, unknown> | null;
}): Promise<RuntimeSnapshot> {
  const payload = await runControlCommand({
    command: "workspace.panel.add",
    target: { workspace_id: args.workspaceId },
    args: {
      panel_id: args.panelId,
      title: args.title ?? null,
      kind: args.kind ?? "extension",
      builtin_panel: args.builtinPanel ?? null,
      extension: args.extension ?? null,
      extension_panel: args.extensionPanel ?? null,
      layout_key: args.layoutKey ?? null,
      position: args.position ?? "right",
      reference_panel_id: args.referencePanelId ?? null,
      direction: args.direction ?? null,
      width: args.width ?? null,
      height: args.height ?? null,
      min_width: args.minWidth ?? null,
      min_height: args.minHeight ?? null,
      max_width: args.maxWidth ?? null,
      max_height: args.maxHeight ?? null,
      visible: args.visible ?? true,
      props: args.props ?? null,
    },
  });
  return runtimeSnapshotFromCommandResult(payload, "Add panel command did not return a runtime snapshot");
}

export async function removeRuntimePanel(args: {
  workspaceId: string;
  panelId: string;
}): Promise<RuntimeSnapshot> {
  const payload = await runControlCommand({
    command: "workspace.panel.remove",
    target: {
      workspace_id: args.workspaceId,
      panel_id: args.panelId,
    },
  });
  return runtimeSnapshotFromCommandResult(payload, "Remove panel command did not return a runtime snapshot");
}

export async function fetchSamples(
  offset: number = 0,
  limit: number = 100,
  label?: string,
  signal?: AbortSignal,
  includeThumbnails: boolean = false
): Promise<SamplesResponse> {
  if (isStaticBundle()) {
    const allSamples = await loadStaticSamples(signal);
    const apiLabel = toApiLabel(label);
    const filtered = allSamples.filter((sample) => {
      if (isMissingLabelFilter(label)) return sample.label === null || sample.label === undefined;
      if (apiLabel !== null) return sample.label === apiLabel;
      return true;
    });
    return {
      total: filtered.length,
      offset,
      limit,
      samples: filtered.slice(offset, offset + limit),
    };
  }
  const apiLabel = toApiLabel(label);
  const params = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
    include_thumbnails: String(includeThumbnails),
  });
  if (isMissingLabelFilter(label)) {
    params.set("missing_label", "true");
  } else if (apiLabel !== null) {
    params.set("label", apiLabel);
  }

  const res = await fetch(`${apiUrl("/samples")}?${params}`, signal ? { signal } : undefined);
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch samples");
  }
  return res.json();
}

export async function fetchEmbeddings(layoutKey?: string): Promise<EmbeddingsData> {
  if (isStaticBundle()) {
    const file = layoutKey
      ? `api/embeddings/${encodeURIComponent(layoutKey)}.json`
      : "api/embeddings/default.json";
    return fetchStaticJson<EmbeddingsData>(file);
  }
  const params = new URLSearchParams();
  if (layoutKey) {
    params.set("layout_key", layoutKey);
  }
  const query = params.toString();
  const res = await fetch(`${apiUrl("/embeddings")}${query ? `?${query}` : ""}`);
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch embeddings");
  }
  return res.json();
}

export async function fetchSamplesBatch(
  sampleIds: string[],
  args: {
    includeThumbnails?: boolean;
    workspaceId?: string | null;
  } = {}
): Promise<Sample[]> {
  if (sampleIds.length === 0) return [];
  if (isStaticBundle()) {
    const allSamples = await loadStaticSamples();
    const byId = new Map(allSamples.map((sample) => [sample.id, sample]));
    return sampleIds.map((id) => byId.get(id)).filter((sample): sample is Sample => Boolean(sample));
  }

  const samples: Sample[] = [];
  for (let offset = 0; offset < sampleIds.length; offset += SAMPLE_BATCH_SIZE) {
    const batchIds = sampleIds.slice(offset, offset + SAMPLE_BATCH_SIZE);
    const params = new URLSearchParams();
    if (args.workspaceId) {
      params.set("workspace_id", args.workspaceId);
    }
    const query = params.toString();
    const res = await fetch(`${apiUrl("/samples/batch")}${query ? `?${query}` : ""}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sample_ids: batchIds,
        include_thumbnails: args.includeThumbnails ?? false,
      }),
    });
    if (!res.ok) {
      await throwApiError(res, "Failed to fetch samples batch");
    }
    const data = await res.json();
    samples.push(...data.samples);
  }
  return samples;
}

export interface CollectionItem {
  sample: Sample;
  score: number | null;
}

export interface CollectionItemsPage {
  collectionId: string;
  offset: number;
  limit: number;
  total: number;
  hasMore: boolean;
  items: CollectionItem[];
}

interface StaticCollectionItemsFile {
  collection_id: string;
  total: number;
  items: Array<{
    sample_id: string;
    rank: number;
    score: number | null;
    sample: Sample;
  }>;
}

export async function fetchCollectionItems(
  collectionId: string,
  args: {
    workspaceId?: string | null;
    offset?: number;
    limit?: number;
    includeThumbnails?: boolean;
    signal?: AbortSignal;
  } = {}
): Promise<CollectionItemsPage> {
  const offset = args.offset ?? 0;
  const limit = args.limit ?? 100;

  if (isStaticBundle()) {
    const payload = await fetchStaticJson<StaticCollectionItemsFile>(
      `api/collections/${encodeURIComponent(collectionId)}/items.json`,
      args.signal
    );
    const rows = payload.items.slice(offset, offset + limit);
    return {
      collectionId: payload.collection_id,
      offset,
      limit,
      total: payload.total,
      hasMore: offset + limit < payload.total,
      items: rows.map((row) => ({ sample: row.sample, score: row.score ?? null })),
    };
  }

  const params = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
    include_thumbnails: String(args.includeThumbnails ?? false),
  });
  if (args.workspaceId) {
    params.set("workspace_id", args.workspaceId);
  }
  const res = await fetch(
    `${apiUrl(`/collections/${encodeURIComponent(collectionId)}/items`)}?${params}`,
    args.signal ? { signal: args.signal } : undefined
  );
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch collection items");
  }
  const data = await res.json();
  return {
    collectionId: data.collection_id,
    offset: data.offset,
    limit: data.limit,
    total: data.total,
    hasMore: Boolean(data.has_more),
    items: (data.items as Array<Record<string, unknown>>).map((item) => {
      const { score, ...sample } = item;
      return {
        sample: sample as unknown as Sample,
        score: typeof score === "number" ? score : null,
      };
    }),
  };
}

export async function fetchSimilarSamples(
  sampleId: string,
  args: {
    k?: number;
    spaceKey?: string;
    layoutKey?: string;
    includeThumbnails?: boolean;
    signal?: AbortSignal;
  } = {}
): Promise<SimilaritySearchResponse> {
  if (isStaticBundle()) {
    const dataset = await fetchDataset(args.signal);
    let spaceKey = args.spaceKey ?? null;
    if (args.layoutKey) {
      const layout = dataset.layouts.find((item) => item.layout_key === args.layoutKey);
      if (layout) spaceKey = layout.space_key;
    }
    const file = `api/search/similar/${encodeURIComponent(sampleId)}/${encodeURIComponent(spaceKey ?? "default")}.json`;
    const payload = await fetchStaticJson<SimilaritySearchResponse>(file, args.signal);
    const k = args.k ?? 10;
    return {
      ...payload,
      k,
      results: payload.results.slice(0, k),
    };
  }
  const params = new URLSearchParams({
    k: String(args.k ?? 10),
  });
  if (args.spaceKey) {
    params.set("space_key", args.spaceKey);
  }
  if (args.layoutKey) {
    params.set("layout_key", args.layoutKey);
  }
  if (args.includeThumbnails !== undefined) {
    params.set("include_thumbnails", String(args.includeThumbnails));
  }

  const res = await fetch(
    `${apiUrl(`/search/similar/${encodeURIComponent(sampleId)}`)}?${params.toString()}`,
    {
      signal: args.signal,
    }
  );
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch similar samples");
  }
  return res.json();
}

export async function fetchTextSimilarSamples(
  queryText: string,
  args: {
    k?: number;
    spaceKey?: string;
    layoutKey?: string;
    includeThumbnails?: boolean;
    signal?: AbortSignal;
  } = {}
): Promise<SimilaritySearchResponse> {
  if (isStaticBundle()) {
    throw new ApiError("Text search is not available in read-only static demos", 400, null);
  }
  const res = await fetch(apiUrl("/search/text"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query_text: queryText,
      k: args.k ?? 10,
      space_key: args.spaceKey ?? null,
      layout_key: args.layoutKey ?? null,
      include_thumbnails: args.includeThumbnails ?? false,
    }),
    signal: args.signal,
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch text search results");
  }
  return res.json();
}

export interface LassoSelectionResponse {
  total: number;
  offset: number;
  limit: number;
  sample_ids: string[];
  samples: Sample[];
}

export interface OrbitView3DRequest {
  yaw: number;
  pitch: number;
  distance: number;
  target_x: number;
  target_y: number;
  target_z: number;
  ortho_scale: number;
}

export async function setLayoutView(args: {
  workspaceId: string;
  layoutKey: string;
  camera3d?: OrbitView3DRequest | null;
}): Promise<void> {
  if (isStaticBundle()) {
    return;
  }
  const res = await fetch(apiUrl("/control/ui/layout-view"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      workspace_id: args.workspaceId,
      layout_key: args.layoutKey,
      camera_3d: args.camera3d ?? null,
    }),
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to persist layout view");
  }
}

export async function fetchLassoSelection(args: {
  layoutKey: string;
  polygon: ArrayLike<number>;
  labelFilter?: string;
  view3d?: OrbitView3DRequest | null;
  viewportWidth?: number | null;
  viewportHeight?: number | null;
  offset?: number;
  limit?: number;
  includeThumbnails?: boolean;
  signal?: AbortSignal;
}): Promise<LassoSelectionResponse> {
  if (isStaticBundle()) {
    return fetchStaticLassoSelection(args);
  }
  const res = await fetch(apiUrl("/selection/lasso"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      layout_key: args.layoutKey,
      polygon: Array.from(args.polygon),
      view_3d: args.view3d ?? null,
      viewport_width: args.viewportWidth ?? null,
      viewport_height: args.viewportHeight ?? null,
      label_filter: toApiLabel(args.labelFilter),
      missing_label_filter: isMissingLabelFilter(args.labelFilter),
      offset: args.offset ?? 0,
      limit: args.limit ?? 100,
      include_thumbnails: args.includeThumbnails ?? false,
    }),
    signal: args.signal,
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch lasso selection");
  }
  return res.json();
}

let staticRuntimeSnapshot: RuntimeSnapshot | null = null;
let staticSamplesCache: Sample[] | null = null;

interface StaticSamplesIndex {
  total: number;
  shard_size: number;
  shards: string[];
}

async function loadStaticSamples(signal?: AbortSignal): Promise<Sample[]> {
  if (staticSamplesCache) return staticSamplesCache;
  const index = await fetchStaticJson<StaticSamplesIndex>("api/samples/index.json", signal);
  const shards = await Promise.all(
    index.shards.map((shard) =>
      fetchStaticJson<SamplesResponse>(`api/samples/${shard}`, signal)
    )
  );
  staticSamplesCache = shards.flatMap((shard) => shard.samples);
  return staticSamplesCache;
}

function mergePatch(
  current: Record<string, unknown>,
  patch: Record<string, unknown>
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...current };
  for (const [key, value] of Object.entries(patch)) {
    if (value === null) {
      delete next[key];
    } else if (
      typeof value === "object" &&
      value !== null &&
      !Array.isArray(value) &&
      typeof next[key] === "object" &&
      next[key] !== null &&
      !Array.isArray(next[key])
    ) {
      next[key] = mergePatch(next[key] as Record<string, unknown>, value as Record<string, unknown>);
    } else {
      next[key] = value;
    }
  }
  return next;
}

async function getStaticSnapshot(): Promise<RuntimeSnapshot> {
  if (staticRuntimeSnapshot) return staticRuntimeSnapshot;
  return fetchRuntimeState();
}

async function runStaticControlCommand(args: {
  command: string;
  target?: Record<string, unknown>;
  args?: Record<string, unknown>;
}): Promise<ControlCommandResult> {
  const snapshot = await getStaticSnapshot();
  if (args.command === "workspace.panel.state.patch") {
    const panelId = typeof args.target?.panel_id === "string" ? args.target.panel_id : null;
    const patch = args.args?.state;
    if (panelId && patch && typeof patch === "object" && !Array.isArray(patch)) {
      const panels = { ...(snapshot.workspace.ui.panels ?? {}) };
      const current = panels[panelId] ?? { state: {}, state_revision: 0 };
      const replaceState = args.args?.replace_state === true;
      const nextState = replaceState
        ? { ...(patch as Record<string, unknown>) }
        : mergePatch(current.state ?? {}, patch as Record<string, unknown>);
      const nextEntry = {
        state: nextState,
        state_revision: (current.state_revision ?? 0) + 1,
      };
      panels[panelId] = nextEntry;
      const customPanels = snapshot.workspace.ui.custom_panels.map((panel) =>
        panel.id === panelId
          ? { ...panel, state: nextState, state_revision: nextEntry.state_revision }
          : panel
      );
      staticRuntimeSnapshot = {
        ...snapshot,
        version: snapshot.version + 1,
        workspace: {
          ...snapshot.workspace,
          ui: {
            ...snapshot.workspace.ui,
            panels,
            custom_panels: customPanels,
          },
        },
      };
      return {
        ok: true,
        command: args.command,
        result: nextEntry,
        snapshot: staticRuntimeSnapshot,
        workspace: staticRuntimeSnapshot.workspace,
        revision: nextEntry.state_revision,
      };
    }
  }

  showReadOnlyNotice();
  return {
    ok: true,
    command: args.command,
    result: {},
    snapshot,
    workspace: snapshot.workspace,
    revision: snapshot.workspace.ui.view_revision,
  };
}

async function fetchStaticLassoSelection(args: {
  layoutKey: string;
  polygon: ArrayLike<number>;
  labelFilter?: string;
  view3d?: OrbitView3DRequest | null;
  viewportWidth?: number | null;
  viewportHeight?: number | null;
  offset?: number;
  limit?: number;
  includeThumbnails?: boolean;
  signal?: AbortSignal;
}): Promise<LassoSelectionResponse> {
  const embeddings = await fetchEmbeddings(args.layoutKey);
  if (embeddings.coords[0]?.length !== 2) {
    return {
      total: 0,
      offset: args.offset ?? 0,
      limit: args.limit ?? 100,
      sample_ids: [],
      samples: [],
    };
  }
  const polygon = Array.from(args.polygon);
  const selectedIds: string[] = [];
  for (let index = 0; index < embeddings.ids.length; index += 1) {
    const coord = embeddings.coords[index];
    const label = embeddings.labels[index];
    if (isMissingLabelFilter(args.labelFilter)) {
      if (label !== null && label !== undefined) continue;
    } else {
      const apiLabel = toApiLabel(args.labelFilter);
      if (apiLabel !== null && label !== apiLabel) continue;
    }
    if (pointInPolygon(coord[0], coord[1], polygon)) {
      selectedIds.push(embeddings.ids[index]);
    }
  }
  const offset = args.offset ?? 0;
  const limit = args.limit ?? 100;
  const pageIds = selectedIds.slice(offset, offset + limit);
  const samples = await fetchSamplesBatch(pageIds, { includeThumbnails: args.includeThumbnails });
  return {
    total: selectedIds.length,
    offset,
    limit,
    sample_ids: pageIds,
    samples,
  };
}

function pointInPolygon(x: number, y: number, polygon: number[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 2; i < polygon.length; j = i, i += 2) {
    const xi = polygon[i];
    const yi = polygon[i + 1];
    const xj = polygon[j];
    const yj = polygon[j + 1];
    const intersects = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}
