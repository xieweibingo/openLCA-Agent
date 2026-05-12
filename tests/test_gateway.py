from pathlib import Path
from types import SimpleNamespace

from openlca_agent.gateway import OlcaGateway, tech_flow_value_to_hotspot


def test_list_databases_reads_openlca_manifest(tmp_path: Path) -> None:
    (tmp_path / "databases.json").write_text(
        '{"localDatabases":[{"name":"tiangong_v020"},{"name":"EF3.1"}],"remoteDatabases":[]}',
        encoding="utf-8",
    )

    databases = OlcaGateway(data_dir=tmp_path).list_databases()

    assert [item["name"] for item in databases] == ["tiangong_v020", "EF3.1"]


def test_tech_flow_value_to_hotspot_uses_provider_name_and_total_share() -> None:
    contribution = SimpleNamespace(
        amount=0.5,
        tech_flow=SimpleNamespace(
            provider=SimpleNamespace(name="Electricity grid mix"),
            flow=SimpleNamespace(name="Electricity"),
        ),
    )

    hotspot = tech_flow_value_to_hotspot(contribution, total=1.0)

    assert hotspot.name == "Electricity grid mix"
    assert hotspot.value == 0.5
    assert hotspot.unit == "kg CO2 eq"
    assert hotspot.contribution == 0.5
