"""Canonical conductor color codes for HouseWire (IEC 60757 letter abbreviations).

This table is owned by HouseWire. Codes follow IEC 60757 letter symbols; CSS
hex values are the HouseWire UI palette for the canvas.
"""
from __future__ import annotations

from typing import Any

# code → {label_en, label_es, css, typical}
CONDUCTOR_COLORS: dict[str, dict[str, str]] = {
    "BK": {
        "label_en": "black",
        "label_es": "negro",
        "css": "#1a1a1a",
        "typical": "Phase from panel / permanent lights phase",
    },
    "BN": {
        "label_en": "brown",
        "label_es": "marrón",
        "css": "#a0522d",
        "typical": "Switched phase, lamp feeds, some socket L",
    },
    "RD": {
        "label_en": "red",
        "label_es": "rojo",
        "css": "#e53935",
        "typical": "Catalog dc default (with BK)",
    },
    "OG": {
        "label_en": "orange",
        "label_es": "naranja",
        "css": "#fb8c00",
        "typical": "Available; uncommon in domestic work",
    },
    "YE": {
        "label_en": "yellow",
        "label_es": "amarillo",
        "css": "#fdd835",
        "typical": "Available; do not use for PE",
    },
    "GN": {
        "label_en": "green",
        "label_es": "verde",
        "css": "#43a047",
        "typical": "Available; prefer GNYE for PE",
    },
    "BU": {
        "label_en": "blue",
        "label_es": "azul",
        "css": "#1e90ff",
        "typical": "Neutral (N)",
    },
    "VT": {
        "label_en": "violet",
        "label_es": "violeta",
        "css": "#8e24aa",
        "typical": "Available",
    },
    "GY": {
        "label_en": "grey",
        "label_es": "gris",
        "css": "#9e9e9e",
        "typical": "Phase (light grey), travellers, some feeds",
    },
    "WH": {
        "label_en": "white",
        "label_es": "blanco",
        "css": "#f0f0f0",
        "typical": "Catalog signal default (with BU)",
    },
    "PK": {
        "label_en": "pink",
        "label_es": "rosa",
        "css": "#ec407a",
        "typical": "Available",
    },
    "TQ": {
        "label_en": "turquoise",
        "label_es": "turquesa",
        "css": "#26a69a",
        "typical": "Available",
    },
    "GNYE": {
        "label_en": "green-yellow",
        "label_es": "verde-amarillo",
        "css": "#adff2f",
        "typical": "Protective earth (PE)",
    },
    "SR": {
        "label_en": "silver",
        "label_es": "plata",
        "css": "#b0bec5",
        "typical": "Available",
    },
}

UNKNOWN_WIRE_CSS = "#8b949e"


def normalize_color_code(code: object) -> str:
    return str(code or "").strip().upper()


def is_known_color_code(code: object) -> bool:
    return normalize_color_code(code) in CONDUCTOR_COLORS


def css_for_color(code: object) -> str:
    key = normalize_color_code(code)
    meta = CONDUCTOR_COLORS.get(key)
    if meta is None:
        return UNKNOWN_WIRE_CSS
    return meta["css"]


def wire_colors_payload() -> dict[str, Any]:
    """JSON-friendly palette for the UI and tooling."""
    return {
        "standard": "HouseWire",
        "letter_standard": "IEC 60757",
        "unknown_css": UNKNOWN_WIRE_CSS,
        "colors": {
            code: {
                "css": meta["css"],
                "label_en": meta["label_en"],
                "label_es": meta["label_es"],
                "typical": meta["typical"],
            }
            for code, meta in CONDUCTOR_COLORS.items()
        },
    }
