import json

import pytest
from mcp import Client

from sap_copilot import server


def body(r):
    """Tool results come back as JSON text content."""
    return r.structured_content or json.loads(r.content[0].text)


@pytest.mark.anyio
async def test_tools_listed():
    async with Client(server.mcp) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert {"get_supplier_invoice", "check_three_way_match", "request_payment_block_release"} <= names


@pytest.mark.anyio
async def test_match_tool_and_audit(_tmp_logs):
    async with Client(server.mcp) as c:
        r = await c.call_tool("check_three_way_match", {"invoice": "5100000002", "fiscal_year": "2026"})
    assert body(r)["status"] == "EXCEPTION"
    log = (_tmp_logs / "audit.jsonl").read_text().splitlines()
    assert json.loads(log[-1])["tool"] == "check_three_way_match"


@pytest.mark.anyio
async def test_release_refused_when_match_fails(_tmp_logs):
    async with Client(server.mcp) as c:
        r = await c.call_tool("request_payment_block_release",
                              {"invoice": "5100000003", "fiscal_year": "2026", "justification": "pls"})
    assert body(r)["status"] == "REFUSED"
    assert not (_tmp_logs / "approvals.jsonl").exists()


@pytest.mark.anyio
async def test_release_creates_human_approval_only(_tmp_logs):
    async with Client(server.mcp) as c:
        r = await c.call_tool("request_payment_block_release",
                              {"invoice": "5100000001", "fiscal_year": "2026", "justification": "matched"})
    assert body(r)["status"] == "PENDING_HUMAN_APPROVAL"
    assert (_tmp_logs / "approvals.jsonl").exists()


@pytest.mark.anyio
async def test_injection_via_tool_rejected(_tmp_logs):
    async with Client(server.mcp) as c:
        r = await c.call_tool("get_supplier", {"supplier": "1' or 1 eq 1"})
    assert "error" in body(r)
