# Multimodal Plan — Text now, Video next (2026-07)

Status: proposed. Companion to `docs/panel-extension-refactor-2026-07.md` and
`docs/architecture-review-2026-07.md`. Extends
`context/implemented/MULTI_MODAL_EMBEDDING_SPACES_AND_LAYOUTS.md` and the AGENTS.md
mandate: "Treat images as an important near-term modality, not the product model."

## Where we actually are

The storage and runtime layers are further along than the product surface suggests:

Already media-agnostic:
- `Sample` carries `modality`, `text`, and free-form `metadata`
  (`src/hyperview/core/sample.py:19-27`); the samples table has a bitmap index on
  `modality` and an FTS index on `text` (`src/hyperview/storage/lancedb_backend.py:108`).
- Embedding spaces, vectors, and layout coordinates are id-keyed and know nothing about
  media (`src/hyperview/storage/schema.py:43-112`).
- `EntityRef(dataset_id, entity_set_id, entity_id)` and `CollectionState` are generic
  (`src/hyperview/runtime.py:525-564`) — frames/chunks were designed for, not implemented.
- Text-query search already exists end to end: `Dataset.find_similar_by_text()`
  (`src/hyperview/core/dataset.py:764`), `POST /api/search/text`, and UI plumbing.

Hard-wired to images:
- Ingestion: `add_images_dir` with image extensions (`src/hyperview/core/dataset.py:217`);
  HF ingestion requires `image_key` and saves `.jpg/.png`
  (`src/hyperview/core/dataset.py:247`, `:466`); CLI mirrors this (`--image-key`).
- Embedding pipeline: orchestration always calls `engine.embed_images()`
  (`src/hyperview/embeddings/pipelines.py:104`); every provider assumes PIL images
  (`src/hyperview/embeddings/providers/lancedb_providers.py`,
  `src/hyperview/embeddings/compute.py`).
- Serving: the thumbnail endpoint decodes with PIL and always returns JPEG
  (`src/hyperview/server/app.py:912`); `Sample.load_image/ensure_dimensions` are PIL calls.
- Frontend: `SampleTile` renders `<img>` unconditionally
  (`frontend/src/components/SampleTile.tsx:34`); grid row layout derives aspect ratio from
  `width/height` (`frontend/src/components/SampleGridView.tsx:24`); the built-in panel is
  literally named `SamplesImageGridPanel`.
- Labels: a single scalar `label: str | None`. No bbox/segmentation/span types exist
  (fine — see scope below).

So the job is not a data-model rewrite. It is: generalize ingestion + embedding providers +
the render path, and formalize fields — the same "generic field mapping / typed Field
discovery" gap the July gap-assessment already ranked as the one real architectural gap.

## Design decisions

**D1 — One record type, `media_type` discriminant. No per-modality Sample subclasses.**
FiftyOne's model (sample has `media_type`; fields are dynamic) is the right shape for a
curation workbench; Rerun's full entity/component model is more than we need at the record
level. Concretely: `filepath` becomes officially nullable ("media pointer, absent for
text-only records"), add `media_type` (MIME-ish: `image/*`, `video/mp4`, `text/plain`,
`application/pdf` later), keep `width/height` as optional media metadata, add `duration_s`
(video/audio). `modality` stays as the coarse discriminant (`image|text|video|audio|multimodal`).
LanceDB schema evolution handles the added columns; backend swap is not needed.

**D2 — Typed field registry (the gap-assessment item, promoted to prerequisite).**
A `Field` catalog per dataset: `name → {type: scalar|text|media|label|vector_ref, nullable,
source}`. Ingestion writes it; `/api/dataset` exposes it; panels and the CLI discover
fields instead of assuming `label`/`text`/`filepath`. This is what makes "add a modality"
a data change rather than a code change, and it is what panel `accepts` declarations
(refactor plan, Phase 9) match against.

