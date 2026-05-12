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


def _print_json(value: dict) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
