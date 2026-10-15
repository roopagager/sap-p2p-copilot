import os
import pytest

os.environ.setdefault("SAP_MODE", "fixture")


@pytest.fixture(autouse=True)
def _tmp_logs(tmp_path, monkeypatch):
    from sap_copilot import audit, server
    monkeypatch.setattr(audit, "LOG", tmp_path / "audit.jsonl")
    monkeypatch.setattr(server, "APPROVALS", tmp_path / "approvals.jsonl")
    yield tmp_path


@pytest.fixture
def anyio_backend():
    return "asyncio"