**D3 — Provider capability split, not new providers.**
Replace the implicit "provider = image encoder" with declared capabilities:
`embed_images(paths)`, `embed_texts(strings)`, or both. CLIP-family providers (including
hyper3-clip) declare both — that is the whole point of a multimodal space. The pipeline
dispatches per-sample by modality into the same `space_key`, which the storage layer
already supports (`MULTI_MODAL_EMBEDDING_SPACES_AND_LAYOUTS.md` anticipated exactly this).
Text-only providers (sentence-transformers class) become possible for free.

**D4 — Frontend renderer registry keyed by modality/media_type.**
`SampleTile` becomes a dispatcher: `image → <img>` (current behavior), `text → text card`
(clamped excerpt, label badge), `video → poster image + duration badge`, unknown →
metadata card fallback. Grid sizing: media tiles keep justified aspect-ratio layout; text
tiles get a fixed aspect bucket so `justified-layout` still works on mixed collections.
Renderers are the third extension surface (after tools and panels) so a PDF or audio
renderer is an extension folder, not a core PR — this is FiftyOne's sample-renderer idea
minus the source-install tax.

**D5 — Preview endpoint generalizes the thumbnail endpoint.**
`GET /api/samples/{id}/thumbnail` stays (images). Add semantics per media type rather than
new panel REST: text needs no preview call (the excerpt rides in the sample payload);
video gets a poster JPEG extracted at ingest (see M3) served through the same thumbnail
route. Static export already ships thumbnails per sample; posters slot into that path.

**D6 — Video = media file + optional `frames` entity set. Normalize at ingest.**
Two lessons from competitors, both hard-won:
- FiftyOne makes frames first-class *within* a sample (dict keyed by frame number) and
  users hit browser-side cliffs (frame labels vanish past ~5k buffered frames, issue #7713).
- Encord's docs spend pages on re-encoding: variable frame rate, ghost frames, and audio
  frames silently break frame-accurate seeking in browsers. Media normalization is not
  optional at scale.

Our shape: the video *sample* is one record (poster, duration, media_type). Frame-level
work (embeddings, per-frame inspection) materializes a `frames` entity set with its own
records and embedding spaces, linked by `EntityRef` — which the runtime was explicitly
designed for. We never buffer per-frame data into the grid; frames are just another
collection you can open. At ingest, probe with ffprobe; if the container is not
web-seekable H.264/AAC MP4, either transcode (opt-in flag) or record
`metadata.needs_transcode = true` and degrade to poster-only rendering. Do not promise
frame-accurate scrubbing on unnormalized media — that is how Encord-scale pain starts.

**D7 — Sequencing: text before video.** Text is cheap (no decode path, FTS already
indexed, tiles are trivial), immediately demo-relevant (multimodal CLIP spaces with
image+text in one layout showcases hyper3-clip), and it forces every generalization video
will need (nullable filepath, capability providers, renderer dispatch) without touching
ffmpeg. Video rides on already-generalized rails.

## Phases

### M0 — Schema + field groundwork (small, unblocks everything)

- Add `media_type`, `duration_s` columns; document `filepath` as nullable; guard
  `ensure_dimensions()`/`to_api_dict()` against non-image samples
  (`src/hyperview/core/sample.py:67-101`).
- Implement the typed `Field` registry (D2): persisted in the dataset (a `fields` table or
  registry JSON alongside `spaces`), surfaced in `/api/dataset` and `hyperview dataset inspect`.
- `SampleResponse`/frontend `Sample` type gain `media_type`; no UI change yet.
- Tests: text-only sample round-trips storage → API → static export without PIL imports.

### M1 — Text ingestion + text corpus embeddings

- `Dataset.add_texts(iterable | jsonl | csv, text_field=..., label_field=...)` and HF
  ingestion via `--text-key` (mirroring `--image-key`); modality set per record.
- Provider protocol split (D3): `supports = {"image"} | {"text"} | {"image","text"}`;
  pipeline batches per modality into one space; error clearly when a space's provider
  lacks a needed capability.
- `embed_texts` for hyper-models CLIP providers; add one text-only provider
  (sentence-transformers) to prove the capability matrix.
- CLI: `hyperview embeddings compute` unchanged in shape — modality routing is internal.
- FTS/hybrid: expose the existing FTS index through `samples.query` (match query on
  `text`) and add optional hybrid rank (vector + FTS reciprocal-rank fusion) to
  `POST /api/search/text`. Static bundles keep text search disabled as today (no paid
  inference, per the $5 constraint).

### M2 — Mixed rendering + panel plumbing

- Renderer dispatch in `SampleTile` (D4): text card + metadata fallback; fixed aspect
  bucket for textless tiles in `SampleGridView`; rename the built-in panel `samples`
  everywhere it is user-visible (it already is `samples` in `PanelDefinition`; drop the
  "ImageGrid" from user-facing labels).
- Renderer registration surface for extensions (`[[renderers]]` in `extension.toml`,
  loaded like panel modules) — coordinate with refactor Phase 9 `accepts`.
- Detail/modal view: text samples show full text; keep it minimal.
- Scatter needs nothing: it renders ids/coords/labels and is already modality-blind —
  a mixed image+text CLIP space in one layout is the headline demo.
- Static export: text lives in the sample row, so shards carry it for free — but
  `_write_sample_media()` runs for every sample and unconditionally does
  `Path(sample.filepath)` plus thumbnail generation
  (`src/hyperview/static_export.py:108`, `:166`); it must skip media/thumbnail work for
  records with no filepath. This is a required change, not a verification.

### M3 — Video, sample-level only

- Ingestion: `add_videos_dir` (extensions `.mp4/.mov/.webm/.mkv`), ffprobe for
  duration/dimensions/codec, poster frame extraction to the thumbnail path, normalization
  policy per D6. ffmpeg is an optional dependency (`hyperview[video]`); absence degrades
  to no poster + warning.
- Embeddings: video-level vector = mean of N uniformly sampled frame embeddings through
  the image capability of the space's provider (cheap, good enough for curation
  clustering; per-frame spaces come in M4).
