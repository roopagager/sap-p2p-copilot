"""Sandbox mode without network: a fake session proves paging, retries and headers."""
from sap_copilot.sap_client import SapClient


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self):
        self.calls = []
        self.queue = [Resp(429, headers={"Retry-After": "0"}),
                      Resp(200, {"d": {"results": [{"Supplier": "1", "__metadata": {}}, {"Supplier": "2"}]}}),
                      Resp(200, {"d": {"results": [{"Supplier": "3"}]}})]

    def get(self, url, params, headers, timeout):
        self.calls.append((url, dict(params), headers))
        return self.queue.pop(0)


def test_paging_retry_and_headers():
    s = FakeSession()
    c = SapClient(mode="sandbox", api_key="k", session=s, page_size=2)
    rows = c.query("A_Supplier")
    assert [r["Supplier"] for r in rows] == ["1", "2", "3"]
    assert "__metadata" not in rows[0]
    assert s.calls[0][2]["APIKey"] == "k"
    assert s.calls[0][0].endswith("/API_BUSINESS_PARTNER/A_Supplier")
    assert s.calls[-1][1]["$skip"] == "2"


def test_filter_is_built_from_validated_keys():
    s = FakeSession()
    s.queue = [Resp(200, {"d": {"results": []}})]
    SapClient(mode="sandbox", api_key="k", session=s).query("A_Supplier", {"Supplier": "17300001"})
    assert s.calls[0][1]["$filter"] == "Supplier eq '17300001'"
