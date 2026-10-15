# SAP P2P Copilot

[![tests](https://github.com/roopagager/sap-p2p-copilot/actions/workflows/tests.yml/badge.svg)](https://github.com/roopagager/sap-p2p-copilot/actions/workflows/tests.yml)

An MCP server that lets an AI assistant investigate **SAP S/4HANA procure-to-pay invoice exceptions**
safely, plus a small job that lands the same SAP data in a lakehouse for Databricks.

- **Read-only SAP tools** over the standard S/4HANA OData APIs (supplier invoice, purchase order,
  goods receipts, supplier).
- **Deterministic three-way match** (invoice ↔ purchase order ↔ goods receipt) in code — the model
  explains, it never does the money logic.
- **No direct writes to SAP.** The only action tool files a request for a *human* approver, and
  refuses if the match fails.
- **Input validation** against OData injection, **audit log** of every call, **eval set**, 19 tests.
- **SAP → lakehouse:** Parquet bronze layer with lineage columns for Databricks Auto Loader.

Runs fully offline with sample data shaped like real SAP OData responses, or against the free
**SAP Business Accelerator Hub sandbox** with your own API key.

## Quick start
```bash
pip install -r requirements.txt
pytest -q                              # 19 tests
python -m evals.run_evals              # 4/4 scorecard
python -m sap_copilot.export_to_lake   # writes lake/bronze/sap/*/part-*.parquet
python -m sap_copilot.server           # MCP server on stdio
```

### Use the real SAP sandbox
1. Create a free account at <https://api.sap.com>, then copy your API key (Settings → Show API Key).
2. `cp .env.example .env`, set `SAP_MODE=sandbox` and `SAP_API_KEY=...`, and export them.
3. Sandbox document numbers differ from the fixtures — list some first, e.g. call `get_purchase_order`
   with an ID you find in the API Hub's "Try out" page.
4. Check entity and field names against the API Hub for your S/4HANA release.

### Connect to an MCP host (e.g. Claude Desktop)
```json
{ "mcpServers": { "sap-p2p-copilot": {
    "command": "python", "args": ["-m", "sap_copilot.server"],
    "cwd": "/path/to/sap-p2p-copilot", "env": { "SAP_MODE": "fixture" } } } }
```
Then ask: *"Why is invoice 5100000002 blocked, and can it be released?"*

## Sample run
```text
$ python -m evals.run_evals
e1  5100000001  MATCHED    PASS  
e2  5100000002  EXCEPTION  PASS  4500000002/00010: Price variance: invoiced 1150.00 vs expected 1000.00 (+15.0%)
e3  5100000003  EXCEPTION  PASS  4500000003/00010: Invoiced quantity 10 exceeds goods received 6
e4  5100000004  EXCEPTION  PASS  Supplier is blocked for payment in the supplier master

4/4 passed
```
And the action tool refusing an invoice that fails the match:
```text
request_payment_block_release(invoice="5100000003", fiscal_year="2026")
→ {"status": "REFUSED", "reason": "Three-way match does not pass",
   "issues": ["4500000003/00010: Invoiced quantity 10 exceeds goods received 6"]}
```

## Tools
| Tool | SAP API | Effect |
|---|---|---|
| `get_supplier_invoice` | API_SUPPLIERINVOICE_PROCESS_SRV | read |
| `get_purchase_order` | API_PURCHASEORDER_PROCESS_SRV | read |
| `get_goods_receipts` | API_MATERIAL_DOCUMENT_SRV | read |
| `get_supplier` | API_BUSINESS_PARTNER | read |
| `check_three_way_match` | all of the above | read + deterministic checks |
| `request_payment_block_release` | — | writes an approval request file only; never changes SAP |

## Sample cases (fixtures)
| Invoice | Result |
|---|---|
| 5100000001 | MATCHED |
| 5100000002 | EXCEPTION — price variance +15% |
| 5100000003 | EXCEPTION — invoiced 10, received 6 |
| 5100000004 | EXCEPTION — supplier blocked for payment |

## Production design
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): identity (principal propagation), Integration Suite,
SAP-supported data routes into Databricks (Business Data Cloud, Datasphere), SAP Note 3255746, and
what would change before going live.
