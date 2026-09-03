# Commands

Use `--json` when chaining commands or inspecting results programmatically.

## Skill Installer

Install the packaged HyperView agent skill for detected agents plus the universal fallback:

```bash
hyperview skill install
```

Refresh installed copies after upgrading HyperView by running install again:

```bash
uv tool install --python 3.12 --upgrade hyperview && hyperview skill install
```

Limit to specific agent targets:

```bash
hyperview skill install --agent claude-code --yes       # ~/.claude/skills/
hyperview skill install --agent github-copilot --yes    # ~/.copilot/skills/
hyperview skill install --agent cursor --yes            # ~/.cursor/skills/
hyperview skill install --agent universal --yes         # ~/.agents/skills/
```

Install for every known profile explicitly:

```bash
hyperview skill install --all-known --yes
```

Install into a repo for project-shared discovery:

```bash
hyperview skill install --scope project --agent github-copilot --yes  # .github/skills/
hyperview skill install --scope project --agent claude-code --yes     # .claude/skills/
hyperview skill install --scope project --agent cursor --yes          # .cursor/skills/
hyperview skill install --scope project --agent universal --yes       # .agents/skills/
```

Preview destinations without writing files:

```bash
hyperview skill install --dry-run --json
```

This is different from `hyperview extension add`, which installs a runtime extension into a running HyperView workspace.

## Datasets and Workspaces

Create a persisted dataset from Hugging Face:

```bash
hyperview dataset create cifar10_demo \
  --hf-dataset uoft-cs/cifar10 \
  --split train \
  --image-key img \
  --label-key label
```

Create a multimodal dataset with captions:

```bash
hyperview dataset create coco_captions_demo \
  --hf-dataset HuggingFaceM4/COCO \
  --split train \
  --image-key image \
  --text-key sentences \
  --samples 500
```

Create a persisted dataset from a local image directory:

```bash
hyperview dataset create local_assets_demo \
  --images-dir assets
```

Create a workspace with its dataset in one step:

```bash
hyperview workspace create research \
  --dataset cifar10_demo \
  --activate
```

Change the dataset attached to a workspace:

```bash
hyperview workspace set-dataset research imagenette_clip_20260411
```

Start the runtime:

```bash
hyperview serve --workspace research --dataset cifar10_demo --no-browser
```

Check a running runtime:

```bash
hyperview status --json
```

## Providers, Embeddings, and Layouts

Use built-in providers directly when possible. Hyper3-CLIP is available through
the `hyper-models` provider:

```python
dataset.compute_embeddings(model="hyper3-clip-v0.5", provider="hyper-models")
```

Register a custom provider only when the model is not available through a
built-in provider:

```bash
hyperview provider register my-provider \
  --import-path my_pkg.provider:MyProvider
```

The same registration is available from Python:

```python
import hyperview as hv

hv.register_provider("my-provider", "my_pkg.provider:MyProvider", overwrite=True)
```

Compute checkpoint-backed embeddings and a layout:

```bash
hyperview embeddings compute \
  --workspace research \
  --dataset cifar10_demo \
  --provider my-provider \
  --model-id experiment-a \
  --checkpoint /path/to/checkpoint.json \
  --layout euclidean:2d
```

Add a new layout to an existing embedding space:

```bash
hyperview layouts compute \
  --workspace research \
  --dataset cifar10_demo \
  --space-key <space-key> \
  --layout euclidean:3d
```

Inspect long-running jobs:

```bash
hyperview jobs list --json
hyperview jobs inspect <job-id> --json
```

## Paper Figures

Export a browserless, paper-ready PNG from the active 3D layout:

```bash
hyperview figure export figures/embedding-sphere.png \
  --workspace research \
  --layout active \
  --json
```

If `--layout` is omitted, HyperView uses the active 3D layout when one is set, otherwise the first available 3D layout. Use `--layout active` when you specifically want the live UI's active layout and want the command to fail if none is active.

