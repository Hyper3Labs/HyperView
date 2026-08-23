"use client";

import React from "react";
import { Settings2, Undo2 } from "lucide-react";

import { Panel } from "@/components/Panel";
import { SampleCollectionState } from "@/components/SampleCollectionState";
import { SampleGridView } from "@/components/SampleGridView";
import { SampleInspectorDialog } from "@/components/SampleInspectorDialog";
import { SampleTile } from "@/components/SampleTile";
import {
  PanelToolbar,
  PanelToolbarButton,
  PanelToolbarMenu,
  type PanelToolbarItem,
} from "@/components/PanelToolbar";
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  useCollection,
  useCommandClient,
  usePanelState,
  usePanelActions,
  useSample,
  useSamples,
  useSimilarSamples,
  useSelection,
  useSupportsSampleSimilarity,
  useSupportsTextSearch,
} from "@/panel-sdk";
import { getDistanceMetricLabel } from "@/lib/similarity";
import type { RuntimeCollection, Sample } from "@/types";

const SAMPLE_GRID_SIZE_OPTIONS = [
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
  { value: "large", label: "Large" },
] as const;

type SampleGridSize = (typeof SAMPLE_GRID_SIZE_OPTIONS)[number]["value"];

interface SamplesPanelParams extends Record<string, unknown> {
  panelId?: string;
  mode?: "auto" | "browse" | "ranked" | "results";
  rank?: Record<string, unknown>;
  collectionId?: string;
  collection_id?: string;
  /** Optional prepared-query anchor shown above collection-backed results. */
  anchorSampleId?: string;
  anchor_sample_id?: string;
  /** Optional sample metadata key used as the tile/anchor display label. */
  labelField?: string;
  label_field?: string;
  /** Show native live text retrieval even when a prepared collection is bound. */
  showTextSearch?: boolean;
  show_text_search?: boolean;
}

interface SamplesRank {
  anchorSampleId: string;
  layoutKey?: string;
  spaceKey?: string;
  k: number;
  source?: string;
  showDistance: boolean;
}

function samplesRank(value: unknown): SamplesRank | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const rank = value as Record<string, unknown>;
  const anchor =
    typeof rank.anchor === "object" && rank.anchor !== null && !Array.isArray(rank.anchor)
      ? (rank.anchor as Record<string, unknown>)
      : null;
  const anchorSampleId = stringState(
    rank.anchorSampleId ??
      rank.anchor_sample_id ??
      anchor?.entityId ??
      anchor?.entity_id
  );
  if (!anchorSampleId) return null;
  const requestedK = typeof rank.k === "number" ? rank.k : 10;
  return {
    anchorSampleId,
    layoutKey:
      stringState(rank.layoutKey ?? rank.layout_key ?? rank.layoutId ?? rank.layout_id) ??
      undefined,
    spaceKey: stringState(rank.spaceKey ?? rank.space_key) ?? undefined,
    k: Math.max(1, Math.floor(requestedK)),
    source: stringState(rank.source) ?? undefined,
    showDistance: rank.showDistance !== false && rank.show_distance !== false,
  };
}

