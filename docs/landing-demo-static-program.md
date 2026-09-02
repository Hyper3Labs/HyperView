# Landing demo static program

Source of truth: `business-development/landing-pages/hyper3labs-landing/components/Demos.tsx`.

This file records product intent and acceptance evidence for the static-export
program. A demo is not complete merely because it exports or renders.

## Inventory

| Demo | Target persona | Decision the demo must support | Status |
| --- | --- | --- | --- |
| ABO Catalog | Catalog search / merchandising lead | Do prepared text requests find the intended product, and do image-neighbourhoods preserve useful product families? | Current multi-panel redesign exported and tested |
| Precision Regions | Facilities, retail, or fleet operations lead | Can a natural-language description surface the exact object region early enough to reduce manual inspection? | Current multi-panel redesign exported and tested |
| Fashion Products | Ecommerce search / merchandising lead | Does typed product search preserve decisive attributes, and does catalog topology expose useful category structure? | Current multi-panel redesign exported and tested |
| Logo Search | Brand operations / creative asset manager | Can detailed creative direction retrieve the intended logo asset, and does the map expose catalog style coverage? | Current multi-panel redesign exported and tested |
| GeoSpatial | Remote-sensing archive / imagery QA lead | Does retrieval preserve exact/parent aerial identity, and do model maps expose topology drift? | Current multi-panel redesign exported and tested |
| Visual Safety | Marketplace trust-and-safety operations lead | Is one extra proxy-positive catch worth five net false reviews and six extra queue slots? | Current multi-panel redesign exported and tested |

## Current redesign pass (2026-07-22)

This section supersedes the older implementation-evidence narratives below.
Those narratives remain as historical context for why the current workspaces
were rebuilt.

The current product contract is full HyperView in a shareable read-only mode:
the shell, GitHub/Discord links, themes, native Samples, native Scatter, panel
layout, and shared selection remain. The static boundary removes only actions
that need a backend. Prepared text-query cases remain visible and interactive;
arbitrary text inference is absent.

| Demo | Current panel composition | Export evidence | Static Space URL |
| --- | --- | --- | --- |
| ABO Catalog | Two native image-neighbour Samples panels, two native model maps, tabbed prepared-results/catalog browse, and a right-side retrieval walkthrough | 531 samples, 5 layouts, similarity k=10, zero warnings | `http://127.0.0.1:3001/spaces/abo-catalog/` |
| Precision Regions | Two native prepared Top-5 Samples panels and a right-side source/ground-truth/query walkthrough; no misleading rank map | 36 samples, 7 prepared collections, zero warnings | `http://127.0.0.1:3001/spaces/precision-regions/` |
| Fashion Products | Native prepared-result Samples, one Hyper3 catalog-topology map, right-side shopper-query walkthrough | 741 samples, 4 layouts, zero warnings | `http://127.0.0.1:3001/spaces/fashion-products/` |
| Logo Search | Native prepared-result Samples, one Hyper3 multimodal style map, right-side creative-brief walkthrough | 160 samples, 4 layouts, zero warnings | `http://127.0.0.1:3001/spaces/logo-search/` |
| GeoSpatial | Two native ranked-neighbour Samples panels, two native model maps, right-side aerial-identity walkthrough | 60 samples, 4 layouts, similarity k=10, zero warnings | `http://127.0.0.1:3001/spaces/geospatial/` |
| Visual Safety | Two native prepared review-queue Samples panels and a right-side operating-point walkthrough; no unsupported map | 120 samples, 9 prepared collections, zero warnings | `http://127.0.0.1:3001/spaces/visual-safety/` |

Shared source fixes made for this pass:

- Native Samples accepts `mode="results"` and an explicit collection binding
  per panel, so multiple prepared result/queue panels coexist without sharing
  the legacy singleton Samples state.
- Result-mode Samples hides live text search when inference is unavailable and
  shows explicit `#1…#N` ordering even when a prepared collection has no
  distance scores.