The export path does not require opening the UI. It supports 3D layouts only; 2D layouts are rejected with a validation message.

Paper defaults are tuned for academic figures:

- `--width 900 --height 900 --scale 2`
- `--theme light`
- `--guide-style paper`
- `--legend auto` (direct labels for small label sets)
- opaque PNG output
- selection rings hidden unless explicitly requested

Use the 3D view selected in the UI by rotating the scatter panel first. HyperView persists the layout camera and `figure export` reuses it for that layout.

Common variants:

```bash
# Cleanest sphere context: silhouette only.
hyperview figure export figures/embedding-outline.png \
  --workspace research \
  --layout active \
  --guide-style outline

# No sphere guide, useful when the embedding separation is the whole message.
hyperview figure export figures/embedding-clean.png \
  --workspace research \
  --layout active \
  --guide-style none \
  --legend direct

# Browser-like guide rings and current selection markers.
hyperview figure export figures/embedding-ui-like.png \
  --workspace research \
  --layout active \
  --guide-style rings \
  --legend on \
  --show-selection

# Add a short panel title when the figure will stand alone.
hyperview figure export figures/embedding-panel-a.png \
  --workspace research \
  --layout active \
  --title "ArcFace spherical embeddings"
```

## Static Spaces

Export a read-only, self-contained bundle and host its files as a Static Space:

```bash
hyperview export research --out dist/research-demo
```

The bundle is location-independent: it references its assets relatively and
resolves its API, media, and panel modules from the document URL. Serve it at a
domain root, or copy its contents anywhere inside a containing site's document
root -- `/spaces/research/`, somewhere deeper, or a different path later -- with
no re-export and nothing to declare. No proxy, cookie, or referrer routing is
required.

Sample similarity is omitted by default. Enable a bounded precomputed index
when the demo exposes nearest-neighbor browsing:

```bash
hyperview export research --out dist/research-demo --similarity-k 25
```

The bundle contains the packaged static frontend, `api/runtime.json`,
`api/dataset.json`, sample shards under `api/samples/`, media and thumbnails,
layout coordinate JSON under `api/embeddings/`, materialized collection items
under `api/collections/`, and extension panel modules under
`api/panels/content/`. It also carries what only a Live Space reads:
per-space sample embedding vectors under `restore/spaces/` and each installed
extension's full folder (manifest, Python tools, assets) under `extensions/`.
It writes a versioned `hyperview-static.json`
manifest and a static-assets-only `wrangler.jsonc` configuration. Deploy the
bundle to Cloudflare from its output directory with:

```bash
npx wrangler deploy --config wrangler.jsonc
```

The generated `index.html` sets `window.__HYPERVIEW_STATIC__ = true`. In this
mode the frontend reads JSON files from the bundle. Selection, prepared-case
panel prop changes, panel state, filtering, and result presentation remain
ephemeral client-side interactions. Durable workspace writes, Python tools,
model execution, and arbitrary inference/search are unavailable; controls for
those capabilities are hidden. The host shows a read-only notice, currently labelled
`Static Space`.

Python launch/session code can export the same bundle:

```python
session = hv.launch(dataset, block=False)
session.export("dist/research-demo", workspace_id="research", similarity_k=25)
```

For persisted workspaces, use the top-level API:

```python
import hyperview as hv

hv.export_workspace("research", "dist/research-demo")
```

## Publishing

`hyperview export` writes a bundle directory; `hyperview publish` takes that
directory to a host. Publishing never re-reads the workspace, so the bundle you
reviewed is exactly the bundle that goes out.

Print the plan first. A dry run touches no network and writes nothing outside a
temporary staging directory:

```bash
hyperview publish dist/research-demo --to hf:hyper3labs/research-demo --dry-run
```

Publish the files as a **Static Space** on Hugging Face. HyperView creates the
Space with `sdk: static` when it does not exist, writes a `README.md` whose
frontmatter configures the Space, and replaces the previous upload so stale
files disappear:

