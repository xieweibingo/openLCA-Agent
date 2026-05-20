from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from openlca_agent.bom import ingest_bom as _ingest_bom
from openlca_agent.gateway import OlcaGateway
from openlca_agent.mapping import (
    CONFIDENCE_THRESHOLD,
    compute_dqi_for_candidate,
    map_bom_item_to_processes,
)
from openlca_agent.models import (
    BomItem,
    CalculationRun,
    Descriptor,
    MappingDecision,
    ProcessCandidate,
    ProductModel,
    RunStage,
)
from openlca_agent.pcf import build_pcf, export_pcf_json, export_pcf_xlsx
from openlca_agent.reporting import export_result as export_run_result
from openlca_agent.reporting import generate_compliance_report as render_compliance_report
from openlca_agent.responses import error, guarded, normalize_exception, ok
from openlca_agent.storage import RunStore


class OpenLcaAgentService:
    def __init__(
        self,
        gateway: Any | None = None,
        output_root: str | Path = "outputs",
    ) -> None:
        self.gateway = gateway or OlcaGateway()
        self.store = RunStore(output_root)

    # ------------------------------------------------------------------
    # Existing standalone tools (backward-compatible)
    # ------------------------------------------------------------------

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
            descriptors = self.gateway.search_processes(
                query=query, limit=max(limit * 3, limit)
            )
            candidates = [_candidate_from_descriptor(item) for item in descriptors]
            if geography:
                candidates.sort(
                    key=lambda item: item.location == geography, reverse=True
                )
            return {"processes": candidates[:limit]}

        return guarded(action)

    def search_product_system(
        self, query: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        return guarded(
            lambda: {
                "product_systems": self.gateway.search_product_systems(query, limit)
            }
        )

    def list_impact_methods(
        self, query: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        return guarded(
            lambda: {"impact_methods": self.gateway.list_impact_methods(query, limit)}
        )

    def calculate_lca(
        self,
        product_system_id: str,
        impact_method_id: str,
        amount: float = 1.0,
    ) -> dict[str, Any]:
        def action() -> CalculationRun:
            raw = self.gateway.calculate_lca(
                product_system_id, impact_method_id, amount
            )
            run = CalculationRun(
                run_id=_new_run_id(),
                product_system=raw["product_system"],
                impact_method=raw["impact_method"],
                total_impacts=raw["total_impacts"],
                hotspots=raw.get("hotspots", []),
                assumptions=["Calculation executed through openLCA IPC."],
                run_handle=raw.get("run_handle"),
                stage=RunStage.CALCULATED,
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
            return {"run": run}

        return guarded(action)

    def export_result(
        self, run_id: str, formats: list[str] | None = None
    ) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            run = self.store.load_run(run_id)
            files = export_run_result(
                run, self.store.run_dir(run_id), formats or ["xlsx"]
            )
            run.files.update(files)
            self.store.save_run(run)
            return {"run_id": run_id, "files": files}

        return guarded(action)

    def export_pcf(self, run_id: str) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            run = self.store.load_run(run_id)
            product_model = run.product_model or self.store.load_product_model(run_id)
            pcf = build_pcf(run, product_model)
            run_dir = self.store.run_dir(run_id)
            json_path = export_pcf_json(pcf, run_dir / "pcf.json")
            xlsx_path = export_pcf_xlsx(pcf, run_dir / "pcf.xlsx")
            run.files["pcf_json"] = json_path
            run.files["pcf_xlsx"] = xlsx_path
            self.store.save_run(run)
            return {"pcf": pcf, "files": {"pcf_json": json_path, "pcf_xlsx": xlsx_path}}

        return guarded(action)

    def _export_pcf_files(self, run: CalculationRun) -> dict[str, str]:
        product_model = run.product_model or self.store.load_product_model(run.run_id)
        pcf = build_pcf(run, product_model)
        run_dir = self.store.run_dir(run.run_id)
        return {
            "pcf_json": export_pcf_json(pcf, run_dir / "pcf.json"),
            "pcf_xlsx": export_pcf_xlsx(pcf, run_dir / "pcf.xlsx"),
        }

    def ingest_bom(
        self,
        source_path: str | None = None,
        inline_text: str | None = None,
    ) -> dict[str, Any]:
        return guarded(
            lambda: {
                "items": _ingest_bom(
                    source_path=source_path, inline_text=inline_text
                )
            }
        )

    def draft_product_model(
        self,
        product_name: str,
        description: str | None = None,
        bom_items: list[dict[str, Any]] | list[BomItem] | None = None,
    ) -> dict[str, Any]:
        def action() -> dict[str, Any]:
            items = _items_from_input(description=description, bom_items=bom_items)
            decisions, unresolved, missing_data = self._run_mapping(items)
            model = ProductModel(
                product_name=product_name,
                items=items,
                mapping_decisions=decisions,
                unresolved_items=unresolved,
                assumptions=[
                    "Process mapping used local explainable rules: "
                    "token similarity plus geography priority.",
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
                    "Review process mapping candidates or call with "
                    "allow_partial_model=True.",
                    {"unresolved_items": model.unresolved_items},
                )
            product_system = self.gateway.create_product_system_from_model(
                model, allow_partial_model
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

    # ------------------------------------------------------------------
    # Idempotent step methods
    # ------------------------------------------------------------------

    def step_ingest_bom(
        self,
        run_id: str,
        source_path: str | None = None,
        inline_text: str | None = None,
        product_name: str | None = None,
    ) -> dict[str, Any]:
        try:
            run_path = self.store.run_path(run_id)
            if run_path.exists():
                run = self.store.load_run(run_id)
                if run.stage >= RunStage.BOM_INGESTED:
                    return ok(run)
            else:
                run = CalculationRun(
                    run_id=run_id,
                    product_system={},
                    impact_method={},
                )

            items = _ingest_bom(source_path=source_path, inline_text=inline_text)
            name = product_name or (items[0].name if items else "unnamed")
            run.product_model = ProductModel(product_name=name, items=items)
            run.stage = RunStage.BOM_INGESTED
            run.error_context = None
            self.store.save_run(run)
            return ok(run)
        except Exception as exc:
            self._try_save_error(run_id, exc)
            return normalize_exception(exc)

    def step_map_processes(self, run_id: str) -> dict[str, Any]:
        try:
            run = self.store.load_run(run_id)
            if run.stage >= RunStage.MAPPED:
                return ok(run)
            if run.stage < RunStage.BOM_INGESTED:
                return error(
                    "WRONG_STAGE",
                    "Must ingest BOM before mapping processes.",
                    'Call step_ingest_bom(run_id, ...) first.',
                )
            model = run.product_model
            if model is None:
                return error(
                    "NO_PRODUCT_MODEL",
                    "Run has no product model.",
                    'Call step_ingest_bom(run_id, ...) first.',
                )
            decisions, unresolved, missing_data = self._run_mapping(model.items)
            model.mapping_decisions = decisions
            model.unresolved_items = unresolved
            model.missing_data = missing_data
            run.stage = RunStage.MAPPED
            run.error_context = None
            run.assumptions = [
                "Process mapping used local explainable rules: "
                "token similarity plus geography priority.",
                "Geography priority is CN > GLO > RoW > RER.",
            ]
            self.store.save_run(run)
            return ok(run)
        except Exception as exc:
            self._try_save_error(run_id, exc)
            return normalize_exception(exc)

    def step_create_product_system(self, run_id: str) -> dict[str, Any]:
        try:
            run = self.store.load_run(run_id)
            if run.stage >= RunStage.PRODUCT_SYSTEM_CREATED:
                return ok(run)
            if run.stage < RunStage.MAPPED:
                return error(
                    "WRONG_STAGE",
                    "Must map processes before creating product system.",
                    'Call step_map_processes(run_id) first.',
                )
            model = run.product_model
            if model is None:
                return error(
                    "NO_PRODUCT_MODEL",
                    "Run has no product model.",
                    'Call step_ingest_bom(run_id, ...) first.',
                )
            product_system = self.gateway.create_product_system_from_model(model)
            run.product_system = product_system
            run.stage = RunStage.PRODUCT_SYSTEM_CREATED
            run.error_context = None
            self.store.save_run(run)
            return ok(run)
        except Exception as exc:
            self._try_save_error(run_id, exc)
            return normalize_exception(exc)

    def step_calculate(
        self, run_id: str, impact_method_id: str
    ) -> dict[str, Any]:
        try:
            run = self.store.load_run(run_id)
            if run.stage >= RunStage.CALCULATED:
                return ok(run)
            if run.stage < RunStage.PRODUCT_SYSTEM_CREATED:
                return error(
                    "WRONG_STAGE",
                    "Must create product system before calculating.",
                    'Call step_create_product_system(run_id) first.',
                )
            product_system_id = run.product_system.get("id")
            if not product_system_id:
                return error(
                    "NO_PRODUCT_SYSTEM",
                    "Run has no product system ID.",
                    'Call step_create_product_system(run_id) first.',
                )
            raw = self.gateway.calculate_lca(
                product_system_id, impact_method_id, amount=1.0
            )
            run.total_impacts = raw["total_impacts"]
            run.hotspots = raw.get("hotspots", [])
            run.impact_method = raw["impact_method"]
            run.stage = RunStage.CALCULATED
            run.error_context = None
            self.store.save_run(run)
            return ok(run)
        except Exception as exc:
            self._try_save_error(run_id, exc)
            return normalize_exception(exc)

    def step_export(
        self, run_id: str, formats: list[str] | None = None
    ) -> dict[str, Any]:
        try:
            run = self.store.load_run(run_id)
            if run.stage >= RunStage.RESULTS_EXPORTED:
                return ok(run)
            if run.stage < RunStage.CALCULATED:
                return error(
                    "WRONG_STAGE",
                    "Must calculate before exporting results.",
                    'Call step_calculate(run_id, impact_method_id) first.',
                )
            fmt_set = {f.lower() for f in (formats or ["xlsx"])}
            standard_formats = fmt_set - {"pcf"}
            if standard_formats:
                files = export_run_result(
                    run, self.store.run_dir(run_id), list(standard_formats)
                )
                run.files.update(files)
            if "pcf" in fmt_set:
                pcf_files = self._export_pcf_files(run)
                run.files.update(pcf_files)
            run.stage = RunStage.RESULTS_EXPORTED
            run.error_context = None
            self.store.save_run(run)
            return ok(run)
        except Exception as exc:
            self._try_save_error(run_id, exc)
            return normalize_exception(exc)

    def step_report(
        self, run_id: str, standards: list[str] | None = None
    ) -> dict[str, Any]:
        try:
            run = self.store.load_run(run_id)
            if run.stage >= RunStage.REPORTED:
                return ok(run)
            if run.stage < RunStage.CALCULATED:
                return error(
                    "WRONG_STAGE",
                    "Must calculate before generating a report.",
                    'Call step_calculate(run_id, impact_method_id) first.',
                )
            product_model = run.product_model or self.store.load_product_model(run_id)
            report = render_compliance_report(
                run,
                product_model,
                self.store.run_dir(run_id),
                standards=standards,
            )
            run.files.update(report.files)
            run.stage = RunStage.REPORTED
            run.error_context = None
            self.store.save_run(run)
            return ok(run)
        except Exception as exc:
            self._try_save_error(run_id, exc)
            return normalize_exception(exc)

    # ------------------------------------------------------------------
    # Semantic mapping tools (Phase 3 — client-side AI semantic analysis)
    # ------------------------------------------------------------------

    def search_processes_semantic(
        self,
        material: str,
        name: str | None = None,
        location: str | None = None,
        supplier: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Enhanced search using multiple strategies (synonyms, sub-terms,
        supplier) to cast a wider net. Returns candidates with
        ``category_path`` for Claude's semantic analysis."""
        try:
            item = BomItem(
                name=name or material,
                material=material,
                quantity=1.0,
                unit="piece",
                location=location,
                supplier=supplier,
            )
            candidates = self.gateway.search_processes_enhanced(item, limit=limit)
            return ok({"query": material, "candidates": candidates})
        except Exception as exc:
            return normalize_exception(exc)

    def get_bom_with_mappings(self, run_id: str) -> dict[str, Any]:
        """Return BOM items with their current mapping status for Claude
        to review before applying semantic refinements."""
        try:
            run = self.store.load_run(run_id)
            model = run.product_model
            if model is None:
                return ok({
                    "product_name": None,
                    "items": [],
                    "unresolved_count": 0,
                    "total_count": 0,
                })

            items_with_status = []
            for i, item in enumerate(model.items):
                decision = (
                    model.mapping_decisions[i]
                    if i < len(model.mapping_decisions)
                    else None
                )
                dqi = decision.dqi if decision else None
                items_with_status.append({
                    "index": i,
                    "item_name": item.name,
                    "item_material": item.material,
                    "item_location": item.location,
                    "item_supplier": item.supplier,
                    "selected_process": (
                        {
                            "id": decision.selected_candidate.id,
                            "name": decision.selected_candidate.name,
                        }
                        if decision and decision.selected_candidate
                        else None
                    ),
                    "confidence": decision.confidence if decision else 0.0,
                    "reason": decision.reason if decision else "",
                    "is_resolved": (
                        decision is not None
                        and decision.selected_candidate is not None
                    ),
                    "dqi_overall": dqi.overall if dqi else None,
                    "dqi_band": dqi.confidence_band if dqi else None,
                })

            return ok({
                "product_name": model.product_name,
                "items": items_with_status,
                "unresolved_count": len(model.unresolved_items),
                "total_count": len(model.items),
            })
        except Exception as exc:
            return normalize_exception(exc)

    def apply_item_mapping(
        self,
        run_id: str,
        item_index: int,
        process_id: str,
        process_name: str = "",
        confidence: float = 1.0,
        reason: str = "",
    ) -> dict[str, Any]:
        """Apply a semantic mapping decision for a single BOM item.

        Called by Claude after analysing candidates.  Updates the run's
        product model and advances ``stage`` to ``MAPPED``.
        """
        try:
            run = self.store.load_run(run_id)
            model = run.product_model
            if model is None:
                return error("NO_PRODUCT_MODEL", "Run has no product model.", "")
            if item_index < 0 or item_index >= len(model.items):
                return error(
                    "INVALID_ITEM_INDEX",
                    f"Item index {item_index} out of range "
                    f"(0-{len(model.items) - 1}).",
                    "",
                )

            item = model.items[item_index]
            existing_decision = (
                model.mapping_decisions[item_index]
                if item_index < len(model.mapping_decisions)
                else None
            )
            candidate = ProcessCandidate(
                id=process_id,
                name=process_name,
                score=confidence,
                reason=reason,
            )
            candidate.dqi = compute_dqi_for_candidate(item, candidate)
            mapping = MappingDecision(
                item=item,
                candidates=(existing_decision.candidates if existing_decision else []),
                selected_candidate=candidate,
                confidence=confidence,
                reason=reason,
                dqi=candidate.dqi,
            )

            if item_index < len(model.mapping_decisions):
                model.mapping_decisions[item_index] = mapping
            else:
                model.mapping_decisions.append(mapping)

            # Remove from unresolved_items if present
            for ui in list(model.unresolved_items):
                if ui.name == item.name and ui.material == item.material:
                    model.unresolved_items.remove(ui)
                    break

            model.missing_data = [
                md for md in model.missing_data
                if item.name not in md
            ]

            run.stage = RunStage.MAPPED
            run.error_context = None
            self.store.save_run(run)
            return ok({"item_index": item_index, "mapping": mapping})
        except Exception as exc:
            self._try_save_error(run_id, exc)
            return normalize_exception(exc)

    def batch_apply_mappings(
        self, run_id: str, mappings: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply multiple semantic mapping decisions in a single call.

        Each entry in *mappings* should have:
        ``item_index``, ``process_id``, and optionally ``process_name``,
        ``confidence``, ``reason``.
        """
        applied = 0
        errors: list[dict[str, Any]] = []
        for m in mappings:
            r = self.apply_item_mapping(
                run_id,
                item_index=m["item_index"],
                process_id=m["process_id"],
                process_name=m.get("process_name", ""),
                confidence=m.get("confidence", 1.0),
                reason=m.get("reason", ""),
            )
            if r.get("ok"):
                applied += 1
            else:
                errors.append({
                    "item_index": m["item_index"],
                    "error": r.get("message", "unknown"),
                })
        return ok({
            "applied_count": applied,
            "error_count": len(errors),
            "errors": errors,
        })

    def auto_map_bom(self, run_id: str) -> dict[str, Any]:
        """Fast automatic mapping using fuzzy string matching.

        This is the same logic as ``step_map_processes`` — useful as a
        baseline before Claude refines low-confidence mappings.
        """
        return self.step_map_processes(run_id)

    def review_mappings(self, run_id: str) -> dict[str, Any]:
        """Return a review-friendly summary of all mapping decisions.

        Highlights unresolved items and low-confidence mappings that need
        Claude's semantic analysis.
        """
        try:
            run = self.store.load_run(run_id)
            model = run.product_model
            if model is None:
                return ok({
                    "mappings": [],
                    "unresolved": [],
                    "total": 0,
                    "resolved": 0,
                    "low_confidence": 0,
                })

            items = []
            for i, item in enumerate(model.items):
                decision = (
                    model.mapping_decisions[i]
                    if i < len(model.mapping_decisions)
                    else None
                )
                selected = decision.selected_candidate if decision else None
                dqi = decision.dqi if decision else None
                items.append({
                    "index": i,
                    "item_name": item.name,
                    "item_material": item.material,
                    "selected_process": selected.name if selected else None,
                    "confidence": decision.confidence if decision else 0.0,
                    "reason": decision.reason if decision else "",
                    "needs_review": (
                        selected is None
                        or (decision and decision.confidence < 0.85)
                    ),
                    "dqi_overall": dqi.overall if dqi else None,
                    "dqi_band": dqi.confidence_band if dqi else None,
                    "dqi_flags": dqi.flags if dqi else [],
                })

            unresolved = [
                {"index": i, "name": item.name, "material": item.material}
                for i, item in enumerate(model.items)
                if i >= len(model.mapping_decisions)
                or model.mapping_decisions[i].selected_candidate is None
            ]

            dqi_high = sum(1 for m in items if m.get("dqi_band") == "high")
            dqi_medium = sum(1 for m in items if m.get("dqi_band") == "medium")
            dqi_low = sum(1 for m in items if m.get("dqi_band") == "low")
            return ok({
                "mappings": items,
                "unresolved": unresolved,
                "total": len(model.items),
                "resolved": len(model.items) - len(unresolved),
                "low_confidence": sum(
                    1 for m in items if m["needs_review"]
                ),
                "dqi_summary": {
                    "high": dqi_high,
                    "medium": dqi_medium,
                    "low": dqi_low,
                },
            })
        except Exception as exc:
            return normalize_exception(exc)

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
            run_id = _new_run_id()

            r = self.step_ingest_bom(
                run_id,
                source_path=source_path,
                inline_text=inline_bom_text,
                product_name=product_name,
            )
            if not r["ok"]:
                return r
            if description:
                run = self.store.load_run(run_id)
                items = _items_from_input(description=description)
                model = run.product_model
                if model is not None:
                    model.items.extend(items)
                    model.functional_unit = description
                self.store.save_run(run)

            r = self.step_map_processes(run_id)
            if not r["ok"]:
                return r

            if allow_partial_model:
                try:
                    run = self.store.load_run(run_id)
                    self.gateway.create_product_system_from_model(
                        run.product_model, allow_partial_model=True
                    )
                except Exception:
                    pass

            r = self.step_create_product_system(run_id)
            if not r["ok"]:
                return r

            r = self.step_calculate(run_id, impact_method_id)
            if not r["ok"]:
                return r

            r = self.step_export(run_id, formats=["xlsx", "pcf"])
            if not r["ok"]:
                return r

            r = self.step_report(run_id, standards=standards)
            if not r["ok"]:
                return r

            run = self.store.load_run(run_id)
            return {"run": run, "report": "See run.files for generated report."}

        return guarded(action)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_mapping(
        self, items: list[BomItem]
    ) -> tuple[
        list[Any],
        list[BomItem],
        list[str],
    ]:
        decisions = []
        unresolved = []
        missing_data = []
        for item in items:
            descriptors = self.gateway.search_processes(item.material, limit=10)
            candidates = [
                _candidate_from_descriptor(d) for d in descriptors
            ]
            decision = map_bom_item_to_processes(
                item, candidates, threshold=CONFIDENCE_THRESHOLD
            )
            decisions.append(decision)
            if decision.selected_candidate is None:
                unresolved.append(item)
                missing_data.append(
                    f"No confident process mapping for {item.name} / {item.material}."
                )
        return decisions, unresolved, missing_data

    def _try_save_error(self, run_id: str, exc: Exception) -> None:
        try:
            run = self.store.load_run(run_id)
            run.error_context = str(exc)
            self.store.save_run(run)
        except Exception:
            pass


def _candidate_from_descriptor(descriptor: Descriptor) -> ProcessCandidate:
    return ProcessCandidate(
        id=descriptor.id,
        name=descriptor.name,
        category=descriptor.category,
        category_path=descriptor.category,
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
        raise ValueError(
            "Provide description or bom_items for product model drafting."
        )
    return _items_from_description(description)


def _items_from_description(description: str) -> list[BomItem]:
    items = []
    for index, segment in enumerate(
        description.replace("\n", ";").split(";"), start=1
    ):
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
                notes="Parsed from natural language description; "
                "quantity and unit require review.",
            )
        )
    if not items:
        raise ValueError("Could not extract any product items from description.")
    return items


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"
