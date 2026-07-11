# Architecture Review (2026-07)

Status: assessment. Companion docs: `docs/panel-extension-refactor-2026-07.md` (panel
contract work), `docs/multimodal-plan-2026-07.md` (modality expansion). This one covers
everything else: what the architecture gets right, and the issues ranked by how much they
will hurt, each with the architectural fix.

## What is working — keep and defend

- **The command control plane.** One typed envelope (`ControlService.run`), one registry,
  machine-readable `CommandResult`, namespaced command ids. This is the agent-native bet
  and it is the right one; neither FiftyOne nor Encord has an equivalent.
- **Unidirectional state flow.** Runtime owns state → versioned snapshots → SSE →
  frontend renders. No frontend-owned business state (with the layout exception noted
  below). This is what makes "agent drives the UI" possible at all.
- **LanceDB as the storage substrate.** Samples + per-space vector tables + layout tables
  with scalar/bitmap/FTS indexes is exactly the multimodal-lakehouse direction (Lance's own
  positioning), and it dodges FiftyOne's MongoDB pains (16MB aggregate limits breaking
  grouped similarity — their issue #7060; numpy masks bloating documents — #4486).
- **Static export as a first-class product artifact.** Read-only bundles matching the
  FiftyOne/Rerun gallery pattern, fits the $5/mo Cloudflare constraint, doubles as the
  Colab/pip distribution story.
- **Repo-local, agent-authored extensions.** Documented separately; the trust model
  (in-process, no marketplace) is coherent — as long as issue #1 below is fixed.

## Issues, ranked

### 1. CORS `allow_origins=["*"]` on a mutating local API — fix now

`src/hyperview/server/app.py:464` allows any origin, any method, any header, on a server
that executes registered commands, installs extensions (`POST /api/control/extensions/install`),
and imports Python modules from disk in-process. Any webpage open in the same browser can
issue `fetch("http://127.0.0.1:6262/api/control/...")` and the browser will happily send
it — drive-by pages can drive a running runtime, and extension install gives a path
toward arbitrary local code execution. Localhost binding does not mitigate this; CORS
wildcard is precisely what removes the browser's cross-origin protection.

Fix (small): allowlist origins to the served frontend + `http://localhost:6363` dev, and
require a per-session bearer token minted at `serve` time (printed in the URL the CLI
opens, stored by the frontend). CLI already talks to the API directly and just adds the
header. One afternoon, closes the hole.

### 2. SSE is a poll loop broadcasting whole snapshots — will not scale with state size