- Scatter remains a native surface with mouse drag to pan, wheel to zoom, and
  Shift-drag lasso; custom panels no longer recreate those controls.

Final layout corrections after persona review:

- Walkthrough-style extension panels consistently occupy the right companion
  rail. Native Samples and Scatter evidence remains in the main work area.
- ABO keeps prepared text results as a tab beside the first ranked-neighbour
  view, while its two model maps stay directly below their corresponding
  ranked panels.
- Precision Regions keeps the two prepared rankings aligned in the main work
  area and puts source scene, target crop, ranks, and slice metric in the
  right-side walkthrough.

Verification to date: all six exports report zero warnings; every prepared
case/model/slice control was exercised in a static browser; mouse pan/zoom was
exercised on the Fashion map; all six URLs have zero failed network requests;
1280, 760, and 390 px layouts have no document-level horizontal overflow; the
frontend lint/build passes; and the full HyperView suite passes 209 tests.
Current screenshots are under `dogfood-output/*-static-redesign.png` and
`dogfood-output/*-static-{760,390}.png`. The final ABO correction is captured
in `dogfood-output/abo-final-v5-{1280,760,390}.png`; the final Precision
correction is in `dogfood-output/precision-final-v10-{1280,760,390}.png`.

Final independent target-persona verdicts:

| Demo | Verdict | Score | Must-fixes remaining |
| --- | --- | ---: | --- |
| ABO Catalog | SHIP | 8.8/10 | None |
| Precision Regions | SHIP | 9.0/10 | None |
| Fashion Products | SHIP | 8.8/10 | None |
| Logo Search | SHIP | 9.0/10 | None |
| GeoSpatial | SHIP | 7.8/10 | None |
| Visual Safety | SHIP | 9.4/10 | None |

## Shared acceptance contract

Every demo must:

1. Lead with one business question and the evidence needed to answer it.
2. Make prepared/static evidence clearly distinct from capabilities that need a
   live runtime, without degrading the full HyperView shell.
3. Use normal JSX and public high-level HyperView APIs or panel SDK hooks only.
4. Keep cross-panel state in runtime/workspace state. Custom panels may choose a
   case, explain evidence, and select samples; they must not recreate generic
   retrieval, selection, or layout infrastructure.
5. Export with zero warnings and run from an ordinary static file server.
6. Pass equivalent live/static case changes, media, selection/reset/filter,
   responsive layout, console, and network checks for all relevant features.
7. Receive a pre-build product review and a final acceptance review from an
   independent reviewer acting as the target persona.

## Precision Regions: pre-build brief

### Buyer and question

The primary persona is an operations lead reviewing inspection or archive
imagery. The decision is: **does the retrieval model put the specifically
described object region early enough that an operator can find it without
scanning a long list of near-misses?**

The facilities, retail, and fleet cases are transfer examples for the same
workflow, not three separate product stories.

### Required evidence

- The natural-language region description.
- The source scene with the intended region visibly boxed, plus the exact crop.
- The same candidate universe for both models.
- Side-by-side ranked results, with the target unmistakably marked and its rank
  visible even when it falls below the displayed first screen.
- A narrow aggregate metric only when its source, slice size, and candidate
  protocol match the claim shown in the workspace.
- A concise operational consequence: fewer candidates to inspect before the
  correct region is found.

### Current-state finding

The landing-page comparison and current static workspace are not the same
experiment. The landing page shows broader text-to-region results and aggregate
slice metrics (for example, the facilities target at CLIP rank 20 across 120
queries). `ranked_cases.json` instead contains eight crops from one source scene
and puts that facilities target at CLIP rank 6. The static workspace must not
present the smaller prepared ranking as proof of the broader aggregate claim.

The current native panels also label these prepared rankings as “nearest
neighbours,” although the business question is exact text-conditioned region
ranking. The implementation should use a contract and labels that truthfully
describe the prepared evidence rather than forcing it into an unrelated map or
generic-neighbour story.

