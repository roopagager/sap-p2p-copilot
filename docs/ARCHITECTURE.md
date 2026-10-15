# Architecture and production notes

## Two paths
**Live path (agent):** MCP host → SAP P2P Copilot → S/4HANA OData APIs (or an SAP Integration Suite
API proxy in front of them). Small, filtered, paged reads; deterministic checks in code; human
approval for anything that changes SAP.

**Analytics path (lakehouse):** SAP data → Databricks for history, trends and Text2SQL. The included
`export_to_lake.py` shows the bronze-layer pattern (Parquet + `_source_service`, `_load_ts`). In
production prefer SAP-supported routes:
- **SAP Business Data Cloud → Databricks:** SAP data products shared into Unity Catalog, zero-copy.
- **SAP Datasphere replication flows → ADLS Gen2**, then Auto Loader into Delta.
- **Avoid ODP-RFC from non-SAP tools** — restricted by SAP Note 3255746, with technical enforcement
  from June 2026. Check the customer's position with their SAP Basis team.

## Identity and authorisation (what changes for production)
| Here (demo) | Production |
|---|---|
| Fixture data / sandbox API key | OAuth 2.0 to S/4HANA or via BTP; **principal propagation** so SAP enforces the end user's own roles |
| Single process | Tool layer behind enterprise SSO (e.g. Entra ID), per-tool authorisation |
| Approval requests in a local file | Customer's workflow (SAP Flexible Workflow, ServiceNow, Teams approval) with segregation-of-duties checks (SAP GRC) |
| Local JSONL audit | Central, tamper-evident logging (SIEM) with correlation IDs |
| Fixed 2% price tolerance | Customer's configured tolerance keys |

## Safety controls already in place
- Allow-list of entity sets; anything else is rejected.
- Every key validated with a strict pattern before it reaches an OData `$filter` (prevents injection).
- Paging (`$top`/`$skip`), retries with backoff on 429/5xx, `Retry-After` honoured, request timeouts.
- Tool outputs are plain data; the agent is instructed to treat them as data, not instructions.
- The only state-changing tool refuses unless the deterministic match passes, and never calls SAP.

## Next steps
1. Point at a customer's S/4HANA sandbox with OAuth and principal propagation.
2. Add SAP business events (Event Mesh) to trigger the workflow when an invoice is blocked.
3. Build the eval set from real historical exceptions with the AP team; track precision/recall.
4. Land history via Business Data Cloud or Datasphere and add a Text2SQL view for AP analytics.
