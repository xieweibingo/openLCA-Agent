import os

import pytest

from openlca_agent.service import OpenLcaAgentService

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("OPENLCA_INTEGRATION") != "1",
    reason="Set OPENLCA_INTEGRATION=1 after opening openLCA and starting IPC Server.",
)
def test_openlca_ipc_health_check() -> None:
    response = OpenLcaAgentService().health_check()

    assert response["ok"] is True
    assert response["data"]["ipc_reachable"] is True
