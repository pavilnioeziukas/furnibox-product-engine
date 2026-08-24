from pathlib import Path
import sys
from types import ModuleType

import pytest

if "dotenv" not in sys.modules:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from validated_dataset.full_bom_type_catalog import FullBomTypeCatalog
from validated_dataset.full_catalog_builder import (
    FullCatalogBuildError,
    build_full_validated_dataset,
)


def test_unresolved_bom_type_error_lists_skus_and_reasons():
    catalog = FullBomTypeCatalog(
        assignments={},
        unresolved={
            "SKU-Z": "Nerastas patikimas analogas.",
            "SKU-A": "Trūksta kategorijos.",
            "SKU-M": "Aktyvus Odoo BOM turi neatpažintą tipą.",
        },
    )

    with pytest.raises(FullCatalogBuildError) as error:
        build_full_validated_dataset(
            environment="production",
            batch_reference="test",
            source_file=Path("bom.xlsx"),
            source_file_hash="hash",
            reform_products={},
            reform_lines={},
            type_catalog=catalog,
            operation_templates={},
        )

    assert str(error.value).splitlines() == [
        "Yra neišspręstų BOM tipų: 3",
        "- SKU-A: Trūksta kategorijos.",
        "- SKU-M: Aktyvus Odoo BOM turi neatpažintą tipą.",
        "- SKU-Z: Nerastas patikimas analogas.",
    ]