```bash
hyperview publish dist/research-demo --to hf:hyper3labs/research-demo
hyperview publish dist/research-demo --to hf:hyper3labs/research-demo --private
hyperview publish dist/research-demo --to hf:hyper3labs/research-demo --title "Research Demo" --emoji "🔭"
```

Publish a **Live Space**: a generated Docker Space that runs
`hyperview serve --from <bundle> --public`, for demos that need text queries,
model jobs, or computed layouts. The image pins the versions the manifest
records; add anything else the demo imports:

```bash
hyperview publish dist/research-demo \
  --to hf:hyper3labs/research-live \
  --mode live \
  --extra-pip "hyper-models[ml]==0.3.1" \
  --extra-pip "torch==2.9.1" \
  --hardware cpu-upgrade
```

Deploy the same bundle to Cloudflare. This runs the Wrangler command the
manifest records, from the bundle directory. `--project` renames the Worker in
`wrangler.jsonc` first:

```bash
hyperview publish dist/research-demo --to cloudflare
hyperview publish dist/research-demo --to cloudflare --project gallery-research
```

Copy the bundle into a containing static site:

```bash
hyperview publish dist/research-demo --to dir:site/spaces/research
```

Authentication for Hugging Face targets comes from `HF_TOKEN` or a prior
`hf auth login`; HyperView does not prompt for one.

From Python:
## Live Spaces from a bundle

The same bundle also runs as a **Live Space**: a real runtime with the
dataset, embedding spaces, layouts, collections, extensions, and the exported
view already applied. Serve one with `--from`:

```bash
hyperview serve --from dist/research-demo --no-browser
```

The dataset lands in the current `HYPERVIEW_DATASETS_DIR` under the name the
bundle records. Restoring the same bundle again reuses it, so a container that
restarts comes back to the same Space instead of re-ingesting.

`--public` drops the session token, the same as setting `HYPERVIEW_NO_AUTH=1`.
Viewer-facing commands (panel state, selection, collections, layout view) stay
open; everything that imports modules, installs extension code, or starts
unbounded compute stays closed, and Python tools return 403.

```bash
hyperview serve --from dist/research-demo --public --host 0.0.0.0 --port 7860 --no-browser
```

Restore under a different workspace id with `--workspace-id`, which applies
only together with `--from`:

```bash
hyperview serve --from dist/research-demo --workspace-id research-live --no-browser
```

Unlike a Static Space, a Live Space answers typed text queries, runs Python
tools, computes new embeddings and layouts, and persists workspace mutations,
because the bundle carries the per-space sample vectors and each extension's
full folder.

Python code can restore the same bundle:

```python
import hyperview as hv

hv.publish("dist/research-demo", to="hf:hyper3labs/research-demo", mode="static")
hv.publish("dist/research-demo", to="hf:hyper3labs/research-live", mode="live", dry_run=True)
hv.launch(from_bundle="dist/research-demo", open_browser=False)
```

To restore without serving -- to inspect or mutate the workspace first:

```python
import hyperview as hv

workspace_id = hv.restore_workspace("dist/research-demo")
```

## Runtime UI

Discover an existing layout key and sample IDs before mutating runtime state:

```bash
curl --max-time 2 'http://127.0.0.1:6262/api/runtime?workspace_id=research' | jq '.workspace.ui'
curl --max-time 2 'http://127.0.0.1:6262/api/embeddings?workspace_id=research' | jq '{layout_key, geometry, ids: (.ids[:3])}'
```

If no layout exists yet (`active_layout_key` is `null` and `/api/embeddings` returns nothing), create one with `hyperview embeddings compute ... --layout euclidean:2d` (creates embeddings + layout) or `hyperview layouts compute ... --space-key <space-key> --layout euclidean:2d` (adds a layout to an existing embedding space).

Runtime command ids are namespaced:

- `workspace.*` for workspace/view/panel placement and panel-owned state storage
- `panel.<type>.*` for panel-owned transitions such as Samples retrieval
- `collection.*` for materialized filters, neighbors, and query result sets

Every control command returns a `CommandResult` envelope with `ok`, `command`,
`result`, `workspace`, `snapshot`, `revision`, and optional `error`. Apply the
returned `snapshot` when present. Do not issue an immediate `/api/runtime`
refetch unless a legacy endpoint did not return a snapshot.

`collection.filter.set`, `collection.selection.set`, and
`collection.neighbors.create` take an **optional panel target**. Their target is
`{"workspace_id": "<workspace>", "panel_id": "<panel>"}`; leaving `panel_id` out
keeps the canonical Samples panel, which is what the CLI and the Python API
send, so nothing about the default path changes. Naming a panel writes that
panel's own state (`ui.panels.<panel_id>`), bumps its `state_revision` — which
is the `revision` the result reports, as for `workspace.panel.state.patch` —
and returns the real `panel_id` in `result`. This is how an extension panel
owns its own collection-backed sample view rather than driving Samples. The
Samples aliases (`samples`, `grid`) resolve to Samples; an unknown `panel_id`
fails with `not_found`.

```bash
curl --max-time 2 -X POST 'http://127.0.0.1:6262/api/control/commands/run' \
  -H 'Content-Type: application/json' \
  -d '{"command":"collection.filter.set","target":{"workspace_id":"research","panel_id":"readout"},"args":{"field":"label","value":"cat"}}'
```

Switch the live UI to a layout and selection:

```bash
hyperview ui layout set --workspace research --layout-key <layout-key>
hyperview ui selection set --workspace research --ids sample-1,sample-8
```

`--layout-key` must be an existing layout (use the `layout_key` returned by `/api/embeddings`). When the chosen layout is Euclidean 3D, HyperView opens or focuses the Euclidean 3D scatter panel.

Add a custom panel through an extension. Panel add/update/remove and panel
layout controls share HyperView's public control command path; prefer these CLI
commands or the matching Python `session.ui` helpers in examples.

```bash
hyperview extension add .hyperview/extensions/label-histogram \
  --workspace research

# The same manifest/source format can be distributed with HyperView.
hyperview extension add --shipped <extension-name> \
  --workspace research

hyperview ui panel add \
  --workspace research \
  --panel-id label-histogram \
  --extension label-histogram \
  --extension-panel label-histogram \
  --position right \
  --width 340 \
  --min-width 280 \
```

Add the built-in samples panel through the same runtime panel API:

```bash
hyperview ui panel add \
  --workspace research \
  --panel-id samples \
  --kind builtin \
  --builtin-panel samples \
  --props-json '{"mode":"browse"}' \
  --position right
```

Add two runtime scatter panels bound to explicit layouts, side by side:

```bash
hyperview ui panel add \
  --workspace research \
  --panel-id uncha-poincare \
  --title "UNCHA" \
  --kind scatter \
  --layout-key <uncha-poincare-layout-key> \
  --position center

hyperview ui panel add \
  --workspace research \
  --panel-id hycoclip-poincare \
  --title "HyCoCLIP" \
  --kind scatter \
  --layout-key <hycoclip-poincare-layout-key> \
  --position center \
  --reference-panel-id uncha-poincare \
  --direction right
```

Python launch scripts can encode the same composition:

```python
view = hv.ui.View(
    hv.ui.Horizontal(
        hv.ui.Scatter("uncha-poincare", title="UNCHA", layout_key=uncha_layout),
        hv.ui.Scatter("hycoclip-poincare", title="HyCoCLIP", layout_key=hycoclip_layout),
    ),
    hv.ui.ExtensionPanel(
        "notes",
        extension="notes",
        panel="notes",
        position="right",
        layout=hv.ui.PanelLayout(width=340, min_width=280),
    ),
    active_panel="notes",
)
session = hv.launch(dataset, block=False)
session.ui.add_extension(".hyperview/extensions/notes")
session.ui.apply_view(view)
```

