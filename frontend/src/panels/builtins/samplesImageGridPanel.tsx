"use client";

import React from "react";
import type { IDockviewPanelProps } from "dockview-react";
import { Grid3X3, Settings2, Undo2 } from "lucide-react";

import { Panel } from "@/components/Panel";
import { SampleCollectionState } from "@/components/SampleCollectionState";
import { SampleGridView } from "@/components/SampleGridView";
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
  useSamples,
  useSelection,
} from "@/panel-sdk";
import { defineBuiltInCenterPanel } from "@/panels/definitions";
import type { RuntimeCollection, Sample } from "@/types";

const SAMPLE_GRID_SIZE_OPTIONS = [
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
  { value: "large", label: "Large" },
] as const;

type SampleGridSize = (typeof SAMPLE_GRID_SIZE_OPTIONS)[number]["value"];

interface SamplesPanelParams extends Record<string, unknown> {
  panelId?: string;
  mode?: "auto" | "browse" | "ranked";
}

function stringState(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function collectionSource(collection: RuntimeCollection | null): string {
  if (!collection) return "Collection";
  if (collection.kind === "all") return "Dataset";
  if (collection.kind === "lasso") return "Lasso";
  if (collection.kind === "neighbors") return "Neighbors";
  if (collection.kind === "search") return "Search";
  if (collection.kind === "filter") return "Filter";
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

  return React.useMemo(
    () => ({ searchByText, clearCollection }),
    [clearCollection, searchByText]
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

export const SamplesImageGridPanel = React.memo(function SamplesImageGridPanel(
  props: IDockviewPanelProps<SamplesPanelParams>
) {
  const { state, patchState } = usePanelState("samples");
  const collectionId = stringState(state.collection_id);
  const collection = useCollection(collectionId);
  const samplesPage = useSamples(collectionId, { pageSize: 60 });
  const selection = useSelection();
  const { clearCollection } = useSamplesPanelCommands();
  const panelMode = props.params?.mode ?? "auto";
  const showRankedPanel = panelMode === "ranked" || collection?.kind === "neighbors";
  const gridSize = SAMPLE_GRID_SIZE_OPTIONS.some((option) => option.value === state.grid_size)
    ? (state.grid_size as SampleGridSize)
    : "medium";
  const selectedIds = React.useMemo(() => new Set(selection.selectedIds), [selection.selectedIds]);
  const queryText = collectionQueryText(collection);
  const filterLabel = collectionFilterLabel(collection);

  const displayedSamples = React.useMemo(() => {
    if (!samplesPage.scores) return samplesPage.samples;
    return samplesPage.samples.map((sample) => {
      const score = samplesPage.scores?.[sample.id];
      return typeof score === "number" ? ({ ...sample, distance: score } as Sample) : sample;
    });
  }, [samplesPage.samples, samplesPage.scores]);

  const toolbarItems = React.useMemo<PanelToolbarItem[]>(
    () => [
      { id: "source", label: "Source", value: showRankedPanel ? "Ranked" : collectionSource(collection) },
      {
        id: "count",
        label: showRankedPanel ? "Results" : "Samples",
        value: samplesPage.total.toLocaleString(),
      },
      ...(queryText
        ? [{ id: "query", label: "Query", value: queryText } satisfies PanelToolbarItem]
        : []),
      ...(filterLabel
        ? [{ id: "filter", label: "Filter", value: filterLabel } satisfies PanelToolbarItem]
        : []),
    ],
    [collection, filterLabel, queryText, samplesPage.total, showRankedPanel]
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
      {!showRankedPanel ? <SamplesTextSearchBar /> : null}

      {samplesPage.error ? (
        <SampleCollectionState tone="error" title="Could not load samples" description={samplesPage.error} />
      ) : samplesPage.loading && displayedSamples.length === 0 ? (
        <SampleCollectionState
          tone="loading"
          title={queryText ? "Searching by text" : "Loading samples"}
          description={queryText ? `Finding matches for "${queryText}".` : "Preparing the active sample collection."}
        />
      ) : !collectionId ? (
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
      ) : (
        <SampleGridView
          samples={displayedSamples}
          onLoadMore={samplesPage.loadMore}
          hasMore={samplesPage.hasMore}
          scrollResetKey={`${collectionId}:${collection?.created_at ?? 0}`}
          showRankSimilarityBadge={showRankedPanel}
          controlledSelectedIds={selectedIds}
          onSelectionChange={(ids) => {
            void selection.setSelection(ids);
          }}
          gridSize={gridSize}
        />
      )}
    </Panel>
  );
});

SamplesImageGridPanel.displayName = "SamplesImageGridPanel";

export const samplesImageGridBuiltInPanel = defineBuiltInCenterPanel({
  id: "grid",
  panelType: "samples",
  component: "grid",
  title: "Samples",
  label: "Samples",
  icon: Grid3X3,
  tabComponent: "samplesTab",
  Component: SamplesImageGridPanel,
  buildAddPanelOptions: ({ position }) => ({
    id: "grid",
    component: "grid",
    title: "Samples",
    tabComponent: "samplesTab",
    ...(position ? { position } : {}),
  }),
});
