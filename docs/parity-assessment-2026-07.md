# HyperView: architecture verdict and a path to parity with Encord / FiftyOne / Rerun

Written 2026-07-04 during the panel/control refactor. Grounded in the
representation/index and collection-materialization work, `docs/architecture.md`,
and the July gap assessment.

## 1. Verdict on the current architecture

**The control plane is architected correctly — and it is the part none of the
three competitors have.** The things that are usually wrong in a tool at this
stage are right here:

- **Machine-readable outcomes end to end.** Every mutation goes through a
  namespaced command (`workspace.*`, `panel.<type>.*`, `collection.*`) and
  returns a `CommandResult` carrying a runtime snapshot. An agent can drive
  the entire workbench without scraping UI state. FiftyOne's operators come
  closest, but they grew out of a plugin system; HyperView's command plane is
  the primary interface, not an add-on.
- **Runtime/workspace state as source of truth.** Layouts resolve server-side,
  panel state is runtime-owned with revisions, selection is a control-plane
  write. The frontend is a renderer, which is why the static export
  (`hyperview export`) fell out almost for free — that trick is only possible
  because no state of record lives in the browser.
- **Collections as first-class query objects.** `all`/`filter`/`neighbors`/
  `search` collections store the *query*, membership is re-materialized on
  read (`GET /api/collections/{id}/items`). This is the correct seed for a
  real view/query system: it is FiftyOne's `DatasetView` concept in embryo,
  and it is already wired through commands, REST, the panel SDK, and static
  export.
- **Explicit extension surfaces.** Provider registry, jobs, panel contracts
  single-sourced from Python, extension panels as JS modules loaded through
  the same `PanelHost` path as built-ins. The built-in/extension symmetry is
  something FiftyOne only reached after years.
- **Representation/index split (contract level).** The right long-term shape
  for multi-vector / late-interaction / hybrid search, introduced without a
  storage migration.

**Where it is architecturally thin is the data model — and that is the entire
gap to the other three tools.** Everything below the control plane assumes:
one dataset per workspace, one entity set (`samples`), one media type
(image + optional text), one annotation type (a string `label`), metadata as
an untyped dict. `EntityRef` (`dataset_id`/`entity_set_id`/`entity_id`)
exists in the object model, but nothing exercises it beyond `"samples"`.
Filters understand `label == value` fast-path and in-memory metadata equality,
and nothing else. There is no schema an agent or panel can discover
(`architecture.md` names this: typed Fields, priority Medium).

So: **correctly architected control plane and extension system; deliberately
minimal data plane.** The order was right — a rich data model behind a bad
control plane is what most tools have, and it's much harder to fix in that
direction. But every parity feature below hangs off the data plane.

Two structural debts worth naming before they calcify:

1. **No frontend test harness.** The Phase 3 hook rewire shipped
   build-verified only. Before panels get more logic, add a minimal vitest +
   React Testing Library setup for the panel SDK hooks and one built-in panel.
2. **In-memory materialization paths.** Non-label filters and several
   resolvers load `ds.samples` wholesale. Fine at 10k samples, dead at 1M.
   Query pushdown into LanceDB (it can do filtered vector search + SQL-ish
   predicates) is the scaling move, and it gets harder the more code grows on
   top of the in-memory idiom.

## 2. What "parity" actually means against these three

The three tools are not one category. Chasing literal feature parity with all
of them is a multi-year, multi-team platform effort and the wrong goal for
where the company is (zero customers, eval→pilot motion, solo founder).
The useful framing: **which of their capabilities does HyperView's actual
buyer (hierarchy-aware retrieval evals/pilots, dataset inspection) hit a wall
without?**

