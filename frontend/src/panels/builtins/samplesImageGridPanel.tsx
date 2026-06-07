"use client";

import React from "react";
import type { IDockviewPanelProps } from "dockview-react";
import { Grid3X3, Settings2, Undo2 } from "lucide-react";

import { SampleCollectionState } from "@/components/SampleCollectionState";
import { SampleDerivedSpace } from "@/components/SampleDerivedSpace";
import { SampleGridView } from "@/components/SampleGridView";
import {
  fetchSamplesBatch,
  fetchSimilarSamples,
  isAbortError,
} from "@/lib/api";
import { findLayoutByKey } from "@/lib/layouts";
import {
  Panel,
  PanelToolbar,
  PanelToolbarButton,
  PanelToolbarMenu,
  usePanelCommands,
  usePanelSamplesView,
  usePanelUiState,
  type PanelToolbarItem,
} from "@/panel-sdk";
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { defineBuiltInCenterPanel } from "@/panels/definitions";
import { useStore } from "@/store/useStore";
import type { Sample, SimilarSample } from "@/types";

const SAMPLE_GRID_SIZE_OPTIONS = [
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
  { value: "large", label: "Large" },
] as const;

type SampleGridSize = (typeof SAMPLE_GRID_SIZE_OPTIONS)[number]["value"];
type SamplesPanelMode = "auto" | "browse" | "ranked";

interface SamplesPanelRankParams extends Record<string, unknown> {
  anchorSampleId?: string;
  layoutKey?: string;
  spaceKey?: string;
  k?: number;
  source?: string;
}

interface SamplesPanelParams extends Record<string, unknown> {
  panelId?: string;
  mode?: SamplesPanelMode;
  rank?: SamplesPanelRankParams;
}

const DEFAULT_RANK_LIMIT = 18;
const RANK_PAGE_INCREMENT = 12;
const MAX_RANK_LIMIT = 96;

function sourceLabel(source: "dataset" | "lasso") {
  if (source === "lasso") return "Lasso";
  return "Dataset";
}

function normalizeRankLimit(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return DEFAULT_RANK_LIMIT;
  return Math.max(1, Math.min(MAX_RANK_LIMIT, Math.round(value)));
}

function getRankAnchorFromSelection(selectedIds: Set<string>) {
  if (selectedIds.size !== 1) return null;
  return Array.from(selectedIds)[0] ?? null;
}