function stringState(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function withDisplayLabel(sample: Sample | null, labelField: string | null): Sample | null {
  if (!sample || !labelField) return sample;
  const value = sample.metadata?.[labelField];
  return typeof value === "string" && value.trim()
    ? { ...sample, label: value.trim() }
    : sample;
}

function collectionSource(collection: RuntimeCollection | null): string {
  if (!collection) return "Collection";
  const source = stringState(collection.query.source);
  if (source) return source;
  if (collection.kind === "all") return "Dataset";
  if (collection.kind === "lasso") return "Lasso";
  if (collection.kind === "neighbors") return "Neighbors";
  if (collection.kind === "search") return "Search";
  if (collection.kind === "filter") return "Filter";
  if (collection.kind === "selection") return "Results";
  return collection.kind.replaceAll("_", " ");
}

function collectionFilterLabel(collection: RuntimeCollection | null): string | null {
  if (collection?.kind !== "filter") return null;
  const value = collection.query.value;
  return typeof value === "string" ? value : value === null ? "undefined" : null;
}

function collectionQueryText(collection: RuntimeCollection | null): string | null {
  if (collection?.kind !== "search") return null;
  return stringState(collection.query.queryText ?? collection.query.query_text);
}

function RankedSamplesContent({
  anchor,
  samples,
  metric,
  source,
  selectedIds,
  onSelectionChange,
  onInspect,
  gridSize,
  scrollResetKey,
  showDistance,
}: {
  anchor: Sample;
  samples: Sample[];
  metric: string | null;
  source?: string;
  selectedIds: ReadonlySet<string>;
  onSelectionChange: (ids: string[]) => void;
  onInspect: (sample: Sample) => void;
  gridSize: SampleGridSize;
  scrollResetKey: string;
  showDistance: boolean;
}) {
  const anchorName = anchor.label || anchor.text || anchor.filename || anchor.id;
  const metricLabel = getDistanceMetricLabel(metric);
  const resultsLabel = [
    `${samples.length.toLocaleString()} nearest neighbour${samples.length === 1 ? "" : "s"}`,
    metricLabel,
    source,
  ].filter(Boolean).join(" · ");

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 border-b border-border bg-secondary/10 px-2 py-2">
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Anchor
        </div>
        <button
          type="button"
          aria-label={`Select anchor ${anchorName}`}
          aria-pressed={selectedIds.has(anchor.id)}
          onClick={() => onSelectionChange([anchor.id])}
          className="group flex max-w-full items-center gap-2 border-0 bg-transparent p-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <SampleTile
            sample={anchor}
            selected={selectedIds.has(anchor.id)}
            showLabel={false}
            className="h-[84px] w-[112px] shrink-0 cursor-pointer border border-border transition-shadow duration-150 group-hover:ring-1 group-hover:ring-primary/40"
          />
          <span className="min-w-0 pr-2">
            <span className="block truncate text-xs font-medium text-foreground" title={anchorName}>
              {anchorName}
            </span>
            <span className="mt-1 block truncate font-mono text-[10px] text-muted-foreground" title={anchor.id}>
              {anchor.id}
            </span>
          </span>
        </button>
      </div>
      <div className="flex h-6 min-h-6 shrink-0 items-center overflow-hidden border-b border-border bg-secondary/20 px-2">
        <span className="truncate text-[11px] text-muted-foreground" title={resultsLabel}>
          {resultsLabel}
        </span>
      </div>
      <SampleGridView
        samples={samples}
        scrollResetKey={scrollResetKey}
        showRankSimilarityBadge
        showDistanceInRankBadge={showDistance}
        distanceMetric={metric}
        controlledSelectedIds={selectedIds}
        onSelectionChange={onSelectionChange}
        onInspect={onInspect}
        gridSize={gridSize}
      />
    </div>
  );
}

function useSamplesPanelCommands() {
  const commandClient = useCommandClient();

  const searchByText = React.useCallback(
    (queryText: string) =>
      commandClient.runCommand("panel.samples.retrieval.set-text-query", {
        args: { query_text: queryText, source: "samples-panel" },
      }),
    [commandClient]
  );

  const clearCollection = React.useCallback(
    () => commandClient.runCommand("panel.samples.retrieval.clear"),
    [commandClient]
  );

  const findSimilar = React.useCallback(
    (sampleId: string, context?: { layoutKey?: string; spaceKey?: string; k?: number }) =>
      commandClient.runCommand("panel.samples.retrieval.set-anchor", {
        args: {
          sample_id: sampleId,
          layout_key: context?.layoutKey,
          space_key: context?.spaceKey,
          k: context?.k ?? 18,
          source: "samples-inspector",
        },
      }),
    [commandClient]
  );

  return React.useMemo(
    () => ({ searchByText, clearCollection, findSimilar }),
    [clearCollection, findSimilar, searchByText]
  );
}

function SamplesTextSearchBar() {
  const { searchByText, clearCollection } = useSamplesPanelCommands();
  const [query, setQuery] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const handleSubmit = React.useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      const trimmed = query.trim();
      if (!trimmed) return;
      setSubmitting(true);
      try {
        await searchByText(trimmed);
      } catch (error) {
        console.error("Failed to run text search:", error);
      } finally {
        setSubmitting(false);
      }
    },
    [query, searchByText]
  );

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 border-b border-border px-3 py-2">
      <input
        aria-label="Search samples by text"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search by text…"
        className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
      />
      <button
        type="submit"
        disabled={submitting || query.trim().length === 0}
        className="h-8 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground disabled:opacity-50"
      >
        Search
      </button>
      <button
        type="button"
        onClick={() => {
          setQuery("");
          void clearCollection().catch((error) => {
            console.error("Failed to clear text search:", error);
          });
        }}
        className="h-8 rounded-md border border-input px-3 text-xs text-muted-foreground"
      >
        Clear
      </button>
    </form>
  );
}

