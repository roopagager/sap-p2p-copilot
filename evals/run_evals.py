"""Scorecard for the deterministic P2P checks. Run before any change: python -m evals.run_evals"""
import json
import sys
from pathlib import Path

from sap_copilot.p2p import three_way_match
from sap_copilot.sap_client import SapClient


def main() -> int:
    cases = json.loads((Path(__file__).parent / "cases.json").read_text())
    client, passed = SapClient(mode="fixture"), 0
    for c in cases:
        r = three_way_match(client, c["invoice"], c["fy"])
        ok = r.status == c["expect_status"] and (
            c["expect_issue_contains"] is None or any(c["expect_issue_contains"] in i for i in r.issues))
        passed += ok
        print(f"{c['id']}  {c['invoice']}  {r.status:9s}  {'PASS' if ok else 'FAIL'}  {'; '.join(r.issues)[:90]}")
    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
