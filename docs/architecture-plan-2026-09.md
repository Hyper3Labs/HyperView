# One workspace, two Spaces: architecture plan (September 2026)

Status: decision record. Phases 0-3, 6 (component kit, panel-aware
collection commands) and 9 shipped in 1.1.0 on 2026-09-03; phases 4, 5, 7 and
8 remain open (see "Status" at the end). Supersedes the naming and mode sections of
`panel-extension-refactor-2026-07.md`; that file is now history.

## Decisions

### D1. The unit of delivery is the exported workspace bundle

`hyperview export <workspace> --out <dir>` produces one self-contained
folder: samples, media, thumbnails, embeddings, layouts, collections,
panel definitions, panel instances and state, extension panel modules,
and a manifest. That folder is the product. Everything downstream is a
way of hosting it.

Today the folder can only be hosted statically. A Live Space is not an
export at all: it is a Dockerfile that re-runs `demo.py` at container
boot, which is why three demos need LanceDB stores that never reach the
container and why DeepFashion is in `RUNTIME_ERROR`. The fix is to make
the runtime able to load the bundle back:

```
hyperview serve --from <dir> --public
```

restores the dataset (space and layout keys preserved), installs the
bundled extensions, applies the saved workspace, and serves the same
shell with the API enabled. The bundle becomes the interface between
building a workspace and running it anywhere.

### D2. Names: Live Space and Static Space

| | Live Space | Static Space |
| --- | --- | --- |
| What runs | `hyperview serve --from bundle --public` in a container | Files on any static host |
| Machine token | `live` | `static` |
| Hugging Face SDK | `docker` | `static` |
| Can do | Everything, including typed text queries and new layouts | Viewer actions, precomputed similarity, materialized searches |

"Static" is what every comparable tool calls this artifact. "Space" is
already our gallery word and aligns with Hugging Face on purpose: a
Static Space deploys to an HF static Space, a Live Space to an HF Docker
Space. Retired everywhere: Shared View, Shared Space, Snapshot, Exhibit,
static demo. `hv.ui.View` keeps the word View; that is the only View.

### D3. One publish verb in core

```
hyperview publish <dir> --to hf:<owner>/<name> --mode static|live
hyperview publish <dir> --to cloudflare
hyperview publish <dir> --to dir:<path>
```

`--mode static` uploads the folder to an HF static Space. `--mode live`
writes a generated Dockerfile and README frontmatter from the manifest,
then uploads to an HF Docker Space. Nothing per demo is hand-written:
title, emoji, pins, workspace id and port all come from the manifest.
`deploy_hf_space.py` in hyperview-spaces retires; the site's mount
script collapses to `publish --to dir:`.

### D4. Extension, panel, tool. Nothing else

| Slot | Name | Status |
| --- | --- | --- |
| Installable unit | **extension** (`extension.toml`) | keep |
| UI unit | **panel**, identified by `panel_type` | keep |
| Python callable | **tool** | keep |
| Frontend contract | **Panel SDK**, versioned on its own (`panel-sdk 2.x`) | keep, add `sdk_version` to the manifest |
| Panel type record | `PanelDefinition` | keep; `PanelSpecEntry` collapses into it |
| Placed panel | `PanelInstance`, wire key `panels` | rename from `CustomPanelSpec` / `custom_panels` |
| Provenance | `origin: bundled \| local` | rename from `source: shipped \| extension \| module` |
| `kind` | deleted | four disagreeing enums; every value is derivable from `panel_type` |

Not adopted: plugin (reserved for the FiftyOne comparison), widget,
view-for-panel (five meanings of "view" already).

### D5. Built-ins go through the extension path; the module path comes up to meet them

The claim "an internal panel is exactly the same architecture as an
external one" is currently half true. Shared: manifest schema,
definition record, props and state contract, command transport, SDK
hooks, static compatibility gate. Not shared: loader, registration
store, renderer namespace, UI placement, default layout, tab and
closability policy, host params, UI kit, command registration.

We do not rewrite scatter as a loose ESM module; it needs a bundler and
`hyper-scatter`. Instead:

- `core` installs through `install_extension(origin="bundled")` at
  startup like any other extension. `renderer: native:*` is legal from
  any bundled extension; `renderer: module:*` from any origin. The two
  enforcement checks that fork them are deleted.
- One placement primitive in Python, `hv.ui.Panel(panel_type=..., id=...,
  props=...)`. `Scatter`, `Samples`, `ExtensionPanel` become sugar.
  `hv.ui.Explorer` appears for free.
- The UI opens any registered panel type, and the default layout may
  include extension panels.
- Tab icon, closability, and host params come from the definition, not
  from `kind` or an id prefix.
- Extensions register commands under `ext.<name>.*` through the same
  hook the core extension uses for `panel.samples.retrieval.*`.
- The Panel SDK regains a minimal component kit (`Panel`, `PanelHeader`,
  `PanelToolbar`). Parity is the stated goal; 1.2k characters of inline
  CSS in the DeepFashion panel is the cost of not having it.
- Declared-but-unread fields: `data_capabilities` becomes the exporter's
  materialization request. `[[panels]].commands` and `queries` are
  deleted until something enforces them.

"Shipped inside the wheel" becomes a release-cadence fact, not an
architecture fact. Say so in the docs.

### D6. Capability is defined once

Read-only HyperView is currently specified four times: the export
manifest, about forty `isStaticBundle()` branches in the frontend, the
static command allowlist in `api.ts`, and the public-server allowlist in
`security.py`. The manifest becomes authoritative. One `useCapabilities()`
hook reads it; the two allowlists derive from one shared table that
`hyperview serve --public` and the static emulator both consume.

### D7. One `demo.toml` per demo, registries generated

For one demo the same facts are restated about forty times across
twenty-two places. `demo.toml` holds slug, title, description, emoji,
workspace id, dataset name, HF Space ids, port, and pins. Registries,
README frontmatter, the root README table, and site cards are generated
from it. About 370 lines of `check_spaces.py` that only reconcile copies
are deleted.

### D8. Ship 1.0.0 first

The security fixes already on the branch are release-worthy. D4's wire
renames are breaking for exported bundles and CLI JSON, so they land in
1.1 behind `_compat.py`, and we regenerate our own bundles. Do not hold
1.0.0 for this plan.

## Bugs found during the audit that ship with 1.0.0

1. Static command emulator hardcodes panel id `samples`
   (`frontend/src/lib/api.ts:1186-1207, 1377, 1450`). An extension panel
   issuing `collection.*` in a Static Space writes another panel's state.
2. `check_spaces.py` hook list is missing `useSupportsSampleSimilarity`;
   a conforming panel is rejected.
3. `static_export.py:806-811` deletes the scatter definition by name
   instead of marking it `static_compatible=False`.
4. `docs/static-spaces.md:36-50` and `references/shared-views.md:17`
   still document the removed `--mount-path`.
5. `agent-context/panels/*` are v1 SDK examples on the v2 blocklist;
   agents copy them.
6. Dead: `BuiltInCenterPanelDefinition`, `getExpectedRuntimePanelComponent`,
   `build_custom_panel(kind="module")`, `"grid"` alias, empty
   `hyper3_clip/` and `vendor/` folders in two demos, committed
   `gallery/out/index.html`.

## Phases

Each phase is independently shippable and sized for one delegated run.

| # | Phase | Repo | Size | Unblocks |
| --- | --- | --- | --- | --- |
| 0 | Fix the six items above; move `v1.0.0` tag; regenerate `uv.lock`; publish | HyperView, spaces | S | release |
| 1 | Bundle restore: `hyperview serve --from <dir>`, space and layout keys preserved, extensions installed from bundle | HyperView | L | D1, DeepFashion |
| 2 | Generic Live Space image + `hyperview publish` (`hf` static and docker, `cloudflare`, `dir`) | HyperView | M | D3, deletes 9 Dockerfiles |
| 3 | Rename pass: Live Space / Static Space, `live`/`static` tokens, registry key `mode`, docs and site copy | all three | S | D2 |
| 4 | Vocabulary: delete `kind`, `PanelInstance` / `panels`, `origin`, `PanelSpecEntry` into `PanelDefinition`, `_compat` shims | HyperView | M | D4 |
| 5 | Core through the extension path; `hv.ui.Panel`; UI opens any panel type; definition-driven tabs, closability, host params | HyperView | M | D5 |
| 6 | Extension command registration `ext.<name>.*`; `sdk.components`; `data_capabilities` honored by the exporter; delete dead manifest fields; manifest `sdk_version` | HyperView | M/L | D5 |
| 7 | `useCapabilities()` from the manifest; one shared allowlist table for `--public` and the static emulator | HyperView | M | D6 |
| 8 | `demo.toml` and generators; `check_spaces.py` shrinks; public API additions `find_layout`, `create_collection`, typed Samples props, HF ingest filters | spaces, HyperView | M | D7 |
| 9 | Site consumes bundles as artifacts via `publish --to dir:`; delete `lib/spaces.ts` hand array and `mount-hyperview-spaces.py` internals | site | S | D3 |