export const SamplesImageGridPanel = React.memo(function SamplesImageGridPanel() {
  const panelState = usePanelState();
  const params = panelState.props as SamplesPanelParams;
  const panelId = panelState.panelId ?? "samples";
  const { state, patchState } = panelState;
  const { focusPanel } = usePanelActions();
  const configuredCollectionId = stringState(
    params.collectionId ?? params.collection_id
  );
  const preparedAnchorId = stringState(
    params.anchorSampleId ?? params.anchor_sample_id
  );
  const labelField = stringState(params.labelField ?? params.label_field);
  const { sample: preparedAnchor } = useSample(preparedAnchorId);
  const runtimeCollectionId = stringState(state.collection_id);
  const collectionId =
    panelId === "samples"
      ? runtimeCollectionId ?? configuredCollectionId
      : configuredCollectionId ?? runtimeCollectionId;
  const collection = useCollection(collectionId);
  const samplesPage = useSamples(collectionId, { pageSize: 60 });
  const selection = useSelection();
  const { clearCollection, findSimilar } = useSamplesPanelCommands();
  const [inspectedSample, setInspectedSample] = React.useState<Sample | null>(null);
  const [findingSimilar, setFindingSimilar] = React.useState(false);
  const [similarityError, setSimilarityError] = React.useState<string | null>(null);
  const sampleSimilarityAvailable = useSupportsSampleSimilarity();
  const panelMode = params.mode ?? "auto";
  const showRankedPanel = panelMode === "ranked" || collection?.kind === "neighbors";
  const showResultRanks =
    showRankedPanel || panelMode === "results" || collection?.kind === "search";
  const rank = React.useMemo(
    () =>
      samplesRank(showRankedPanel ? params.rank : null) ??
      samplesRank(collection?.kind === "neighbors" ? collection.query : null),
    [collection, params.rank, showRankedPanel]
  );
  const rankedPage = useSimilarSamples(rank);
  const page = rank
    ? { ...rankedPage, scores: null, hasMore: false, loadMore: () => {} }
    : samplesPage;
  const gridSize = SAMPLE_GRID_SIZE_OPTIONS.some((option) => option.value === state.grid_size)
    ? (state.grid_size as SampleGridSize)
    : "medium";
  const selectedIds = React.useMemo(() => new Set(selection.selectedIds), [selection.selectedIds]);
  const queryText = collectionQueryText(collection);
  const filterLabel = collectionFilterLabel(collection);
  const textSearchAvailable = useSupportsTextSearch();
  const showTextSearch =
    params.showTextSearch === true || params.show_text_search === true;

  const displayedSamples = React.useMemo(() => {
    const scored = !page.scores ? page.samples : page.samples.map((sample) => {
      const score = page.scores?.[sample.id];
      return typeof score === "number" ? ({ ...sample, distance: score } as Sample) : sample;
    });
    return labelField
      ? scored.map((sample) => withDisplayLabel(sample, labelField) ?? sample)
      : scored;
  }, [labelField, page.samples, page.scores]);
  const displayRankedAnchor = React.useMemo(
    () => withDisplayLabel(rankedPage.querySample, labelField),
    [labelField, rankedPage.querySample]
  );
  const displayPreparedAnchor = React.useMemo(
    () => withDisplayLabel(preparedAnchor, labelField),
    [labelField, preparedAnchor]
  );
  const isAuthoredPreparedCollection =
    Boolean(configuredCollectionId) &&
    collectionId === configuredCollectionId &&
    collection?.kind === "selection";

  const toolbarItems = React.useMemo<PanelToolbarItem[]>(
    () => [
      {
        id: "source",
        label: "Source",
        value: showRankedPanel ? rank?.source ?? "Ranked" : collectionSource(collection),
      },
      {
        id: "count",
        label: showRankedPanel ? "Results" : "Samples",
        value: page.total.toLocaleString(),
      },
      ...(queryText
        ? [{ id: "query", label: "Query", value: queryText } satisfies PanelToolbarItem]
        : []),
      ...(filterLabel
        ? [{ id: "filter", label: "Filter", value: filterLabel } satisfies PanelToolbarItem]
        : []),
    ],
    [collection, filterLabel, page.total, queryText, rank?.source, showRankedPanel]
  );

  const toolbarActions = React.useMemo(
    () => (
      <>
        {collection?.kind === "lasso" ? (
          <PanelToolbarButton
            onClick={() => {
              void clearCollection();
            }}
          >
            <Undo2 className="h-3 w-3" />
            Clear lasso
          </PanelToolbarButton>
        ) : null}
        <PanelToolbarMenu
          icon={<Settings2 className="h-3.5 w-3.5" />}
          label="Sample panel settings"
          title={`Thumbnail size: ${gridSize}`}
          contentClassName="min-w-[220px]"
        >
          <DropdownMenuLabel>Thumbnail size</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup
            value={gridSize}
            onValueChange={(value) => {
              void patchState({ grid_size: value });
            }}
          >
            {SAMPLE_GRID_SIZE_OPTIONS.map((option) => (
              <DropdownMenuRadioItem key={option.value} value={option.value}>
                <span className="truncate">{option.label}</span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </PanelToolbarMenu>
      </>
    ),
    [clearCollection, collection?.kind, gridSize, patchState]
  );

  return (
    <Panel className="h-full">
      <PanelToolbar items={toolbarItems} actions={toolbarActions} />
      {!showRankedPanel && panelMode !== "results" &&
      (!configuredCollectionId || showTextSearch) && textSearchAvailable ? (
        <SamplesTextSearchBar />
      ) : null}

      {page.error ? (
        <SampleCollectionState tone="error" title="Could not load samples" description={page.error} />
      ) : page.loading && displayedSamples.length === 0 ? (
        <SampleCollectionState
          tone="loading"
          title={queryText ? "Searching by text" : "Loading samples"}
          description={queryText ? `Finding matches for "${queryText}".` : "Preparing the active sample collection."}
        />
      ) : !rank && !collectionId ? (
        <SampleCollectionState
          title="No sample collection"
          description="Bind a collection to this panel to display its samples."
        />
      ) : displayedSamples.length === 0 ? (
        <SampleCollectionState
          title={filterLabel ? "No samples match this filter" : "No samples available"}
          description={
            filterLabel
              ? "Clear the current label filter to return to the full dataset."
              : "The collection has no samples to display."
          }
        />
      ) : rank && displayRankedAnchor ? (
        <RankedSamplesContent
          anchor={displayRankedAnchor}
          samples={displayedSamples}
          metric={rankedPage.metric}
          source={rank.source}
          selectedIds={selectedIds}
          onSelectionChange={(ids) => {
            void selection.setSelection(ids);
          }}
          onInspect={setInspectedSample}
          gridSize={gridSize}
          scrollResetKey={`rank:${rank.anchorSampleId}:${rank.layoutKey ?? rank.spaceKey ?? "default"}`}
          showDistance={rank.showDistance}
        />
      ) : displayPreparedAnchor && isAuthoredPreparedCollection ? (
        <RankedSamplesContent
          anchor={displayPreparedAnchor}
          samples={displayedSamples}
          metric={null}
          source={collectionSource(collection)}
          selectedIds={selectedIds}
          onSelectionChange={(ids) => { void selection.setSelection(ids); }}
          onInspect={setInspectedSample}
          gridSize={gridSize}
          scrollResetKey={`prepared:${displayPreparedAnchor.id}:${collectionId ?? "none"}`}
          showDistance={false}
        />
      ) : (
        <SampleGridView
          samples={displayedSamples}
          onLoadMore={page.loadMore}
          hasMore={page.hasMore}
          scrollResetKey={rank ? `rank:${rank.anchorSampleId}:${rank.layoutKey ?? rank.spaceKey ?? "default"}` : `${collectionId}:${collection?.created_at ?? 0}`}
          showRankSimilarityBadge={showResultRanks}
          distanceMetric={rankedPage.metric}
          controlledSelectedIds={selectedIds}
          onSelectionChange={(ids) => {
            void selection.setSelection(ids);
          }}
          onInspect={setInspectedSample}
          gridSize={gridSize}
        />
      )}
      <SampleInspectorDialog
        sample={inspectedSample}
        onOpenChange={(open) => {
          if (!open) {
            setInspectedSample(null);
            setSimilarityError(null);
          }
        }}
        findingSimilar={findingSimilar}
        similarityError={similarityError}
        onFindSimilar={sampleSimilarityAvailable
          ? (sample) => {
              setFindingSimilar(true);
              setSimilarityError(null);
              void findSimilar(sample.id, {
                layoutKey: rank?.layoutKey,
                spaceKey: rank?.spaceKey,
                k: rank?.k ?? 18,
              })
                .then(async () => {
                  setInspectedSample(null);
                  if (panelId !== "samples") await focusPanel("samples");
                })
                .catch((error) => {
                  setSimilarityError(
                    error instanceof Error ? error.message : "Similarity data is unavailable"
                  );
                })
                .finally(() => setFindingSimilar(false));
            }
          : undefined}
      />
    </Panel>
  );
});

SamplesImageGridPanel.displayName = "SamplesImageGridPanel";
