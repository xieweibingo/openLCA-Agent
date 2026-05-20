from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from openlca_agent.server import build_mcp
from openlca_agent.service import OpenLcaAgentService

app = typer.Typer(help="openLCA-Agent command line tools.")


@app.command()
def health(
    port: Annotated[int, typer.Option(help="openLCA IPC server port.")] = 8080,
    data_dir: Annotated[str | None, typer.Option(help="openLCA data directory.")] = None,
) -> None:
    service = OpenLcaAgentService()
    _print_json(service.health_check(port=port, data_dir=data_dir))


@app.command()
def mcp() -> None:
    build_mcp().run()


@app.command()
def smoke(
    bom: Annotated[
        Path,
        typer.Option(help="BOM CSV/XLSX path for parser smoke test."),
    ] = Path("examples/packaging_bom.csv"),
) -> None:
    service = OpenLcaAgentService()
    _print_json(service.ingest_bom(source_path=str(bom)))


@app.command()
def export_pcf(
    run_id: Annotated[str, typer.Argument(help="Run ID to export PCF for.")],
) -> None:
    """Export PCF (PACT Pathfinder 2.0) files for a completed run."""
    service = OpenLcaAgentService()
    _print_json(service.export_pcf(run_id))


@app.command()
def assess(
    product_name: Annotated[str, typer.Option(help="Product name.")],
    impact_method_id: Annotated[str, typer.Option(help="Impact method ID.")],
    bom: Annotated[Path | None, typer.Option(help="BOM CSV/XLSX path.")] = None,
    inline: Annotated[str | None, typer.Option(help="Inline BOM text (CSV).")] = None,
    allow_partial: Annotated[
        bool, typer.Option(help="Allow partial product model.")
    ] = False,
) -> None:
    """One-shot end-to-end product assessment (ingest → map → calculate → export → report)."""
    service = OpenLcaAgentService()
    _print_json(
        service.assess_product(
            product_name=product_name,
            impact_method_id=impact_method_id,
            source_path=str(bom) if bom else None,
            inline_bom_text=inline,
            allow_partial_model=allow_partial,
        )
    )


def _print_json(value: dict) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
