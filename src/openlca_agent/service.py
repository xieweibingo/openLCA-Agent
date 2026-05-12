from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from openlca_agent.bom import ingest_bom
from openlca_agent.gateway import OlcaGateway
from openlca_agent.mapping import CONFIDENCE_THRESHOLD, map_bom_item_to_processes
from openlca_agent.models import (
    BomItem,
    CalculationRun,
    Descriptor,
    ProcessCandidate,
    ProductModel,
)
from openlca_agent.reporting import export_result as export_run_result
from openlca_agent.reporting import generate_compliance_report as render_compliance_report
from openlca_agent.responses import error, guarded
from openlca_agent.storage import RunStore


class OpenLcaAgentService:
    def __init__(
        self,
        gateway: Any | None = None,
        output_root: str | Path = "outputs",
    ) -> None:
        self.gateway = gateway or OlcaGateway()
        self.store = RunStore(output_root)

    def health_check(self, port: int = 8080, data_dir: str | None = None) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            if port != getattr(self.gateway, "port", port) or data_dir:
                gateway = OlcaGateway(port=port, data_dir=data_dir)
                return gateway.health_check()
            return self.gateway.health_check()

        return guarded(action)

    def list_databases(self, data_dir: str | None = None) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            path = Path(data_dir) if data_dir else None
            return {"databases": self.gateway.list_databases(path)}

        return guarded(action)

    def search_process(
        self,
        query: str,
        geography: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            descriptors = self.gateway.search_processes(query=query, limit=max(limit * 3, limit))
            candidates = [_candidate_from_descriptor(item) for item in descriptors]
            if geography:
                candidates.sort(key=lambda item: item.location == geography, reverse=True)
            return {"processes": candidates[:limit]}

        return guarded(action)

    def search_product_system(self, query: str | None = None, limit: int = 10) -> dict[str, Any]:
        return guarded(
            lambda: {"product_systems": self.gateway.search_product_systems(query, limit)}
        )

    def list_impact_methods(self, query: str | None = None, limit: int = 20) -> dict[str, Any]:
        return guarded(lambda: {"impact_methods": self.gateway.list_impact_methods(query, limit)})

    def calculate_lca(
        self,
        product_system_id: str,
        impact_method_id: str,
        amount: float = 1.0,
    ) -> dict[str, Any]:
        def action() -> CalculationRun:
            raw = self.gateway.calculate_lca(product_system_id, impact_method_id, amount)
            run = CalculationRun(
                run_id=_new_run_id(),
                product_system=raw["product_system"],
                impact_method=raw["impact_method"],
                total_impacts=raw["total_impacts"],
                hotspots=raw.get("hotspots", []),
                assumptions=["Calculation executed through openLCA IPC."],
                run_handle=raw.get("run_handle"),
            )
            self.store.save_run(run)
            return run

        return guarded(action)

    def get_impact_results(self, run_id: str) -> dict[str, Any]:
        return guarded(lambda: self.store.load_run(run_id))

    def hotspot_analysis(
        self,
        run_id: str,
        impact_category: str | None = None,
        dimension: str = "process",
        limit: int = 10,
    ) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            run = self.store.load_run(run_id)
            detail = self.gateway.hotspot_analysis(run_id, impact_category, dimension, limit)
            run.hotspots = detail.get("hotspots", run.hotspots)
            if detail.get("hotspot_detail_unavailable"):
                run.missing_data.append("hotspot_detail_unavailable")
            self.store.save_run(run)
            return {"run": run, "hotspot_detail": detail}

        return guarded(action)

    def export_result(self, run_id: str, formats: list[str] | None = None) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            run = self.store.load_run(run_id)
            files = export_run_result(run, self.store.run_dir(run_id), formats or ["xlsx"])
            run.files.update(files)
            self.store.save_run(run)
            return {"run_id": run_id, "files": files}

        return guarded(action)

    def ingest_bom(
        self,
        source_path: str | None = None,
        inline_text: str | None = None,
    ) -> dict[str, Any]:
        return guarded(
            lambda: {"items": ingest_bom(source_path=source_path, inline_text=inline_text)}
        )

    def draft_product_model(
        self,
        product_name: str,
        description: str | None = None,
        bom_items: list[dict[str, Any]] | list[BomItem] | None = None,
    ) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            items = _items_from_input(description=description, bom_items=bom_items)
            decisions = []
            unresolved = []
            missing_data = []
            for item in items:
                descriptors = self.gateway.search_processes(item.material, limit=10)
                candidates = [_candidate_from_descriptor(descriptor) for descriptor in descriptors]
                decision = map_bom_item_to_processes(
                    item,
                    candidates,
                    threshold=CONFIDENCE_THRESHOLD,
                )
                decisions.append(decision)
                if decision.selected_candidate is None:
                    unresolved.append(item)
                    missing_data.append(
                        f"No confident process mapping for {item.name} / {item.material}."
                    )
            model = ProductModel(
                product_name=product_name,
                items=items,
                mapping_decisions=decisions,
                unresolved_items=unresolved,
                assumptions=[
                    "Process mapping used local explainable rules: token similarity "
                    "plus geography priority.",
                    "Geography priority is CN > GLO > RoW > RER.",
                ],
                missing_data=missing_data,
            )
            return {"product_model": model}

        return guarded(action)

    def create_product_system_from_model(
        self,
        product_model: dict[str, Any] | ProductModel,
        allow_partial_model: bool = False,
    ) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            model = ProductModel.model_validate(product_model)
            if model.unresolved_items and not allow_partial_model:
                return error(
                    "UNRESOLVED_MODEL_ITEMS",
                    "Product model contains unresolved BOM items.",
                    "Review process mapping candidates or call with allow_partial_model=True.",
                    {"unresolved_items": model.unresolved_items},
                )
            product_system = self.gateway.create_product_system_from_model(
                model,
                allow_partial_model,
            )
            return {"product_system": product_system, "product_model": model}

        return guarded(action)

    def generate_compliance_report(
        self,
        run_id: str,
        standards: list[str] | None = None,
    ) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            run = self.store.load_run(run_id)
            product_model = run.product_model or self.store.load_product_model(run_id)
            report = render_compliance_report(
                run,
                product_model,
                self.store.run_dir(run_id),
                standards=standards,
            )
            run.files.update(report.files)
            self.store.save_run(run)
            return {"report": report, "run": run}

        return guarded(action)

    def assess_product(
        self,
        product_name: str,
        impact_method_id: str,
        source_path: str | None = None,
        inline_bom_text: str | None = None,
        description: str | None = None,
        allow_partial_model: bool = False,
        standards: list[str] | None = None,
    ) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            items = ingest_bom(source_path=source_path, inline_text=inline_bom_text) if (
                source_path or inline_bom_text
            ) else None
            model_response = self.draft_product_model(
                product_name=product_name,
                description=description,
                bom_items=items,
            )
            if not model_response["ok"]:
                return model_response
            model = ProductModel.model_validate(model_response["data"]["product_model"])
            create_response = self.create_product_system_from_model(model, allow_partial_model)
            if not create_response["ok"]:
                return create_response
            product_system = create_response["data"]["product_system"]
            raw = self.gateway.calculate_lca(product_system["id"], impact_method_id, amount=1.0)
            run = CalculationRun(
                run_id=_new_run_id(),
                product_system=raw["product_system"],
                impact_method=raw["impact_method"],
                total_impacts=raw["total_impacts"],
                hotspots=raw.get("hotspots", []),
                product_model=model,
                assumptions=["End-to-end assessment generated by openLCA-Agent MVP."],
                missing_data=model.missing_data,
            )
            self.store.save_run(run)
            self.store.save_product_model(run.run_id, model)
            report = render_compliance_report(
                run,
                model,
                self.store.run_dir(run.run_id),
                standards=standards,
            )
            run.files.update(report.files)
            self.store.save_run(run)
            return {"run": run, "report": report}

        return guarded(action)


def _candidate_from_descriptor(descriptor: Descriptor) -> ProcessCandidate:
    return ProcessCandidate(
        id=descriptor.id,
        name=descriptor.name,
        category=descriptor.category,
        location=descriptor.location,
        score=0.0,
    )


def _items_from_input(
    description: str | None,
    bom_items: list[dict[str, Any]] | list[BomItem] | None,
) -> list[BomItem]:
    if bom_items:
        return [
            item if isinstance(item, BomItem) else BomItem.model_validate(item)
            for item in bom_items
        ]
    if not description:
        raise ValueError("Provide description or bom_items for product model drafting.")
    return _items_from_description(description)


def _items_from_description(description: str) -> list[BomItem]:
    items = []
    for index, segment in enumerate(description.replace("\n", ";").split(";"), start=1):
        text = segment.strip()
        if not text:
            continue
        material = text
        quantity = 1.0
        unit = "piece"
        items.append(
            BomItem(
                name=f"described item {index}",
                material=material,
                quantity=quantity,
                unit=unit,
                notes="Parsed from natural language description; quantity and unit require review.",
            )
        )
    if not items:
        raise ValueError("Could not extract any product items from description.")
    return items


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"
