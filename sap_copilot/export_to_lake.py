"""Land SAP P2P entities as Parquet in a bronze folder for Databricks (Auto Loader / COPY INTO).

    python -m sap_copilot.export_to_lake --out lake/bronze/sap

Pattern only: in production prefer SAP-supported routes - Business Data Cloud data products shared
into Unity Catalog, or Datasphere replication flows to ADLS - over pulling large volumes through
OData. Avoid ODP-RFC from non-SAP tools (SAP Note 3255746). See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from .sap_client import SERVICES, SapClient


def export(out: str | Path, client: SapClient | None = None) -> dict[str, int]:
    client = client or SapClient()
    out = Path(out)
    load_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    counts = {}
    for entity in SERVICES:
        rows = client.query(entity, limit=10_000)
        df = pd.DataFrame(rows)
        df["_source_service"] = SERVICES[entity]
        df["_load_ts"] = load_ts
        target = out / entity
        target.mkdir(parents=True, exist_ok=True)
        df.to_parquet(target / f"part-{load_ts.replace(':', '')}.parquet", index=False)
        counts[entity] = len(df)
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="lake/bronze/sap")
    for k, v in export(ap.parse_args().out).items():
        print(f"{k:28s} {v:6d} rows")
