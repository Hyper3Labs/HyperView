# HyperView Spaces

`hyperview export` writes a **bundle**: one folder that is the unit of
delivery. It hosts two ways.

- A **Static Space** serves the bundle's files from a static host. It preserves
  the full HyperView shell and prepared viewing experience without running
  Python, LanceDB, or a container for each visitor, and is read-only with
  respect to durable workspace and backend/model operations.
- A **Live Space** hands the same folder to a running HyperView with
  `hyperview serve --from`, backing it with a real runtime. Use it when
  visitors need typed text queries, provider/model jobs, computed layouts,
  Python tools, or durable mutation.

One export covers both.

## Export

Build the dataset, embeddings, layouts, view, and extension panels normally,
then export the workspace:

```bash
hyperview export research --out dist/research
```

Sample-to-sample similarity is omitted by default to keep export cost and
bundle size bounded. Enable it explicitly with `--similarity-k`:

```bash
hyperview export research --out dist/research --similarity-k 25
```

The output includes a versioned `hyperview-static.json` manifest, the frontend,
runtime and dataset snapshots, lazy sample and similarity shards, media,
thumbnails, layouts, materialized collections, compatible extension panels,
and `wrangler.jsonc`.

Re-exporting into an existing HyperView bundle replaces it. Exporting into a
non-empty directory that is not already a HyperView bundle is rejected.

The exporter reports warnings in the CLI result and in the manifest's
`warnings` array when referenced local media or panel module source is missing.
Treat those warnings as release blockers for public demos: the bundle remains
browsable so it can be inspected, but affected images or panels are unavailable.

A bundle is location-independent. It references its assets relatively and
resolves its API, media, and panel modules from the document URL, so the same
export works at an origin root and inside `spaces/research/` of a containing
site, with no re-export and nothing to declare. Several Shared Spaces can sit on
one origin without cookies, referrer routing, or per-Space servers.

A bundle whose manifest records a `mount_path` was produced by an older
HyperView and must be re-exported.

## Publish a bundle

The exported directory is the unit of delivery. `hyperview publish` takes that
directory to a host; it never re-reads the workspace, so what you reviewed
locally is what visitors get.

There are two ways to host a bundle, and the choice is about what visitors are
allowed to do:

- A **Static Space** serves the bundle's files. No Python, no database, no model
  runs for a visitor. Everything on offer was computed during the export.
- A **Live Space** runs a container with `hyperview serve --from <bundle>
  --public` inside it. Visitors get the same prepared view plus the things a
  server can do: new text queries, model jobs, computed layouts.

Start with a dry run, always. It prints the plan and the files it would
generate, and it touches neither the network nor the destination:

```bash
hyperview publish dist/research --to hf:hyper3labs/research-demo --dry-run
```

### Hugging Face, as a Static Space

```bash
hyperview publish dist/research --to hf:hyper3labs/research-demo
```

If the Space does not exist, HyperView creates it with `sdk: static`. It then
uploads the bundle, replacing the previous contents so files from an older
export do not linger. It also writes the `README.md` whose YAML frontmatter is
how a Space is configured: title, emoji, SDK, and a one-line description, all
derived from the bundle's manifest. Override the two that are a matter of taste:

```bash
hyperview publish dist/research \
  --to hf:hyper3labs/research-demo \
  --title "Research Demo" \
  --emoji "🔭" \
  --private
```

Authentication comes from the `HF_TOKEN` environment variable or a prior
`hf auth login`. HyperView does not prompt for a token.

### Hugging Face, as a Live Space

```bash
hyperview publish dist/research --to hf:hyper3labs/research-live --mode live
```

This stages the bundle together with a generated `Dockerfile` and a `README.md`
declaring `sdk: docker` and `app_port: 7860`, then creates the Space with the
Docker SDK and uploads the staged directory. The image installs the HyperView
version and model pins the manifest records, copies the bundle in, and runs
`hyperview serve --from /home/user/app/bundle --host 0.0.0.0 --port 7860
--public`.

Add whatever else the demo imports, and request more than the free CPU when the
models need it:

```bash
hyperview publish dist/research \
  --to hf:hyper3labs/research-live \
  --mode live \
  --extra-pip "hyper-models[ml]==0.3.1" \
  --extra-pip "torch==2.9.1" \
  --hardware cpu-upgrade
```

The generated image sets `HYPERVIEW_NO_AUTH=1`. That flag marks the server
public rather than unprotected: a Space cannot hand a visitor a session token,
so without it panel creation and case switching would fail with a 401. Visitors
get the viewer commands and nothing more. Provider registration, extension
install, tool execution, and embedding or layout compute stay behind the token
and answer 403.

### Cloudflare

```bash
hyperview publish dist/research --to cloudflare
```

