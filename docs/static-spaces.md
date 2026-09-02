# HyperView Shared Spaces

A Shared Space is a portable, read-only workspace export. It preserves the full
HyperView shell and prepared viewing experience without running Python,
LanceDB, or a container for each visitor. Use a Live Space when visitors need
new queries, provider/model jobs, computed layouts, or durable mutation.

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

```python
import hyperview as hv

hv.publish("dist/research", to="hf:hyper3labs/research-demo", mode="static")
hv.publish("dist/research", to="hf:hyper3labs/research-live", mode="live", dry_run=True)
```

## Cloudflare

The generated Wrangler configuration contains only a Static Assets binding and
no Worker script. From the exported directory:

```bash
npx wrangler deploy --config wrangler.jsonc
```

Cloudflare serves matching files directly and uses `index.html` as the SPA
fallback. No HyperView request invokes Python, LanceDB, a model, or a Cloudflare
Container. Keep a Hugging Face Live Space as the runtime-connected deployment when a demo
needs compute, text search, Python tools, or persistent workspace mutation.

## Shared Space capabilities

Shared Spaces support browsing samples and media, exported layouts, selection,
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
file = "panel.js"
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