- Frontend: poster tile with duration badge; detail view uses native `<video>` with the
  media content endpoint (`FileResponse` already supports range requests via Starlette).
- Static export: media size becomes a real concern — add `--max-media-mb` / `--no-media
  media_type=video` exporter options; posters always ship.

### M4 — Frames as an entity set (when a use case demands it)

- Materialize `frames` entity records (`video_id`, `frame_index`, `t_s`, extracted frame
  image) via a runtime job; frames get their own embedding spaces/layouts like any records.
- Grid can open a `frames` collection scoped to a video; hover-scrub on video tiles.
- Explicitly deferred until a concrete workflow (e.g. video dataset dedup or frame-level
  retrieval) pulls it — do not build ahead of demand here.

## What is out of scope, on purpose

- Rich annotation types (bbox/segmentation/spans) and any labeling-workforce features —
  that is Encord's business, not the embedding-workbench wedge. The `Field` registry
  leaves room for `label`-typed structured fields later.
- Audio, PDF/DICOM — the renderer + capability plumbing makes each an extension-sized
  project later; naming them in core now buys nothing.
- Grouped/multi-slice records (FiftyOne groups, Encord data groups) — revisit when a
  paired-modality dataset (e.g. image+caption as *linked records* rather than one
  multimodal record) actually appears in an eval.

## Dependencies on the other plans

- M0's field registry is the same work item as gap-assessment's "typed Field discovery" —
  one implementation, referenced by both plans.
- M2's renderer registry assumes refactor Phase 6 (SDK as the only data path) is done or
  in flight; renderers should be born SDK-clean.
- Panel `accepts` declarations (refactor Phase 9) become meaningful the moment M2 lands.