### Static boundary

The static share may switch among prepared cases, inspect both model rankings,
and synchronize sample selection. It must not offer a functional-looking free
text query. New region descriptions, model inference, and recomputation belong
in a hosted HyperView Space.

### Acceptance target

A target user should be able to answer within ten seconds: what was requested,
which region is correct, where each model ranked it, what mistakes appeared
first, and what claim is (and is not) supported by the prepared evidence.

## Precision Regions: implementation evidence

- Replaced the mismatched eight-crop rank-map story with the three prepared
  business-evidence cases used by the landing page: facilities, retail, and
  fleet.
- The workspace now has one purpose-built evidence panel: source scene and
  boxed target, exact query, aligned Hyper3/CLIP Top 5 lists, target ranks,
  narrowly scoped slice metrics, and provenance. Fleet intentionally exposes
  an aggregate tie so the demo does not imply that every slice is a win.
- The demo uses a record-only dataset and an explicit Extension-only view. It
  has no dummy coordinates, nearest-neighbour state, rank map, backend search
  control, raw runtime request, or private frontend API.
- Live and static case switching and result selection were exercised for all
  cases. The final static export contains 115 files, reports zero warnings,
  loads all media, and exposes no text-query control.
- Desktop evidence: `dogfood-output/precision-v2-live-fleet-1280.png` and
  `dogfood-output/precision-v2-static-fleet-1280.png`.
- Responsive evidence includes the final 390 px audit under
  `dogfood-output/final-responsive-audit/`; the Dockview panel now accepts a
  240 px minimum width, owns its bounded height, and has no horizontal
  overflow.
- HyperView regression suite: 209 tests passed.
- Final independent facilities-operations acceptance: **SHIP**. Scores were
  business clarity 9.5, trust/auditability 9.0, interaction 9.2, visual quality
  8.8, static parity 9.8, and code cleanliness 9.6. Final screenshots are under
  `dogfood-output/precision-final-review/`.
- Final narrow-width re-acceptance: **SHIP, 9.2/10**. The intended Facilities
  case is the default; native scrolling reaches the exact bottom at 390 and
  760 px; selection/reset, media, console, and network checks pass. Shared
  evidence is under `dogfood-output/narrow-final-acceptance/`.

## Fashion Products: pre-build brief

### Buyer and question

The primary persona is an ecommerce search or merchandising lead deciding
whether a multimodal retrieval model deserves a catalog-search pilot. The
question is: **when a shopper combines several decisive product attributes,
does the model put the exact SKU on the first results screen instead of
returning plausible but wrong substitutes?**

This is a typed-query retrieval audit, not a general-purpose embedding-map
demo. Color, fit, garment type, material, construction, and pattern are useful
only insofar as the ranked results visibly preserve the attributes the shopper
specified.

### Required evidence

- The prepared shopper request and its decisive attributes.
- The exact target product, large enough to recognize, plus its rank for both
  models.
- Aligned first-screen results for both models, with useful product labels and
  the exact target unmistakably marked.
- A concise explanation of the first failure mode (for example color drift or
  garment-category drift), grounded in the visible results.
- Aggregate metrics and candidate-pool size clearly separated from the three
  prepared qualitative cases. The benchmark must acknowledge that the
  aggregate edge is small and that each model has strong wins.
- Samples should support inspection of the currently chosen result set; it must
  not dominate or contradict the ranked comparison.

### Static boundary

The static share may switch among prepared shopper requests, compare both
ranked result sets, inspect the exact target, and synchronize result selection
with Samples. It must not expose an arbitrary text box or imply that a new
query will run model inference. Context maps are optional and should be omitted
unless they answer the buyer's typed-search decision more clearly than ranks.

### Acceptance target

