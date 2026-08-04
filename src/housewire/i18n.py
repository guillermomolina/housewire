"""Locale helpers shared by UI APIs and clipboard paste placeholders."""
from __future__ import annotations

SUPPORTED_LOCALES = frozenset({"en", "es"})
DEFAULT_LOCALE = "en"

# Paste placeholders when name/label are empty (persisted into site YAML).
UNNAMED = {
    "en": "Unnamed",
    "es": "Sin nombre",
}
UNLABELED = {
    "en": "Unlabeled",
    "es": "Sin etiqueta",
}

ABOUT_DESCRIPTION = {
    "en": (
        "Document home electrical installations in YAML (house/v2) and edit them "
        "with an interactive physical canvas and shell."
    ),
    "es": (
        "Documenta instalaciones eléctricas domésticas en YAML (house/v2) y "
        "edítalas con un lienzo físico interactivo y un shell."
    ),
}


def normalize_locale(raw: object | None) -> str:
    """Map browser/API language tags to a supported UI locale."""
    s = str(raw or "").strip().lower().replace("_", "-")
    if not s:
        return DEFAULT_LOCALE
    primary = s.split("-", 1)[0]
    if primary in SUPPORTED_LOCALES:
        return primary
    if s.startswith("es"):
        return "es"
    return DEFAULT_LOCALE


def unnamed_for(locale: str) -> str:
    loc = normalize_locale(locale)
    return UNNAMED.get(loc, UNNAMED[DEFAULT_LOCALE])


def unlabeled_for(locale: str) -> str:
    loc = normalize_locale(locale)
    return UNLABELED.get(loc, UNLABELED[DEFAULT_LOCALE])


def about_description_for(locale: str) -> str:
    loc = normalize_locale(locale)
    return ABOUT_DESCRIPTION.get(loc, ABOUT_DESCRIPTION[DEFAULT_LOCALE])
