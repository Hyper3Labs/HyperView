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

This is different from `hyperview extension add`, which installs a runtime plugin into a running HyperView workspace.

## Datasets and Workspaces

Create a persisted dataset from Hugging Face:

```bash
hyperview dataset create cifar10_demo \
  --hf-dataset uoft-cs/cifar10 \
  --split train \
  --image-key img \
  --label-key label
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

Register a custom provider:

```bash
hyperview provider register my-provider \
  --import-path my_pkg.provider:MyProvider
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

The export path is pure Python and does not require Playwright, browser bundling, Node, or a running frontend. It supports 3D layouts only; 2D layouts are rejected with a validation message.

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

## Runtime UI

Discover an existing layout key and sample IDs before mutating runtime state:

```bash
curl --max-time 2 'http://127.0.0.1:6262/api/runtime?workspace_id=research' | jq '.workspace.ui'
curl --max-time 2 'http://127.0.0.1:6262/api/embeddings?workspace_id=research' | jq '{layout_key, geometry, ids: (.ids[:3])}'
```

If no layout exists yet (`active_layout_key` is `null` and `/api/embeddings` returns nothing), create one with `hyperview embeddings compute ... --layout euclidean:2d` (creates embeddings + layout) or `hyperview layouts compute ... --space-key <space-key> --layout euclidean:2d` (adds a layout to an existing embedding space).

Switch the live UI to a layout and selection:

```bash
hyperview ui layout set --workspace research --layout-key <layout-key>
hyperview ui selection set --workspace research --ids sample-1,sample-8
```

`--layout-key` must be an existing layout (use the `layout_key` returned by `/api/embeddings`). When the chosen layout is Euclidean 3D, HyperView opens or focuses the Euclidean 3D scatter panel.

Add a native panel from a local JavaScript module file:

```bash
hyperview ui panel add \
  --workspace research \
  --panel-id label-histogram \
  --title "Label Histogram" \
  --position right \
  --module-file agent-context/panels/label-histogram/index.js
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

Remove a runtime panel by id:

```bash
hyperview ui panel remove \
  --workspace research \
  --panel-id hycoclip-poincare
```

## Plugins and Tools

Create backend-plus-frontend plugins under `.hyperview/extensions/<name>/` so they can be versioned with the project and auto-attached on `hyperview serve`. For a server that is already running, install one explicitly:

```bash
hyperview extension add .hyperview/extensions/selection-profile \
  --workspace research \
  --json
```

Inspect and run installed plugin tools:

```bash
hyperview extension list --json
# => {"extensions":[{"name":"selection-profile","folder":"...","workspace_id":"research","panels":["selection-profile"],"tools":[{"uri":"selection_profile.summarize",...}]}]}

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