Within ten seconds, a retail buyer should be able to say what the shopper
wanted, which attributes matter, what the correct SKU is, whether it appears on
the first screen for each model, and how narrowly the evidence should be
interpreted. The prepared-case control, active result, and selected sample must
remain visually unmistakable at desktop and narrow widths.

### Pre-build persona review

An independent ecommerce search/merchandising reviewer scored the current
static demo about 5.2/10 (business clarity 6, evidence 4, visual hierarchy 5,
interaction 5, static suitability 6). The redesign must address these findings:

- Give the exact target and decisive attribute checklist first-class visual
  treatment; the target is currently too small to audit.
- Align both models' Top 5 evidence. A target at #32 or #56 must be shown as a
  separate rank fact, never appended to the strip as though it followed #6.
- Explain why the aggregate probe has 1,120 candidates while the viewer holds
  741 images, and separate aggregate evidence from prepared examples.
- Balance three curated wins against the small aggregate lift (+1.1 pp Hit@1,
  +2.2 pp Hit@10). Include a representative tie/regression case if source
  evidence exists; otherwise state explicitly that the cases are selected wins
  and expose both models' strong-win counts.
- Revalidate the cream/blue halter case. Its text currently combines several
  attributes that are not self-evident from the target image.
- Make both model comparisons visible together, remove duplicate headings, and
  keep Samples secondary to the proof.
- Do not conflate the prepared result set with selection. Choosing a case should
  present results; clicking one item should select it without collapsing the
  Samples result set to a single item, and Reset should have a clear meaning.
- At 760 px and at the landing iframe's approximate 650 px height, the decision
  evidence must not require horizontal scrolling or hide the candidate proof
  below the fold.

Review evidence: `dogfood-output/fashion-buyer-pre-review/initial-1280.png`,
`olive-case-1280.png`, `halter-case-1280.png`, and `responsive-760.png`.

## Fashion Products: implementation evidence

- Reduced the story to the one landing-page case that is visually auditable:
  light-denim leggings, exact SKU rank #1 vs #32. The questionable cream/blue
  case and visually ambiguous olive/navy case are no longer public evidence.
- Replaced the 741-image viewer with a bounded ten-image evidence dataset. The
  panel shows a large ground-truth target, requested attributes, aligned Top 5
  rows, visible failure labels, and exact-target ranks.
- Aggregate context is visible beside the example: 180 metadata-generated
  queries, 1,120 candidates, modest Hit@1/Hit@10 lifts, and 13 Hyper3 vs 9 CLIP
  strong wins. The claim explicitly says the selected case is not a universal
  text-search advantage.
- Removed Samples-result filtering, bulk selection, context maps, arbitrary
  text search, live inference controls, and duplicate viewer evidence. Clicking
  a result now changes only shared selection; the evidence set remains stable.
- The implementation uses normal JSX plus `usePanelState`, `useSamples`, and
  `useSelection`; it contains no raw request, browser storage/event bridge,
  private API, fake coordinates, or backend command workaround.
- Live/static screenshots: `dogfood-output/fashion-v3/live-1280x650.png`,
  `live-896x650-v4.png`, and `static-1280x650.png`.
- The rebuilt static bundle contains 63 files, reports zero warnings, loads all
  eleven rendered images, exposes no inputs, and has no console or failed
  network requests after the shared HyperView favicon fix.
- The final responsive pass lowered the view's generic panel minimum to 240 px
  and made the evidence root own its bounded height. At 390 px the document,
  Dockview surface, and panel are all exactly 390 px wide, while the complete
  evidence remains vertically reachable.
- Final independent merchandising acceptance: **SHIP**, with no must-fixes.
  Scores were business clarity 9.2, evidence/trust 8.8, visual hierarchy 9.0,
  interaction 9.2, static parity 10.0, and code cleanliness 9.4. At matched
  selection the live/static panel pixels were identical; the final 760 px shell
  and panel have no overflow. Evidence is under
  `dogfood-output/fashion-final-review/`.
