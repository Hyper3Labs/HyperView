# HyperView Architecture Direction

HyperView is an agent-native workspace for exploring datasets through
representations, indexes, collections, layouts, and panels. The core design goal
is to keep data, retrieval, visualization, and UI composition separate enough
that built-in panels and extensions can use the same low-level primitives.

This document describes the target architecture. The current implementation is
still an MVP, so the migration plan is intentionally incremental.

## Target Vocabulary

### Workspace

A workspace is the durable runtime scope. It contains dataset references,
derived representations, indexes, collections, layouts, panels, interaction
channels, and the current View.

For now, HyperView should keep the user-facing model as one primary dataset per
workspace. Internally, every data-bearing object should still be scoped by
`dataset_id` so that multiple datasets can be supported later without changing
the object model.

### DatasetRef and EntitySet

A dataset is a container. An entity set is the row universe inside that
container.

Examples:

- `samples`
- `frames`
- `patches`
- `detections`
- `text_chunks`
- `documents`

Every entity reference should eventually be scoped:

```ts
type EntityRef = {
  datasetId: string;
  entitySetId: string;
  entityId: string;
};
```

This is the primitive that makes multi-dataset work, video frames, object
patches, and multimodal records possible without special cases.

### Field

A field is a typed component on an entity set.

Examples:

- media fields: `image`, `video`, `audio`, `text`
- annotation fields: `label`, `bbox`, `segmentation`, `tags`
- metadata fields: `brand`, `department`, `split`
- numeric fields: `score`, `loss`, `uncertainty`
- representation fields: `clip_vector`, `colbert_tokens`
- coordinate fields: `umap_xy`, `pca_xyz`

Fields should carry enough schema metadata for panels and extensions to discover
what they can render or query.

### Representation

A representation is a derived data field, usually produced by a model or
transform. This replaces most public uses of the current `space` concept.

```ts
type Representation = {
  id: string;
  datasetId: string;
  entitySetId: string;
  fieldPath: string;
  kind: "vector" | "multi_vector" | "coordinate" | "scalar" | "text" | "custom";
  shape: number[] | string[];
  modelId?: string;
  modality?: "image" | "text" | "video" | "audio" | "multimodal" | "custom";
};
```

A CLIP image embedding is a `Representation(kind="vector")`. A late-interaction
model such as ColBERT/ColPali is a `Representation(kind="multi_vector")`.

### Index

An index is a searchable/scorable access path over a representation. It is
separate from the representation because the same vectors can support different
indexes, scorers, or retrieval strategies.

```ts
type Index = {
  id: string;
  representationId: string;
  queryMode: "nearest" | "text" | "hybrid" | "maxsim" | "custom";
  scorer: "cosine" | "dot" | "l2" | "maxsim" | "custom";
  backend?: "lancedb" | "memory" | "custom";
};
```

This is where single-vector, multi-vector, hybrid, and late-interaction search
belong. LanceDB's multivector search is a useful reference point: it supports
multiple vectors per item for late-interaction models such as ColBERT and
ColPali, with MaxSim-style scoring.

### Collection

A collection is an ordered or queryable set of entities. It is not a renderer.

```ts
type Collection = {
  id: string;
  datasetId: string;
  entitySetId: string;
  kind:
    | "all"
    | "filter"
    | "selection"
    | "neighbors"
    | "lasso"
    | "search"
    | "tool_result"
    | "extension";
  query: Record<string, unknown>;
  scores?: Record<string, number>;
};
```

Nearest neighbors should be a collection:

```ts
{
  id: "neighbors:clip:sample-123",
  kind: "neighbors",
  query: {
    anchor: { datasetId: "abo", entitySetId: "samples", entityId: "sample-123" },
    indexId: "clip-image-cosine",
    k: 18
  }
}
```

A label filter should also be a collection:

```ts
{
  id: "label:LIGHT_FIXTURE",
  kind: "filter",
  query: { field: "label", op: "eq", value: "LIGHT_FIXTURE" }
}
```

The important rule is that filters, lasso results, nearest-neighbor results,
search results, and tool results are peer concepts. They all produce
collections.

### Layout

A layout is a visual coordinate representation. It is usually derived from a
vector representation, but it is not the same thing as the representation.

```ts
type Layout = {
  id: string;
  representationId: string;
  coordinateField: string;
  dimensions: 2 | 3 | number;
  coordinateModel?: "cartesian" | "poincare-ball" | "spherical" | "custom";
  method?: "umap" | "pca" | "tsne" | "custom";
};
```

`coordinateModel` is renderer metadata, not a top-level atom. A Poincare scatter
panel is a renderer that accepts `coordinateModel="poincare-ball"` and
`dimensions=2`. Other scatter panels can declare different capabilities.