function useRankedSamplesPanel(rank: SamplesPanelRankParams | undefined, enabled: boolean) {
  const datasetInfo = useStore((state) => state.datasetInfo);
  const selectedIds = useStore((state) => state.selectedIds);
  const loadedSamples = useStore((state) => state.samples);

  const configuredLimit = normalizeRankLimit(rank?.k);
  const [limit, setLimit] = React.useState(configuredLimit);
  const [anchorSample, setAnchorSample] = React.useState<Sample | null>(null);
  const [rankedSamples, setRankedSamples] = React.useState<SimilarSample[]>([]);
  const [metric, setMetric] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const selectedAnchorId = React.useMemo(
    () => getRankAnchorFromSelection(selectedIds),
    [selectedIds]
  );
  const anchorSampleId = enabled ? rank?.anchorSampleId ?? selectedAnchorId : null;
  const layoutKey = rank?.layoutKey;
  const spaceKey = rank?.spaceKey;

  const loadedAnchorSample = React.useMemo(
    () =>
      anchorSampleId
        ? loadedSamples.find((sample) => sample.id === anchorSampleId) ?? null
        : null,
    [anchorSampleId, loadedSamples]
  );

  React.useEffect(() => {
    setLimit(configuredLimit);
  }, [configuredLimit, anchorSampleId, layoutKey, spaceKey]);

  React.useEffect(() => {
    if (!enabled || !anchorSampleId) {
      setAnchorSample(null);
      setRankedSamples([]);
      setMetric(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const abort = new AbortController();
    setLoading(true);
    setError(null);

    const fetchAnchor = loadedAnchorSample
      ? Promise.resolve(loadedAnchorSample)
      : fetchSamplesBatch([anchorSampleId]).then((samples) => samples[0] ?? null);

    Promise.all([
      fetchAnchor,
      fetchSimilarSamples(anchorSampleId, {
        k: limit,
        layoutKey,
        spaceKey: layoutKey ? undefined : spaceKey,
        includeThumbnails: false,
        signal: abort.signal,
      }),
    ])
      .then(([nextAnchorSample, response]) => {
        if (cancelled || abort.signal.aborted) return;
        setAnchorSample(nextAnchorSample);
        setRankedSamples(
          response.results.filter((sample) => sample.id !== anchorSampleId)
        );
        setMetric(response.metric);
      })
      .catch((err) => {
        if (cancelled || isAbortError(err)) return;
        console.error("Failed to fetch ranked samples:", err);
        setAnchorSample(loadedAnchorSample);
        setRankedSamples([]);
        setMetric(null);
        setError(err instanceof Error ? err.message : "Failed to fetch ranked samples");
      })
      .finally(() => {
        if (cancelled || abort.signal.aborted) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
      abort.abort();
    };
  }, [anchorSampleId, enabled, layoutKey, limit, loadedAnchorSample, spaceKey]);

  const sourceDescription = React.useMemo(() => {
    if (!datasetInfo) return rank?.source ?? null;
    const layout = layoutKey ? findLayoutByKey(datasetInfo.layouts, layoutKey) : null;
    const resolvedSpaceKey = spaceKey ?? layout?.space_key ?? null;
    const space =
      resolvedSpaceKey === null
        ? null
        : datasetInfo.spaces.find((candidate) => candidate.space_key === resolvedSpaceKey) ??
          null;
    if (!space) return rank?.source ?? layoutKey ?? spaceKey ?? null;
    const geometry = space.geometry ? ` · ${space.geometry}` : "";
    const layoutMethod = layout?.method ? ` · ${layout.method}` : "";
    return `${space.model_id}${geometry}${layoutMethod}`;
  }, [datasetInfo, layoutKey, rank?.source, spaceKey]);

  return {
    anchorSampleId,
    anchorSample,
    rankedSamples,
    metric,
    sourceDescription,
    loading,
    error,
    hasMore: rankedSamples.length >= limit && limit < MAX_RANK_LIMIT,
    loadMore: () => setLimit((current) => Math.min(MAX_RANK_LIMIT, current + RANK_PAGE_INCREMENT)),
    scrollResetKey: [
      "ranked",
      anchorSampleId ?? "none",
      layoutKey ?? "none",
      spaceKey ?? "none",
      limit,
    ].join(":"),
  };
}

export const SamplesImageGridPanel = React.memo(function SamplesImageGridPanel(
  props: IDockviewPanelProps<SamplesPanelParams>
) {
  const { collection, derivedSpace } = usePanelSamplesView();
  const { clearLassoSelection } = usePanelCommands();
  const { sampleGridSize, setSampleGridSize } = usePanelUiState();
  const panelMode = props.params?.mode ?? "auto";
  const showRankedPanel = panelMode === "ranked";
  const rankedPanel = useRankedSamplesPanel(props.params?.rank, showRankedPanel);
  const showDefaultDerivedSpace = panelMode === "auto" && derivedSpace.visible;

  const toolbarItems = React.useMemo<PanelToolbarItem[]>(
    () => {
      if (showRankedPanel) {
        return [
          {
            id: "source",
            label: "Source",
            value: "Ranked",
          },
          {
            id: "count",
            label: "Results",
            value: rankedPanel.rankedSamples.length.toLocaleString(),
          },
          ...(rankedPanel.anchorSampleId
            ? [
                {
                  id: "anchor",
                  label: "Anchor",
                  value: rankedPanel.anchorSampleId,
                } satisfies PanelToolbarItem,
              ]
            : []),
        ];
      }

      return [
        {
          id: "source",
          label: "Source",
          value: sourceLabel(collection.meta.source),
        },
        {
          id: "count",
          label: "Samples",
          value: collection.total.toLocaleString(),
        },
        ...(collection.meta.labelFilter
          ? [
              {
                id: "filter",
                label: "Filter",
                value: collection.meta.labelFilter,
              } satisfies PanelToolbarItem,
            ]
          : []),
      ];
    },
    [
      collection.meta.labelFilter,
      collection.meta.source,
      collection.total,
      rankedPanel.anchorSampleId,
      rankedPanel.rankedSamples.length,
      showRankedPanel,
    ]
  );

  const toolbarActions = React.useMemo(
    () => (
      <>
        {collection.meta.source === "lasso" ? (
          <PanelToolbarButton onClick={clearLassoSelection}>
            <Undo2 className="h-3 w-3" />
            Clear lasso
          </PanelToolbarButton>
        ) : null}
        <PanelToolbarMenu
          icon={<Settings2 className="h-3.5 w-3.5" />}
          label="Sample panel settings"
          title={`Thumbnail size: ${sampleGridSize}`}
          contentClassName="min-w-[220px]"
        >
          <DropdownMenuLabel>
            Thumbnail size
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup
            value={sampleGridSize}
            onValueChange={(value) => setSampleGridSize(value as SampleGridSize)}
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
    [clearLassoSelection, collection.meta.source, sampleGridSize, setSampleGridSize]
  );

  return (
    <Panel className="h-full">
      <PanelToolbar items={toolbarItems} actions={toolbarActions} />

      {showRankedPanel ? (
        !rankedPanel.anchorSampleId ? (
          <SampleCollectionState
            title="No rank anchor"
            description="Select one sample or set rank.anchorSampleId in this panel's props."
          />
        ) : rankedPanel.anchorSample === null && rankedPanel.loading ? (
          <SampleCollectionState
            tone="loading"
            title="Loading ranked samples"
            description="Resolving the anchor and ranking candidates."
          />
        ) : rankedPanel.anchorSample === null ? (
          <SampleCollectionState
            tone="error"
            title="Could not load rank anchor"
            description={rankedPanel.error ?? rankedPanel.anchorSampleId}
          />
        ) : (
          <SampleDerivedSpace
            selectionSamples={[rankedPanel.anchorSample]}
            neighborSamples={rankedPanel.rankedSamples}
            neighborsMetric={rankedPanel.metric}
            neighborsSourceLabel={rankedPanel.sourceDescription}
            neighborsLoading={rankedPanel.loading}
            hasMoreNeighbors={rankedPanel.hasMore}
            loadMoreNeighbors={rankedPanel.loadMore}
            neighborsError={rankedPanel.error}
            neighborsScrollResetKey={rankedPanel.scrollResetKey}
            neighborsTitle="Ranked samples"
          />
        )
      ) : showDefaultDerivedSpace ? (
        <SampleDerivedSpace
          selectionSamples={derivedSpace.selectionSamples}
          neighborSamples={derivedSpace.neighborSamples}
          neighborsMetric={derivedSpace.neighborsMetric}
          neighborsSourceLabel={derivedSpace.neighborsSourceLabel}
          neighborsLoading={derivedSpace.neighborsLoading}
          hasMoreNeighbors={derivedSpace.hasMoreNeighbors}
          loadMoreNeighbors={derivedSpace.loadMoreNeighbors}
          neighborsError={derivedSpace.neighborsError}
          neighborsScrollResetKey={derivedSpace.neighborsScrollResetKey}
        />
      ) : null}

      {showRankedPanel ? null : collection.error ? (
        <SampleCollectionState
          tone="error"
          title="Could not load samples"
          description={collection.error}
        />
      ) : collection.loading && collection.samples.length === 0 ? (
        <SampleCollectionState
          tone="loading"
          title="Loading samples"
          description="Preparing the active sample collection."
        />
      ) : collection.samples.length === 0 ? (
        showDefaultDerivedSpace ? null : (
          <SampleCollectionState
            title={collection.emptyTitle}
            description={collection.emptyDescription}
          />
        )
      ) : !showDefaultDerivedSpace ? (
        <SampleGridView
          samples={collection.samples}
          onLoadMore={collection.loadMore}
          hasMore={collection.hasMore}
          scrollResetKey={collection.meta.scrollResetKey}
        />
      ) : null
      }
    </Panel>
  );
});

SamplesImageGridPanel.displayName = "SamplesImageGridPanel";

export const samplesImageGridBuiltInPanel = defineBuiltInCenterPanel({
  id: "grid",
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