- Final narrow-width re-acceptance: **SHIP, 9.0/10**. The light-denim case is
  the default; native scrolling reaches the exact bottom at 390 and 760 px;
  selection/reset and isolated repeated media/network checks pass. Shared
  evidence is under `dogfood-output/narrow-final-acceptance/`.

## Logo Search: pre-build brief

### Buyer and question

The primary persona is a brand-operations or creative-asset manager deciding
whether semantic retrieval can replace manual folder/tag browsing for a logo
archive. The question is: **given a detailed creative brief, does the model put
the exact existing logo—or a genuinely usable shortlist preserving its motif,
composition, palette, background, and style—on the first review screen?**

This is text-to-logo retrieval. An embedding map is not evidence that the brief
was satisfied unless it directly helps the buyer audit the ranked result.

### Required evidence

- A prepared creative brief broken into recognizable decision attributes:
  business category, central motif, composition, palette/background, and style.
- A large ground-truth asset plus exact-target rank for both models.
- Aligned Top 5 result images with concise match/miss labels tied to the brief,
  not opaque dataset captions or generic category names.
- Aggregate Hit@1/Hit@5/MRR context with exact corpus/query scope and an explicit
  statement that dataset descriptions are not real creative-team search logs.
- Multiple cases only when each demonstrates a distinct operational failure
  mode; curated wins must not be presented as the aggregate distribution.

### Static boundary

The static share may switch among prepared briefs, inspect results, and select
an asset. It must not expose arbitrary text search or imply new model inference.
The evidence dataset should contain only the assets needed by the prepared
comparisons. Scatter maps should be omitted unless a reviewer can name the
additional brand decision they support.

### Acceptance target

Within ten seconds, a brand manager should be able to identify the brief, its
decisive visual constraints, the correct asset, where each model ranked it, and
which first-screen near-misses violated the brief. Both Top 5 rows and the
target must fit the landing viewport without generated-JS data, base64 props,
private imports, or runtime-side UI file generation.

### Pre-build persona review

An independent brand-operations reviewer scored the previous demo about 3.8/10
(business clarity 4, evidence 3, visual hierarchy 3, interaction 5, static
suitability 4). All four case/rank selectors worked, but the UI showed no ranked
result evidence: an unrelated 160-logo Samples grid and two incomparable maps
dominated the page while a 320 px sidebar showed only the target and ranks.

The review also found generated 1.9 MB base64 `case_data.js`, a private Sample
import, `React.createElement`, startup embedding/layout recomputation, raw
captions with no attribute audit, hidden case tabs, narrow-width overflow, and a
false `isTarget: false` flag on every top-level target.

Review evidence is under `dogfood-output/logo-buyer-pre-review/`.

## Logo Search: implementation evidence

- Rebuilt the demo as one full-width paired-caption retrieval audit. All four
  case controls are visible and explicitly labeled `Curated win`.
- Each case now exposes category, motif, composition, palette, and style; a
  ground-truth asset with HF row id; exact ranks; aligned Hyper3/CLIP Top 5 rows;
  meaningful motif captions; and a collapsible raw dataset caption.
- Persistent aggregate context covers all 160 captions/candidates: Hit@1
  35.6% (57) vs 16.3% (26), Hit@5 73.1% (117) vs 48.8% (78), and MRR +0.207.
  The claim states that the dataset is synthetic/curated and not a production
  DAM or trademark benchmark.
- Replaced the 160-row runtime viewer with the 32 unique images needed by the
  prepared comparisons. Removed both maps, embedding/layout computation,
  Hugging Face startup loading, generated JavaScript, base64 images, private
  imports, and text-query affordances.
- The panel is normal JSX using only `usePanelState`, `useSamples`, and
  `useSelection`. Case changes select the matching target; any result can be
  selected; clear affects selection only and never changes the evidence set.
- Live/static checks passed all four cases and ranks at 1280, 760, and 390 px.
  All eleven rendered images load, document/panel widths match every viewport,
  there are no inputs, console errors, or failed requests, and the static export
  reports zero warnings.
