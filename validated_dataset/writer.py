from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from manifest.manifest_paths import (
    ManifestConfigurationError,
    shared_data_root,
)
from validated_dataset.models import ValidatedDataset


class DatasetWriterError(RuntimeError):
    """Nepavyko išsaugoti Validated Product Dataset."""


def dataset_environment_dir(
    environment: str,
) -> Path:
    normalized_environment = str(
        environment or ""
    ).strip().lower()

    if normalized_environment == "prod":
        normalized_environment = "production"

    if normalized_environment not in {
        "stage",
        "production",
    }:
        raise DatasetWriterError(
            f"Neleistina aplinka: {environment!r}"
        )

    try:
        root = shared_data_root()
    except ManifestConfigurationError as exc:
        raise DatasetWriterError(
            str(exc)
        ) from exc

    path = (
        root
        / "validated_datasets"
        / normalized_environment
    )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def write_validated_dataset(
    dataset: ValidatedDataset,
) -> Path:
    if not dataset.products:
        raise DatasetWriterError(
            "Negalima išsaugoti tuščio Dataset."
        )

    created_at = datetime.now(
        timezone.utc
    )

    environment_directory = (
        dataset_environment_dir(
            dataset.environment
        )
    )

    output_directory = (
        environment_directory
        / created_at.strftime("%Y-%m-%d")
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = created_at.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_path = (
        output_directory
        / f"Validated_Product_Dataset_{timestamp}.json"
    )

    dataset_json = json.dumps(
        dataset.to_dict(),
        ensure_ascii=False,
        indent=2,
    )

    try:
        output_path.write_text(
            dataset_json,
            encoding="utf-8",
        )
    except OSError as exc:
        raise DatasetWriterError(
            "Nepavyko išsaugoti Dataset: "
            f"{output_path}: {exc}"
        ) from exc

    latest_path = (
        environment_directory
        / "latest.json"
    )

    try:
        latest_path.write_text(
            dataset_json,
            encoding="utf-8",
        )
    except OSError as exc:
        raise DatasetWriterError(
            "Nepavyko atnaujinti latest.json: "
            f"{latest_path}: {exc}"
        ) from exc

    return output_path.resolve()