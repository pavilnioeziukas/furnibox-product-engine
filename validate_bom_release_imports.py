from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from bom_release import load_latest_dataset_record
from bom_release.import_validator import validate_release_imports
from config import load_settings
from dotenv import load_dotenv
from output_paths import environment_slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Tikrina sugeneruotus BOM Release XLSX failus prieš Odoo importą. "
            "Odoo neskaito ir nekeičia."
        )
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--release-id",
        default=f"REFORM_v08_{date.today():%Y%m%d}",
    )
    parser.add_argument("--release-reference", default=None)
    parser.add_argument("--import-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    base = Path(__file__).resolve().parent
    load_dotenv(base / ".env")
    args = parse_args()
    if environment_slug() != "production":
        raise PermissionError(
            "Priešimportinė BOM Release patikra skirta Production paketui. "
            "Pasirink Production aplinką .env."
        )

    release_reference = (
        args.release_reference or args.release_id
    ).strip()
    settings = load_settings()
    dataset, dataset_path = load_latest_dataset_record(args.dataset)
    import_dir = (
        args.import_dir.resolve()
        if args.import_dir
        else settings.output_dir / f"BOM_Release_{args.release_id}"
    )
    result = validate_release_imports(
        dataset=dataset,
        release_id=args.release_id,
        release_reference=release_reference,
        import_dir=import_dir,
    )

    print()
    print("=" * 80)
    print("BOM RELEASE PRE-IMPORT VALIDATION")
    print("=" * 80)
    print("Dataset:", dataset_path)
    print("Importo katalogas:", import_dir)
    print("Statusas:", "PASS" if result.passed else "FAIL")
    print("Failai patikrinti:", result.files_checked)
    print("BOM aprėptis:", f"{result.actual_boms}/{result.expected_boms}")
    print("Komponentų eilutės:", result.component_rows)
    print("Operacijų eilutės:", result.operation_rows)
    print("Klaidos:", len(result.errors))
    for error in result.errors[:25]:
        print("-", error)
    if len(result.errors) > 25:
        print("-", f"... dar {len(result.errors) - 25}")
    print("Odoo pakeitimai: 0")
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
