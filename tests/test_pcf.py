from __future__ import annotations

from pathlib import Path

from openlca_agent.models import CalculationRun, Hotspot, ImpactResult, ProductModel, RunStage
from openlca_agent.pcf import build_pcf, export_pcf_json, export_pcf_xlsx


def _make_run() -> CalculationRun:
    return CalculationRun(
        run_id="test-run-1",
        product_system={"id": "ps-1", "name": "Demo product"},
        impact_method={"id": "ef31", "name": "EF 3.1"},
        total_impacts=[
            ImpactResult(impact_category="Climate change", value=12.5, unit="kg CO2 eq"),
        ],
        hotspots=[
            Hotspot(name="Steel production", value=8.0, unit="kg CO2 eq", contribution=0.64),
            Hotspot(name="Transport", value=3.0, unit="kg CO2 eq", contribution=0.24),
        ],
        assumptions=["Process mapping used fuzzy matching."],
        missing_data=["No supplier-specific electricity data."],
        stage=RunStage.CALCULATED,
    )


def test_build_pcf() -> None:
    run = _make_run()
    model = ProductModel(
        product_name="Demo product",
        functional_unit="1 kg",
    )
    pcf = build_pcf(run, model)

    assert pcf.spec_version == "2.0"
    assert pcf.product_name == "Demo product"
    assert pcf.product_id == "ps-1"
    assert pcf.declared_unit == "1 kg"
    assert pcf.total_pcf == 12.5
    assert pcf.fossil_ghg_emissions == 12.5
    assert pcf.impact_method == "EF 3.1"
    assert len(pcf.processes) == 2
    assert pcf.processes[0].process_name == "Steel production"
    assert pcf.processes[0].value == 8.0
    assert pcf.processes[0].contribution == 0.64
    assert pcf.assumptions == ["Process mapping used fuzzy matching."]
    assert pcf.missing_data == ["No supplier-specific electricity data."]


def test_build_pcf_no_model() -> None:
    run = _make_run()
    pcf = build_pcf(run)

    assert pcf.product_name == "Demo product"
    assert pcf.product_id == "ps-1"
    assert pcf.declared_unit == "1 piece"
    assert pcf.total_pcf == 12.5


def test_build_pcf_no_climate_change() -> None:
    run = _make_run()
    run.total_impacts = [
        ImpactResult(impact_category="Acidification", value=0.05, unit="mol H+ eq"),
    ]
    pcf = build_pcf(run)
    assert pcf.total_pcf == 0.0


def test_export_pcf_json(tmp_path: Path) -> None:
    run = _make_run()
    pcf = build_pcf(run)
    path = tmp_path / "pcf.json"
    result = export_pcf_json(pcf, path)

    assert Path(result).exists()
    content = path.read_text(encoding="utf-8")
    assert '"spec_version": "2.0"' in content
    assert '"total_pcf": 12.5' in content
    assert '"product_name": "Demo product"' in content


def test_export_pcf_xlsx(tmp_path: Path) -> None:
    run = _make_run()
    pcf = build_pcf(run)
    path = tmp_path / "pcf.xlsx"
    result = export_pcf_xlsx(pcf, path)

    assert Path(result).exists()
    assert path.stat().st_size > 0


def test_build_pcf_with_empty_hotspots() -> None:
    run = _make_run()
    run.hotspots = []
    pcf = build_pcf(run)

    assert pcf.processes == []
    assert pcf.total_pcf == 12.5


def test_build_pcf_combines_assumptions_and_missing_data() -> None:
    run = _make_run()
    model = ProductModel(
        product_name="Demo",
        assumptions=["Model-level assumption."],
        missing_data=["Model-level missing data."],
    )
    pcf = build_pcf(run, model)

    assert "Process mapping used fuzzy matching." in pcf.assumptions
    assert "Model-level assumption." in pcf.assumptions
    assert "No supplier-specific electricity data." in pcf.missing_data
    assert "Model-level missing data." in pcf.missing_data
