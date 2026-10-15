"""SAP P2P Copilot - MCP server exposing governed, read-only SAP procure-to-pay tools.

Run:  python -m sap_copilot.server            (stdio, for Claude Desktop / any MCP host)
Test: pytest -q

Design rules (see docs/ARCHITECTURE.md):
  * Read-only tools only touch SAP. The single 'action' tool never writes to SAP -
    it files an approval request that a human must approve in the customer's own process.
  * All inputs are validated as plain SAP keys; tool outputs are data, never instructions.
  * Every call is written to the audit log.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from mcp.server import MCPServer

from . import audit
from .p2p import three_way_match
from .sap_client import SapClient, safe_id

mcp = MCPServer("SAP P2P Copilot")
_client: SapClient | None = None
APPROVALS = Path("approval_requests.jsonl")


def client() -> SapClient:
    global _client
    if _client is None:
        _client = SapClient()
    return _client


def _call(tool: str, args: dict, fn):
    try:
        out = fn()
        audit.record(tool, args, "ok")
        return out
    except (ValueError, LookupError) as e:
        audit.record(tool, args, f"rejected: {e}")
        return {"error": str(e)}


@mcp.tool()
def get_supplier_invoice(invoice: str, fiscal_year: str) -> dict:
    """Get an SAP supplier invoice header and its purchase-order-referenced items (read-only)."""
    return _call("get_supplier_invoice", {"invoice": invoice, "fiscal_year": fiscal_year}, lambda: {
        "header": (client().query("A_SupplierInvoice", {"SupplierInvoice": invoice, "FiscalYear": fiscal_year}) or [None])[0],
        "items": client().query("A_SuplrInvcItemPurOrdRef", {"SupplierInvoice": invoice, "FiscalYear": fiscal_year}),
    })


@mcp.tool()
def get_purchase_order(purchase_order: str) -> dict:
    """Get an SAP purchase order header and items (read-only)."""
    return _call("get_purchase_order", {"purchase_order": purchase_order}, lambda: {
        "header": (client().query("A_PurchaseOrder", {"PurchaseOrder": purchase_order}) or [None])[0],
        "items": client().query("A_PurchaseOrderItem", {"PurchaseOrder": purchase_order}),
    })


@mcp.tool()
def get_goods_receipts(purchase_order: str) -> list[dict]:
    """List goods receipts (movement type 101) posted against a purchase order (read-only)."""
    return _call("get_goods_receipts", {"purchase_order": purchase_order}, lambda: [
        g for g in client().query("A_MaterialDocumentItem", {"PurchaseOrder": purchase_order})
        if g.get("GoodsMovementType") == "101"])


@mcp.tool()
def get_supplier(supplier: str) -> dict:
    """Get basic supplier master data, including payment and posting blocks (read-only)."""
    return _call("get_supplier", {"supplier": supplier}, lambda: (
        client().query("A_Supplier", {"Supplier": supplier}) or [{"error": "supplier not found"}])[0])


@mcp.tool()
def check_three_way_match(invoice: str, fiscal_year: str) -> dict:
    """Run a deterministic three-way match (invoice vs purchase order vs goods receipt).
    Returns MATCHED or EXCEPTION with the specific issues and the SAP evidence consulted."""
    return _call("check_three_way_match", {"invoice": invoice, "fiscal_year": fiscal_year},
                 lambda: three_way_match(client(), invoice, fiscal_year).to_dict())


@mcp.tool()
def request_payment_block_release(invoice: str, fiscal_year: str, justification: str) -> dict:
    """Propose releasing a payment block. This NEVER changes SAP: it files an approval request
    for a human approver. Refused unless the three-way match currently passes."""
    args = {"invoice": invoice, "fiscal_year": fiscal_year}
    try:
        safe_id(invoice), safe_id(fiscal_year)
        result = three_way_match(client(), invoice, fiscal_year)
    except (ValueError, LookupError) as e:
        audit.record("request_payment_block_release", args, f"rejected: {e}")
        return {"error": str(e)}
    if result.status != "MATCHED":
        audit.record("request_payment_block_release", args, "refused: match failed", issues=result.issues)
        return {"status": "REFUSED", "reason": "Three-way match does not pass", "issues": result.issues}
    request = {"request_id": str(uuid.uuid4()), "invoice": invoice, "fiscal_year": fiscal_year,
               "justification": justification[:500], "status": "PENDING_HUMAN_APPROVAL",
               "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "evidence": result.evidence}
    with APPROVALS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(request) + "\n")
    audit.record("request_payment_block_release", args, "approval_requested", request_id=request["request_id"])
    return request


if __name__ == "__main__":
    mcp.run()
