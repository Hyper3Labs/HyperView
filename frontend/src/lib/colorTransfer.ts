import {
  FALLBACK_LABEL_COLOR,
  createLabelColorMap,
  normalizeLabel,
  type LabelColorMapId,
} from "@/lib/labelColors";

export interface CategoricalLabelTransferFunction {
  kind: "categorical";
  paletteId: LabelColorMapId;
  colorFor: (label: string | null | undefined) => string;
}

export function createCategoricalLabelTransferFunction(params: {
  labels: string[];
  paletteId: LabelColorMapId;
}): CategoricalLabelTransferFunction {
  const { labels, paletteId } = params;
  const colorMap = createLabelColorMap(labels, { paletteId });

  return {
    kind: "categorical",
    paletteId,
    colorFor: (label) => colorMap[normalizeLabel(label)] ?? FALLBACK_LABEL_COLOR,
  };
}