Phases 1 and 2 are the highest leverage: they turn "one workspace, two
Spaces" from a slogan into `export` then `publish`, and they fix the
production outage. Phases 4 through 6 are the extension parity work and
can run in parallel with 1 and 2 on a branch.

## What a demo author does after this plan

```bash
python demos/<slug>/demo.py --build-only      # builds the workspace locally, exits
hyperview export <workspace> --out dist/<slug>
hyperview publish dist/<slug> --to hf:hyper3labs/<name> --mode static
hyperview publish dist/<slug> --to hf:hyper3labs/<name>-live --mode live
```

No Dockerfile, no README frontmatter, no registry edit, no mount script.

## Status (2026-09-03)

Shipped in 1.1.0: `hyperview serve --from`, `hyperview publish`, the
Live Space / Static Space naming, `hv.ui.Panel` and typed panel props,
`create_collection` and `find_layout`, `launch(extensions=)`, the panel SDK
component kit, panel-aware collection commands, the machine-readable SDK
surface, and the six bug fixes above. All nine demos use the new API; the six
Static Spaces on the landing site are 1.1.0 exports; DeepFashion and ABO
deploy as Live Spaces from those same bundles through the existing
Trusted-Publisher workflows (`deploy_mode: live-bundle`).

Still open: D4 vocabulary (delete `kind`, `PanelInstance`), D5 routing `core`
through the extension path and opening extension panels from the UI, D6 one
capability table, D7 `demo.toml` (deprioritised: demos are intentionally
free-form). A restore data-safety fix (media copied out of the bundle, export
refusing to read from its own output) is in progress for 1.1.1.

### Panel parity (branch `fix/panel-parity`)

Closed on this branch, against the D4/D5/D6 list:

- **The renderer namespace decides rendering, not `kind`.** The two checks that
  forced core panels to be `native:` and extension panels to be `module:` are
  gone, and `PanelHost` routes on the renderer prefix. A core panel may ship as
  a module and an installed extension may name a bundled component; both draw.
- **`kind` is migrated in one place.** `_migrate_kind()` is the single
  translation from the legacy transport values (`scatter`, `extension`) to the
  two the runtime keeps.
- **`module_file` is off the wire.** `WorkspaceState.to_dict()` no longer
  discloses the server-side path of a panel module; the registry keeps it
  through `to_dict(for_storage=True)`, so a restart still reopens the panel.
- **The View menu opens extension panels.** A panel definition now carries
  `extension_panel`, the manifest id, so the frontend can send the extension
  request shape for a `module:` renderer instead of hard-coding `builtin` --
  which used to fail outright for an installed extension and, for a shipped one
  like `reference`, dock a module panel into the native host.
- **`SAMPLES_PANEL_ID` is public.** `hv.ui.SAMPLES_PANEL_ID` and
  `sdk.constants.SAMPLES_PANEL_ID` name the panel that collection commands
  default to, on both sides of the wire.
- **Every collection command is panel-scoped.** `collection.search.create` and
  `panel.samples.retrieval.set-anchor` take a `CollectionTarget` like the other
  three, in the runtime and in the Static Space emulator alike.

Still open after it: `kind` itself survives on `CustomPanelSpec` and the
transport (D4 wants it deleted, not merely made non-deciding), and capability
information is still defined in more than one table (D6).