### Panel

A panel is a renderer/controller bound to sources.

```ts
type Panel = {
  id: string;
  type: "image-grid" | "scatter" | "facets" | "inspector" | "table" | "extension";
  sources: {
    collectionId?: string;
    layoutId?: string;
    entityRef?: EntityRef;
  };
  state: Record<string, unknown>;
};
```

Examples:

- ImageGrid renders a `Collection`.
- Scatter renders a `Layout`.
- Facets/Labels renders field summaries over a collection or entity set.
- Inspector renders one or more entities.
- Extension panels can render any source they declare support for.

### View

A View is the workspace composition layer. It defines which panels exist, how
they are arranged, and what sources they are bound to.

This is analogous to Rerun's blueprint/view composition layer, but HyperView
should use the name `View` in public APIs because it is already the term used by
the current Python UI composition API.

```ts
type View = {
  id: string;
  panels: Panel[];
  layoutTree: Record<string, unknown>;
  interactionChannels: InteractionChannel[];
};
```

### Interaction Channel

Selection, hover, and focus are interaction state, not data model atoms.

```ts
type InteractionChannel = {
  id: string;
  selectionCollectionId?: string;
  hoveredEntity?: EntityRef;
  focusedPanelId?: string;
};
```

Panels can publish to and subscribe from channels. This gives coordinated
highlighting and selection without making every panel-specific behavior global.

## Current vs Target Model

| Area | Current HyperView | Target model | Priority |
| --- | --- | --- | --- |
| Workspace data | One active dataset per workspace | One primary dataset now, multiple dataset refs later | Later |
| Sample identity | Plain `sample_id` strings | Scoped `EntityRef` with `datasetId`, `entitySetId`, `entityId` | High |
| Dataset model | Dataset of samples | Dataset with entity sets: samples, frames, patches, chunks | Medium |
| Fields | Mostly implicit sample fields | Typed fields/components discoverable by panels | Medium |
| Space | First-class embedding space | Split into `Representation` and `Index` | High |
| Geometry | Special enum on space/layout/panel | Renderer/layout metadata such as `coordinateModel` | Medium |
| Layout | Projection of a space | Coordinate field over a representation | Medium |
| Similarity query | Global `similarity_query` UI state | `Collection(kind="neighbors")` backed by an index | High |
| Label filter | Global `labelFilter` value | `Collection(kind="filter")` created by Facets/Labels | High |
| Selection | Global set of sample ids | Interaction-channel selection as a collection | Medium |
| Hover | Global `hoveredId` | Ephemeral interaction-channel entity ref | Low |
| Image grid | Owns dataset, selection, neighbors display | Renderer for one or more collections | High |
| Neighbors | Derived section inside image grid | Peer-level collection rendered by ImageGrid or other panels | High |
| Scatter | Panel bound to layout | Renderer bound to layout with declared capabilities | Medium |
| Left panel | Explorer/labels panel with global label filter | Facets panel that creates/activates filter collections | Medium |
| Panel commands | Mixed `ui ...` commands and SDK helpers | Commands owned by workspace or panels | High |
| Extensions | Tools and panel modules | Tools, panels, collection sources, renderers, commands | Medium |
| View composition | `hv.ui.View` with panels and positions | Keep and extend as the first-class composition layer | Already good |

## Migration Plan

### 1. Introduce target vocabulary without changing UX

Add internal types and docs for:

- `EntityRef`
- `Representation`
- `Index`
- `Collection`
- `Layout`
- `Panel`
- `View`
- `InteractionChannel`

Keep current APIs working while mapping existing fields into the new names.

### 2. Replace `similarity_query` with collections

Keep `showSimilar()` as the public command, but implement it by creating or
activating a collection:

```ts
Collection(kind="neighbors", query={ anchor, indexId, k })
```

The Samples/ImageGrid panel should render this collection. The nearest-neighbor
query should not depend on the active scatter panel.

### 3. Move label filter into collections

Replace global `labelFilter` with:

```ts
Collection(kind="filter", query={ field: "label", op: "eq", value })
```

The Facets/Labels panel owns commands that create or activate these collections.

### 4. Make ImageGrid a collection renderer

The ImageGrid should receive `collectionId` or named collection slots. It should
not own dataset paging, selection display, nearest-neighbor display, and filter
display as separate hardcoded concepts.

### 5. Add a panel command registry

Move public CLI/API control toward panel-owned commands:

```bash
hyperview panel samples show-neighbors --sample-id ... --index-id ...
hyperview panel labels filter --field label --value LIGHT_FIXTURE
hyperview panel scatter lasso --layout-id ... --polygon ...
```

