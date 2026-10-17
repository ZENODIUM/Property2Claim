import asyncio

from app import mcp_server


def test_read_only_mcp_tools_expose_persisted_data(test_context, monkeypatch):
    _, Session, _ = test_context
    monkeypatch.setattr(mcp_server, "SessionLocal", Session)

    portfolio = mcp_server.get_portfolio()
    excerpt = mcp_server.get_document_excerpt(1)
    tools = asyncio.run(mcp_server.mcp.list_tools())

    assert portfolio["company_count"] == 8
    assert portfolio["companies"][0]["sites"]
    assert excerpt["found"] is True
    assert excerpt["document"]["filename"]
    assert "storage_path" not in excerpt["document"]
    assert {"get_portfolio", "get_floorplan", "list_evidence", "get_document_excerpt"} <= {tool.name for tool in tools}
