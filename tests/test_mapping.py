from openlca_agent.mapping import map_bom_item_to_processes
from openlca_agent.models import BomItem, ProcessCandidate


def test_mapping_prefers_geography_then_name_score() -> None:
    item = BomItem(name="Outer box", material="kraft paper", quantity=1, unit="kg", location="CN")
    candidates = [
        ProcessCandidate(id="row", name="kraft paper production", location="RoW", score=0.0),
        ProcessCandidate(id="cn", name="kraft paper production", location="CN", score=0.0),
        ProcessCandidate(id="film", name="packaging film production", location="CN", score=0.0),
    ]

    decision = map_bom_item_to_processes(item, candidates)

    assert decision.selected_candidate is not None
    assert decision.selected_candidate.id == "cn"
    assert decision.confidence >= 0.70
    assert "geography" in decision.reason


def test_mapping_marks_low_confidence_items_unresolved() -> None:
    item = BomItem(name="Sensor", material="unknown composite", quantity=1, unit="piece")
    candidates = [
        ProcessCandidate(id="glass", name="market for glass bottle", location="GLO", score=0.0),
    ]

    decision = map_bom_item_to_processes(item, candidates)

    assert decision.selected_candidate is None
    assert decision.confidence < 0.70
    assert decision.unresolved_reason
