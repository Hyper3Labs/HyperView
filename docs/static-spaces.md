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

A bundle is location-independent: the shell, static API, media, and panel
modules resolve relative to the document URL, so the same directory works at an
origin root or copied into `spaces/research/` under a larger static site, and
several Shared Spaces can be open on one origin without cookies, referrer
routing, or per-Space servers. A bundle whose manifest records a `mount_path`
was produced by an older HyperView and must be re-exported.

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
capability flags, panel compatibility, artifact paths, and Cloudflare deployment
metadata. Consumers should reject unsupported future `schema_version` values
rather than guessing at paths.
