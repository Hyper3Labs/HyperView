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
  process.env.NEXT_PUBLIC_HYPERVIEW_API_BASE ?? "";
const MISSING_LABEL_SENTINEL = "undefined";
const READ_ONLY_DEMO_NOTICE = "Static Space";
const RUNTIME_CLIENT_ID = `hv-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
const SAMPLE_BATCH_SIZE = 1000;
/**
 * The panel id the workspace's default Samples panel owns.
 *
 * The runtime spells this `hv.ui.SAMPLES_PANEL_ID` (SAMPLES_PANEL_STATE_ID in
 * src/hyperview/runtime.py); panel modules read it off the SDK global as
 * `sdk.constants.SAMPLES_PANEL_ID` instead of copying the literal.
 */
export const SAMPLES_PANEL_ID = "samples";
const SAMPLES_PANEL_STATE_ID = SAMPLES_PANEL_ID;
// Keep in sync with SAMPLES_PANEL_STATE_ALIASES in src/hyperview/runtime.py.
const SAMPLES_PANEL_STATE_ALIASES = new Set([SAMPLES_PANEL_STATE_ID, "grid"]);
const SESSION_TOKEN_STORAGE_KEY = "hyperview.session-token";
const MUTATING_METHODS = new Set(["POST", "PATCH", "DELETE"]);

let sessionToken: string | null = null;

declare global {
  interface Window {
    __HYPERVIEW_STATIC__?: boolean;
  }
}

function captureSessionToken(): void {
  if (typeof window === "undefined") return;

  const url = new URL(window.location.href);
  const urlToken = url.searchParams.get("token");
  if (urlToken) {
    sessionToken = urlToken;
    try {
      window.sessionStorage.setItem(SESSION_TOKEN_STORAGE_KEY, urlToken);
    } catch {
      // In-memory auth still works when storage is unavailable.
    }
    url.searchParams.delete("token");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    return;
  }

  try {
    sessionToken = window.sessionStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
  } catch {
    sessionToken = null;
  }
}

captureSessionToken();

function isApiRequest(input: RequestInfo | URL): boolean {
  const rawUrl = input instanceof Request ? input.url : String(input);
  try {
    return new URL(rawUrl, window.location.origin).pathname.startsWith("/api/");
  } catch {
    return rawUrl.startsWith("/api/") || rawUrl.includes("/api/");
  }
}

/** Central request path for every mutating HyperView API call. */
export function apiRequest(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
  const headers = new Headers(input instanceof Request ? input.headers : undefined);
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));

  if (sessionToken && MUTATING_METHODS.has(method) && isApiRequest(input)) {
    headers.set("Authorization", `Bearer ${sessionToken}`);
  }

  return fetch(input, { ...init, headers });
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
  // Resolve against the document itself, so a bundle works wherever it is
  // published without being told its own URL prefix at build time.
  return new URL(path.replace(/^\/+/, ""), window.location.href).toString();
}

function resolveStaticSampleUrls(sample: Sample): Sample {
  if (!isStaticBundle()) return sample;
  return {
    ...sample,
    thumbnail: backendUrl(sample.thumbnail),
    media_url: backendUrl(sample.media_url),
    thumbnail_url: backendUrl(sample.thumbnail_url),
  };
}

async function fetchStaticJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  // Exported workspace state keeps stable filenames across deployments. Ask
  // browsers/CDNs to revalidate JSON so a newly published Static Space cannot
  // combine a fresh hashed frontend with stale runtime or collection state.
  const res = await fetch(staticAssetUrl(path), {
    cache: "no-cache",
    ...(signal ? { signal } : {}),
  });
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

export interface StaticBundleManifest {
  schema_version: number;
  kind: "hyperview-static-space" | string;
  static: boolean;
  capabilities: {
    sample_similarity?: boolean;
    [key: string]: unknown;
  };
}

let staticBundleManifestPromise: Promise<StaticBundleManifest> | null = null;

/** Read deployment capabilities declared by a Static Space export. */
export function fetchStaticBundleManifest(): Promise<StaticBundleManifest | null> {
  if (!isStaticBundle()) return Promise.resolve(null);
  staticBundleManifestPromise ??= fetchStaticJson<StaticBundleManifest>(
    "hyperview-static.json"
  );
  return staticBundleManifestPromise;
}

export interface ToolMetadata {
  uri: string;
  description: string | null;
  extension: string | null;
  signature: Record<string, unknown>;
}

interface ToolRunResponse<T = unknown> {
  ok: boolean;
  result?: T;
  error?: string;
}

export async function runControlCommand(args: {
  command: string;
  target?: Record<string, unknown>;
  args?: Record<string, unknown>;
}): Promise<ControlCommandResult> {
  if (isStaticBundle()) {
    return runStaticControlCommand(args);
  }
  const res = await apiRequest(apiUrl("/control/commands/run"), {
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

export async function listTools(): Promise<ToolMetadata[]> {
  if (isStaticBundle()) {
    throw new ApiError(
      "Tools require the HyperView server and are unavailable in static exports.",
      400,
      null
    );
  }
  const res = await apiRequest(apiUrl("/tools"), {
    headers: {
      Accept: "application/json",
    },
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to list tools");
  }
  const payload = (await res.json()) as { tools: ToolMetadata[] };
  return payload.tools;
}

export async function runTool<T = unknown>(
  tool: string,
  workspaceId: string,
  params: Record<string, unknown> = {}
): Promise<T> {
  if (isStaticBundle()) {
    throw new ApiError(
      "Tools require the HyperView server and are unavailable in static exports.",
      400,
      null
    );
  }
  const res = await apiRequest(apiUrl("/tools/run"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      tool,
      workspace_id: workspaceId,
      params,
    }),
  });
  if (!res.ok) {
    await throwApiError(res, `Failed to run tool ${tool}`);
  }
  const payload = (await res.json()) as ToolRunResponse<T>;
  if (payload.ok === false) {
    const message = payload.error ?? "Tool execution failed.";
    throw new ApiError(`Tool ${tool} failed: ${message}`, 400, message);
  }
  return payload.result as T;
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
    if (staticRuntimeSnapshot) return staticRuntimeSnapshot;
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
  /** The panel whose sample view the filtered collection lands in. Omit for the Samples panel. */
  panelId?: string | null;
  field?: string;
  value?: string | null;
  clear?: boolean;
}): Promise<RuntimeSnapshot> {
  const payload = await runControlCommand({
    command: "collection.filter.set",
    target: {
      workspace_id: args.workspaceId,
      ...(args.panelId ? { panel_id: args.panelId } : {}),
    },
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
  const payload = await runControlCommand({
    command: "workspace.activate",
    target: { workspace_id: workspaceId },
  });
  return runtimeSnapshotFromCommandResult(
    payload,
    "Workspace activation command did not return a runtime snapshot"
  );
}

export async function addRuntimePanel(args: {
  workspaceId: string;
  panelId: string;
  title?: string | null;
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
    return fetchStaticSamplesPage(offset, limit, label, signal);
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
    return fetchStaticSamplesByIds(sampleIds);
  }

  const samples: Sample[] = [];
  for (let offset = 0; offset < sampleIds.length; offset += SAMPLE_BATCH_SIZE) {
    const batchIds = sampleIds.slice(offset, offset + SAMPLE_BATCH_SIZE);
    const params = new URLSearchParams();
    if (args.workspaceId) {
      params.set("workspace_id", args.workspaceId);
    }
    const query = params.toString();
    const res = await apiRequest(`${apiUrl("/samples/batch")}${query ? `?${query}` : ""}`, {
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
    const ephemeralCollection = await getStaticEphemeralCollection(collectionId);
    if (ephemeralCollection) {
      return fetchStaticEphemeralCollectionItems(ephemeralCollection, offset, limit, args.signal);
    }
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
      items: rows.map((row) => ({
        sample: resolveStaticSampleUrls(row.sample),
        score: row.score ?? null,
      })),
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
    return fetchStaticSimilarSamples(sampleId, args);
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
    throw new ApiError("Text search is not available in a Static Space", 400, null);
  }
  const res = await apiRequest(apiUrl("/search/text"), {
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
}): Promise<RuntimeSnapshot | null> {
  if (isStaticBundle()) {
    return null;
  }
  const payload = await runControlCommand({
    command: "workspace.layout-view.set",
    target: { workspace_id: args.workspaceId },
    args: {
      layout_key: args.layoutKey,
      camera_3d: args.camera3d ?? null,
    },
  });
  return runtimeSnapshotFromCommandResult(
    payload,
    "Layout view command did not return a runtime snapshot"
  );
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
  const res = await apiRequest(apiUrl("/selection/lasso"), {
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

interface StaticSampleLabelCount {
  value: string | null;
  count: number;
}

interface StaticSampleShard {
  path: string;
  offset: number;
  count: number;
  sample_ids?: string[];
  label_counts?: StaticSampleLabelCount[];
}

interface StaticSamplesIndex {
  schema_version?: number;
  total: number;
  shard_size: number;
  shards: Array<string | StaticSampleShard>;
}

interface StaticSimilarityShardRef {
  path: string;
  sample_ids: string[];
}

interface StaticSimilaritySpace {
  metric: string;
  shards: StaticSimilarityShardRef[];
}

interface StaticSimilarityIndex {
  schema_version: number;
  k: number;
  default_space_key: string;
  spaces: Record<string, StaticSimilaritySpace>;
}

interface StaticSimilarityShard {
  space_key: string;
  metric: string;
  k: number;
  queries: Record<
    string,
    {
      results: Array<{ sample_id: string; distance: number }>;
    }
  >;
}

let staticSamplesIndexPromise: Promise<StaticSamplesIndex> | null = null;
const staticSampleShardPromises = new Map<string, Promise<SamplesResponse>>();
let staticSimilarityIndexPromise: Promise<StaticSimilarityIndex> | null = null;
const staticSimilarityShardPromises = new Map<string, Promise<StaticSimilarityShard>>();

function getStaticSamplesIndex(): Promise<StaticSamplesIndex> {
  staticSamplesIndexPromise ??= fetchStaticJson<StaticSamplesIndex>("api/samples/index.json");
  return staticSamplesIndexPromise;
}

function normalizedStaticSampleShards(index: StaticSamplesIndex): StaticSampleShard[] {
  return index.shards.map((entry, shardIndex) => {
    if (typeof entry !== "string") return entry;
    const offset = shardIndex * index.shard_size;
    return {
      path: entry,
      offset,
      count: Math.min(index.shard_size, Math.max(0, index.total - offset)),
    };
  });
}

function getStaticSampleShard(path: string): Promise<SamplesResponse> {
  let pending = staticSampleShardPromises.get(path);
  if (!pending) {
    pending = fetchStaticJson<SamplesResponse>(`api/samples/${path}`).then((payload) => ({
      ...payload,
      samples: payload.samples.map(resolveStaticSampleUrls),
    }));
    staticSampleShardPromises.set(path, pending);
  }
  return pending;
}

function sampleMatchesLabel(sample: Sample, label?: string): boolean {
  if (isMissingLabelFilter(label)) return sample.label === null || sample.label === undefined;
  const apiLabel = toApiLabel(label);
  return apiLabel === null || sample.label === apiLabel;
}

function staticShardMatchCount(shard: StaticSampleShard, label?: string): number | null {
  if (!label) return shard.count;
  if (!shard.label_counts) return null;
  if (isMissingLabelFilter(label)) {
    return shard.label_counts.find((entry) => entry.value === null)?.count ?? 0;
  }
  const apiLabel = toApiLabel(label);
  if (apiLabel === null) return shard.count;
  return shard.label_counts.find((entry) => entry.value === apiLabel)?.count ?? 0;
}

async function fetchStaticSamplesPage(
  offset: number,
  limit: number,
  label?: string,
  signal?: AbortSignal
): Promise<SamplesResponse> {
  signal?.throwIfAborted();
  const index = await getStaticSamplesIndex();
  const shards = normalizedStaticSampleShards(index);
  const counts = shards.map((shard) => staticShardMatchCount(shard, label));

  if (counts.some((count) => count === null)) {
    const loaded = await Promise.all(shards.map((shard) => getStaticSampleShard(shard.path)));
    const filtered = loaded
      .flatMap((shard) => shard.samples)
      .filter((sample) => sampleMatchesLabel(sample, label));
    return { total: filtered.length, offset, limit, samples: filtered.slice(offset, offset + limit) };
  }

  const total = counts.reduce<number>((sum, count) => sum + (count ?? 0), 0);
  let remainingOffset = Math.max(0, offset);
  const samples: Sample[] = [];
  for (let shardIndex = 0; shardIndex < shards.length && samples.length < limit; shardIndex += 1) {
    signal?.throwIfAborted();
    const matchCount = counts[shardIndex] ?? 0;
    if (remainingOffset >= matchCount) {
      remainingOffset -= matchCount;
      continue;
    }
    const payload = await getStaticSampleShard(shards[shardIndex].path);
    const matching = payload.samples.filter((sample) => sampleMatchesLabel(sample, label));
    const available = matching.slice(remainingOffset, remainingOffset + limit - samples.length);
    samples.push(...available);
    remainingOffset = 0;
  }
  return { total, offset, limit, samples };
}

async function fetchStaticSamplesByIds(sampleIds: string[]): Promise<Sample[]> {
  const index = await getStaticSamplesIndex();
  const shards = normalizedStaticSampleShards(index);
  const pathById = new Map<string, string>();
  for (const shard of shards) {
    for (const sampleId of shard.sample_ids ?? []) pathById.set(sampleId, shard.path);
  }

  const paths = new Set(
    sampleIds.map((sampleId) => pathById.get(sampleId)).filter(Boolean)
  );
  const selectedShards = paths.size > 0 ? shards.filter((shard) => paths.has(shard.path)) : shards;
  const loaded = await Promise.all(selectedShards.map((shard) => getStaticSampleShard(shard.path)));
  const byId = new Map(loaded.flatMap((shard) => shard.samples).map((sample) => [sample.id, sample]));
  return sampleIds.map((sampleId) => byId.get(sampleId)).filter((sample): sample is Sample => Boolean(sample));
}

async function getStaticEphemeralCollection(
  collectionId: string
): Promise<RuntimeCollection | null> {
  if (
    !collectionId.startsWith("static-filter-") &&
    !collectionId.startsWith("static-selection-") &&
    !collectionId.startsWith("static-neighbors-")
  ) {
    return null;
  }
  const snapshot = await getStaticSnapshot();
  return (
    snapshot.workspace.collections.find(
      (collection) =>
        collection.id === collectionId &&
        (collection.kind === "filter" ||
          collection.kind === "selection" ||
          collection.kind === "neighbors")
    ) ?? null
  );
}

function staticSampleFieldValue(sample: Sample, field: string): unknown {
  let value: unknown = sample;
  for (const segment of field.split(".")) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
    value = (value as Record<string, unknown>)[segment];
  }
  return value;
}

function sampleMatchesStaticFilter(sample: Sample, collection: RuntimeCollection): boolean {
  const { field, op, value } = collection.query;
  if (typeof field !== "string" || op !== "eq") return false;
  const sampleValue = staticSampleFieldValue(sample, field);
  if (value === null) return sampleValue === null || sampleValue === undefined;
  return sampleValue === value;
}

async function fetchStaticEphemeralCollectionItems(
  collection: RuntimeCollection,
  offset: number,
  limit: number,
  signal?: AbortSignal
): Promise<CollectionItemsPage> {
  signal?.throwIfAborted();
  if (collection.kind === "neighbors") {
    const anchor = collection.query.anchor;
    const anchorId =
      typeof anchor === "string"
        ? anchor
        : anchor && typeof anchor === "object" && !Array.isArray(anchor)
          ? String(
              (anchor as Record<string, unknown>).entityId ??
                (anchor as Record<string, unknown>).entity_id ??
                ""
            )
          : "";
    if (!anchorId) {
      throw new ApiError(`Neighbor collection ${collection.id} has no anchor`, 400, null);
    }
    const requestedK =
      typeof collection.query.k === "number" ? Math.max(1, Math.floor(collection.query.k)) : 10;
    const rawSpaceKey = collection.query.spaceKey ?? collection.query.space_key;
    const rawIndexId = collection.query.indexId ?? collection.query.index_id;
    const spaceKey =
      typeof rawSpaceKey === "string"
        ? rawSpaceKey
        : typeof rawIndexId === "string" && rawIndexId.startsWith("space:")
          ? rawIndexId.slice(6)
          : undefined;
    const rawLayoutKey = collection.query.layoutId ?? collection.query.layout_id;
    const response = await fetchStaticSimilarSamples(anchorId, {
      k: requestedK,
      spaceKey,
      layoutKey: typeof rawLayoutKey === "string" ? rawLayoutKey : undefined,
      signal,
    });
    const rows = response.results.slice(offset, offset + limit);
    return {
      collectionId: collection.id,
      offset,
      limit,
      total: response.results.length,
      hasMore: offset + limit < response.results.length,
      items: rows.map((sample) => ({ sample, score: sample.distance })),
    };
  }
  if (collection.kind === "selection") {
    const ids = Array.isArray(collection.query.ids)
      ? collection.query.ids.map((sampleId) => String(sampleId))
      : [];
    const pageIds = ids.slice(offset, offset + limit);
    const samples = await fetchStaticSamplesByIds(pageIds);
    signal?.throwIfAborted();
    return {
      collectionId: collection.id,
      offset,
      limit,
      total: ids.length,
      hasMore: offset + limit < ids.length,
      items: samples.map((sample) => ({ sample, score: null })),
    };
  }
  const index = await getStaticSamplesIndex();
  const shards = normalizedStaticSampleShards(index);
  const loaded = await Promise.all(shards.map((shard) => getStaticSampleShard(shard.path)));
  signal?.throwIfAborted();
  const matching = loaded
    .flatMap((shard) => shard.samples)
    .filter((sample) => sampleMatchesStaticFilter(sample, collection));
  return {
    collectionId: collection.id,
    offset,
    limit,
    total: matching.length,
    hasMore: offset + limit < matching.length,
    items: matching.slice(offset, offset + limit).map((sample) => ({ sample, score: null })),
  };
}

function getStaticSimilarityIndex(): Promise<StaticSimilarityIndex> {
  staticSimilarityIndexPromise ??= fetchStaticJson<StaticSimilarityIndex>(
    "api/search/similar/index.json"
  );
  return staticSimilarityIndexPromise;
}

function getStaticSimilarityShard(path: string): Promise<StaticSimilarityShard> {
  let pending = staticSimilarityShardPromises.get(path);
  if (!pending) {
    pending = fetchStaticJson<StaticSimilarityShard>(`api/search/similar/${path}`);
    staticSimilarityShardPromises.set(path, pending);
  }
  return pending;
}

async function fetchStaticSimilarSamples(
  sampleId: string,
  args: {
    k?: number;
    spaceKey?: string;
    layoutKey?: string;
    includeThumbnails?: boolean;
    signal?: AbortSignal;
  }
): Promise<SimilaritySearchResponse> {
  const datasetPromise = fetchDataset(args.signal);
  let index: StaticSimilarityIndex;
  try {
    index = await getStaticSimilarityIndex();
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
    const [querySample] = await fetchStaticSamplesByIds([sampleId]);
    return {
      query_id: sampleId,
      query_sample: querySample ?? null,
      space_key: args.spaceKey ?? null,
      metric: "unknown",
      k: args.k ?? 10,
      results: [],
    };
  }
  const dataset = await datasetPromise;
  let spaceKey = args.spaceKey ?? index.default_space_key;
  if (args.layoutKey) {
    const layout = dataset.layouts.find((item) => item.layout_key === args.layoutKey);
    if (layout && index.spaces[layout.space_key]) spaceKey = layout.space_key;
  }
  const space = index.spaces[spaceKey];
  if (!space) throw new ApiError(`Similarity space is not exported: ${spaceKey}`, 404, null);
  const shardRef = space.shards.find((shard) => shard.sample_ids.includes(sampleId));
  if (!shardRef) throw new ApiError(`Sample is not indexed for similarity: ${sampleId}`, 404, null);

  const shard = await getStaticSimilarityShard(shardRef.path);
  const query = shard.queries[sampleId];
  if (!query) throw new ApiError(`Sample is not indexed for similarity: ${sampleId}`, 404, null);
  const k = Math.max(1, Math.min(args.k ?? 10, index.k));
  const resultRows = query.results.slice(0, k);
  const hydrated = await fetchStaticSamplesByIds([
    sampleId,
    ...resultRows.map((row) => row.sample_id),
  ]);
  const byId = new Map(hydrated.map((sample) => [sample.id, sample]));
  return {
    query_id: sampleId,
    query_sample: byId.get(sampleId) ?? null,
    space_key: spaceKey,
    metric: space.metric,
    k,
    results: resultRows.flatMap((row) => {
      const sample = byId.get(row.sample_id);
      return sample ? [{ ...sample, distance: row.distance }] : [];
    }),
  };
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

function staticPanelStateEntry(
  snapshot: RuntimeSnapshot,
  panelId: string
): { state: Record<string, unknown>; state_revision: number } {
  return snapshot.workspace.ui.panels?.[panelId] ?? { state: {}, state_revision: 0 };
}

// The commands whose target carries an optional `panel_id`. Keep in sync with
// the CommandSpecs that use CollectionTarget in src/hyperview/control/ui_panel.py.
const COLLECTION_PANEL_TARGET_COMMANDS = new Set([
  "collection.filter.set",
  "collection.selection.set",
  "collection.neighbors.create",
  "collection.search.create",
  "panel.samples.retrieval.set-anchor",
]);

// Mirrors the runtime's panel-state resolution: a panel addresses itself by id,
// and the Samples aliases (plus an unrouted command) fall back to the shared
// Samples state slot.
function resolveStaticPanelStateId(
  snapshot: RuntimeSnapshot,
  target?: Record<string, unknown>
): string {
  const requested = typeof target?.panel_id === "string" ? target.panel_id.trim() : "";
  if (!requested || SAMPLES_PANEL_STATE_ALIASES.has(requested)) return SAMPLES_PANEL_STATE_ID;
  const known = snapshot.workspace.ui.custom_panels.some((panel) => panel.id === requested);
  return known ? requested : SAMPLES_PANEL_STATE_ID;
}

function updateStaticCollectionPanelState(
  snapshot: RuntimeSnapshot,
  panelId: string,
  state: Record<string, unknown>,
  collections: RuntimeCollection[],
  selectedIds: string[]
): RuntimeSnapshot {
  const current = staticPanelStateEntry(snapshot, panelId);
  return {
    ...snapshot,
    version: snapshot.version + 1,
    workspace: {
      ...snapshot.workspace,
      collections,
      ui: {
        ...snapshot.workspace.ui,
        selected_ids: selectedIds,
        panels: {
          ...snapshot.workspace.ui.panels,
          [panelId]: {
            state,
            state_revision: current.state_revision + 1,
          },
        },
      },
    },
  };
}

function runStaticLabelFilterCommand(
  snapshot: RuntimeSnapshot,
  panelId: string,
  args: Record<string, unknown>
): ControlCommandResult {
  const retainedCollections = snapshot.workspace.collections.filter(
    (collection) => collection.kind !== "filter"
  );
  const clear = args.clear === true;
  let collection: RuntimeCollection | null = null;
  const currentState = staticPanelStateEntry(snapshot, panelId).state;
  let state: Record<string, unknown> = { ...currentState };
  if (!clear) {
    const field = typeof args.field === "string" ? args.field : "label";
    const value = typeof args.value === "string" ? args.value : null;
    const source = typeof args.source === "string" ? args.source : "static-demo";
    const collectionId =
      `static-filter-${encodeURIComponent(field)}-` +
      encodeURIComponent(value ?? "missing");
    collection = {
      id: collectionId,
      dataset_id: snapshot.workspace.dataset_name ?? "",
      entity_set_id: "samples",
      kind: "filter",
      query: { field, op: "eq", value, source },
      scores: null,
      created_at: Math.floor(Date.now() / 1000),
    };
    state = {
      ...currentState,
      mode: "collection",
      retrieval: null,
      collection_id: collectionId,
      collection,
      focus_request: null,
    };
    retainedCollections.push(collection);
  } else {
    const allCollection = retainedCollections.find((item) => item.kind === "all") ?? null;
    state = {
      ...currentState,
      mode: "collection",
      retrieval: null,
      collection_id: allCollection?.id ?? null,
      collection: allCollection,
      focus_request: null,
    };
  }
  staticRuntimeSnapshot = updateStaticCollectionPanelState(
    snapshot,
    panelId,
    state,
    retainedCollections,
    []
  );
  return {
    ok: true,
    command: "collection.filter.set",
    result: {
      panel_id: panelId,
      collection_id: collection?.id ?? null,
      collection,
    },
    snapshot: staticRuntimeSnapshot,
    workspace: staticRuntimeSnapshot.workspace,
    revision: staticRuntimeSnapshot.workspace.ui.panels[panelId].state_revision,
  };
}

let staticSelectionCounter = 0;

async function runStaticSimilarityAnchorCommand(
  snapshot: RuntimeSnapshot,
  panelId: string,
  args: Record<string, unknown>
): Promise<ControlCommandResult> {
  const sampleId = typeof args.sample_id === "string" ? args.sample_id.trim() : "";
  if (!sampleId) {
    return {
      ok: false,
      command: "panel.samples.retrieval.set-anchor",
      snapshot,
      workspace: snapshot.workspace,
      revision: snapshot.workspace.ui.view_revision,
      error: { code: "validation_error", message: "sample_id must be a non-empty string" },
    };
  }
  const requestedK = typeof args.k === "number" ? Math.floor(args.k) : 18;
  const layoutKey = typeof args.layout_key === "string" ? args.layout_key : undefined;
  let spaceKey = typeof args.space_key === "string" ? args.space_key : undefined;
  if (!spaceKey && typeof args.index_id === "string") {
    spaceKey = args.index_id.startsWith("space:") ? args.index_id.slice(6) : args.index_id;
  }
  let response: SimilaritySearchResponse;
  try {
    response = await fetchStaticSimilarSamples(sampleId, {
      k: requestedK,
      layoutKey,
      spaceKey,
      includeThumbnails: false,
    });
  } catch (error) {
    return {
      ok: false,
      command: "panel.samples.retrieval.set-anchor",
      snapshot,
      workspace: snapshot.workspace,
      revision: snapshot.workspace.ui.view_revision,
      error: {
        code: "not_found",
        message: error instanceof Error ? error.message : "Similarity data is unavailable",
      },
    };
  }
  const resolvedSpaceKey = response.space_key ?? spaceKey ?? null;
  const dataset = await fetchDataset();
  const resolvedLayoutKey =
    layoutKey ??
    dataset.layouts.find((layout) => layout.space_key === resolvedSpaceKey)?.layout_key ??
    null;
  const k = Math.max(1, Math.min(requestedK, response.k));
  const source = typeof args.source === "string" ? args.source : "samples-panel";
  const collectionId = `static-neighbors-${encodeURIComponent(sampleId)}-${encodeURIComponent(resolvedSpaceKey ?? "default")}`;
  const collection: RuntimeCollection = {
    id: collectionId,
    dataset_id: snapshot.workspace.dataset_name ?? "",
    entity_set_id: "samples",
    kind: "neighbors",
    query: {
      anchor: {
        datasetId: snapshot.workspace.dataset_name ?? "",
        entitySetId: "samples",
        entityId: sampleId,
      },
      indexId: resolvedSpaceKey ? `space:${resolvedSpaceKey}` : null,
      layoutId: resolvedLayoutKey,
      spaceKey: resolvedSpaceKey,
      k,
      source,
    },
    scores: null,
    created_at: Math.floor(Date.now() / 1000),
  };
  const current = staticPanelStateEntry(snapshot, panelId);
  const retainedCollections = snapshot.workspace.collections.filter(
    (entry) => entry.kind !== "neighbors" && entry.kind !== "search"
  );
  retainedCollections.push(collection);
  const state = {
    ...(current.state ?? {}),
    mode: "retrieval",
    retrieval: {
      anchor_sample_id: sampleId,
      layout_key: resolvedLayoutKey,
      index_id: resolvedSpaceKey ? `space:${resolvedSpaceKey}` : null,
      space_key: resolvedSpaceKey,
      k,
      source,
    },
    collection_id: collectionId,
    collection,
    focus_request: null,
  };
  staticRuntimeSnapshot = updateStaticCollectionPanelState(
    snapshot,
    panelId,
    state,
    retainedCollections,
    []
  );
  return {
    ok: true,
    command: "panel.samples.retrieval.set-anchor",
    result: { panel_id: panelId, collection_id: collectionId, collection },
    snapshot: staticRuntimeSnapshot,
    workspace: staticRuntimeSnapshot.workspace,
    revision: staticRuntimeSnapshot.workspace.ui.panels[panelId].state_revision,
  };
}

function runStaticSelectionCommand(
  snapshot: RuntimeSnapshot,
  panelId: string,
  args: Record<string, unknown>
): ControlCommandResult {
  const current = staticPanelStateEntry(snapshot, panelId);
  const retainedCollections = snapshot.workspace.collections.filter(
    // Prepared comparison collections are exported with kind=selection and
    // may still be referenced by sibling panel props. Only replace the
    // ephemeral collection created by an earlier static interaction.
    (collection) => !collection.id.startsWith("static-selection-")
  );
  const clear = args.clear === true;
  const focus = args.focus !== false;
  const sampleIds = clear
    ? []
    : Array.from(
        new Set(
          (Array.isArray(args.sample_ids) ? args.sample_ids : [])
            .map((sampleId) => String(sampleId).trim())
            .filter(Boolean)
        )
      );
  let collection: RuntimeCollection | null = null;
  if (!clear) {
    staticSelectionCounter += 1;
    const collectionId = `static-selection-${Date.now()}-${staticSelectionCounter}`;
    collection = {
      id: collectionId,
      dataset_id: snapshot.workspace.dataset_name ?? "",
      entity_set_id: "samples",
      kind: "selection",
      query: {
        ids: sampleIds,
        source: typeof args.source === "string" ? args.source : "static-panel",
      },
      scores: null,
      created_at: Date.now(),
    };
    retainedCollections.push(collection);
  } else {
    collection = retainedCollections.find((item) => item.kind === "all") ?? null;
  }
  const nextState = {
    ...(current.state ?? {}),
    mode: "collection",
    retrieval: null,
    collection_id: collection?.id ?? null,
    collection,
    focus_request: focus
      ? {
          kind: clear ? "all" : "selection",
          ...(clear ? {} : { collection_id: collection?.id ?? null }),
          revision: current.state_revision + 1,
        }
      : null,
  };
  staticRuntimeSnapshot = updateStaticCollectionPanelState(
    snapshot,
    panelId,
    nextState,
    retainedCollections,
    sampleIds
  );
  return {
    ok: true,
    command: "collection.selection.set",
    result: {
      panel_id: panelId,
      collection_id: collection?.id ?? null,
      collection,
      selected_ids: sampleIds,
    },
    snapshot: staticRuntimeSnapshot,
    workspace: staticRuntimeSnapshot.workspace,
    revision: staticRuntimeSnapshot.workspace.ui.panels[panelId].state_revision,
  };
}

function runStaticPanelPropsCommand(
  snapshot: RuntimeSnapshot,
  command: "workspace.panel.update" | "workspace.panel.update-props",
  target: Record<string, unknown>,
  args: Record<string, unknown>
): ControlCommandResult | null {
  const panelId = typeof target.panel_id === "string" ? target.panel_id : null;
  const props = args.props;
  if (!panelId || !props || typeof props !== "object" || Array.isArray(props)) return null;
  const panelIndex = snapshot.workspace.ui.custom_panels.findIndex((panel) => panel.id === panelId);
  if (panelIndex < 0) return null;

  const customPanels = snapshot.workspace.ui.custom_panels.map((panel, index) =>
    index === panelIndex ? { ...panel, props: { ...(props as Record<string, unknown>) } } : panel
  );
  const nextWorkspace = {
    ...snapshot.workspace,
    ui: {
      ...snapshot.workspace.ui,
      custom_panels: customPanels,
      view_revision: (snapshot.workspace.ui.view_revision ?? 0) + 1,
    },
  };
  staticRuntimeSnapshot = {
    ...snapshot,
    version: snapshot.version + 1,
    workspace: nextWorkspace,
  };
  return {
    ok: true,
    command,
    result: {
      panel_id: panelId,
      props: { ...(props as Record<string, unknown>) },
    },
    snapshot: staticRuntimeSnapshot,
    workspace: nextWorkspace,
    revision: nextWorkspace.ui.view_revision,
  };
}

function runStaticPanelFocusCommand(
  snapshot: RuntimeSnapshot,
  target: Record<string, unknown>
): ControlCommandResult | null {
  const panelId = typeof target.panel_id === "string" ? target.panel_id : null;
  if (!panelId) return null;
  const panelIndex = snapshot.workspace.ui.custom_panels.findIndex((panel) => panel.id === panelId);
  if (panelIndex < 0) return null;

  const panel = snapshot.workspace.ui.custom_panels[panelIndex];
  const changed = snapshot.workspace.ui.active_panel_id !== panelId || !panel.visible;
  const customPanels = panel.visible
    ? snapshot.workspace.ui.custom_panels
    : snapshot.workspace.ui.custom_panels.map((entry, index) =>
        index === panelIndex ? { ...entry, visible: true } : entry
      );
  const nextWorkspace = changed
    ? {
        ...snapshot.workspace,
        ui: {
          ...snapshot.workspace.ui,
          custom_panels: customPanels,
          active_panel_id: panelId,
          view_revision: (snapshot.workspace.ui.view_revision ?? 0) + 1,
        },
      }
    : snapshot.workspace;
  staticRuntimeSnapshot = changed
    ? {
        ...snapshot,
        version: snapshot.version + 1,
        workspace: nextWorkspace,
      }
    : snapshot;
  return {
    ok: true,
    command: "workspace.panel.focus",
    result: { panel_id: panelId, active: true, visible: true },
    snapshot: staticRuntimeSnapshot,
    workspace: nextWorkspace,
    revision: nextWorkspace.ui.view_revision,
  };
}

async function runStaticControlCommandNow(args: {
  command: string;
  target?: Record<string, unknown>;
  args?: Record<string, unknown>;
}): Promise<ControlCommandResult> {
  const snapshot = await getStaticSnapshot();
  // Collection commands write the issuing panel's state, so an extension panel
  // driving them in a bundle updates itself rather than a panel named "samples".
  // The set that carries a panel target mirrors the CommandSpecs whose target is
  // a CollectionTarget on the live server; every other command here is
  // workspace-scoped and always resolves to the shared Samples state slot.
  const collectionPanelId = COLLECTION_PANEL_TARGET_COMMANDS.has(args.command)
    ? resolveStaticPanelStateId(snapshot, args.target)
    : SAMPLES_PANEL_STATE_ID;
  if (
    args.command === "panel.samples.retrieval.set-anchor" ||
    args.command === "collection.neighbors.create"
  ) {
    return runStaticSimilarityAnchorCommand(snapshot, collectionPanelId, args.args ?? {});
  }
  if (args.command === "collection.filter.set") {
    return runStaticLabelFilterCommand(snapshot, collectionPanelId, args.args ?? {});
  }
  if (args.command === "collection.selection.set") {
    return runStaticSelectionCommand(snapshot, collectionPanelId, args.args ?? {});
  }
  if (args.command === "workspace.panel.focus") {
    const result = runStaticPanelFocusCommand(snapshot, args.target ?? {});
    if (result) return result;
  }
  if (
    args.command === "workspace.panel.update-props" ||
    args.command === "workspace.panel.update"
  ) {
    const result = runStaticPanelPropsCommand(
      snapshot,
      args.command,
      args.target ?? {},
      args.args ?? {}
    );
    if (result) return result;
  }
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
    ok: false,
    command: args.command,
    snapshot,
    workspace: snapshot.workspace,
    revision: snapshot.workspace.ui.view_revision,
    error: {
      code: "conflict",
      message: "This operation requires a Live Space.",
    },
  };
}

let staticMutationQueue: Promise<unknown> = Promise.resolve();

function enqueueStaticMutation<T>(operation: () => Promise<T>): Promise<T> {
  const pending = staticMutationQueue.then(operation, operation);
  staticMutationQueue = pending.then(
    () => undefined,
    () => undefined
  );
  return pending;
}

function runStaticControlCommand(args: {
  command: string;
  target?: Record<string, unknown>;
  args?: Record<string, unknown>;
}): Promise<ControlCommandResult> {
  return enqueueStaticMutation(() => runStaticControlCommandNow(args));
}

export function updateStaticSelection(sampleIds: string[]): Promise<RuntimeSnapshot> {
  return enqueueStaticMutation(async () => {
    const snapshot = await getStaticSnapshot();
    const selectedIds = Array.from(new Set(sampleIds));
    staticRuntimeSnapshot = {
      ...snapshot,
      version: snapshot.version + 1,
      workspace: {
        ...snapshot.workspace,
        ui: {
          ...snapshot.workspace.ui,
          selected_ids: selectedIds,
          view_revision: snapshot.workspace.ui.view_revision + 1,
        },
      },
    };
    return staticRuntimeSnapshot;
  });
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
