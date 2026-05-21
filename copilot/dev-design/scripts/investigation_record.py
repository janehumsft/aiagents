#!/usr/bin/env python3
"""
investigation_record.py - Update the status of an investigation source.

The agent calls this after launching, monitoring, or completing a subagent
run for one source. Maintains scope.json and the manifest's investigation
step block.

Statuses:
    pending       initial state
    in-progress   subagent launched, output not yet written
    done          raw file exists and has been validated
    failed        subagent could not complete; capture --error reason

Usage examples:
    # Mark a subagent launched
    python investigation_record.py --workspace <ws> --source client \
        --status in-progress --agent-id explore-1

    # Mark a subagent done after it wrote its raw file
    python investigation_record.py --workspace <ws> --source client \
        --status done --raw-file raw/client.md

    # Mark a failure
    python investigation_record.py --workspace <ws> --source service \
        --status failed --error "rate limited"

Exit codes:
    0  success
    2  workspace / scope.json missing
    3  unknown source id or invalid status
"""
from __future__ import annotations
import argparse
import datetime
import json
import sys
from pathlib import Path

VALID_STATUSES = {"pending", "in-progress", "done", "failed"}


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--agent-id", default="")
    p.add_argument("--raw-file", default="")
    p.add_argument("--error", default="")
    args = p.parse_args()

    if args.status not in VALID_STATUSES:
        print(json.dumps({
            "error": f"unknown status: {args.status}",
            "validStatuses": sorted(VALID_STATUSES),
        }), file=sys.stderr)
        return 3

    ws = Path(args.workspace).resolve()
    inv_dir = ws / "workspace" / "investigation"
    scope_path = inv_dir / "scope.json"
    manifest_path = ws / "workspace" / "manifest.json"
    if not scope_path.exists():
        print(json.dumps({"error": f"scope.json not found at {scope_path}"}), file=sys.stderr)
        return 2
    if not manifest_path.exists():
        print(json.dumps({"error": f"manifest not found at {manifest_path}"}), file=sys.stderr)
        return 2

    scope = _read_json(scope_path)
    sources = scope.get("sources") or []
    target = next((s for s in sources if s["id"] == args.source), None)
    if target is None:
        print(json.dumps({
            "error": f"unknown source id: {args.source}",
            "validIds": [s["id"] for s in sources],
        }), file=sys.stderr)
        return 3

    prev = target.get("status", "pending")
    target["status"] = args.status
    if args.agent_id:
        target["agentId"] = args.agent_id
    if args.raw_file:
        target["rawFile"] = args.raw_file.replace("\\", "/")
    if args.status == "done":
        target["completedAt"] = now_iso()
        target["error"] = None
    elif args.status == "failed":
        target["completedAt"] = now_iso()
        target["error"] = args.error or "(no error message provided)"
    elif args.status == "in-progress":
        target["startedAt"] = now_iso()
        target["error"] = None
    scope["updatedAt"] = now_iso()
    _write_json(scope_path, scope)

    manifest = _read_json(manifest_path)
    inv_step = manifest.setdefault("steps", {}).setdefault("investigation", {})
    # Recompute rollup counts.
    counts = {s: 0 for s in VALID_STATUSES}
    for s in sources:
        counts[s.get("status", "pending")] += 1
    inv_step["statusCounts"] = counts
    inv_step["sourceCount"] = len(sources)
    incomplete = counts["pending"] + counts["in-progress"]
    if incomplete == 0 and counts["done"] > 0 and inv_step.get("status") != "done":
        # All subagent runs landed; flag for synthesis. The synthesizer
        # script flips status to "done" once it succeeds.
        inv_step["status"] = "synthesizable"
    elif inv_step.get("status") in (None, "pending", "skipped"):
        inv_step["status"] = "in-progress"
    manifest["updatedAt"] = now_iso()
    _write_json(manifest_path, manifest)

    print(json.dumps({
        "ok": True,
        "source": args.source,
        "previous": prev,
        "status": args.status,
        "investigationStatus": inv_step["status"],
        "statusCounts": counts,
        "rawFile": target.get("rawFile"),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
