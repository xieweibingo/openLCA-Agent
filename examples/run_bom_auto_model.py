from __future__ import annotations

import json
import sys

from openlca_agent.service import OpenLcaAgentService

IMPACT_METHOD_ID = "787c02f1-d1f2-36d6-8e06-2307cc3ebebc"
DEMO_PRODUCT_NAME = "AI demo PC bottle shell"
DEMO_BOM = """name,material,quantity,unit,location,notes
PC resin,Polycarbonate granulate,0.5,kg,RER,Main bottle polymer
Electricity,Electricity grid mix,1.0,kWh,IT,Foreground processing electricity
"""


def main() -> int:
    service = OpenLcaAgentService()
    response = service.assess_product(
        product_name=DEMO_PRODUCT_NAME,
        impact_method_id=IMPACT_METHOD_ID,
        inline_bom_text=DEMO_BOM,
        standards=["PCF", "EPD", "CBAM", "DPP"],
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
