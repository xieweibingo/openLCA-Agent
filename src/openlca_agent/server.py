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
            "and exporting reviewable LCA compliance reports."
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
    async def generate_compliance_report(
        run_id: str,
        standards: list[str] | None = None,
    ) -> dict[str, Any]:
        return service.generate_compliance_report(run_id, standards=standards)

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
