"""Demo: compose a HyperView workspace from Python.

A workspace is described the way a Rerun blueprint is: panel instances, and how
they sit next to each other. This example shows the four things a real launch
script needs beyond the panels themselves.

- ``dataset.find_layout(...)`` looks a layout up by what produced it. Layout
  keys carry a content hash of the embedding and projection parameters, so they
  are only knowable after the layout is computed and cannot be pinned as
  constants that survive a rebuild.
- ``session.create_collection(...)`` stores an ordered set of samples and
  returns its id, so a panel can open on a prepared result set.
- ``hv.ui.Samples(...)`` takes the panel's documented props as keyword
  arguments; ``hv.ui.Panel(...)`` places any registered panel type, including
  ones with no dedicated class.
- ``hv.launch(..., extensions=[...])`` registers extensions before anything
  else touches the runtime, which is what makes an extension panel placeable in
  the view that follows.

Run it with ``uv run python examples/composed_workspace.py``.
"""

from __future__ import annotations

import hyperview as hv

DATASET_NAME = "cifar10_composed_workspace"
WORKSPACE_ID = "composed-workspace-demo"
HIGHLIGHT_COUNT = 12

dataset = hv.Dataset(DATASET_NAME)
added, skipped = dataset.add_from_huggingface(
    "uoft-cs/cifar10",
    split="train",
    image_key="img",
    label_key="label",
    max_samples=200,
)
print(f"Ingested {added} samples ({skipped} skipped)")

dataset.compute_embeddings(model="openai/clip-vit-base-patch32")
dataset.compute_visualization(layout="euclidean:2d")

layout_key = dataset.find_layout(geometry="euclidean", dimension=2)
if layout_key is None:
    raise SystemExit("No 2D euclidean layout to open the map on.")
print(f"Opening the map on {layout_key}")

# Extensions are registered before the runtime does anything else, so the view
# below can place the reference extension's panel.
session = hv.launch(
    dataset,
    workspace_id=WORKSPACE_ID,
    extensions=["reference"],
    open_browser=False,
    block=False,
)

highlights = session.create_collection(
    [sample.id for sample in dataset.samples[:HIGHLIGHT_COUNT]],
    name=f"First {HIGHLIGHT_COUNT} samples",
    workspace_id=WORKSPACE_ID,
)

view = hv.ui.View(
    hv.ui.Horizontal(
        hv.ui.Samples(
            id="highlights",
            title="Highlights",
            mode="results",
            collection_id=highlights,
            show_text_search=True,
        ),
        hv.ui.Scatter(id="map", title="CLIP map", layout_key=layout_key),
        shares=[1, 1],
    ),
    # The explorer has no dedicated class in older scripts; Panel places any
    # registered panel type by name.
    hv.ui.Panel(
        "explorer",
        id="labels",
        position="right",
        layout=hv.ui.PanelLayout(width=260, min_width=200),
    ),
    hv.ui.ExtensionPanel(
        id="reference",
        extension="reference",
        panel="reference",
        position="right",
        # state= is the panel's opening runtime state, applied with the view.
        state={"notes": "Opened by examples/composed_workspace.py"},
    ),
    active_panel="highlights",
)
session.ui.apply_view(view, workspace_id=WORKSPACE_ID)

print(f"HyperView is running at {session.url}")
session.open_browser()
session.wait()
