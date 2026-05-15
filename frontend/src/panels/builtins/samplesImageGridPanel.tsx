"use client";

import React from "react";
import type { IDockviewPanelProps } from "dockview";
import { Grid3X3, Settings2, Undo2 } from "lucide-react";

import { SampleCollectionState } from "@/components/SampleCollectionState";
import { SampleDerivedSpace } from "@/components/SampleDerivedSpace";
import { SampleGridView } from "@/components/SampleGridView";
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

const SAMPLE_GRID_SIZE_OPTIONS = [
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
  { value: "large", label: "Large" },
] as const;

type SampleGridSize = (typeof SAMPLE_GRID_SIZE_OPTIONS)[number]["value"];

function sourceLabel(source: "dataset" | "lasso") {
  if (source === "lasso") return "Lasso";
  return "Dataset";
}

export const SamplesImageGridPanel = React.memo(function SamplesImageGridPanel(
  _props: IDockviewPanelProps
) {
  const { collection, derivedSpace } = usePanelSamplesView();
  const { clearLassoSelection } = usePanelCommands();
  const { sampleGridSize, setSampleGridSize } = usePanelUiState();

  const toolbarItems = React.useMemo<PanelToolbarItem[]>(
    () => [
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
    ],
    [collection.meta.labelFilter, collection.meta.source, collection.total]
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

      {derivedSpace.visible && (
        <SampleDerivedSpace
          selectionSamples={derivedSpace.selectionSamples}
          neighborSamples={derivedSpace.neighborSamples}
          neighborsMetric={derivedSpace.neighborsMetric}
          neighborsLoading={derivedSpace.neighborsLoading}
          hasMoreNeighbors={derivedSpace.hasMoreNeighbors}
          loadMoreNeighbors={derivedSpace.loadMoreNeighbors}
          neighborsError={derivedSpace.neighborsError}
          neighborsScrollResetKey={derivedSpace.neighborsScrollResetKey}
        />
      )}

      {collection.error ? (
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
        derivedSpace.visible ? null : (
          <SampleCollectionState
            title={collection.emptyTitle}
            description={collection.emptyDescription}
          />
        )
      ) : !derivedSpace.visible ? (
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
    renderer: "always",
    ...(position ? { position } : {}),
  }),
});
