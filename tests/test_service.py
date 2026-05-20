from pathlib import Path

from openlca_agent.models import Descriptor, ImpactResult
from openlca_agent.service import OpenLcaAgentService


class FakeGateway:
    def __init__(self) -> None:
        self.created_models = []

    def health_check(self) -> dict:
        return {"ipc_reachable": True, "database_open": True}

    def list_databases(self, data_dir: Path | None = None) -> list[dict]:
        return [{"name": "elcd_bottles_20220715"}]

    def search_processes(self, query: str, limit: int = 10) -> list[Descriptor]:
        if "unknown" in query:
            return [Descriptor(id="p3", name="market for glass bottle", location="GLO")]
        return [
            Descriptor(id="p1", name=f"{query} production", location="CN", category="materials"),
            Descriptor(
                id="p2",
                name="unrelated glass bottle",
                location="GLO",
                category="materials",
            ),
        ][:limit]

    def search_product_systems(self, query: str | None = None, limit: int = 10) -> list[Descriptor]:
        return [Descriptor(id="ps1", name="Bottle system")][:limit]

    def list_impact_methods(self, query: str | None = None, limit: int = 20) -> list[Descriptor]:
        return [Descriptor(id="m1", name="EF 3.1")][:limit]

    def calculate_lca(self, product_system_id: str, impact_method_id: str, amount: float = 1.0):
        return {
            "run_handle": "handle-1",
            "product_system": {"id": product_system_id, "name": "Bottle system"},
            "impact_method": {"id": impact_method_id, "name": "EF 3.1"},
            "total_impacts": [
                ImpactResult(
                    impact_category="Climate change",
                    value=amount,
                    unit="kg CO2 eq",
                )
            ],
        }

    def create_product_system_from_model(self, product_model, allow_partial_model=False):
        self.created_models.append(product_model)
        return {"id": "ps-created", "name": f"AI_PRODUCT_{product_model.product_name}"}


def test_health_check_returns_structured_ok_response(tmp_path: Path) -> None:
    service = OpenLcaAgentService(gateway=FakeGateway(), output_root=tmp_path)

    response = service.health_check()

    assert response["ok"] is True
    assert response["data"]["ipc_reachable"] is True


def test_assess_product_from_inline_bom_generates_report_files(tmp_path: Path) -> None:
    service = OpenLcaAgentService(gateway=FakeGateway(), output_root=tmp_path)

    response = service.assess_product(
        product_name="Demo bottle",
        impact_method_id="m1",
        inline_bom_text="name,material,quantity,unit,location\nOuter box,kraft paper,1,kg,CN\n",
    )

    assert response["ok"] is True
    run = response["data"]["run"]
    assert Path(run["files"]["markdown"]).exists()
    assert Path(run["files"]["xlsx"]).exists()
    assert Path(run["files"]["pcf_json"]).exists()
    assert Path(run["files"]["pcf_xlsx"]).exists()


def test_create_product_system_blocks_unresolved_items_by_default(tmp_path: Path) -> None:
    service = OpenLcaAgentService(gateway=FakeGateway(), output_root=tmp_path)
    model_response = service.draft_product_model(
        product_name="Demo",
        bom_items=[
            {
                "name": "Sensor",
                "material": "unknown composite",
                "quantity": 1,
                "unit": "piece",
            }
        ],
    )

    response = service.create_product_system_from_model(model_response["data"]["product_model"])

    assert response["ok"] is False
    assert response["error_code"] == "UNRESOLVED_MODEL_ITEMS"


def test_gateway_errors_return_remediation(tmp_path: Path) -> None:
    class BrokenGateway(FakeGateway):
        def health_check(self) -> dict:
            raise ConnectionError("connection refused")

    service = OpenLcaAgentService(gateway=BrokenGateway(), output_root=tmp_path)

    response = service.health_check()

    assert response["ok"] is False
    assert response["error_code"] == "OPENLCA_IPC_UNAVAILABLE"
    assert "Start openLCA" in response["remediation"]
