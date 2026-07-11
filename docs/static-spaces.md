# Static HyperView Spaces

Static Spaces are read-only workspace exports for public demos. They preserve
the prepared HyperView viewing experience without running Python, LanceDB, or a
container for each visitor.

## Export

Build the dataset, embeddings, layouts, view, and extension panels normally,
then export the workspace:

```bash
hyperview export research --out dist/research
```

Sample-to-sample similarity is precomputed by default. Control its bundle size
with `--similarity-k`, or omit it entirely with `--similarity-k 0`:

```bash
hyperview export research --out dist/research --similarity-k 25
```

The output includes a versioned `hyperview-static.json` manifest, the frontend,
runtime and dataset snapshots, lazy sample and similarity shards, media,
thumbnails, layouts, materialized collections, compatible extension panels,
and `wrangler.jsonc`.

Re-exporting into an existing HyperView bundle replaces it. Exporting into a
non-empty directory that is not already a HyperView bundle is rejected.

## Cloudflare

The generated Wrangler configuration contains only a Static Assets binding and
no Worker script. From the exported directory:

```bash
npx wrangler deploy --config wrangler.jsonc
```

Cloudflare serves matching files directly and uses `index.html` as the SPA
fallback. No HyperView request invokes Python, LanceDB, a model, or a Cloudflare
Container. Keep Hugging Face Spaces as the full-runtime deployment when a demo
needs compute, text search, Python tools, or persistent workspace mutation.

## Static Capabilities

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
capability flags, panel compatibility, artifact paths, and Cloudflare deployment
metadata. Consumers should reject unsupported future `schema_version` values
rather than guessing at paths.
