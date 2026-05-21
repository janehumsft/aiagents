#!/usr/bin/env python3
"""
walker.py - Per-section progress tracker for the dev-design skill.

The walker tracks the status of each of the 11 template sections in the
workspace manifest (`manifest.sectionStatus`). The agent drives Q&A through
this tool so users can skip, defer, or come back to any section without
losing context.

Statuses:
    pending      - never started
    in-progress  - the agent is currently asking questions for this section
    deferred     - user asked to come back later (still counts as incomplete)
    skipped      - user explicitly chose to leave it as TODO markers
    done         - the fragment has been written

Subcommands:
    list        Print all sections + statuses + suggested next section
    next        Print the next section to work on (or none if all complete)
    set         Update one section's status
    show        Dump a single section's metadata + question bank
    summary     Compact JSON summary suitable for a final-step recap

Common args:
    --workspace <ws>    Path to the dev-design-* folder (required)

Examples:
    python walker.py list --workspace ./dev-design-12345-foo
    python walker.py set  --workspace ./dev-design-12345-foo \
        --section 01-summary-and-goals --status done
    python walker.py next --workspace ./dev-design-12345-foo

Exit codes:
    0  success
    2  workspace missing / manifest unreadable
    3  invalid arguments (bad section id or status)
"""
from __future__ import annotations
import argparse
import datetime
import json
import sys
from pathlib import Path

SECTION_IDS = [
    "00-preamble",
    "01-summary-and-goals",
    "02-signoffs",
    "03-scope",
    "04-feature-flags",
    "05-implementation-phases",
    "06-tradeoffs",
    "07-telemetry",
    "08-ownership",
    "09-test-scenarios",
    "10-appendix",
]

SECTION_TITLES = {
    "00-preamble": "Preamble (title + metadata)",
    "01-summary-and-goals": "Summary and Goals",
    "02-signoffs": "Signoffs",
    "03-scope": "Scope",
    "04-feature-flags": "Feature Flags",
    "05-implementation-phases": "Implementation Phases",
    "06-tradeoffs": "Tradeoffs",
    "07-telemetry": "Telemetry",
    "08-ownership": "Ownership",
    "09-test-scenarios": "Test Scenarios",
    "10-appendix": "Appendix",
}

REQUIRED_SECTIONS = {
    "00-preamble", "01-summary-and-goals", "05-implementation-phases",
    "09-test-scenarios",
}

STATUSES = {"pending", "in-progress", "deferred", "skipped", "done"}
INCOMPLETE_STATUSES = {"pending", "in-progress", "deferred"}


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _load_manifest(workspace: Path) -> tuple[dict, Path]:
    manifest_path = workspace / "workspace" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found at {manifest_path}")
    manifest = _read_json(manifest_path)
    section_status = manifest.setdefault(
        "sectionStatus", {sid: "pending" for sid in SECTION_IDS}
    )
    # Heal: ensure every section id exists in the map.
    for sid in SECTION_IDS:
        section_status.setdefault(sid, "pending")
    return manifest, manifest_path


def _next_section(section_status: dict) -> str | None:
    # Prefer pending in order, then deferred, then in-progress (resume).
    for sid in SECTION_IDS:
        if section_status.get(sid) == "pending":
            return sid
    for sid in SECTION_IDS:
        if section_status.get(sid) == "in-progress":
            return sid
    for sid in SECTION_IDS:
        if section_status.get(sid) == "deferred":
            return sid
    return None


def _progress_counts(section_status: dict) -> dict:
    counts = {s: 0 for s in STATUSES}
    for sid in SECTION_IDS:
        counts[section_status.get(sid, "pending")] += 1
    return counts