- Evidence: `dogfood-output/logo-v5/live-1280x650-v6.png`,
  `live-390x844-v7.png`, `static-1280x650.png`, and `static-390x844.png`.
- Final independent brand-operations acceptance: **SHIP** after two review
  fixes. The aggregate metrics now stack cleanly at the 760 px breakpoint, and
  the obsolete 1.9 MB generated/base64 `case_data.js` payload was deleted from
  both source and export. The v8 bundle is 3.1 MB (107 files, 32 samples), has
  zero warnings, contains no base64 extension payload, and passes 1280, 760,
  and 390 px live/static checks with 11/11 visible images and no console,
  network, or horizontal-overflow errors. Final evidence is under
  `dogfood-output/logo-final-review-r2/`.
- Final narrow-width re-acceptance: **SHIP, 9.4/10**. The barber-franchise case
  is the default; native scrolling reaches the exact bottom at 390 and 760 px;
  case/result selection, reset, cross-list highlighting, media, console, and
  network checks all pass. Shared evidence is under
  `dogfood-output/narrow-final-acceptance/`.

## GeoSpatial: pre-build brief

### Buyer and question

The primary persona is a remote-sensing archive or imagery-QA lead deciding
whether a general-purpose visual embedding is useful for image-to-image search
over aerial scenes. The question is: **when an analyst supplies one aerial
tile, does the model return scenes from the same exact class and, when exact
matches are scarce, remain inside the same operational parent group instead of
drifting into unrelated land use?**

This is a nearest-neighbour retrieval audit, not a land-cover classifier and
not a map-visualization demo. The operational consequence is the number of
irrelevant tiles an analyst must inspect before finding a usable scene.

### Required evidence

- The same visible anchor tile for both models, with its exact RESISC45 scene
  class and operational parent group.
- Two aligned, native nearest-neighbour result panels over the same candidate
  pool. Each result must expose its scene class and make exact-class,
  same-parent, and off-parent outcomes distinguishable.
- Exact-class hits and parent-group hits at ten for each prepared case, plus a
  concise description of the visible drift.
- Aggregate results over the bounded inspection set, with its 60-tile,
  12-class, five-per-class composition stated next to the metrics. Any broader
  benchmark result must be separately sourced and must never be blended with
  this curated subset.
- More than one operational failure mode: transport infrastructure, a
  vegetation/land-cover scene, and a scene where linear structure can be
  confused with unrelated agricultural geometry.
- Dataset provenance and a narrow claim: this compares neighborhood quality
  against CLIP-B/32; it does not establish specialist remote-sensing model
  superiority.

### Static boundary

The static share may switch among prepared anchor tiles, inspect both persisted
rankings, select an anchor or result, and reset the prepared comparison. It
must not imply arbitrary image upload, fresh embedding inference, or backend
recomputation. HyperView's built-in ranked Samples panels should own nearest-
neighbour rendering and anchor presentation; the custom panel should only
choose a prepared anchor and explain its business evidence.

Scatter plots should be included only if the persona review identifies a
separate archive decision that they answer. Pan, zoom, and lasso working on a
plot is not sufficient justification for using dashboard space on it.

### Acceptance target

Within ten seconds, an imagery-QA lead should be able to identify the anchor,
the exact and parent labels that count as success, how the two models' first ten
results differ, which off-group mistakes create review burden, and how narrowly
the 60-tile evidence should be interpreted. The same comparison must work at
the landing viewport and at 760 and 390 px without startup downloads, private
imports, generated UI code, or duplicate retrieval logic in the custom panel.

### Pre-build persona review

An independent remote-sensing archive / imagery-QA reviewer scored the previous
demo business clarity 4.0, evidence/trust 3.0, visual hierarchy 3.0,
interaction 2.0, static suitability 3.0, and code cleanliness 2.5. The three
case buttons only changed selection; they never presented either model's
neighbors. An unrelated all-items gallery and two incomparable Euclidean versus
Poincaré UMAPs dominated the screen, while the decision panel was off-screen at
760 and 390 px.

