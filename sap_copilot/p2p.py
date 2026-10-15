"""Deterministic procure-to-pay checks. Money logic lives in code, never in the model."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .sap_client import SapClient, safe_id

PRICE_TOLERANCE = 0.02   # 2% - make these the customer's real tolerance keys in production
QTY_TOLERANCE = 0.0


@dataclass
class LineResult:
    po: str
    po_item: str
    invoiced_qty: float
    ordered_qty: float
    received_qty: float
    invoiced_amount: float
    expected_amount: float
    issues: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    invoice: str
    fiscal_year: str
    supplier: str
    supplier_name: str
    status: str                      # MATCHED | EXCEPTION
    issues: list[str]
    lines: list[dict]
    evidence: list[str]              # SAP objects consulted, for the audit trail

    def to_dict(self):
        return asdict(self)


def _f(x) -> float:
    return float(str(x or "0").replace(",", ""))


def three_way_match(client: SapClient, invoice: str, fiscal_year: str) -> MatchResult:
    invoice, fiscal_year = safe_id(invoice), safe_id(fiscal_year)
    heads = client.query("A_SupplierInvoice", {"SupplierInvoice": invoice, "FiscalYear": fiscal_year})
    if not heads:
        raise LookupError(f"supplier invoice {invoice}/{fiscal_year} not found")
    head = heads[0]
    evidence = [f"SupplierInvoice {invoice}/{fiscal_year}"]
    supplier_id = head["InvoicingParty"]
    sup = client.query("A_Supplier", {"Supplier": supplier_id})
    supplier_name = sup[0]["SupplierName"] if sup else "unknown"
    evidence.append(f"Supplier {supplier_id}")

    issues: list[str] = []
    if sup and sup[0].get("PaymentIsBlockedForSupplier"):
        issues.append("Supplier is blocked for payment in the supplier master")

    lines: list[LineResult] = []
    for it in client.query("A_SuplrInvcItemPurOrdRef", {"SupplierInvoice": invoice, "FiscalYear": fiscal_year}):
        po, poi = it["PurchaseOrder"], it["PurchaseOrderItem"]
        po_rows = client.query("A_PurchaseOrderItem", {"PurchaseOrder": po, "PurchaseOrderItem": poi})
        gr_rows = [g for g in client.query("A_MaterialDocumentItem", {"PurchaseOrder": po, "PurchaseOrderItem": poi})
                   if g.get("GoodsMovementType") == "101"]
        evidence += [f"PurchaseOrderItem {po}/{poi}", f"GoodsReceipts for {po}/{poi}: {len(gr_rows)}"]
        inv_qty, inv_amt = _f(it["QuantityInPurchaseOrderUnit"]), _f(it["SupplierInvoiceItemAmount"])
        if not po_rows:
            lines.append(LineResult(po, poi, inv_qty, 0, 0, inv_amt, 0, ["Purchase order item not found"]))
            continue
        p = po_rows[0]
        unit_price = _f(p["NetPriceAmount"]) / max(_f(p["NetPriceQuantity"]), 1)
        ordered, received = _f(p["OrderQuantity"]), sum(_f(g["QuantityInEntryUnit"]) for g in gr_rows)
        expected = round(inv_qty * unit_price, 2)
        line = LineResult(po, poi, inv_qty, ordered, received, inv_amt, expected)
        if inv_qty > received * (1 + QTY_TOLERANCE):
            line.issues.append(f"Invoiced quantity {inv_qty:g} exceeds goods received {received:g}")
        if inv_qty > ordered * (1 + QTY_TOLERANCE):
            line.issues.append(f"Invoiced quantity {inv_qty:g} exceeds ordered {ordered:g}")
        if expected and abs(inv_amt - expected) / expected > PRICE_TOLERANCE:
            line.issues.append(f"Price variance: invoiced {inv_amt:.2f} vs expected {expected:.2f} "
                               f"({(inv_amt - expected) / expected:+.1%})")
        lines.append(line)

    issues += [f"{l.po}/{l.po_item}: {i}" for l in lines for i in l.issues]
    return MatchResult(invoice, fiscal_year, supplier_id, supplier_name,
                       "EXCEPTION" if issues else "MATCHED", issues,
                       [asdict(l) for l in lines], evidence)
