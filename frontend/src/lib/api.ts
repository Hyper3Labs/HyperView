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
    pending = fetchStaticJson<SamplesResponse>(`api/samples/${path}`);
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

function updateStaticSamplesPanelState(
  snapshot: RuntimeSnapshot,
  state: Record<string, unknown>,
  collections: RuntimeCollection[]
): RuntimeSnapshot {
  const current = snapshot.workspace.ui.panels?.samples ?? { state: {}, state_revision: 0 };
  return {
    ...snapshot,
    version: snapshot.version + 1,
    workspace: {
      ...snapshot.workspace,
      collections,
      ui: {
        ...snapshot.workspace.ui,
        selected_ids: [],
        panels: {
          ...snapshot.workspace.ui.panels,
          samples: {
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
  args: Record<string, unknown>
): ControlCommandResult {
  const retainedCollections = snapshot.workspace.collections.filter(
    (collection) => collection.kind !== "filter"
  );
  const clear = args.clear === true;
  let collection: RuntimeCollection | null = null;
  let state: Record<string, unknown> = {};
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
      mode: "collection",
      collection_id: collectionId,
      collection,
    };
    retainedCollections.push(collection);
  }
  staticRuntimeSnapshot = updateStaticSamplesPanelState(snapshot, state, retainedCollections);
  return {
    ok: true,
    command: "collection.filter.set",
    result: {
      collection_id: collection?.id ?? null,
      collection,
    },
    snapshot: staticRuntimeSnapshot,
    workspace: staticRuntimeSnapshot.workspace,
    revision: staticRuntimeSnapshot.workspace.ui.panels.samples.state_revision,
  };
}

async function runStaticControlCommand(args: {
  command: string;
  target?: Record<string, unknown>;
  args?: Record<string, unknown>;
}): Promise<ControlCommandResult> {
  const snapshot = await getStaticSnapshot();
  if (args.command === "collection.filter.set") {
    return runStaticLabelFilterCommand(snapshot, args.args ?? {});
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
