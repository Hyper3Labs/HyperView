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
const RUNTIME_CLIENT_ID = `hv-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
const SAMPLE_BATCH_SIZE = 1000;

export function apiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}/api${normalizedPath}`;
}

export function backendUrl(pathOrUrl: string | null | undefined): string | null {
  if (!pathOrUrl) return null;
  if (/^https?:\/\//.test(pathOrUrl)) return pathOrUrl;
  if (pathOrUrl.startsWith("/api/")) return `${API_BASE}${pathOrUrl}`;
  return pathOrUrl;
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

export async function fetchDataset(signal?: AbortSignal): Promise<DatasetInfo> {
  const res = await fetch(apiUrl("/dataset"), signal ? { signal } : undefined);
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch dataset");
  }
  return res.json();
}

export async function fetchRuntimeState(workspaceId?: string | null): Promise<RuntimeSnapshot> {
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
  await runControlCommand({
    command: "panel.labels.filter",
    target: { workspace_id: args.workspaceId },
    args: {
      field: args.field ?? "label",
      ...(args.clear ? { clear: true } : { value: toApiLabel(args.value) }),
      source: "frontend",
    },
  });
  return fetchRuntimeState(args.workspaceId);
}

export async function setActiveWorkspace(workspaceId: string): Promise<RuntimeSnapshot> {
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
  await runControlCommand({
    command: "ui.panel.add",
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
  return fetchRuntimeState(args.workspaceId);
}

export async function removeRuntimePanel(args: {
  workspaceId: string;
  panelId: string;
}): Promise<RuntimeSnapshot> {
  await runControlCommand({
    command: "ui.panel.remove",
    target: {
      workspace_id: args.workspaceId,
      panel_id: args.panelId,
    },
  });
  return fetchRuntimeState(args.workspaceId);
}

export async function fetchSamples(
  offset: number = 0,
  limit: number = 100,
  label?: string,
  signal?: AbortSignal,
  includeThumbnails: boolean = false
): Promise<SamplesResponse> {
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