| Capability | FiftyOne | Encord | Rerun | HyperView today |
|---|---|---|---|---|
| Agent-native control plane, machine-readable outcomes | partial (operators) | API/SDK, not agent-first | no | **yes — differentiator** |
| Embedding spaces, similarity/text search, layouts | Brain (strong) | Active (embedding views) | weak | **yes**, incl. hyperbolic — differentiator |
| Static shareable demos, no backend | no | no | .rrd recordings + web viewer | **yes** — differentiator |
| Typed field schema, discoverable by UI | yes | ontologies | ECS archetypes | **no — root gap** |
| Rich label types (boxes, masks, keypoints, polylines) | yes | yes | as renderables | no (string label only) |
| Query/filter DSL over fields | ViewExpressions (strong) | filters + metrics | dataframe API | `label == value` |
| Model evaluation (mAP, confusion, PR, comparisons) | yes | yes | no | no |
| Data/label quality metrics (uniqueness, near-dupes, label errors) | Brain | Active (core) | no | no (but embeddings already in place) |
| Video / frame-level data | yes | yes (core) | yes (core, temporal) | no |
| 3D / point clouds / spatial transforms | yes (FO3D) | limited | yes (core) | no |
| Multi-view / grouped samples (e.g. product SKU with N views) | grouped datasets | yes | entity tree | no |
| Annotation workflows, review/QA, ontologies, teams | integrates out | **core product** | no | no |
| Time-series / streaming ingestion SDK | limited | no | **core product** | no |
| Scale beyond memory | MongoDB-backed views | cloud | out-of-core recordings | partial (LanceDB underused) |

Read the column and the strategy writes itself: HyperView should reach
**functional parity with FiftyOne's curation/inspection core**, adopt
**Encord Active's quality-metrics ideas** (not Encord's annotation factory),
and borrow **Rerun's distribution ideas** (recordings/blueprints ≈ static
bundles/runtime layouts, where HyperView is already ahead). Full Encord
annotation workflows, DICOM, and Rerun's robotics streaming are **non-goals**
— integrate or ignore.

## 3. Gap analysis, ordered by how much everything else depends on it

### Gap 0 — Typed fields / generic dataset records (the root)

Already named in `architecture.md` and the gap assessment as the one real
architectural gap. Everything in section 2's "no" column needs it: label
types are field types; query DSL needs a schema to validate against; quality
metrics need typed numeric fields to write scores into; multi-view needs
entity sets; video needs a `frames` entity set with a time field.

