from pathlib import Path

import pytest

from openlca_agent.bom import ingest_bom


def test_ingest_bom_reads_csv_and_normalizes_units(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_text(
        "name,material,quantity,unit,supplier,location,notes\n"
        "Outer box,kraft paper,0.12,kilogram,Acme,CN,carton\n",
        encoding="utf-8",
    )

    items = ingest_bom(source_path=path)

    assert len(items) == 1
    assert items[0].name == "Outer box"
    assert items[0].material == "kraft paper"
    assert items[0].quantity == 0.12
    assert items[0].unit == "kg"
    assert items[0].location == "CN"


def test_ingest_bom_requires_source_path_or_inline_text() -> None:
    with pytest.raises(ValueError, match="source_path or inline_text"):
        ingest_bom()


def test_ingest_bom_rejects_missing_required_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("name,quantity,unit\nBox,1,kg\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        ingest_bom(source_path=path)
