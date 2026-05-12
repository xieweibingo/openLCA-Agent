# openLCA-Agent

AI-oriented MCP server for driving local openLCA workflows through openLCA IPC.

## Quick Start

1. Open openLCA Desktop.
2. Open the database you want to operate on.
3. Start the IPC server from openLCA Developer Tools on port `8080`.
4. Run:

```powershell
uv run --python 3.12 openlca-agent health
uv run --python 3.12 openlca-agent mcp
```

Outputs are written below `outputs/<run_id>/`.

## Development Checks

```powershell
uv run --python 3.12 --with pytest --with openpyxl pytest -q
uv run --python 3.12 openlca-agent smoke
```

Live integration checks require openLCA Desktop to be running with the target database opened and
the IPC Server started:

```powershell
$env:OPENLCA_INTEGRATION='1'
uv run --python 3.12 --with pytest pytest -q -m integration
```

Run the demo bottle calculation and export `results.xlsx` plus `report.md`:

```powershell
uv run --python 3.12 python examples/run_elcd_bottles.py
```
