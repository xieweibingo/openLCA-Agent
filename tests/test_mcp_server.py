from openlca_agent.server import build_mcp


def test_mcp_server_builds_with_expected_name() -> None:
    mcp = build_mcp()

    assert mcp.name == "openLCA-Agent"