The review also identified three selected wins with no tie/loss; confusion
between a capped 60-tile subset aggregate and separate undocumented benchmark
claims; a private `Sample` import; startup dataset download, embedding, and UMAP
work; a 700-line monolith; and a `React.createElement` panel with unused layout
props. The accepted redesign requirement was one responsive evidence surface
with a visible anchor, aligned Top-10 lanes, outcome tags, versioned protocol,
and an explicit regression. Review evidence is under
`dogfood-output/geo-archive-pre-review/` when available.

## GeoSpatial: implementation evidence

- Replaced the Samples-plus-two-map layout with one full-width aerial retrieval
  audit. Four cases now cover Airplane and Forest wins, a Storage Tank
  built-environment win, and an Airport regression where CLIP is better.
- Both Top-10 lanes come from HyperView's persisted similarity contract. The
  custom panel presents the same anchor, labels every result exact class / same
  parent / off group, and synchronizes shared selection; it does not contain or
  recompute rankings.
- Added the generic `useSimilarSamples` hook to the public extension-panel SDK
  and documented its live/static contract. The static export precomputes `k=10`
  and the same JSX works in both modes.
- Added `evidence_cases.json` with the 60-query protocol, aggregate, required
  space keys, exact/parent counts, and ordered result IDs. Runtime results are
  checked against those ordered IDs and fail visibly if the evidence drifts.
- Removed maps, arbitrary search, startup downloads/recomputation, private
  imports, generated UI data, and `React.createElement`. The launch source is a
  small public-API adapter around the prepared versioned dataset.
- Live and static checks passed all four expected count pairs, result and anchor
  selection, reset, 21/21 images, and 1280/760/390 widths. The 3.3 MB static
  bundle contains 171 files, 60 samples, 240 precomputed similarity queries,
  and zero exporter warnings.
- Final independent imagery-QA acceptance: **SHIP** after two CSS fixes. The
  panel now owns its bounded Dockview height and native vertical scrolling, so
  both result lanes, protocol, and legend remain reachable at 760 and 390 px.
  The anchor-image selector is scoped separately from Reset, which is now
  readable and restores the default airplane evidence in live and static mode.
  Final report and screenshots are under
  `dogfood-output/geospatial-final-review-r2/`.

## Visual Safety: pre-build brief

### Buyer and question

The primary persona is a marketplace trust-and-safety operations lead. The
bounded question is: **on this curated 120-image Open Images label proxy, is
Hyper3-CLIP's slightly higher proxy-positive recall worth its lower precision
and larger review queue versus CLIP at the documented operating points?**

This is not a policy classifier. It cannot establish that content is safe,
approve a listing, age-gate an item, or generalize to sexual content, hate,
self-harm, contextual violence, jurisdictions, or seller metadata.

### Required evidence

- A visible non-production proxy disclaimer and proxy-positive/proxy-negative
  language throughout.
- A materialized prediction ledger supporting thresholds, TP/FP/FN/TN, queued
  count/rate, recall, precision, AUROC, and AP for both models.
- One operational verdict in counts: whether one additional caught positive
  justifies five additional false positives and six additional queued reviews.
  Rounded rates alone are not sufficient evidence for those exact integers.
- Four auditable examples from the same ledger: candidate-only true positive,
  candidate-only false positive, candidate false negative, and an ambiguous or
  shared outcome. Each needs source label, both scores, thresholds, both queue
  decisions, and the real image/sample identity.
- Dataset composition and concentration, inclusion labels, split, model and
  prompt/scoring versions, artifact hash/date, per-image source/license, and
  explicit limits on production extrapolation.

### Static boundary