`/api/events` (`src/hyperview/server/app.py:492`) polls the runtime version and, on any
change, serializes the *entire* snapshot to every subscriber. Snapshot already includes
all workspaces, panel definitions, tools, collections, panel states
(`src/hyperview/runtime.py:2551`) — and panel state is duplicated into two places within
it (`:2588`). Cost per mutation is O(subscribers × total-state), and any panel patching
its state at interaction frequency (a scrubber, a slider) multiplies it. This is the
FiftyOne-App-freeze class of failure (#7068, #7570) approaching from a different road.

Fix, staged: (a) replace version polling with a condition variable/asyncio event —
free latency win; (b) de-duplicate panel state in the snapshot (refactor Phase 8);
(c) when it actually hurts, move to revisioned sub-tree deltas — the plumbing
(`state_revision`, `client_id` echo suppression) already exists, so deltas are an
encoding change, not a redesign. Don't build (c) speculatively; do (a) and (b) soon.

### 3. Dockview layout lives in `localStorage`, violating the source-of-truth rule

`frontend/src/components/DockviewWorkspace.tsx:712` persists layout client-side for
non-explicit views while runtime views bypass it. The plan's own ground rule says
runtime/workspace state is the source of truth and localStorage is user-preference only —
but panel arrangement *is* workspace state: an agent asking "what does the user see"
gets the wrong answer. Fix folded into refactor Phase 7 (layout becomes workspace state
behind a `workspace.layout.*` command).

### 4. Jobs are fire-and-forget daemon threads

Compute jobs (embeddings, layouts) are in-memory threads (`src/hyperview/runtime.py:2105`):
no persistence across restart, no cancellation, no queue/backpressure — N concurrent
embedding jobs will happily oversubscribe the GPU/CPU. For a single-user local tool this
is tolerable; it becomes untenable the moment a hosted or long-running deployment exists.

Fix in two steps: persist job records (id, kind, args, status, error) in the workspace
registry so `hyperview jobs` survives restart and failures are inspectable; serialize
compute jobs through a small worker queue (one thread, FIFO) with a cancel flag checked
between batches. Full process isolation (subprocess per job) only if/when a hosted
runtime is real.

### 5. Two thumbnail paths; base64 thumbnails stored in DB rows

Samples carry `thumbnail_base64` in the LanceDB row (`src/hyperview/storage/schema.py:43`)
*and* there is an on-demand JPEG endpoint (`src/hyperview/server/app.py:912`). Inline
base64 bloats every samples-table scan and every API page that includes it, and it is
redundant with the endpoint + HTTP caching (ETags already implemented). Fix: stop
persisting inline thumbnails for new ingests; serve exclusively via the endpoint with a
disk cache under `~/.hyperview/media/thumbs/`; keep reading the legacy column for old
datasets. This also simplifies the multimodal preview story (multimodal plan D5).

### 6. The two God modules

`src/hyperview/runtime.py` (~2,600 lines: workspaces, panels, collections, jobs,
extensions, snapshots, migration shims) and `src/hyperview/server/app.py` (~1,400 lines:
40 routes, serialization, SSE, media, static mounting). Both are where every feature
lands by default, which is how the panel-contract duplication happened in the first
place. Fix mechanically, no behavior change: `runtime/` package (workspaces, panels,
collections, jobs, extensions) and FastAPI routers (`server/routes/{control,samples,
collections,media,events}.py`). Do it *after* refactor Phases 5–7 so the moves don't
conflict with contract changes.

### 7. Typed field discovery is missing (the gap-assessment gap)

Everything assumes `label`/`text`/`filepath`. This is the one item both the gap
assessment and the multimodal plan converge on; it is scheduled as multimodal M0 and
should be treated as core-architecture work, not modality work.

### 8. Repo boundary confusion

The monorepo contains `hyperview-spaces/` (whose README says it is a standalone repo),
`hyper-scatter/`, `hyper-models/`, `hyper-lrp/` (each with its own packaging, two of them
PyPI dependencies of HyperView), plus cloned external repos under `context/repos*/`.
Consequences: unclear versioning between HyperView and its published deps, CI ambiguity,
repo weight. Fix: either commit to a workspace-style monorepo (path deps in dev,
published pins in release, one lockfile discipline) or extract the published packages;
pick one and write it down. Move `context/repos*/` clones out of the repo entirely.

### 9. Small confirmed defects (cheap, do opportunistically)

- Warm worker reads `hyperview_version` from `/__hyperview__/health`, but the endpoint
  returns `version` (`hyperview-spaces/warm-worker/src/index.ts:132` vs
  `src/hyperview/server/app.py:476`) — the status page is reading a field that never exists.
- `scripts/export_frontend.sh` tells the user to run `uv run hyperview demo`; no `demo`
  subcommand exists in the CLI parser.
- Deprecated command aliases (`src/hyperview/control/aliases.py`) log a server-side
  warning (`aliases.py:30`) but surface nothing to the caller in `CommandResult` and have
  no sunset date (folded into refactor Phase 8).
- Stale SDK examples under `agent-context/extensions/` reference removed hooks (folded
  into refactor Phase 8; actively harmful in an agent-native repo because agents copy them).

## What I deliberately did not flag

- **In-process extension execution** — it is a trust-model choice, consistent with
  "agents write source into your repo," and sandboxing would kill the DX that
  differentiates the product. Revisit only if third-party distribution becomes a goal.
- **SQLite/JSON registries (`providers.json`, `workspaces.json`)** — flat files are fine
  at this scale; migrating them buys nothing now.
- **The Python-thread uvicorn embedding in `Session`** — quirky but works for the
  notebook/CLI dual use; not worth churn.

## Suggested order of attack

1. Issue #1 (CORS/token) — immediately, independent of everything.
2. Refactor Phases 5–6 (finish collections, SDK-as-only-path) — highest product leverage.
3. Multimodal M0+M1 (fields + text) — unlocks the multimodal CLIP demo that supports the
   eval→pilot motion.
4. Issues #2a/#2b, #5 (SSE wakeup, snapshot de-dup, thumbnail path) — performance hygiene.
5. Refactor Phase 7–8 + issue #6 (registry, layout, module splits) — consolidation.
6. Issue #8 (repo boundaries) — background, whenever release friction next makes it obvious.
