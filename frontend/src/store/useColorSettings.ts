import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { LabelColorMapId } from "@/lib/labelColors";

export interface LabelColorMapOption {
  value: LabelColorMapId;
  label: string;
}

export const LABEL_COLOR_MAP_OPTIONS: LabelColorMapOption[] = [
  { value: "auto", label: "Auto" },
  { value: "tab20", label: "Tab 20" },
  { value: "tab10", label: "Tab 10" },
  { value: "wong", label: "Wong" },
  { value: "classic20", label: "Classic 20" },
];

interface ColorSettingsState {
  labelColorMapId: LabelColorMapId;
  setLabelColorMapId: (value: LabelColorMapId) => void;
}

export const useColorSettings = create<ColorSettingsState>()(
  persist(
    (set) => ({
      labelColorMapId: "auto",
      setLabelColorMapId: (value) => set({ labelColorMapId: value }),
    }),
    {
      name: "hyperview-color-settings",
      version: 1,
      storage: createJSONStorage(() => localStorage),
    }
  )
);