The static share may inspect the fixed operating point and materialized cases,
select samples, and switch among any genuinely precomputed scenarios. It must
not expose a fake continuous threshold slider, model inference, or policy
action. A three-state scenario selector is acceptable only if each state is
backed by a real score ledger.

Maps should be omitted from the landing story unless they directly explain
correctness. The core decision is a review-queue tradeoff, not embedding
geometry.

### Pre-build persona review

An independent trust-and-safety operations reviewer scored the previous demo
business clarity 4.0, evidence/trust 2.5, visual hierarchy 4.0, interaction
4.5, static suitability 3.5, and code cleanliness 3.0. It showed three policy-
sounding anecdotes and one candidate map but no thresholds, confusion matrix,
queue size, misses, false positives, prediction scores, or baseline geometry.

The 120-image sample is artificially balanced and concentrated (including 30
of 60 proxy negatives labeled Clothing, and 42 of 60 proxy positives across
Beer, Wine, and Knife). CLIP's AUROC is higher; the candidate recall advantage
exists only at an undisclosed operating point. The current source also uses a
private import, hardcoded metrics without a ledger, startup downloads and two
embedding/layout computations, dead model/layout arguments, and
`React.createElement`. At 390 px most of the readout is clipped.

### Acceptance target

Within ten seconds, a safety lead should be able to state each model's queue
size, extra catches, false-review cost, residual misses, and the exact proxy
limitations. The static and live versions must show the same ledger-backed
counts and examples without any policy-decision or backend-only affordance.

## Visual Safety: implementation evidence

- Replaced the old hardcoded zero-shot anecdotes and embedding map with one
  review-queue operating-point audit. The headline decision is explicit:
  Hyper3 catches one additional proxy-positive while adding five net false
  reviews and increasing the queue from 62 to 68 of 120. The churn is explicit:
  seven candidate-only false reviews enter and two CLIP-only false reviews
  leave the queue.
- Added `benchmark.json`, a content-hashed 120-row prediction ledger generated
  by `build_evidence.py`. It records both models' seven neighbours, vote score,
  queue decision, source identity/license, protocol, confusion counts, AUROC,
  and average precision. The same fixed 5-of-7 supermajority rule is applied to
  both models without fitting a threshold.
- Four cases come directly from the ledger: the only candidate-only catch, a
  candidate-only false review, the candidate's remaining false negative, and a
  shared false review. Every case shows the real image, proxy/source labels,
  both vote counts, and both queue decisions.
- Removed policy-sounding approve/age-gate actions, maps, text search, startup
  downloads, embedding/layout recomputation, private imports, and
  `React.createElement`. The launcher uses `hv.Sample` and a single public
  extension panel; the panel is normal JSX using only `usePanelState`,
  `useSamples`, and `useSelection`.
- Live and static checks passed all four cases, selection/clear behavior,
  default-case reset on reload, image loading, and exact 1280/760/390 widths.
  There are no inputs, page errors, console errors, or failed local media.
  Live/static 1280 screenshots are visually equivalent except for the concise
  `Static Space` host label.
- The panel owns its bounded Dockview height and scrolls to the exact bottom at
  narrow widths. Evidence cards prefer full media over thumbnails, and the
  visible break-even conclusion says to choose Hyper3 only if the additional
  catch justifies six more queue slots and five net false reviews; otherwise it
  recommends retaining CLIP, whose AUROC and average precision are stronger on
  this proxy.
- The zero-warning static bundle is 11.1 MB with 283 files, 120 samples, no
  layouts, and no similarity index. Evidence is under
  `dogfood-output/visual-safety-v2/` and
  `dogfood-output/visual-safety-final-review/`.
- Final independent trust-and-safety acceptance: **SHIP, 9.4/10**. The reviewer
  verified native wheel scrolling to the exact bottom at 390 px in live and
  static mode, all four ledger cases and full-resolution media, exact
  live/static decision copy, clear queue-churn and break-even language, no
  horizontal overflow at 1280/760/390, and no console, page, network, or export
  warnings.
