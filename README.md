# openLCA-Agent

AI-oriented MCP server for driving local openLCA workflows through openLCA IPC.  
27 tools covering BOM ingestion, process mapping, product system creation, LCA calculation,
idempotent multi-step workflows, AI semantic mapping, PCF export, and compliance reporting.

## Quick Start

1. Open openLCA Desktop.
2. Open the database you want to operate on.
3. Start the IPC Server from openLCA Developer Tools on port `8080`.
4. Run:

```powershell
uv run --python 3.12 openlca-agent health
uv run --python 3.12 openlca-agent mcp
```

Outputs are written below `outputs/<run_id>/`.

## CLI Commands

| Command | Description |
|---------|-------------|
| `openlca-agent health` | Check IPC connectivity and database status |
| `openlca-agent mcp` | Start the MCP server for Claude integration |
| `openlca-agent smoke` | BOM parser smoke test |
| `openlca-agent export-pcf <run_id>` | Export PCF (PACT Pathfinder 2.0) for a completed run |
| `openlca-agent assess` | One-shot end-to-end product assessment |

## MCP Tools (27 total)

### Standalone tools
| Tool | Description |
|------|-------------|
| `health_check` | Check openLCA IPC connectivity |
| `list_databases` | List local openLCA databases |
| `search_process` | Search openLCA processes by keyword |
| `search_product_system` | Search product systems |
| `list_impact_methods` | List available impact assessment methods |
| `calculate_lca` | Run calculation for a product system |
| `get_impact_results` | Retrieve stored calculation results |
| `hotspot_analysis` | Process-level contribution analysis |
| `export_result` | Export results to XLSX/JSON/CSV |
| `export_pcf` | Export PACT Pathfinder 2.0 PCF (JSON+XLSX) |
| `ingest_bom` | Parse BOM from CSV or inline text |
| `draft_product_model` | Auto-map BOM items to openLCA processes |
| `create_product_system_from_model` | Create product system from mapped model |
| `generate_compliance_report` | Generate compliance report (Markdown+XLSX) |

### Idempotent step workflow (6 steps)
| Tool | Description |
|------|-------------|
| `step_ingest_bom` | Step 1: Ingest BOM and create run |
| `step_map_processes` | Step 2: Map BOM items to processes |
| `step_create_product_system` | Step 3: Create product system |
| `step_calculate` | Step 4: Run LCA calculation |
| `step_export` | Step 5: Export results (supports `"pcf"` format) |
| `step_report` | Step 6: Generate compliance report |

Steps are idempotent — each skips automatically if already completed.

### AI Semantic Mapping tools
| Tool | Description |
|------|-------------|
| `search_processes_semantic` | Multi-strategy process search with synonyms |
| `get_bom_with_mappings` | BOM items with current mapping status |
| `apply_item_mapping` | Apply a single semantic mapping |
| `batch_apply_mappings` | Apply multiple mappings at once |
| `auto_map_bom` | Fast fuzzy auto-mapping (baseline) |
| `review_mappings` | Review and flag low-confidence mappings |
| `assess_product` | One-shot end-to-end: ingest → map → model → calculate → export → report + PCF |

## PCF Export

Follows PACT Pathfinder Framework 2.0 subset:
- `pcf.json` — structured JSON (product info, declared unit, total PCF, process contributions, assumptions)
- `pcf.xlsx` — Excel workbook with PCF_INFO, PROCESSES, ASSUMPTIONS, MISSING_DATA sheets

Generated automatically by `step_export` with `formats=["pcf"]` or via `export_pcf` tool.

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

### Example workflows

BOM auto-model (creates a foreground product system from CSV, calculates, exports, and generates PCF):

```powershell
uv run --python 3.12 python examples/run_bom_auto_model.py
```

ELCD bottle assessment (runs on existing database product system with PCF export):

```powershell
uv run --python 3.12 python examples/run_elcd_bottles.py
```
