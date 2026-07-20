"""Aplinkai saugūs Furnibox Product Engine rezultatų keliai."""

from __future__ import annotations

import os
from pathlib import Path


def environment_slug() -> str | None:
    """Grąžina stage/production arba None, jei aplinka nenustatyta."""
    name = os.getenv("FURNIBOX_ENVIRONMENT", "").strip().lower()
    url = os.getenv("ODOO_URL", "").strip().lower()
    if name == "stage" or "stage" in url:
        return "stage"
    if name in {"production", "prod"} or (url and "stage" not in url):
        return "production"
    return None


def environment_output_dir(base: Path) -> Path:
    """GUI režime atskiria aplinkas; rankiniame sename režime palieka output."""
    root = base / "output"
    slug = environment_slug()
    path = root / slug if slug else root
    path.mkdir(parents=True, exist_ok=True)
    return path