This runs the Wrangler command recorded in the manifest, from the bundle
directory -- the same command described under [Cloudflare](#cloudflare) below.
Rename the Worker with `--project`, which rewrites `wrangler.jsonc` before
deploying:

```bash
hyperview publish dist/research --to cloudflare --project gallery-research
```

If `npx` is not on `PATH`, publishing stops and tells you to install Node.js
rather than failing somewhere inside the deploy.

### A directory in a containing site

```bash
hyperview publish dist/research --to dir:site/spaces/research
```

This copies the bundle onto the packaged frontend at that path. Use it when the
Space lives inside a site you already deploy.

### From Python
resolves its API, media, and panel modules from the document URL, so it can be
served at a domain root or copied anywhere inside a containing site's document
root -- `spaces/research/`, somewhere deeper, or a different path later -- with
no re-export and nothing to declare. Several Static Spaces can be open on one
origin without cookies, referrer routing, or per-Space servers.

## Run a bundle as a Live Space

Hand the exported folder to a running HyperView:

```bash
hyperview serve --from dist/research --no-browser
```

Restore recreates the dataset in the current `HYPERVIEW_DATASETS_DIR` under the
name the bundle records, points sample media at the bundle's own copies,
recreates every embedding space and layout under the ids and keys the export
used, recreates the collections the view references, installs each extension
the bundle carries, and applies the exported workspace snapshot. The server
opens on exactly the exported view.

Restore is idempotent. A container that restarts against the same datasets
directory reuses the dataset it finds rather than re-ingesting, and
re-registering vectors and coordinates is an upsert.

Add `--public` for a Space with no session token — the flag spelling of
`HYPERVIEW_NO_AUTH=1`, which still works:

```bash
hyperview serve --from dist/research --public --host 0.0.0.0 --port 7860 --no-browser
```

Public is not open. Anonymous visitors keep the viewer commands; anything that
imports modules, installs extension code, or starts unbounded compute stays
closed, and Python tools answer 403.

`--workspace-id` restores under a different workspace id and applies only
together with `--from`. Python callers use the same path:

```python
import hyperview as hv

hv.publish("dist/research", to="hf:hyper3labs/research-demo", mode="static")
hv.publish("dist/research", to="hf:hyper3labs/research-live", mode="live", dry_run=True)
```
hv.launch(from_bundle="dist/research", open_browser=False)

# Or restore without serving, to inspect or mutate the workspace first.
workspace_id = hv.restore_workspace("dist/research")
```

Unlike a Static Space, a Live Space answers typed text queries, runs Python
tools, computes new embeddings and layouts, and persists workspace mutations.
That is why the bundle carries per-space sample embedding vectors under
`restore/` and each extension's full folder under `extensions/`: a browser
needs neither, and a live server cannot reconstruct either from a 2D
projection or from the panel source published for static hosting.

## Cloudflare

The generated Wrangler configuration contains only a Static Assets binding and
no Worker script. From the exported directory:

```bash
npx wrangler deploy --config wrangler.jsonc
```

Cloudflare serves matching files directly and uses `index.html` as the SPA
fallback. No HyperView request invokes Python, LanceDB, a model, or a Cloudflare
Container. Run the same bundle as a Live Space when a demo needs compute, text search,
Python tools, or persistent workspace mutation.

## Static Space capabilities

Static Spaces support browsing samples and media, exported layouts, selection,
2D lasso, label filtering, materialized collections, precomputed
sample-to-sample similarity, and browser-only extension panels. They do not
support text-query inference, new embeddings or layouts, Python tools, 3D
lasso, runtime jobs, or durable control-plane mutations.

Panel state patches are ephemeral for the current browser session. Other
mutating commands show the read-only notice and leave the exported runtime
snapshot unchanged.

## Extension Panels

Extension panels are static-compatible by default. Mark a panel that requires
the live server explicitly:

```toml
[[panels]]
id = "analysis"
title = "Analysis"
file = "panel.jsx"
static_compatible = false
static_reason = "Requires the analysis.run Python tool."
```

Server-required panels remain visible in the exported view with the reason, but
their module and Python/tool source files are not published. A static-compatible
panel may use bundled assets, exported queries, selection, and ephemeral panel
state through `HyperViewPanelSDK`.

## Bundle Contract

`hyperview-static.json` is the entrypoint for deployment tooling. It records the
bundle schema and HyperView versions, creation time, workspace fingerprint,
capability flags, panel compatibility, artifact paths, Cloudflare deployment
metadata, and under `deployment.targets` the hosting models the bundle supports
and the `hyperview publish` command for each. Consumers should reject unsupported future `schema_version` values
rather than guessing at paths.

A `restore` section describes what a Live Space needs: the dataset name and
sample index, the media root, each embedding space with its provider id, model
id, dimension, and vector file, each layout key with its coordinate file, the
collection ids, and the extension folders. A sibling `producer` section records
the `hyperview` and `hyper-models` versions that produced the vectors, so a
container can tell whether it is able to encode a query into the same space.
Both are additive: `schema_version` stays `1` and every field a Static Space
consumer already reads is unchanged. `restore.schema_version` versions the
restore contract on its own.
