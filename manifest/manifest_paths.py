from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from output_paths import environment_slug


load_dotenv()


class ManifestConfigurationError(RuntimeError):
    """Neteisinga arba nepilna manifestų konfigūracija."""


def shared_data_root() -> Path:
    raw_path = os.getenv(
        "FURNIBOX_SHARED_DATA",
        "",
    ).strip()

    if not raw_path:
        raise ManifestConfigurationError(
            "Nenustatytas FURNIBOX_SHARED_DATA. "
            "Įrašyk bendro Furnibox duomenų katalogo kelią į .env."
        )

    return Path(raw_path).expanduser().resolve()


def manifest_environment_dir() -> Path:
    environment = environment_slug()

    if environment not in {
        "stage",
        "production",
    }:
        raise ManifestConfigurationError(
            "Nepavyko nustatyti aplinkos. "
            "Patikrink FURNIBOX_ENVIRONMENT ir ODOO_URL."
        )

    path = (
        shared_data_root()
        / "manifests"
        / environment
    )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path