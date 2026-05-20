from __future__ import annotations

from openlca_agent.dqi import _completeness, _geo_score, _tech_similarity, compute_dqi
from openlca_agent.mapping import compute_dqi_for_candidate, map_bom_item_to_processes
from openlca_agent.models import (
    BomItem,
    DqiScore,
    MappingDecision,
    ProcessCandidate,
    ProductModel,
)
from openlca_agent.pcf import _build_dqi_lookup, build_pcf
from openlca_agent.service import OpenLcaAgentService


def _make_item(material: str = "HDPE", location: str = "CN") -> BomItem:
    return BomItem(name="Test item", material=material, quantity=1.0, unit="kg", location=location)


def _make_candidate(
    name: str = "HDPE production",
    location: str = "CN",
    category: str = "Plastics/HDPE",
    pid: str = "p-001",
) -> ProcessCandidate:
    return ProcessCandidate(id=pid, name=name, category=category, location=location)


# ─── DQI computation unit tests ────────────────────────────────────────────


def test_geo_score_exact_match() -> None:
    item = _make_item(location="CN")
    candidate = _make_candidate(location="CN")
    assert _geo_score(item, candidate) == 100.0


def test_geo_score_global() -> None:
    item = _make_item(location="CN")
    candidate = _make_candidate(location="GLO")
    assert _geo_score(item, candidate) == 50.0


def test_geo_score_row() -> None:
    item = _make_item(location="CN")
    candidate = _make_candidate(location="RoW")
    assert _geo_score(item, candidate) == 40.0


def test_geo_score_missing() -> None:
    item = _make_item(location="CN")
    candidate = _make_candidate(location="")
    assert _geo_score(item, candidate) == 20.0


def test_geo_score_different_region() -> None:
    item = _make_item(location="CN")
    candidate = _make_candidate(location="DE")
    assert _geo_score(item, candidate) == 60.0


def test_tech_similarity_uses_material_and_name() -> None:
    item = _make_item(material="HDPE")
    candidate = _make_candidate(name="HDPE production", category="Plastics")
    score = _tech_similarity(item, candidate)
    assert score > 40.0


def test_tech_similarity_boosts_on_category_match() -> None:
    item = _make_item(material="hdpe")
    candidate = _make_candidate(name="Something else", category="HDPE granulate")
    score = _tech_similarity(item, candidate)
    assert score >= 10.0  # category boost applied


def test_completeness_full() -> None:
    candidate = _make_candidate()
    assert _completeness(candidate) == 100.0


def test_completeness_partial() -> None:
    candidate = ProcessCandidate(id="p1", name="Only name", category=None, location=None)
    assert _completeness(candidate) == 50.0


def test_completeness_minimal() -> None:
    candidate = ProcessCandidate(id="", name="", category=None, location=None)
    assert _completeness(candidate) == 0.0


def test_compute_dqi_returns_structured_scores() -> None:
    dqi = compute_dqi(_make_item(), _make_candidate())
    assert 0 <= dqi.overall <= 100
    assert 0 <= dqi.geographical <= 100
    assert 0 <= dqi.technological <= 100
    assert dqi.temporal == 50.0
    assert 0 <= dqi.completeness <= 100
    assert dqi.confidence_band in ("high", "medium", "low")
    assert len(dqi.flags) >= 1  # temporal flag always present


def test_compute_dqi_high_band() -> None:
    # Use matching names to get high tech similarity
    item = BomItem(name="HDPE", material="HDPE", quantity=1.0, unit="kg", location="CN")
    candidate = _make_candidate(name="HDPE production", location="CN", category="HDPE")
    dqi = compute_dqi(item, candidate)
    assert dqi.confidence_band in ("high", "medium")


def test_compute_dqi_temporal_flag() -> None:
    dqi = compute_dqi(_make_item(), _make_candidate())
    assert any("temporal" in f for f in dqi.flags)


# ─── Mapping integration tests ──────────────────────────────────────────────


def test_mapping_decision_includes_dqi() -> None:
    item = BomItem(name="HDPE", material="HDPE", quantity=1.0, unit="kg", location="CN")
    candidate = _make_candidate(name="HDPE", location="CN", category="Plastics")
    decision = map_bom_item_to_processes(item, [candidate], threshold=0.65)
    assert decision.dqi is not None
    assert decision.dqi.overall > 0
    assert decision.confidence >= 0.65


def test_unresolved_mapping_has_no_dqi() -> None:
    item = _make_item(material="Unknown composite")
    unknown = _make_candidate(name="Unrelated glass", location="GLO", category="Glass")
    decision = map_bom_item_to_processes(item, [unknown])
    assert decision.selected_candidate is None
    assert decision.dqi is None


# ─── PCF integration tests ──────────────────────────────────────────────────


def test_build_dqi_lookup_maps_process_names() -> None:
    item = BomItem(name="HDPE", material="HDPE", quantity=1.0, unit="kg", location="CN")
    candidate = _make_candidate(name="HDPE production", location="CN", category="HDPE")
    candidate.dqi = compute_dqi(item, candidate)
    decision = MappingDecision(
        item=item,
        selected_candidate=candidate,
        confidence=0.95,
        reason="test",
        dqi=candidate.dqi,
    )
    model = ProductModel(product_name="Demo", mapping_decisions=[decision])
    lookup = _build_dqi_lookup(model)
    assert "HDPE production" in lookup
    assert lookup["HDPE production"][1] in ("high", "medium")


def test_pcf_processes_have_dqi() -> None:
    from openlca_agent.models import CalculationRun, Hotspot, ImpactResult, RunStage

    item = BomItem(name="HDPE", material="HDPE", quantity=1.0, unit="kg", location="CN")
    candidate = _make_candidate(name="HDPE production", location="CN", category="Plastics")
    candidate.dqi = compute_dqi(item, candidate)
    model = ProductModel(
        product_name="Demo",
        mapping_decisions=[
            MappingDecision(
                item=item,
                selected_candidate=candidate,
                confidence=0.95,
                reason="test",
                dqi=candidate.dqi,
            )
        ],
    )
    run = CalculationRun(
        run_id="test",
        product_system={"id": "ps-1", "name": "Demo"},
        impact_method={"id": "ef31", "name": "EF 3.1"},
        total_impacts=[ImpactResult(impact_category="Climate change", value=10.0, unit="kg CO2 eq")],
        hotspots=[Hotspot(name="HDPE production", value=8.0, unit="kg CO2 eq", contribution=0.8)],
        stage=RunStage.CALCULATED,
    )
    pcf = build_pcf(run, model)
    assert len(pcf.processes) == 1
    assert pcf.processes[0].dqi_overall is not None
    assert pcf.processes[0].dqi_confidence_band in ("high", "medium")


def test_pcf_no_model_no_dqi() -> None:
    from openlca_agent.models import CalculationRun, Hotspot, ImpactResult, RunStage

    run = CalculationRun(
        run_id="test",
        product_system={"id": "ps-1", "name": "Demo"},
        impact_method={"id": "ef31", "name": "EF 3.1"},
        total_impacts=[ImpactResult(impact_category="Climate change", value=10.0, unit="kg CO2 eq")],
        hotspots=[Hotspot(name="Some process", value=5.0, unit="kg CO2 eq", contribution=0.5)],
        stage=RunStage.CALCULATED,
    )
    pcf = build_pcf(run)
    assert pcf.processes[0].dqi_overall is None
    assert pcf.processes[0].dqi_confidence_band is None