Shape (per architecture.md's own vocabulary): `Field{path, kind, dtype,
schema}` registered per entity set, discoverable via `/api/dataset`, with
media/annotation/metadata/numeric/representation/coordinate kinds. The
`--image-key/--label-key` CLI flags become the first two entries of a real
`FieldMapping` instead of hardcoded parameters.

### Gap 1 — Query algebra over collections

`filter` collections should accept a small, composable predicate tree
(`and`/`or`/`not`, `eq/ne/in/lt/gt/contains/exists`, over typed field paths)
instead of a single field/op/value. This is deliberately *not* FiftyOne's
full ViewExpression language — a JSON predicate tree is easier for agents to
emit reliably, which turns the biggest FiftyOne feature into an agent-native
strength. Push predicates down to LanceDB where possible; that also retires
the in-memory scan debt (§1.2).

### Gap 2 — Label types beyond `label: str`

Detections (boxes), segmentation masks, keypoints, classifications-with-
confidence as field kinds; overlay rendering in the samples grid and a
region/crop view (RefCOCOg-style region search is already a sales demo —
today it's done with pre-cropped images because there is no box field).

### Gap 3 — Evaluation + quality metrics ("Brain/Active-lite")

Two halves, both jobs that write typed fields (which is why Gap 0 comes
first):

- **Retrieval evaluation first, detection later.** HyperView's buyers are
  retrieval buyers. `evaluate.retrieval` (qrels → R@K, mAP, MRR, leakage@K,
  parent-P@K per collection/index) is directly the customer-eval workflow the
  commercial assessment says must be standardized. FiftyOne parity here is
  COCO-style `evaluate_detections`; that can wait for Gap 2.
- **Embedding-derived quality metrics**: uniqueness/near-duplicates (vector
  index already exists), label-outlier scores (label vs. embedding
  neighborhood disagreement — with hyperbolic geometry this is a
  *differentiated* label-error detector for hierarchies), coverage per
  taxonomy branch. This is Encord Active's core value, and HyperView already
  owns the hard part (the embeddings).

### Gap 4 — Grouped / multi-view samples and second entity sets

First real use of `entity_set_id != "samples"`: product → N views, image →
regions. Directly serves catalog customers (multi-view SKU retrieval is in
the commercial assessment's eval wishlist).

### Gap 5 — Video/frames and 3D

Video = a `frames` entity set with a time axis plus frame-level fields —
architecturally just Gap 0 + Gap 4 applied again, but a large UI investment
(scrubbing, per-frame overlays). 3D/point-cloud rendering is a new renderer
class. Neither serves the current pipeline; sequence them behind demand from
an actual deal (an industrial-inspection or AV lead would pull video
forward).

### Gap 6 — Ecosystem: annotation round-trip and import/export

Parity move is FiftyOne's, not Encord's: export a collection to CVAT/Label
Studio/Encord, re-import labels into fields. Plus COCO/YOLO/HF dataset
import-export. This makes HyperView composable with annotation factories
instead of competing with them.

## 4. Sequenced roadmap

Ground rules carried over from the refactor: commands-first, LanceDB stays,
every phase lands green, skill docs updated. Sizes are relative
(S ≈ days, M ≈ 1–2 weeks, L ≈ 3+ weeks solo).

| Phase | Contents | Size | Unblocks |
|---|---|---|---|
| **P1. Fields & records** | Field registry per entity set, typed field kinds, `FieldMapping` on ingestion, `/api/dataset` schema discovery, frontend sidebar driven by schema | M | everything |
| **P2. Query algebra** | JSON predicate tree in `filter` collections, LanceDB pushdown, `collection.filter.set` accepts it, sidebar filter UI emits it | M | FiftyOne-core parity |
| **P3. Retrieval eval + quality jobs** | `evaluate.retrieval` job + report panel; uniqueness/near-dupes/label-outlier jobs writing typed fields | M | customer evals, Active-lite |
| **P4. Label types + overlays** | detections/masks/keypoints field kinds, grid overlays, region view | L | Encord/FO annotation-adjacent parity |
| **P5. Groups & entity sets** | grouped samples, regions as entity set, group-aware grid | M | catalog/multi-view deals |
| **P6. Annotation round-trip + formats** | CVAT/Label Studio/Encord export-import, COCO/YOLO/HF formats | M | ecosystem composability |
| **P7. Video (demand-gated)** | frames entity set, time axis, scrubber UI | L | inspection/AV verticals |
| **P8. 3D (demand-gated)** | point-cloud renderer panel | L | robotics/AV verticals |

Parallel hygiene (small, do alongside P1–P2): frontend test harness;
LanceDB-backed pagination for every remaining `ds.samples` scan. The built-in
Samples grid now renders its bound `collection_id` directly.

After P1–P3, HyperView is at *functional* parity with the FiftyOne workflows
its buyers actually use (curate → filter → embed → search → evaluate →
export), has Encord Active's most valuable ideas in differentiated form, and
keeps three moats none of them have: agent-native control, hyperbolic/
hierarchy-aware retrieval, and zero-infra static demo bundles. That is
"parity where it matters"; literal parity (P4–P8) should be pulled by
revenue, not pushed by roadmap.

## 5. Risks and honest caveats

- **Sequencing risk:** P1 is the one phase where a wrong abstraction is
  expensive (every later phase builds on Field). It deserves a design doc and
  review before code, the way the July refactor plan did.
- **Solo-founder throughput:** P1–P3 is ~6–8 focused weeks in the best case.
  Per the current strategy, sales blocks come first; this roadmap assumes
  engineering happens in the remaining capacity, and P3 is the only phase
  that directly manufactures sales artifacts (customer eval reports). If
  pipeline pressure rises, do P3's retrieval-eval job *first* against the
  current thin data model (qrels can be plain metadata) and accept rework.
- **Scale claims:** until LanceDB pushdown lands, don't demo above ~50k
  samples live. Static bundles sidestep this for demos.
- **Competitor motion:** FiftyOne ships plugins fast and Voxel51 is
  well-funded; the defensible ground is agent-nativeness and hierarchy-aware
  retrieval, not feature count. Any quarter spent cloning their features
  instead of deepening the wedge is a quarter they can't lose.
