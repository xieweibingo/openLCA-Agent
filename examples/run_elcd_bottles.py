from __future__ import annotations

import json
import sys

from openlca_agent.service import OpenLcaAgentService

PRODUCT_SYSTEM_ID = "0fff6db0-464b-44f3-81af-381d88e7a1c3"
IMPACT_METHOD_ID = "787c02f1-d1f2-36d6-8e06-2307cc3ebebc"


def main() -> int:
    service = OpenLcaAgentService()
    calculation = service.calculate_lca(
        product_system_id=PRODUCT_SYSTEM_ID,
        impact_method_id=IMPACT_METHOD_ID,
        amount=1.0,
    )
    if not calculation["ok"]:
        print(json.dumps(calculation, ensure_ascii=False, indent=2))
        return 1

    run_id = calculation["data"]["run_id"]
    service.export_result(run_id, formats=["xlsx", "json", "csv"])
    service.export_pcf(run_id)  # PACT Pathfinder 2.0 JSON + XLSX
    report = service.generate_compliance_report(run_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
