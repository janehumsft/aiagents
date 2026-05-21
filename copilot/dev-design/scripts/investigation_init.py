#!/usr/bin/env python3
"""
investigation_init.py - Open or resume an investigation for a dev-design
workspace.

Creates:
    <ws>/workspace/investigation/
        plan.md              # human-readable goals + per-source rationale
        scope.json           # machine-readable focus areas + source list
        raw/                 # subagent outputs (one .md per source)
        synth/               # final synthesized artifacts

Updates:
    manifest.steps.investigation = {"status": "in-progress", ...}

Sources are passed as repeatable --source flags. Each value uses one of:
    local:<id>:<path>           e.g. local:client:Q:/src/client
    github:<id>:<owner/repo>    e.g. github:service:myorg/service

Focus areas come from repeated --focus flags (free-form short strings).

Stdout is a JSON summary the agent uses to know which sources are pending
and which scoped-prompt entries to send to each subagent.

Exit codes:
    0  success (created or refreshed scope)
    2  workspace missing
    3  invalid --source / --focus argument
    4  investigation already in progress and --force not passed
"""
from __future__ import annotations
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

SECTION_IDS_TOUCHED = ["01-summary-and-goals", "03-scope", "05-implementation-phases", "06-tradeoffs", "07-telemetry"]


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "source"


def _parse_source(raw: str) -> dict:
    parts = raw.split(":", 2)
    if len(parts) != 3 or parts[0] not in {"local", "github"}:
        raise ValueError(
            f"bad --source value {raw!r}; expected 'local:<id>:<path>' or "
            f"'github:<id>:<owner/repo>'"
        )
    kind, ident, value = parts
    ident = _slug(ident)
    if kind == "local":
        return {
            "id": ident,
            "kind": "local",
            "name": ident,
            "path": value,
            "rawFile": f"raw/{ident}.md",
            "status": "pending",
            "agentId": None,
            "completedAt": None,
        }
    return {
        "id": ident,
        "kind": "github",
        "name": ident,
        "ref": value,
        "rawFile": f"raw/{ident}.md",
        "status": "pending",
        "agentId": None,
        "completedAt": None,
    }


PLAN_TEMPLATE = """# Investigation plan - {feature}

Created: {created}

## Why we're investigating

The user opted into investigation mode to ground the dev design in real
code rather than rely solely on a one-pager. This document captures the
plan; the actual findings will land in `synth/findings.md` and
`synth/work-breakdown.md` once subagent runs complete.

## Focus areas

{focus_block}

## Sources

{sources_block}

## Output map

Each subagent writes to its assigned file in `raw/`. Files must follow the
template in `prompts/investigation-subagent.md`:

- `## Summary`
- `## Key files & symbols`
- `## Proposed changes`
- `## Risks & unknowns`
- `## Citations`

`investigation_synthesize.py` aggregates the raw files into:

- `synth/findings.md` -- narrative cross-source summary
- `synth/work-breakdown.md` -- proposed work grouped by source + phase
- `synth/repos.json` -- machine-readable source list
- `synth/citations.json` -- every cited file / URL

The dev-design sections that get enriched after synthesis:
{touched}
"""


