from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from openlca_agent.service import OpenLcaAgentService


def build_mcp(service: OpenLcaAgentService | None = None) -> FastMCP:
    service = service or OpenLcaAgentService()
    mcp = FastMCP(
        "openLCA-Agent",
        instructions=(
            "Tools for controlling local openLCA through IPC, drafting product models, "
            "and exporting reviewable LCA compliance reports. "
            "Use step_* tools for idempotent multi-step workflows that survive failures. "
            "Steps must be called in order: step_ingest_bom, step_map_processes, "
            "step_create_product_system, step_calculate, step_export, step_report. "
            "Each step skips automatically if already completed. "
            "step_export also supports format \"pcf\" for PACT Pathfinder 2.0 JSON+XLSX. "
            "Use assess_product for one-shot end-to-end assessment (includes PCF export). "
            "For AI-enhanced semantic mapping: call auto_map_bom for fast baseline, "
            "then get_bom_with_mappings + search_processes_semantic + "
            "batch_apply_mappings to refine low-confidence mappings with "
            "Claude's semantic understanding."
        ),
    )

    @mcp.tool()
    async def health_check(
        port: int = 8080,
        data_dir: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Checking openLCA IPC connectivity and local database manifest.")
        return service.health_check(port=port, data_dir=data_dir)

    @mcp.tool()
    async def list_databases(data_dir: str | None = None) -> dict[str, Any]:
        return service.list_databases(data_dir=data_dir)

    @mcp.tool()
    async def search_process(
        query: str,
        geography: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return service.search_process(query=query, geography=geography, limit=limit)

    @mcp.tool()
    async def search_product_system(query: str | None = None, limit: int = 10) -> dict[str, Any]:
        return service.search_product_system(query=query, limit=limit)

    @mcp.tool()
    async def list_impact_methods(query: str | None = None, limit: int = 20) -> dict[str, Any]:
        return service.list_impact_methods(query=query, limit=limit)

    @mcp.tool()
    async def calculate_lca(
        product_system_id: str,
        impact_method_id: str,
        amount: float = 1.0,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Running openLCA calculation.")
        return service.calculate_lca(product_system_id, impact_method_id, amount)

    @mcp.tool()
    async def get_impact_results(run_id: str) -> dict[str, Any]:
        return service.get_impact_results(run_id)

    @mcp.tool()
    async def hotspot_analysis(
        run_id: str,
        impact_category: str | None = None,
        dimension: str = "process",
        limit: int = 10,
    ) -> dict[str, Any]:
        return service.hotspot_analysis(run_id, impact_category, dimension, limit)

    @mcp.tool()
    async def export_result(run_id: str, formats: list[str] | None = None) -> dict[str, Any]:
        return service.export_result(run_id, formats=formats or ["xlsx"])

    @mcp.tool()
    async def ingest_bom(
        source_path: str | None = None,
        inline_text: str | None = None,
    ) -> dict[str, Any]:
        return service.ingest_bom(source_path=source_path, inline_text=inline_text)

    @mcp.tool()
    async def draft_product_model(
        product_name: str,
        description: str | None = None,
        bom_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return service.draft_product_model(product_name, description, bom_items)

    @mcp.tool()
    async def create_product_system_from_model(
        product_model: dict[str, Any],
        allow_partial_model: bool = False,
    ) -> dict[str, Any]:
        return service.create_product_system_from_model(product_model, allow_partial_model)

    @mcp.tool()
    async def export_pcf(
        run_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Exporting PCF (PACT Pathfinder 2.0) files.")
        return service.export_pcf(run_id)

    @mcp.tool()
    async def generate_compliance_report(
        run_id: str,
        standards: list[str] | None = None,
    ) -> dict[str, Any]:
        return service.generate_compliance_report(run_id, standards=standards)

    # ------------------------------------------------------------------
    # Idempotent step tools (Phase 2)
    # ------------------------------------------------------------------

    @mcp.tool()
    async def step_ingest_bom(
        run_id: str,
        source_path: str | None = None,
        inline_text: str | None = None,
        product_name: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Step 1/6: Ingesting BOM and creating run.")
        return service.step_ingest_bom(
            run_id,
            source_path=source_path,
            inline_text=inline_text,
            product_name=product_name,
        )

    @mcp.tool()
    async def step_map_processes(
        run_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Step 2/6: Mapping BOM items to openLCA processes.")
        return service.step_map_processes(run_id)

    @mcp.tool()
    async def step_create_product_system(
        run_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Step 3/6: Creating product system in openLCA.")
        return service.step_create_product_system(run_id)

    @mcp.tool()
    async def step_calculate(
        run_id: str,
        impact_method_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Step 4/6: Running openLCA calculation.")
        return service.step_calculate(run_id, impact_method_id)

    @mcp.tool()
    async def step_export(
        run_id: str,
        formats: list[str] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Step 5/6: Exporting results.")
        return service.step_export(
            run_id, formats=formats or ["xlsx", "pcf"]
        )

    @mcp.tool()
    async def step_report(
        run_id: str,
        standards: list[str] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Step 6/6: Generating compliance report.")
        return service.step_report(run_id, standards=standards)

    # ------------------------------------------------------------------
    # Semantic mapping tools (Phase 3)
    # ------------------------------------------------------------------

    @mcp.tool()
    async def search_processes_semantic(
        material: str,
        name: str | None = None,
        location: str | None = None,
        supplier: str | None = None,
        limit: int = 30,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Searching processes with semantic strategies.")
        return service.search_processes_semantic(
            material=material,
            name=name,
            location=location,
            supplier=supplier,
            limit=limit,
        )

    @mcp.tool()
    async def get_bom_with_mappings(
        run_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Retrieving BOM items with current mapping status.")
        return service.get_bom_with_mappings(run_id)

    @mcp.tool()
    async def apply_item_mapping(
        run_id: str,
        item_index: int,
        process_id: str,
        process_name: str = "",
        confidence: float = 1.0,
        reason: str = "",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info(f"Applying mapping for BOM item index {item_index}.")
        return service.apply_item_mapping(
            run_id,
            item_index=item_index,
            process_id=process_id,
            process_name=process_name,
            confidence=confidence,
            reason=reason,
        )

    @mcp.tool()
    async def batch_apply_mappings(
        run_id: str,
        mappings: list[dict[str, Any]],
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info(f"Applying {len(mappings)} semantic mappings.")
        return service.batch_apply_mappings(run_id, mappings)

    @mcp.tool()
    async def auto_map_bom(
        run_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Running automatic fuzzy process mapping.")
        return service.auto_map_bom(run_id)

    @mcp.tool()
    async def review_mappings(
        run_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Reviewing current mapping decisions.")
        return service.review_mappings(run_id)

    @mcp.tool()
    async def assess_product(
        product_name: str,
        impact_method_id: str,
        source_path: str | None = None,
        inline_bom_text: str | None = None,
        description: str | None = None,
        allow_partial_model: bool = False,
        standards: list[str] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info("Assessing product: ingest, map, model, calculate, and report.")
        return service.assess_product(
            product_name=product_name,
            impact_method_id=impact_method_id,
            source_path=source_path,
            inline_bom_text=inline_bom_text,
            description=description,
            allow_partial_model=allow_partial_model,
            standards=standards,
        )

    return mcp


def main() -> None:
    build_mcp().run()


if __name__ == "__main__":
    main()