Update an existing runtime panel title or props without changing its identity:

```bash
hyperview ui panel update \
  --workspace research \
  --panel-id samples \
  --title "Ranked Samples" \
  --props-json '{"mode":"ranked","rank":{"anchorSampleId":"<sample-id>","layoutKey":"<layout-key>","k":18}}' \
  --json
```

Resize, move, focus, hide, or show a runtime panel through durable view state:

```bash
hyperview ui panel resize \
  --workspace research \
  --panel-id notes \
  --width 380 \
  --min-width 300

hyperview ui panel move \
  --workspace research \
  --panel-id notes \
  --position right \
  --reference-panel-id samples \
  --direction right

hyperview ui panel focus --workspace research --panel-id notes
hyperview ui panel close --workspace research --panel-id notes
hyperview ui panel show --workspace research --panel-id notes
```

Read or patch durable panel-owned state:

```bash
hyperview ui panel state get \
  --workspace research \
  --panel-id samples \
  --json

hyperview ui panel state patch \
  --workspace research \
  --panel-id samples \
  --state-json '{"settings":{"density":"compact"}}' \
  --expected-revision 0 \
  --json
```

Remove a runtime panel by id:

```bash
hyperview ui panel remove \
  --workspace research \
  --panel-id hycoclip-poincare
```

Pin nearest-neighbor results to the Samples panel state for a specific embedding layout:

```bash
hyperview ui samples retrieval set-anchor \
  --workspace research \
  --sample-id <sample-id> \
  --index-id space:<space-key> \
  --k 18

hyperview ui samples retrieval set-k \
  --workspace research \
  --k 36

hyperview ui samples retrieval set-text \
  --workspace research \
  --query "a dog playing in the park" \
  --index-id space:<space-key> \
  --k 18
```

Clear the explicit Samples retrieval context:

```bash
hyperview ui samples retrieval clear --workspace research
```

Use `hyperview ui samples retrieval ...` for compatibility with existing CLI
flows. Raw commands should use the canonical `panel.samples.retrieval.*`
command ids.

Use panel collection shortcuts when the desired outcome is a Samples panel collection:

```bash
hyperview panel samples show-results \
  --workspace research \
  --sample-id sample-1 \
  --sample-id sample-8 \
  --json

hyperview panel samples reset --workspace research --json

hyperview panel samples show-neighbors \
  --workspace research \
  --sample-id <sample-id> \
  --index-id space:<space-key> \
  --k 18 \
  --json

hyperview panel labels filter \
  --workspace research \
  --value cat \
  --json

hyperview panel labels filter --workspace research --clear
```

## Extensions and Tools

Create extensions under `.hyperview/extensions/<name>/` so they can be versioned with the project and auto-registered on `hyperview serve`. For a server that is already running, install one explicitly:

```bash
hyperview extension add .hyperview/extensions/selection-profile \
  --workspace research \
  --json
```

Inspect and run installed extension tools:

```bash
hyperview extension list --json
# => {"extensions":[{"name":"selection-profile","folder":"...","workspace_id":"research","panel_definitions":[{"id":"selection-profile",...}],"tools":[{"uri":"selection_profile.summarize",...}]}]}

hyperview tools list --json
hyperview tools run selection_profile.summarize \
  --workspace research \
  --param 'sample_ids=["sample-1","sample-8"]' \
  --json
```

`--param key=value` parses the value as JSON, then falls back to a raw string if JSON parsing fails. Use:

- `--param 'top_k=5'` for numbers
- `--param 'enabled=true'` for booleans
- `--param 'name=foo'` for short strings (raw fallback) or `--param 'name="foo bar"'` for explicit JSON strings
- `--param 'ids=["a","b"]'` or `--param 'opts={"k":1}'` for arrays/objects