def render_plan(feature: str, focus: list[str], sources: list[dict]) -> str:
    if focus:
        focus_block = "\n".join(f"- {f}" for f in focus)
    else:
        focus_block = "_(none specified; subagents will infer from work-item title + summary)_"
    if sources:
        lines = []
        for s in sources:
            if s["kind"] == "local":
                lines.append(f"- **local** `{s['name']}` -> `{s['path']}` (writes `{s['rawFile']}`)")
            else:
                lines.append(f"- **github** `{s['name']}` -> `{s['ref']}` (writes `{s['rawFile']}`)")
        sources_block = "\n".join(lines)
    else:
        sources_block = "_(no sources configured yet; re-run investigation_init.py with --source ...)_"
    touched = "\n".join(f"- §{sid.split('-', 1)[0]} ({sid})" for sid in SECTION_IDS_TOUCHED)
    return PLAN_TEMPLATE.format(
        feature=feature,
        created=now_iso(),
        focus_block=focus_block,
        sources_block=sources_block,
        touched=touched,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", required=True)
    p.add_argument("--focus", action="append", default=[])
    p.add_argument("--source", action="append", default=[],
                   help="Repeatable. 'local:<id>:<path>' or 'github:<id>:<owner/repo>'.")
    p.add_argument("--max-parallel", type=int, default=4)
    p.add_argument("--areas-per-source", type=int, default=2)
    p.add_argument("--one-pager", default="",
                   help="Optional path to a one-pager markdown the agent should "
                        "cross-reference. Copied into inputs/ on first run.")
    p.add_argument("--force", action="store_true",
                   help="Reset scope.json + plan.md even if investigation is in progress.")
    args = p.parse_args()

    ws = Path(args.workspace).resolve()
    manifest_path = ws / "workspace" / "manifest.json"
    if not manifest_path.exists():
        print(json.dumps({"error": f"manifest not found at {manifest_path}"}), file=sys.stderr)
        return 2
    manifest = _read_json(manifest_path)

    inv_dir = ws / "workspace" / "investigation"
    raw_dir = inv_dir / "raw"
    synth_dir = inv_dir / "synth"
    scope_path = inv_dir / "scope.json"
    plan_path = inv_dir / "plan.md"

    try:
        sources = [_parse_source(s) for s in args.source]
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 3

    # Dedupe sources by id, last write wins.
    by_id: dict[str, dict] = {}
    for s in sources:
        by_id[s["id"]] = s
    sources = list(by_id.values())

    existing_status = (manifest.get("steps") or {}).get("investigation", {}).get("status")
    if scope_path.exists() and existing_status == "in-progress" and not args.force:
        # Merge: keep status of sources that match by id; append new ones.
        existing_scope = _read_json(scope_path)
        existing_sources = existing_scope.get("sources") or []
        merged: dict[str, dict] = {s["id"]: s for s in existing_sources}
        for s in sources:
            if s["id"] in merged:
                # Preserve runtime state; only update path/ref/name.
                m = merged[s["id"]]
                for k in ("kind", "path", "ref", "name", "rawFile"):
                    if k in s:
                        m[k] = s[k]
            else:
                merged[s["id"]] = s
        sources = list(merged.values())
        focus = list({*existing_scope.get("focusAreas", []), *args.focus})
        created = existing_scope.get("createdAt") or now_iso()
        merged_existing = True
    else:
        focus = list(args.focus)
        created = now_iso()
        merged_existing = False

    inv_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(exist_ok=True)
    synth_dir.mkdir(exist_ok=True)

    # Optional one-pager
    one_pager_dest = None
    if args.one_pager:
        src_op = Path(args.one_pager).resolve()
        if not src_op.exists():
            print(json.dumps({"error": f"--one-pager not found: {src_op}"}), file=sys.stderr)
            return 3
        one_pager_dest = ws / "workspace" / "inputs" / "one-pager.md"
        one_pager_dest.write_text(src_op.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

    scope = {
        "createdAt": created,
        "updatedAt": now_iso(),
        "focusAreas": focus,
        "budget": {
            "maxParallel": max(1, args.max_parallel),
            "areasPerSource": max(1, args.areas_per_source),
        },
        "sources": sources,
        "onePager": str(one_pager_dest.relative_to(ws)).replace("\\", "/") if one_pager_dest else None,
    }
    _write_json(scope_path, scope)

    feature = manifest.get("featureName") or manifest.get("slug") or "feature"
    plan_path.write_text(render_plan(feature, focus, sources), encoding="utf-8")

    steps = manifest.setdefault("steps", {})
    inv_step = steps.setdefault("investigation", {})
    inv_step["status"] = "in-progress"
    inv_step["openedAt"] = inv_step.get("openedAt") or now_iso()
    inv_step["focusAreas"] = focus
    inv_step["sourceCount"] = len(sources)
    manifest["updatedAt"] = now_iso()
    _write_json(manifest_path, manifest)

    summary = {
        "ok": True,
        "merged": merged_existing,
        "scopePath": str(scope_path),
        "planPath": str(plan_path),
        "focusAreas": focus,
        "sources": [
            {"id": s["id"], "kind": s["kind"],
             "target": s.get("path") or s.get("ref"),
             "status": s["status"], "rawFile": s["rawFile"]}
            for s in sources
        ],
        "budget": scope["budget"],
        "pendingCount": sum(1 for s in sources if s["status"] == "pending"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