Keep low-level `hyperview ui ...` commands for workspace shell state and
debugging.

### 6. Split `space_key` into representation and index concepts

For compatibility, `space_key` can remain a temporary alias:

```text
space_key -> representationId + defaultIndexId
```

New code should prefer explicit `representationId` and `indexId`.

### 7. Downgrade geometry to renderer/layout metadata

Replace public geometry-as-atom thinking with:

```ts
Layout {
  dimensions: 2 | 3
  coordinateModel: "cartesian" | "poincare-ball" | "spherical" | "custom"
}
```

Scatter panels declare what coordinate models and dimensions they accept.

### 8. Add multi-dataset support only after IDs are scoped

Do not start by adding many active datasets. First ensure every collection,
layout, representation, index, and interaction channel is dataset-scoped. Then
multi-dataset Views become an additive feature.

## Comparison: FiftyOne

FiftyOne is the closest reference for HyperView's data/query layer.

Useful similarities:

- FiftyOne's `DatasetView` is created by operations on a dataset, and views are
  largely interchangeable with datasets in many operations.
- Dataset views can filter samples, select/exclude fields, filter nested labels,
  and transform the row universe into patches, clips, trajectories, or frames.
- FiftyOne Brain computes similarity indexes and exposes similarity search as a
  view operation: `sort_by_similarity(...)` returns a view of sorted results.
- Object similarity works over patch views, not just whole-image samples.

What HyperView should borrow:

- Treat filters, patches, frames, clips, and similarity results as first-class
  collections/views over entity sets.
- Make similarity search produce an ordered collection rather than a special
  ImageGrid mode.
- Keep indexes separate from the current displayed panel.

Where HyperView should differ:

- HyperView should be more explicit about panel composition and panel commands.
  FiftyOne has strong dataset views, but HyperView needs an agent-addressable UI
  control plane.
- HyperView should separate `Representation` and `Index` earlier, because
  embedding comparison, multivector retrieval, and custom extension indexes are
  central use cases.
- HyperView should make extensions able to add collection sources, renderers,
  and commands, not only visual panels or backend tools.

## Comparison: Rerun

Rerun is the closest reference for HyperView's runtime/view composition layer.

Useful similarities:

- Rerun separates logged data from viewer composition.
- Rerun's viewer composition model has view/container concepts; its Python API
  exposes typed views such as spatial 2D/3D, dataframe, tensor, text, map, and
  time-series views.
- Rerun is built for multimodal and multi-rate data, and its docs emphasize
  logging, visualizing, and querying data across recordings.
- Rerun's DataframeView is a useful signpost for panels that display query
  results rather than hardcoded data modes.

What HyperView should borrow:

- Keep data separate from the View that displays it.
- Let each renderer declare what data/source capabilities it accepts.
- Treat View composition as a first-class API, not a side effect of extension
  manifests.

Where HyperView should differ:

- Rerun's public term is still blueprint-oriented in its Python API. HyperView
  should call the composition layer `View` publicly.
- Rerun is optimized around time, recordings, timelines, and robotics/Physical
  AI logs. HyperView is optimized around dataset curation, embeddings,
  retrieval, and agent-driven workspace control.
- HyperView needs collections and indexes as central atoms. Rerun's model is
  stronger for temporal entity/component logs than for FiftyOne-style dataset
  views and similarity result collections.

## Recommended Direction

The next architectural step is not multi-dataset support and not more special
panel state. The next step is to make collections first-class.

The practical sequence is:

1. Introduce `Collection` internally.
2. Represent nearest neighbors as `Collection(kind="neighbors")`.
3. Represent label filters as `Collection(kind="filter")`.
4. Make ImageGrid render collections.
5. Add panel-owned commands that create or activate collections.
6. Split current `space_key` usage into `Representation` and `Index`.
7. Move coordinate-model details into layout/renderer metadata.
8. Add scoped entity refs everywhere before enabling multi-dataset Views.

## References

- Rerun getting started: https://docs.rerun.io/dev/getting-started/
- Rerun Python blueprint APIs: https://ref.rerun.io/docs/python/main/common/blueprint_apis/
- Rerun Python blueprint views: https://ref.rerun.io/docs/python/stable/common/blueprint_views/
- FiftyOne dataset views: https://docs.voxel51.com/user_guide/using_views.html
- FiftyOne creating views: https://docs.voxel51.com/recipes/creating_views.html
- FiftyOne Brain similarity: https://docs.voxel51.com/brain.html#similarity
- LanceDB multivector search: https://docs.lancedb.com/search/multivector-search