def _load_question_bank(skill_dir: Path) -> dict:
    path = skill_dir / "prompts" / "section-questions.json"
    if path.exists():
        try:
            return _read_json(path)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list(args) -> int:
    manifest, _ = _load_manifest(Path(args.workspace).resolve())
    section_status = manifest["sectionStatus"]
    sections = []
    for sid in SECTION_IDS:
        status = section_status.get(sid, "pending")
        sections.append({
            "id": sid,
            "title": SECTION_TITLES[sid],
            "required": sid in REQUIRED_SECTIONS,
            "status": status,
        })
    payload = {
        "workspace": str(Path(args.workspace).resolve()),
        "feature": manifest.get("featureName"),
        "slug": manifest.get("slug"),
        "sections": sections,
        "progress": _progress_counts(section_status),
        "next": _next_section(section_status),
        "totalSections": len(SECTION_IDS),
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_next(args) -> int:
    manifest, _ = _load_manifest(Path(args.workspace).resolve())
    sid = _next_section(manifest["sectionStatus"])
    if sid is None:
        print(json.dumps({"next": None, "done": True}))
        return 0
    bank = _load_question_bank(Path(__file__).parent.parent)
    payload = {
        "next": sid,
        "title": SECTION_TITLES[sid],
        "required": sid in REQUIRED_SECTIONS,
        "status": manifest["sectionStatus"].get(sid, "pending"),
        "questions": (bank.get(sid) or {}).get("questions", []),
        "done": False,
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_set(args) -> int:
    if args.section not in SECTION_IDS:
        print(json.dumps({
            "error": f"unknown section id: {args.section}",
            "validSections": SECTION_IDS,
        }), file=sys.stderr)
        return 3
    if args.status not in STATUSES:
        print(json.dumps({
            "error": f"unknown status: {args.status}",
            "validStatuses": sorted(STATUSES),
        }), file=sys.stderr)
        return 3

    workspace = Path(args.workspace).resolve()
    manifest, manifest_path = _load_manifest(workspace)
    prev = manifest["sectionStatus"].get(args.section, "pending")
    manifest["sectionStatus"][args.section] = args.status
    manifest["updatedAt"] = now_iso()

    # Roll up steps.sections.render when no section is incomplete.
    incomplete = [
        sid for sid in SECTION_IDS
        if manifest["sectionStatus"].get(sid) in INCOMPLETE_STATUSES
    ]
    render_step = manifest.setdefault("steps", {}).setdefault(
        "sections.render", {"status": "pending"}
    )
    if not incomplete:
        if render_step.get("status") != "done":
            render_step["status"] = "done"
            render_step["completedAt"] = now_iso()
            # Anything previously assembled is now stale.
            asm = manifest["steps"].get("assemble") or {}
            if asm.get("status") == "done":
                asm["status"] = "stale"
                manifest["steps"]["assemble"] = asm
    else:
        if render_step.get("status") == "done":
            render_step["status"] = "in-progress"
            render_step.pop("completedAt", None)
            asm = manifest["steps"].get("assemble") or {}
            if asm.get("status") == "done":
                asm["status"] = "stale"
                manifest["steps"]["assemble"] = asm

    _write_json(manifest_path, manifest)
    print(json.dumps({
        "ok": True,
        "section": args.section,
        "previous": prev,
        "status": args.status,
        "next": _next_section(manifest["sectionStatus"]),
        "progress": _progress_counts(manifest["sectionStatus"]),
    }))
    return 0


def cmd_show(args) -> int:
    if args.section not in SECTION_IDS:
        print(json.dumps({
            "error": f"unknown section id: {args.section}",
            "validSections": SECTION_IDS,
        }), file=sys.stderr)
        return 3
    manifest, _ = _load_manifest(Path(args.workspace).resolve())
    bank = _load_question_bank(Path(__file__).parent.parent)
    entry = bank.get(args.section) or {}
    fragment_path = (
        Path(args.workspace).resolve()
        / "workspace" / "sections" / f"{args.section}.md"
    )
    payload = {
        "id": args.section,
        "title": SECTION_TITLES[args.section],
        "required": args.section in REQUIRED_SECTIONS,
        "status": manifest["sectionStatus"].get(args.section, "pending"),
        "fragmentPath": str(fragment_path),
        "fragmentExists": fragment_path.exists(),
        "description": entry.get("description"),
        "seedSources": entry.get("seedSources", []),
        "questions": entry.get("questions", []),
        "renderNotes": entry.get("renderNotes"),
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_summary(args) -> int:
    manifest, _ = _load_manifest(Path(args.workspace).resolve())
    section_status = manifest["sectionStatus"]
    counts = _progress_counts(section_status)
    missing_required = [
        sid for sid in REQUIRED_SECTIONS
        if section_status.get(sid) in INCOMPLETE_STATUSES
    ]
    payload = {
        "feature": manifest.get("featureName"),
        "slug": manifest.get("slug"),
        "progress": counts,
        "complete": counts.get("done", 0) + counts.get("skipped", 0),
        "totalSections": len(SECTION_IDS),
        "missingRequired": sorted(missing_required),
        "renderStatus": (manifest.get("steps") or {}).get("sections.render", {}).get("status"),
        "assembleStatus": (manifest.get("steps") or {}).get("assemble", {}).get("status"),
    }
    print(json.dumps(payload, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    sub.add_parser("next")
    sub.add_parser("summary")

    sp_set = sub.add_parser("set")
    sp_set.add_argument("--section", required=True)
    sp_set.add_argument("--status", required=True)

    sp_show = sub.add_parser("show")
    sp_show.add_argument("--section", required=True)

    args = p.parse_args()
    try:
        if args.cmd == "list":
            return cmd_list(args)
        if args.cmd == "next":
            return cmd_next(args)
        if args.cmd == "set":
            return cmd_set(args)
        if args.cmd == "show":
            return cmd_show(args)
        if args.cmd == "summary":
            return cmd_summary(args)
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
