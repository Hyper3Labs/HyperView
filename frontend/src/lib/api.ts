import type { DatasetInfo, EmbeddingsData, Sample, SamplesResponse } from "@/types";

const API_BASE = process.env.NODE_ENV === "development" ? "http://127.0.0.1:6262" : "";
const MISSING_LABEL_SENTINEL = "undefined";

function toApiLabel(label: string | null | undefined): string | null {
  if (!label || label === MISSING_LABEL_SENTINEL) {
    return null;
  }
  return label;
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

export async function fetchDataset(): Promise<DatasetInfo> {
  const res = await fetch(`${API_BASE}/api/dataset`);
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch dataset");
  }
  return res.json();
}

export async function fetchSamples(
  offset: number = 0,
  limit: number = 100,
  label?: string
): Promise<SamplesResponse> {
  const apiLabel = toApiLabel(label);
  const params = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
  });
  if (apiLabel !== null) {
    params.set("label", apiLabel);
  }

  const res = await fetch(`${API_BASE}/api/samples?${params}`);
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
  const res = await fetch(`${API_BASE}/api/embeddings${query ? `?${query}` : ""}`);
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch embeddings");
  }
  return res.json();
}

export async function fetchSample(sampleId: string): Promise<Sample> {
  const res = await fetch(`${API_BASE}/api/samples/${sampleId}`);
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch sample");
  }
  return res.json();
}

export async function fetchSamplesBatch(sampleIds: string[]): Promise<Sample[]> {
  const res = await fetch(`${API_BASE}/api/samples/batch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sample_ids: sampleIds }),
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch samples batch");
  }
  const data = await res.json();
  return data.samples;
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
  const res = await fetch(`${API_BASE}/api/selection/lasso`, {
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
      offset: args.offset ?? 0,
      limit: args.limit ?? 100,
      include_thumbnails: args.includeThumbnails ?? true,
    }),
    signal: args.signal,
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch lasso selection");
  }
  return res.json();
}
