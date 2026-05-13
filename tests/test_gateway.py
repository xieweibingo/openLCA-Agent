from pathlib import Path
from types import SimpleNamespace

from openlca_agent.gateway import (
    GENERATED_CATEGORY,
    OlcaGateway,
    categorize_product_system,
    tech_flow_value_to_hotspot,
)


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


def test_categorize_product_system_updates_created_system_ref() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.product_system = SimpleNamespace(id="ps1", name="AI_PRODUCT_demo", category=None)
            self.put_calls = []

        def get(self, model_type, uid: str):
            assert uid == "ps1"
            return self.product_system

        def put(self, model) -> None:
            self.put_calls.append(model)

    ref = SimpleNamespace(id="ps1", name="AI_PRODUCT_demo", category=None)
    client = FakeClient()

    categorized = categorize_product_system(client, ref)

    assert client.product_system.category == GENERATED_CATEGORY
    assert categorized["category"] == GENERATED_CATEGORY
    assert client.put_calls == [client.product_system]
