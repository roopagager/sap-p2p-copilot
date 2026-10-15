import pandas as pd

from sap_copilot.export_to_lake import export
from sap_copilot.sap_client import SapClient


def test_export_writes_parquet_with_lineage(tmp_path):
    counts = export(tmp_path, SapClient(mode="fixture"))
    assert counts["A_SupplierInvoice"] == 4
    df = pd.read_parquet(next((tmp_path / "A_PurchaseOrderItem").glob("*.parquet")))
    assert {"_source_service", "_load_ts"} <= set(df.columns)
