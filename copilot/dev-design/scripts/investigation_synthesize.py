#!/usr/bin/env python3
"""
investigation_synthesize.py - Aggregate raw subagent outputs into the
final investigation artifacts.

Reads:
    <ws>/workspace/investigation/scope.json
    <ws>/workspace/investigation/raw/*.md

Writes:
    <ws>/workspace/investigation/synth/findings.md
    <ws>/workspace/investigation/synth/work-breakdown.md
    <ws>/workspace/investigation/synth/repos.json
    <ws>/workspace/investigation/synth/citations.json

Each raw markdown file must contain these H2 sections (case-insensitive
match on the section title; order does not matter):

    ## Summary
    ## Key files & symbols    (or "Key files and symbols")
    ## Proposed changes
    ## Risks & unknowns       (or "Risks and unknowns")
    ## Citations

The Citations section is *required* to be non-empty (at least one line
that looks like a list item). This forces subagents to ground their claims.

Exit codes:
    0  success
    2  workspace / scope.json missing
    3  invalid raw file(s) - missing required section or empty citations.
       The stderr JSON lists every offending file + reason so the agent can
       re-prompt the relevant subagent.
    4  no done sources to synthesize
"""
from __future__ import annotations
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    ("summary", ["summary"]),
    ("key_files", ["key files & symbols", "key files and symbols"]),
    ("proposed", ["proposed changes"]),
    ("risks", ["risks & unknowns", "risks and unknowns"]),
    ("citations", ["citations"]),
]

H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
URL_RE = re.compile(r"https?://[\w./\-?=&%#:+,@~]+", re.IGNORECASE)
FILE_RE = re.compile(r"`([^`]+\.[A-Za-z0-9]{1,8}[^`]*)`")


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def parse_sections(text: str) -> dict[str, str]:
    """Split a raw markdown body at H2 boundaries, return {lowered_title: body}."""
    sections: dict[str, str] = {}
    matches = list(H2_RE.finditer(text))
    if not matches:
        return sections
    for i, m in enumerate(matches):
        title = m.group(1).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections[title] = body
    return sections


def validate_raw(path: Path) -> tuple[dict[str, str], list[str]]:
    """Return (parsed sections, list of problems). Empty list = valid."""
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {}, [f"could not read: {e}"]
    sections = parse_sections(text)
    resolved: dict[str, str] = {}
    for key, aliases in REQUIRED_SECTIONS:
        found = None
        for alias in aliases:
            if alias in sections:
                found = sections[alias]
                break
        if found is None:
            problems.append(f"missing required H2 section: '{aliases[0]}'")
        else:
            resolved[key] = found
    if "citations" in resolved:
        cit_lines = [
            ln for ln in resolved["citations"].splitlines()
            if ln.strip().startswith(("-", "*", "1.", "2.", "3.")) or ln.strip().startswith(tuple(f"{i}." for i in range(10)))
        ]
        # Also accept inline URLs anywhere in the section body
        has_url = bool(URL_RE.search(resolved["citations"]))
        if not cit_lines and not has_url:
            problems.append("citations section is empty or has no list items / URLs")
    return resolved, problems


def extract_citations(body: str) -> list[dict]:
    """Pull out individual citation lines, preserving the original text plus any URL."""
    items: list[dict] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        stripped = re.sub(r"^[-*]\s+", "", line)
        stripped = re.sub(r"^\d+\.\s+", "", stripped)
        if not stripped:
            continue
        url_match = URL_RE.search(stripped)
        file_match = FILE_RE.search(stripped)
        items.append({
            "text": stripped,
            "url": url_match.group(0) if url_match else None,
            "file": file_match.group(1) if file_match else None,
        })
    return items


FINDINGS_HEADER = """# Investigation findings - {feature}

Synthesized: {synthesized}

This document is a derived artifact. It is reconstructed from the raw
subagent outputs under `raw/` whenever `investigation_synthesize.py`
runs. To make corrections, edit the raw files (or re-run the relevant
subagent) and re-synthesize.

"""

WORK_BREAKDOWN_HEADER = """# Work breakdown - {feature}

Synthesized: {synthesized}

Proposed changes grouped by source. Each section is a verbatim copy of
the "Proposed changes" body from the corresponding raw subagent output.

"""


