from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from openlca_agent.models import BomItem, Descriptor, Hotspot, ImpactResult, ProcessCandidate, ProductModel

DEFAULT_DATA_DIR = Path(r"C:\Users\11587\openLCA-data-1.4")
GENERATED_CATEGORY = "AI generated/BOM auto-model"


class OlcaGateway:
    def __init__(self, port: int = 8080, data_dir: str | Path | None = None) -> None:
        self.port = port
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from olca_ipc import Client

            self._client = Client(self.port)
        return self._client

    def health_check(self) -> dict[str, Any]:
        processes = self.search_processes("", limit=1)
        product_systems = self.search_product_systems(limit=1)
        impact_methods = self.list_impact_methods(limit=1)
        return {
            "ipc_reachable": True,
            "database_open": bool(processes or product_systems or impact_methods),
            "process_descriptor_count_sample": len(processes),
            "product_system_descriptor_count_sample": len(product_systems),
            "impact_method_descriptor_count_sample": len(impact_methods),
            "data_dir": str(self.data_dir),
            "databases": self.list_databases(self.data_dir),
            "note": "IPC operations apply to the database currently opened in openLCA Desktop.",
        }

    def list_databases(self, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
        root = Path(data_dir) if data_dir else self.data_dir
        manifest = root / "databases.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return data.get("localDatabases", [])
        databases = root / "databases"
        if not databases.exists():
            return []
        return [{"name": child.name} for child in databases.iterdir() if child.is_dir()]

    def search_processes(self, query: str, limit: int = 10) -> list[Descriptor]:
        from olca_schema import Process

        return self._search_descriptors(Process, query=query, limit=limit, model_type="PROCESS")

    def search_processes_enhanced(
        self, item: BomItem, limit: int = 30
    ) -> list[ProcessCandidate]:
        """Multi-strategy search for a BOM item.

        Uses ``search_strategies()`` to generate several search queries from
        the item's material, name, and supplier fields, then merges and
        deduplicates the results.  Returns ``ProcessCandidate`` objects with
        ``category_path`` set for Claude's semantic analysis.
        """
        from openlca_agent.mapping import search_strategies

        strategies = search_strategies(item)
        seen_ids: set[str] = set()
        results: list[ProcessCandidate] = []

        for query in strategies:
            descriptors = self.search_processes(query=query, limit=limit)
            for d in descriptors:
                if not d.id or d.id in seen_ids:
                    continue
                seen_ids.add(d.id)
                results.append(
                    ProcessCandidate(
                        id=d.id,
                        name=d.name,
                        category=d.category,
                        category_path=d.category,
                        location=d.location,
                        model_type="PROCESS",
                        score=0.0,
                    )
                )
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        return results[:limit]

    def search_product_systems(self, query: str | None = None, limit: int = 10) -> list[Descriptor]:
        from olca_schema import ProductSystem

        return self._search_descriptors(
            ProductSystem,
            query=query or "",
            limit=limit,
            model_type="PRODUCT_SYSTEM",
        )

    def list_impact_methods(self, query: str | None = None, limit: int = 20) -> list[Descriptor]:
        from olca_schema import ImpactMethod

        return self._search_descriptors(
            ImpactMethod,
            query=query or "",
            limit=limit,
            model_type="IMPACT_METHOD",
        )

    def calculate_lca(
        self,
        product_system_id: str,
        impact_method_id: str,
        amount: float = 1.0,
    ) -> dict[str, Any]:
        from olca_schema import CalculationSetup, ImpactMethod, ProductSystem

        product_system_ref = self.client.get_descriptor(ProductSystem, uid=product_system_id)
        impact_method_ref = self.client.get_descriptor(ImpactMethod, uid=impact_method_id)
        if product_system_ref is None:
            raise ValueError(f"Product system not found: {product_system_id}")
        if impact_method_ref is None:
            raise ValueError(f"Impact method not found: {impact_method_id}")

        result = self.client.calculate(
            CalculationSetup(
                target=product_system_ref,
                impact_method=impact_method_ref,
                amount=amount,
            )
        )
        result.wait_until_ready()
        impact_refs = result.get_impact_categories()
        total_impacts = [_impact_to_model(value) for value in result.get_total_impacts()]
        hotspots = _extract_hotspots(result, impact_refs, total_impacts)
        try:
            result.dispose()
        except Exception:
            pass
        return {
            "run_handle": None,
            "product_system": _ref_to_dict(product_system_ref),
            "impact_method": _ref_to_dict(impact_method_ref),
            "total_impacts": total_impacts,
            "hotspots": hotspots,
        }

    def hotspot_analysis(
        self,
        run_id: str,
        impact_category: str | None = None,
        dimension: str = "process",
        limit: int = 10,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "impact_category": impact_category,
            "dimension": dimension,
            "limit": limit,
            "hotspots": [],
            "hotspot_detail_unavailable": True,
            "message": (
                "Detailed contribution analysis requires a live openLCA result handle. "
                "This MVP stores total impacts and marks hotspot detail unavailable when "
                "the result object cannot be queried further."
            ),
        }

    def create_product_system_from_model(
        self,
        product_model: ProductModel,
        allow_partial_model: bool = False,
    ) -> dict[str, str]:
        if product_model.unresolved_items and not allow_partial_model:
            raise ValueError("Product model contains unresolved BOM items.")

        from olca_schema import (
            Exchange,
            Flow,
            FlowProperty,
            FlowPropertyFactor,
            FlowPropertyType,
            FlowType,
            LinkingConfig,
            Process,
            ProcessType,
            ProviderLinking,
            Ref,
            RefType,
            Unit,
            UnitGroup,
        )

        suffix = uuid.uuid4().hex[:8]
        flow_property = FlowProperty(
            id=str(uuid.uuid4()),
            name=f"AI item count {suffix}",
            category=GENERATED_CATEGORY,
            flow_property_type=FlowPropertyType.PHYSICAL_QUANTITY,
        )
        unit_group = UnitGroup(
            id=str(uuid.uuid4()),
            name=f"AI unit group {suffix}",
            category=GENERATED_CATEGORY,
            default_flow_property=flow_property.to_ref(),
            units=[Unit(id=str(uuid.uuid4()), name="piece", conversion_factor=1, is_ref_unit=True)],
        )
        flow_property.unit_group = unit_group.to_ref()
        product_flow = Flow(
            id=str(uuid.uuid4()),
            name=f"AI_PRODUCT_{product_model.product_name}_{suffix}",
            category=GENERATED_CATEGORY,
            flow_type=FlowType.PRODUCT_FLOW,
            flow_properties=[
                FlowPropertyFactor(
                    conversion_factor=1,
                    flow_property=flow_property.to_ref(),
                    is_ref_flow_property=True,
                )
            ],
        )

        reference_exchange = Exchange(
            internal_id=1,
            flow=product_flow.to_ref(),
            amount=1,
            is_input=False,
            is_quantitative_reference=True,
        )
        exchanges = [reference_exchange]
        for index, decision in enumerate(product_model.mapping_decisions, start=2):
            if decision.selected_candidate is None:
                continue
            provider_process = self.client.get(Process, uid=decision.selected_candidate.id)
            provider_ref = (
                provider_process.to_ref()
                if provider_process is not None
                else Ref(
                    id=decision.selected_candidate.id,
                    name=decision.selected_candidate.name,
                    ref_type=RefType.Process,
                )
            )
            reference_exchange = _reference_exchange(provider_process)
            input_flow = (
                reference_exchange.flow
                if reference_exchange is not None and reference_exchange.flow is not None
                else Ref(name=decision.selected_candidate.name, ref_type=RefType.Flow)
            )
            exchanges.append(
                Exchange(
                    internal_id=index,
                    flow=input_flow,
                    amount=decision.item.quantity,
                    unit=(
                        reference_exchange.unit
                        if reference_exchange
                        else Ref(name=decision.item.unit)
                    ),
                    flow_property=reference_exchange.flow_property if reference_exchange else None,
                    is_input=True,
                    default_provider=provider_ref,
                )
            )

        process = Process(
            id=str(uuid.uuid4()),
            name=product_flow.name,
            category=GENERATED_CATEGORY,
            process_type=ProcessType.UNIT_PROCESS,
            exchanges=exchanges,
            description="Generated by openLCA-Agent MVP. Review before external use.",
        )
        self.client.put(unit_group)
        self.client.put(flow_property)
        self.client.put(product_flow)
        process_ref = self.client.put(process)
        system_ref = self.client.create_product_system(
            process_ref or process.to_ref(),
            LinkingConfig(
                provider_linking=ProviderLinking.PREFER_DEFAULTS,
                prefer_unit_processes=True,
            ),
        )
        if system_ref is None:
            raise RuntimeError("openLCA did not return a product system reference.")
        return categorize_product_system(self.client, system_ref)

    def _search_descriptors(
        self,
        model_type_cls,
        query: str,
        limit: int,
        model_type: str,
    ) -> list[Descriptor]:
        descriptors = self.client.get_descriptors(model_type_cls)
        normalized_query = query.lower().strip()
        items = [_descriptor_to_model(ref, model_type=model_type) for ref in descriptors]
        if normalized_query:
            items = [
                item
                for item in items
                if normalized_query in item.name.lower()
                or normalized_query in (item.category or "").lower()
            ]
        return items[:limit]


def _descriptor_to_model(ref, model_type: str | None = None) -> Descriptor:
    return Descriptor(
        id=str(getattr(ref, "id", "") or ""),
        name=str(getattr(ref, "name", "") or ""),
        category=getattr(ref, "category", None),
        location=getattr(ref, "location", None),
        model_type=model_type,
    )


def _ref_to_dict(ref) -> dict[str, Any]:
    return {
        "id": str(getattr(ref, "id", "") or ""),
        "name": str(getattr(ref, "name", "") or ""),
        "category": getattr(ref, "category", None),
        "location": getattr(ref, "location", None),
    }


def categorize_product_system(
    client,
    product_system_ref,
    category: str = GENERATED_CATEGORY,
) -> dict[str, Any]:
    from olca_schema import ProductSystem

    product_system = client.get(ProductSystem, uid=getattr(product_system_ref, "id", None))
    if product_system is not None:
        product_system.category = category
        client.put(product_system)
        return _ref_to_dict(product_system)
    product_system_ref.category = category
    return _ref_to_dict(product_system_ref)


def _impact_to_model(value) -> ImpactResult:
    category = getattr(value, "impact_category", None)
    amount = getattr(value, "amount", None)
    category_name = getattr(category, "name", "") or getattr(category, "id", "") or "unknown"
    return ImpactResult(
        impact_category=str(category_name),
        value=float(amount or 0.0),
        unit=getattr(category, "ref_unit", None),
    )


def _extract_hotspots(
    result,
    impact_refs: list[Any],
    total_impacts: list[ImpactResult],
) -> list[Hotspot]:
    if not impact_refs:
        return []
    impact_ref = impact_refs[0]
    total = total_impacts[0].value if total_impacts else 0.0
    unit = total_impacts[0].unit if total_impacts else None
    try:
        contributions = result.get_impact_contributions_of(impact_ref)
    except Exception:
        return []
    hotspots = [
        tech_flow_value_to_hotspot(contribution, total=total, unit=unit)
        for contribution in contributions
    ]
    hotspots.sort(key=lambda item: abs(item.value), reverse=True)
    return [hotspot for hotspot in hotspots if hotspot.value != 0][:10]


def tech_flow_value_to_hotspot(
    contribution: Any,
    total: float,
    unit: str | None = "kg CO2 eq",
) -> Hotspot:
    amount = float(getattr(contribution, "amount", None) or 0.0)
    tech_flow = getattr(contribution, "tech_flow", None)
    provider = getattr(tech_flow, "provider", None)
    flow = getattr(tech_flow, "flow", None)
    name = getattr(provider, "name", None) or getattr(flow, "name", None) or "unknown"
    share = amount / total if total else None
    return Hotspot(
        name=str(name),
        value=amount,
        unit=unit,
        contribution=share,
        dimension="process",
    )


def _reference_exchange(process) -> Any | None:
    if process is None or not getattr(process, "exchanges", None):
        return None
    for exchange in process.exchanges:
        if getattr(exchange, "is_quantitative_reference", False):
            return exchange
    for exchange in process.exchanges:
        if not getattr(exchange, "is_input", True):
            return exchange
    return None
