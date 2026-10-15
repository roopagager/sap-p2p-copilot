"""Read-only client for SAP S/4HANA OData V2 APIs.

Two modes (SAP_MODE env var):
  fixture  - offline sample data shaped exactly like the OData responses (default; used by tests)
  sandbox  - SAP Business Accelerator Hub sandbox (https://api.sap.com), needs SAP_API_KEY

Production would point at the customer's S/4HANA (or an Integration Suite API proxy)
with OAuth / principal propagation instead of an API key - see docs/ARCHITECTURE.md.
Verify service and field names against api.sap.com for the customer's release.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

# Entity set -> OData service that exposes it (S/4HANA Cloud standard APIs)
SERVICES = {
    "A_SupplierInvoice": "API_SUPPLIERINVOICE_PROCESS_SRV",
    "A_SuplrInvcItemPurOrdRef": "API_SUPPLIERINVOICE_PROCESS_SRV",
    "A_PurchaseOrder": "API_PURCHASEORDER_PROCESS_SRV",
    "A_PurchaseOrderItem": "API_PURCHASEORDER_PROCESS_SRV",
    "A_MaterialDocumentItem": "API_MATERIAL_DOCUMENT_SRV",
    "A_Supplier": "API_BUSINESS_PARTNER",
}
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SAFE = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


def safe_id(value: str) -> str:
    """Reject anything that isn't a plain SAP key - blocks OData/query injection via tool inputs."""
    if not isinstance(value, str) or not _SAFE.match(value):
        raise ValueError(f"invalid SAP key: {value!r}")
    return value


class SapClient:
    def __init__(self, mode: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, session: requests.Session | None = None,
                 page_size: int = 100, max_retries: int = 4):
        self.mode = (mode or os.environ.get("SAP_MODE", "fixture")).lower()
        self.api_key = api_key or os.environ.get("SAP_API_KEY", "")
        self.base_url = (base_url or os.environ.get(
            "SAP_BASE_URL", "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap")).rstrip("/")
        self.session = session or requests.Session()
        self.page_size = page_size
        self.max_retries = max_retries
        if self.mode == "sandbox" and not self.api_key:
            raise RuntimeError("SAP_MODE=sandbox needs SAP_API_KEY (free at api.sap.com)")

    # ---- public API -------------------------------------------------------
    def query(self, entity: str, filters: dict[str, str] | None = None,
              select: list[str] | None = None, limit: int = 500) -> list[dict]:
        """Return rows of an entity set, filtered by exact-match key fields."""
        if entity not in SERVICES:
            raise ValueError(f"entity not allowed: {entity}")
        filters = {k: safe_id(v) for k, v in (filters or {}).items()}
        if self.mode == "fixture":
            return self._fixture(entity, filters, select)[:limit]
        return self._odata(entity, filters, select, limit)

    # ---- fixture mode -----------------------------------------------------
    def _fixture(self, entity, filters, select):
        rows = json.loads((FIXTURES / f"{entity}.json").read_text())["d"]["results"]
        rows = [r for r in rows if all(str(r.get(k)) == v for k, v in filters.items())]
        return [{k: r[k] for k in select} for r in rows] if select else rows

    # ---- sandbox / real OData --------------------------------------------
    def _odata(self, entity, filters, select, limit):
        url = f"{self.base_url}/{SERVICES[entity]}/{entity}"
        params = {"$format": "json", "$top": str(min(self.page_size, limit)), "$skip": "0"}
        if filters:
            params["$filter"] = " and ".join(f"{k} eq '{v}'" for k, v in filters.items())
        if select:
            params["$select"] = ",".join(select)
        rows: list[dict] = []
        while len(rows) < limit:
            page = self._get(url, params)["d"]["results"]
            for r in page:
                r.pop("__metadata", None)
            rows += page
            if len(page) < int(params["$top"]):
                break
            params["$skip"] = str(int(params["$skip"]) + len(page))
        return rows[:limit]

    def _get(self, url, params):
        headers = {"APIKey": self.api_key, "Accept": "application/json"}
        for attempt in range(self.max_retries + 1):
            r = self.session.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.max_retries:
                    r.raise_for_status()
                wait = float(r.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, 30))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("unreachable")
