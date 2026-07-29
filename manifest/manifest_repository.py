from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from manifest.manifest_paths import (
    ManifestConfigurationError,
    shared_data_root,
)


class ManifestRepositoryError(RuntimeError):
    """Nepavyko rasti arba nuskaityti BOM manifesto."""


@dataclass(frozen=True)
class ManifestReference:
    path: Path
    manifest_id: str
    batch_reference: str
    created_at_utc: str
    environment: str
    manifest_type: str
    schema_version: str


class ManifestRepository:
    EXPECTED_MANIFEST_TYPE = "bom_import_package"

    def __init__(
        self,
        shared_root: Path | None = None,
    ) -> None:
        try:
            self.shared_root = (
                shared_root.resolve()
                if shared_root is not None
                else shared_data_root()
            )
        except ManifestConfigurationError as exc:
            raise ManifestRepositoryError(
                str(exc)
            ) from exc

    def environment_directory(
        self,
        environment: str,
    ) -> Path:
        normalized = self.normalize_environment(
            environment
        )

        return (
            self.shared_root
            / "manifests"
            / normalized
        )

    def list_manifests(
        self,
        environment: str,
    ) -> list[ManifestReference]:
        directory = self.environment_directory(
            environment
        )

        if not directory.exists():
            return []

        references: list[ManifestReference] = []

        for path in directory.rglob(
            "BOM_Import_Manifest_*.json"
        ):
            if not path.is_file():
                continue

            try:
                data = self.load_file(path)
                reference = self.build_reference(
                    path=path,
                    data=data,
                )
            except ManifestRepositoryError:
                # Sugadintas ar ne tos schemos failas
                # neturi sustabdyti kitų manifestų paieškos.
                continue

            if (
                reference.environment
                != self.normalize_environment(
                    environment
                )
            ):
                continue

            if (
                reference.manifest_type
                != self.EXPECTED_MANIFEST_TYPE
            ):
                continue

            references.append(reference)

        references.sort(
            key=lambda item: (
                self.parse_created_at(
                    item.created_at_utc
                ),
                item.path.name,
            ),
            reverse=True,
        )

        return references

    def load_latest(
        self,
        environment: str,
    ) -> dict[str, Any]:
        references = self.list_manifests(
            environment
        )

        if not references:
            raise ManifestRepositoryError(
                "Manifestų nerasta aplinkai "
                f"{environment!r} kataloge "
                f"{self.environment_directory(environment)}"
            )

        return self.load_file(
            references[0].path
        )

    def load_latest_reference(
        self,
        environment: str,
    ) -> ManifestReference:
        references = self.list_manifests(
            environment
        )

        if not references:
            raise ManifestRepositoryError(
                "Manifestų nerasta aplinkai "
                f"{environment!r}."
            )

        return references[0]

    def load_by_batch(
        self,
        *,
        environment: str,
        batch_reference: str,
    ) -> dict[str, Any]:
        normalized_batch = str(
            batch_reference or ""
        ).strip()

        if not normalized_batch:
            raise ManifestRepositoryError(
                "Nenurodytas batch_reference."
            )

        matches: list[ManifestReference] = [
            reference
            for reference in self.list_manifests(
                environment
            )
            if reference.batch_reference
            == normalized_batch
        ]

        if not matches:
            raise ManifestRepositoryError(
                "Manifestas nerastas: "
                f"environment={environment}, "
                f"batch_reference={normalized_batch}"
            )

        if len(matches) > 1:
            raise ManifestRepositoryError(
                "Rasti keli manifestai tuo pačiu "
                f"batch_reference={normalized_batch}: "
                + ", ".join(
                    str(reference.path)
                    for reference in matches
                )
            )

        return self.load_file(
            matches[0].path
        )

    def find_bom(
        self,
        *,
        manifest: dict[str, Any],
        root_sku: str,
    ) -> dict[str, Any] | None:
        normalized_sku = str(
            root_sku or ""
        ).strip().upper()

        if not normalized_sku:
            raise ManifestRepositoryError(
                "Nenurodytas root SKU."
            )

        matches = [
            bom
            for bom in manifest.get(
                "boms",
                [],
            )
            if str(
                bom.get("root_sku") or ""
            ).strip().upper()
            == normalized_sku
        ]

        if not matches:
            return None

        if len(matches) > 1:
            raise ManifestRepositoryError(
                "Manifeste rasti keli BOM tam pačiam "
                f"root SKU {normalized_sku}."
            )

        return matches[0]

    @classmethod
    def load_file(
        cls,
        path: Path,
    ) -> dict[str, Any]:
        resolved_path = path.resolve()

        if not resolved_path.exists():
            raise ManifestRepositoryError(
                f"Manifesto failas nerastas: "
                f"{resolved_path}"
            )

        try:
            data = json.loads(
                resolved_path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as exc:
            raise ManifestRepositoryError(
                "Neteisingas manifesto JSON: "
                f"{resolved_path}: {exc}"
            ) from exc
        except OSError as exc:
            raise ManifestRepositoryError(
                "Nepavyko nuskaityti manifesto: "
                f"{resolved_path}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise ManifestRepositoryError(
                "Manifesto šaknis turi būti JSON objektas: "
                f"{resolved_path}"
            )

        cls.validate_manifest(
            data=data,
            path=resolved_path,
        )

        return data

    @classmethod
    def validate_manifest(
        cls,
        *,
        data: dict[str, Any],
        path: Path,
    ) -> None:
        required_fields = [
            "schema_version",
            "manifest_type",
            "manifest_id",
            "batch_reference",
            "created_at_utc",
            "environment",
            "source",
            "output_files",
            "boms",
        ]

        missing = [
            field
            for field in required_fields
            if field not in data
        ]

        if missing:
            raise ManifestRepositoryError(
                "Manifestui trūksta laukų "
                f"{missing}: {path}"
            )

        if (
            data.get("manifest_type")
            != cls.EXPECTED_MANIFEST_TYPE
        ):
            raise ManifestRepositoryError(
                "Netinkamas manifest_type: "
                f"{data.get('manifest_type')!r}: "
                f"{path}"
            )

        if not isinstance(
            data.get("boms"),
            list,
        ):
            raise ManifestRepositoryError(
                f"Laukas 'boms' nėra sąrašas: {path}"
            )

        if not isinstance(
            data.get("output_files"),
            list,
        ):
            raise ManifestRepositoryError(
                "Laukas 'output_files' nėra sąrašas: "
                f"{path}"
            )

        cls.parse_created_at(
            str(data.get("created_at_utc") or "")
        )

    @classmethod
    def build_reference(
        cls,
        *,
        path: Path,
        data: dict[str, Any],
    ) -> ManifestReference:
        return ManifestReference(
            path=path.resolve(),
            manifest_id=str(
                data.get("manifest_id") or ""
            ),
            batch_reference=str(
                data.get("batch_reference") or ""
            ),
            created_at_utc=str(
                data.get("created_at_utc") or ""
            ),
            environment=str(
                data.get("environment") or ""
            ).strip().lower(),
            manifest_type=str(
                data.get("manifest_type") or ""
            ),
            schema_version=str(
                data.get("schema_version") or ""
            ),
        )

    @staticmethod
    def parse_created_at(
        value: str,
    ) -> datetime:
        normalized = str(
            value or ""
        ).strip()

        if not normalized:
            raise ManifestRepositoryError(
                "Manifestas neturi created_at_utc."
            )

        try:
            return datetime.fromisoformat(
                normalized.replace(
                    "Z",
                    "+00:00",
                )
            )
        except ValueError as exc:
            raise ManifestRepositoryError(
                "Neteisingas created_at_utc: "
                f"{normalized!r}"
            ) from exc

    @staticmethod
    def normalize_environment(
        environment: str,
    ) -> str:
        normalized = str(
            environment or ""
        ).strip().lower()

        if normalized == "prod":
            normalized = "production"

        if normalized not in {
            "stage",
            "production",
        }:
            raise ManifestRepositoryError(
                f"Neleistina aplinka: {environment!r}"
            )

        return normalized