def build_findings(feature: str, raws: list[dict]) -> str:
    parts = [FINDINGS_HEADER.format(feature=feature, synthesized=now_iso())]
    parts.append("## Sources covered\n")
    for r in raws:
        parts.append(
            f"- **{r['source']}** ({r['kind']}) -- target: `{r['target']}` -- raw: `{r['rawFile']}`"
        )
    parts.append("")
    parts.append("## Per-source summaries\n")
    for r in raws:
        parts.append(f"### {r['source']} ({r['kind']})\n")
        parts.append(r["sections"].get("summary", "_(no summary)_"))
        parts.append("")
    parts.append("## Cross-source risks & unknowns\n")
    for r in raws:
        risks = r["sections"].get("risks", "").strip()
        if not risks:
            continue
        parts.append(f"### From {r['source']}\n")
        parts.append(risks)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def build_work_breakdown(feature: str, raws: list[dict]) -> str:
    parts = [WORK_BREAKDOWN_HEADER.format(feature=feature, synthesized=now_iso())]
    for r in raws:
        target = r["target"]
        parts.append(f"## {r['source']} ({r['kind']}: `{target}`)\n")
        proposed = r["sections"].get("proposed", "").strip()
        if proposed:
            parts.append(proposed)
        else:
            parts.append("_(no proposed changes reported)_")
        parts.append("")
        key_files = r["sections"].get("key_files", "").strip()
        if key_files:
            parts.append("**Key files & symbols touched**\n")
            parts.append(key_files)
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", required=True)
    p.add_argument("--force", action="store_true",
                   help="Re-synthesize even if step is already done.")
    p.add_argument("--allow-partial", action="store_true",
                   help="Synthesize over the subset of sources whose status is 'done', "
                        "ignoring pending/in-progress/failed entries.")
    args = p.parse_args()

    ws = Path(args.workspace).resolve()
    inv_dir = ws / "workspace" / "investigation"
    scope_path = inv_dir / "scope.json"
    manifest_path = ws / "workspace" / "manifest.json"
    if not scope_path.exists() or not manifest_path.exists():
        print(json.dumps({
            "error": "missing manifest or scope.json; run investigation_init.py first",
            "scopePath": str(scope_path),
            "manifestPath": str(manifest_path),
        }), file=sys.stderr)
        return 2

    manifest = _read_json(manifest_path)
    scope = _read_json(scope_path)
    sources = scope.get("sources") or []

    inv_step = (manifest.get("steps") or {}).get("investigation", {})
    if inv_step.get("status") == "done" and not args.force:
        print(json.dumps({
            "skipped": True,
            "reason": "investigation already synthesized; use --force to refresh",
        }))
        return 0

    eligible = [s for s in sources if s.get("status") == "done"]
    if not args.allow_partial:
        incomplete = [s for s in sources if s.get("status") in ("pending", "in-progress")]
        if incomplete:
            print(json.dumps({
                "error": "some sources are not yet done; pass --allow-partial to synthesize subset",
                "incomplete": [{"id": s["id"], "status": s["status"]} for s in incomplete],
            }), file=sys.stderr)
            return 4
    if not eligible:
        print(json.dumps({"error": "no completed sources to synthesize"}), file=sys.stderr)
        return 4

    # Validate every raw file and abort if any fail.
    problems: dict[str, list[str]] = {}
    raws: list[dict] = []
    for s in eligible:
        raw_path = inv_dir / s["rawFile"]
        sections, errs = validate_raw(raw_path)
        if errs:
            problems[s["id"]] = errs + [f"raw path: {raw_path}"]
            continue
        raws.append({
            "source": s["name"],
            "id": s["id"],
            "kind": s["kind"],
            "target": s.get("path") or s.get("ref"),
            "rawFile": s["rawFile"],
            "sections": sections,
            "rawPath": str(raw_path),
        })
    if problems:
        print(json.dumps({
            "error": "one or more raw files failed validation; re-prompt the subagent",
            "problems": problems,
        }, indent=2), file=sys.stderr)
        return 3

    synth_dir = inv_dir / "synth"
    synth_dir.mkdir(parents=True, exist_ok=True)

    feature = manifest.get("featureName") or "feature"
    findings_md = build_findings(feature, raws)
    work_md = build_work_breakdown(feature, raws)

    (synth_dir / "findings.md").write_text(findings_md, encoding="utf-8")
    (synth_dir / "work-breakdown.md").write_text(work_md, encoding="utf-8")

    repos = [
        {
            "id": r["id"], "name": r["source"], "kind": r["kind"],
            "target": r["target"], "rawFile": r["rawFile"],
        }
        for r in raws
    ]
    _write_json(synth_dir / "repos.json", repos)

    citations: list[dict] = []
    for r in raws:
        items = extract_citations(r["sections"].get("citations", ""))
        for item in items:
            citations.append({
                "source": r["source"],
                "sourceId": r["id"],
                "text": item["text"],
                "url": item["url"],
                "file": item["file"],
            })
    _write_json(synth_dir / "citations.json", citations)

    inv_step["status"] = "done"
    inv_step["synthesizedAt"] = now_iso()
    inv_step["partial"] = args.allow_partial
    inv_step["synthesizedSourceCount"] = len(raws)
    inv_step["citationCount"] = len(citations)
    # Mark dependent sections stale so the assemble step re-renders.
    for dep in ("sections.render", "assemble"):
        step = manifest.get("steps", {}).get(dep)
        if step and step.get("status") == "done":
            step["status"] = "stale"
    manifest["updatedAt"] = now_iso()
    _write_json(manifest_path, manifest)

    print(json.dumps({
        "ok": True,
        "synthesizedSources": [r["id"] for r in raws],
        "citationCount": len(citations),
        "findingsPath": str(synth_dir / "findings.md"),
        "workBreakdownPath": str(synth_dir / "work-breakdown.md"),
        "reposPath": str(synth_dir / "repos.json"),
        "citationsPath": str(synth_dir / "citations.json"),
        "partial": args.allow_partial,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
