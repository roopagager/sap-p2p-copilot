"""Append-only JSONL audit log: every tool call, who asked, what SAP objects were read."""
import json
import os
import time
from pathlib import Path

LOG = Path(os.environ.get("AUDIT_LOG", "audit_log.jsonl"))


def record(tool: str, args: dict, outcome: str, user: str | None = None, **extra) -> None:
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tool": tool, "args": args,
             "user": user or os.environ.get("COPILOT_USER", "unknown"), "outcome": outcome, **extra}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
