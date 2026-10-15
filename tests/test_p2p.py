import pytest

from sap_copilot.p2p import three_way_match
from sap_copilot.sap_client import SapClient, safe_id

C = SapClient(mode="fixture")


def test_clean_invoice_matches():
    assert three_way_match(C, "5100000001", "2026").status == "MATCHED"


def test_price_variance_detected():
    r = three_way_match(C, "5100000002", "2026")
    assert r.status == "EXCEPTION" and any("Price variance" in i for i in r.issues)


def test_quantity_above_goods_receipt_detected():
    r = three_way_match(C, "5100000003", "2026")
    assert any("exceeds goods received" in i for i in r.issues)


def test_blocked_supplier_detected():
    r = three_way_match(C, "5100000004", "2026")
    assert any("blocked for payment" in i for i in r.issues)


def test_evidence_trail_recorded():
    r = three_way_match(C, "5100000001", "2026")
    assert any(e.startswith("PurchaseOrderItem 4500000001") for e in r.evidence)


@pytest.mark.parametrize("bad", ["5100' or 1 eq 1", "../etc/passwd", "", "x" * 60])
def test_injection_rejected(bad):
    with pytest.raises(ValueError):
        safe_id(bad)


def test_unknown_entity_rejected():
    with pytest.raises(ValueError):
        C.query("A_JournalEntry")


def test_missing_invoice():
    with pytest.raises(LookupError):
        three_way_match(C, "9999999999", "2026")
