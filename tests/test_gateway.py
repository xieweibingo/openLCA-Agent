from pathlib import Path

from openlca_agent.gateway import OlcaGateway


def test_list_databases_reads_openlca_manifest(tmp_path: Path) -> None:
    (tmp_path / "databases.json").write_text(
        '{"localDatabases":[{"name":"tiangong_v020"},{"name":"EF3.1"}],"remoteDatabases":[]}',
        encoding="utf-8",
    )

    databases = OlcaGateway(data_dir=tmp_path).list_databases()

    assert [item["name"] for item in databases] == ["tiangong_v020", "EF3.1"]
