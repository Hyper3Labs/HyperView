"""Deterministic categorical colors shared by static figure export."""

from __future__ import annotations

import colorsys

MISSING_LABEL_SENTINEL = "undefined"
MISSING_LABEL_COLOR = "#39d3cc"
FALLBACK_LABEL_COLOR = "#8b949e"

TAB_20_LABEL_PALETTE = [
    "#0072b2",
    "#e69f00",
    "#009e73",
    "#d55e00",
    "#cc79a7",
    "#56b4e9",
    "#000000",
    "#7f7f7f",
    "#332288",
    "#88ccee",
    "#44aa99",
    "#117733",
    "#999933",
    "#ddcc77",
    "#cc6677",
    "#882255",
    "#aa4499",
    "#6699cc",
    "#661100",
    "#888888",
]

OVERFLOW_HUE_STEP_DEGREES = 137.508


def normalize_label(label: str | None) -> str:
    return label if label else MISSING_LABEL_SENTINEL


def _stable_label_sort_key(label: str) -> tuple[int, str]:
    return (1, label) if label == MISSING_LABEL_SENTINEL else (0, label)


def _overflow_color(index: int) -> str:
    hue = (43.0 + index * OVERFLOW_HUE_STEP_DEGREES) % 360.0
    saturation = [0.72, 0.64, 0.78][index % 3]
    lightness = [0.46, 0.54, 0.38, 0.62][(index // 3) % 4]
    r, g, b = colorsys.hls_to_rgb(hue / 360.0, lightness, saturation)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def create_label_color_map(labels: list[str | None]) -> dict[str, str]:
    unique = sorted({normalize_label(label) for label in labels}, key=_stable_label_sort_key)
    colors: dict[str, str] = {}
    used: set[str] = set()
    non_missing_index = 0
    overflow_index = 0

    for label in unique:
        if label == MISSING_LABEL_SENTINEL:
            colors[label] = MISSING_LABEL_COLOR
            used.add(MISSING_LABEL_COLOR.lower())
            continue

        if non_missing_index < len(TAB_20_LABEL_PALETTE):
            candidate = TAB_20_LABEL_PALETTE[non_missing_index]
        else:
            candidate = _overflow_color(overflow_index)

        safety = 0
        while candidate.lower() in used and safety < 2048:
            overflow_index += 1
            candidate = _overflow_color(overflow_index)
            safety += 1

        if non_missing_index >= len(TAB_20_LABEL_PALETTE):
            overflow_index += 1

        if candidate.lower() in used:
            candidate = FALLBACK_LABEL_COLOR

        colors[label] = candidate
        used.add(candidate.lower())
        non_missing_index += 1

    return colors


def hex_to_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    raw = color.strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) not in {6, 8}:
        return 255, 255, 255, alpha
    r = int(raw[0:2], 16)
    g = int(raw[2:4], 16)
    b = int(raw[4:6], 16)
    a = int(raw[6:8], 16) if len(raw) == 8 else alpha
    return r, g, b, a
