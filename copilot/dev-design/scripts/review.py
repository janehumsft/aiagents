#!/usr/bin/env python3
"""
review.py - Lint an existing dev-design workspace (Phase 8).

Reviews a workspace folder produced by init_workspace.py and reports any
issues that would block a healthy publish: missing required sections,
empty/placeholder sections, unresolved `<!-- TODO(dev-design): -->`
markers, unfilled template placeholders, malformed Mermaid diagrams,
stale assembler state, deferred/skipped sections, and the current
publish status.

Subcommands:

    lint --workspace <ws> [--json] [--strict] [--no-mermaid]
         [--only <check> ...] [--skip <check> ...]
        Run all checks (or the chosen subset). Exit code reflects the
        worst severity (0 clean, 2 warnings, 3 errors). --strict
        promotes warnings to errors.

    list-checks
        Print every check id with a one-line description.

Check IDs:

    SECTIONS_PRESENT      every expected section fragment file exists
    SECTIONS_NONEMPTY     each fragment has substantive content
                          (heading + non-comment body)
    TODOS_RESOLVED        no unresolved <!-- TODO(dev-design): ... --> markers
    PLACEHOLDERS_FILLED   no `[Bracketed Template Placeholders]` remain
                          inside the rendered .md or fragments
    MANIFEST_VALID        manifest.json parses and has required fields
    ASSEMBLE_FRESH        assemble.lastRenderedAt newer than the most
                          recent fragment mtime
    MERMAID_VALID         every .mmd under workspace/diagrams/ parses
    SECTION_STATUS        warn on deferred / skipped sections
    PUBLISH_STATUS        info on publish.ado / publish.pr current state

Severities:

    error   -> blocks (exit 3)
    warning -> visible but doesn't block by default (exit 2; --strict -> 3)
    info    -> shown only, exit 0

JSON output shape:

    {
      "workspace": "<abs path>",
      "summary": {"errors": N, "warnings": N, "info": N},
      "checks": [
        {"id": "...", "severity": "error",
         "message": "...", "location": "sections/01-...md:14"},
        ...
      ]
    }
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.resolve()
SKILL_DIR = SCRIPTS_DIR.parent

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

# Heuristic: any of these means "looks like a placeholder still"
PLACEHOLDER_PATTERNS = [
    r"\[Project/Feature Name\]",
    r"\[Phase Name\]",
    r"\[Team/Role\]",
    r"\[One-line description[^\]]*\]",
    r"\[Describe the current system[^\]]*\]",
    r"\[Reviewer[^\]]*\]",
    r"\[Owner[^\]]*\]",
    r"\[Service[^\]]*\]",
    r"\[Team/Service\]",
    r"\[Channel[^\]]*\]",
    r"\[Add or remove[^\]]*\]",
]
PLACEHOLDER_RE = re.compile("|".join(PLACEHOLDER_PATTERNS))

TODO_RE = re.compile(r"<!--\s*TODO\(dev-design\):[^>]*-->", re.IGNORECASE)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

CHECK_DESCRIPTIONS = {
    "SECTIONS_PRESENT": "every expected section fragment file exists",
    "SECTIONS_NONEMPTY": "each fragment has substantive content beyond the heading",
    "TODOS_RESOLVED": "no unresolved <!-- TODO(dev-design): --> markers",
    "PLACEHOLDERS_FILLED": "no [Bracketed Template Placeholders] remain",
    "MANIFEST_VALID": "manifest.json parses and has the required fields",
    "ASSEMBLE_FRESH": "assemble step is up to date with section fragments",
    "MERMAID_VALID": "every .mmd diagram parses",
    "SECTION_STATUS": "no sections left deferred/skipped silently",
    "PUBLISH_STATUS": "publish.ado / publish.pr current state",
}

ALL_CHECK_IDS = list(CHECK_DESCRIPTIONS.keys())


class Finding:
    __slots__ = ("check_id", "severity", "message", "location")

    def __init__(self, check_id: str, severity: str, message: str, location: str = ""):
        self.check_id = check_id
        self.severity = severity
        self.message = message
        self.location = location

    def to_dict(self) -> dict:
        out = {"id": self.check_id, "severity": self.severity, "message": self.message}
        if self.location:
            out["location"] = self.location
        return out


def _strip_comments(text: str) -> str:
    return HTML_COMMENT_RE.sub("", text)


def _is_substantive(text: str) -> bool:
    """True if a fragment has non-heading, non-comment, non-placeholder content."""
    stripped = _strip_comments(text)
    body_lines = []
    for raw in stripped.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith(">"):
            line = line.lstrip("> ").strip()
            if not line:
                continue
        body_lines.append(line)
    if not body_lines:
        return False
    joined = "\n".join(body_lines)
    placeholder_only = PLACEHOLDER_RE.sub("", joined).strip()
    return bool(placeholder_only)


def _section_path(ws: Path, sid: str) -> Path:
    return ws / "workspace" / "sections" / f"{sid}.md"


def check_manifest(ws: Path) -> tuple[list[Finding], dict | None]:
    manifest_path = ws / "workspace" / "manifest.json"
    if not manifest_path.exists():
        return (
            [Finding("MANIFEST_VALID", "error",
                     "manifest.json not found", str(manifest_path))],
            None,
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (
            [Finding("MANIFEST_VALID", "error",
                     f"manifest.json failed to parse: {exc}",
                     str(manifest_path))],
            None,
        )

    findings: list[Finding] = []
    for required in ("schemaVersion", "skillVersion", "slug", "steps", "sectionStatus"):
        if required not in manifest:
            findings.append(
                Finding("MANIFEST_VALID", "error",
                        f"manifest is missing required field '{required}'",
                        str(manifest_path))
            )
    return findings, manifest


def check_sections_present(ws: Path, manifest: dict) -> list[Finding]:
    findings: list[Finding] = []
    status_map = manifest.get("sectionStatus") or {}
    for sid in SECTION_IDS:
        path = _section_path(ws, sid)
        if path.exists():
            continue
        section_status = status_map.get(sid)
        if section_status == "skipped":
            findings.append(
                Finding("SECTIONS_PRESENT", "info",
                        f"section '{sid}' marked skipped (no fragment present)",
                        f"workspace/sections/{sid}.md")
            )
            continue
        # No fragment: section will render from the template, which is
        # almost certainly placeholder content. Flag as warning so the
        # walker can fill it.
        findings.append(
            Finding("SECTIONS_PRESENT", "warning",
                    f"section '{sid}' has no fragment; rendered doc will "
                    f"show the template's placeholder content",
                    f"workspace/sections/{sid}.md")
        )
    return findings


def check_sections_nonempty(ws: Path, manifest: dict) -> list[Finding]:
    findings: list[Finding] = []
    status_map = manifest.get("sectionStatus") or {}
    for sid in SECTION_IDS:
        path = _section_path(ws, sid)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        section_status = status_map.get(sid)
        if not _is_substantive(text):
            sev = "info" if section_status in ("skipped", "deferred") else "warning"
            findings.append(
                Finding("SECTIONS_NONEMPTY", sev,
                        f"section '{sid}' has no substantive content "
                        f"(only headings/comments/placeholders)",
                        f"workspace/sections/{sid}.md")
            )
    return findings


def check_todos(ws: Path) -> list[Finding]:
    findings: list[Finding] = []
    sections_dir = ws / "workspace" / "sections"
    if not sections_dir.exists():
        return findings
    for path in sorted(sections_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if TODO_RE.search(line):
                findings.append(
                    Finding("TODOS_RESOLVED", "warning",
                            f"unresolved TODO marker: {line.strip()[:120]}",
                            f"workspace/sections/{path.name}:{idx}")
                )
    return findings


def check_placeholders(ws: Path, manifest: dict) -> list[Finding]:
    findings: list[Finding] = []
    status_map = manifest.get("sectionStatus") or {}
    for sid in SECTION_IDS:
        path = _section_path(ws, sid)
        if not path.exists():
            continue
        if status_map.get(sid) in ("skipped",):
            continue
        text = path.read_text(encoding="utf-8")
        stripped = _strip_comments(text)
        for idx, line in enumerate(stripped.splitlines(), start=1):
            m = PLACEHOLDER_RE.search(line)
            if not m:
                continue
            findings.append(
                Finding("PLACEHOLDERS_FILLED", "warning",
                        f"placeholder '{m.group(0)}' left in section "
                        f"'{sid}'",
                        f"workspace/sections/{path.name}:{idx}")
            )
    return findings


def check_assemble_freshness(ws: Path, manifest: dict) -> list[Finding]:
    findings: list[Finding] = []
    step = (manifest.get("steps") or {}).get("assemble") or {}
    status = step.get("status")
    if status != "done":
        findings.append(
            Finding("ASSEMBLE_FRESH", "warning",
                    f"assemble step is '{status or 'pending'}'; "
                    f"run assemble.py to refresh the rendered .md")
        )
        return findings
    output_path_str = step.get("outputPath")
    if not output_path_str:
        findings.append(
            Finding("ASSEMBLE_FRESH", "warning",
                    "assemble step has no recorded outputPath")
        )
        return findings
    output_path = Path(output_path_str)
    if not output_path.exists():
        findings.append(
            Finding("ASSEMBLE_FRESH", "error",
                    f"rendered .md is missing: {output_path}",
                    str(output_path))
        )
        return findings
    rendered_mtime = output_path.stat().st_mtime
    sections_dir = ws / "workspace" / "sections"
    newer = []
    if sections_dir.exists():
        for path in sections_dir.glob("*.md"):
            if path.stat().st_mtime > rendered_mtime + 1:
                newer.append(path.name)
    if newer:
        findings.append(
            Finding("ASSEMBLE_FRESH", "warning",
                    f"{len(newer)} fragment(s) edited since last "
                    f"assemble ({', '.join(sorted(newer))}); re-run "
                    f"assemble.py",
                    str(output_path))
        )
    return findings


def check_mermaid(ws: Path) -> list[Finding]:
    findings: list[Finding] = []
    diagrams_dir = ws / "workspace" / "diagrams"
    if not diagrams_dir.exists():
        return findings
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        import mermaid_draft  # noqa: WPS433
    except ImportError:
        findings.append(
            Finding("MERMAID_VALID", "info",
                    "mermaid_draft module unavailable; skipped mermaid lint")
        )
        return findings
    finally:
        if str(SCRIPTS_DIR) in sys.path:
            try:
                sys.path.remove(str(SCRIPTS_DIR))
            except ValueError:
                pass
    for path in sorted(diagrams_dir.glob("*.mmd")):
        errors = mermaid_draft.validate_file(path)
        for err in errors:
            findings.append(
                Finding("MERMAID_VALID", "error",
                        err,
                        f"workspace/diagrams/{path.name}")
            )
    return findings


def check_section_status(manifest: dict) -> list[Finding]:
    findings: list[Finding] = []
    status_map = manifest.get("sectionStatus") or {}
    for sid, status in status_map.items():
        if status == "deferred":
            findings.append(
                Finding("SECTION_STATUS", "warning",
                        f"section '{sid}' is deferred; come back and "
                        f"answer the remaining questions before publishing")
            )
        elif status == "skipped":
            findings.append(
                Finding("SECTION_STATUS", "info",
                        f"section '{sid}' was skipped")
            )
    return findings


def check_publish_status(manifest: dict) -> list[Finding]:
    findings: list[Finding] = []
    steps = manifest.get("steps") or {}
    for key in ("publish.ado", "publish.pr"):
        step = steps.get(key) or {}
        status = step.get("status", "pending")
        if status == "pending":
            findings.append(
                Finding("PUBLISH_STATUS", "info",
                        f"{key}: not yet attempted")
            )
        elif status == "skipped":
            reason = step.get("reason") or "(no reason recorded)"
            findings.append(
                Finding("PUBLISH_STATUS", "info",
                        f"{key}: skipped — {reason}")
            )
        elif status == "done":
            url = step.get("url") or step.get("prUrl") or ""
            suffix = f" → {url}" if url else ""
            findings.append(
                Finding("PUBLISH_STATUS", "info",
                        f"{key}: done{suffix}")
            )
        else:
            findings.append(
                Finding("PUBLISH_STATUS", "info",
                        f"{key}: status={status}")
            )
    return findings


def run_lint(ws: Path, enabled: set[str], skip_mermaid: bool) -> list[Finding]:
    findings: list[Finding] = []

    manifest_findings, manifest = check_manifest(ws)
    if "MANIFEST_VALID" in enabled:
        findings.extend(manifest_findings)
    if manifest is None:
        return findings  # cannot continue without manifest

    if "SECTIONS_PRESENT" in enabled:
        findings.extend(check_sections_present(ws, manifest))
    if "SECTIONS_NONEMPTY" in enabled:
        findings.extend(check_sections_nonempty(ws, manifest))
    if "TODOS_RESOLVED" in enabled:
        findings.extend(check_todos(ws))
    if "PLACEHOLDERS_FILLED" in enabled:
        findings.extend(check_placeholders(ws, manifest))
    if "ASSEMBLE_FRESH" in enabled:
        findings.extend(check_assemble_freshness(ws, manifest))
    if "MERMAID_VALID" in enabled and not skip_mermaid:
        findings.extend(check_mermaid(ws))
    if "SECTION_STATUS" in enabled:
        findings.extend(check_section_status(manifest))
    if "PUBLISH_STATUS" in enabled:
        findings.extend(check_publish_status(manifest))

    return findings


def render_human(ws: Path, findings: list[Finding]) -> str:
    by_sev = {"error": [], "warning": [], "info": []}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f)

    lines = [f"dev-design review: {ws}", "=" * 40]
    summary = (
        f"errors: {len(by_sev['error'])}  "
        f"warnings: {len(by_sev['warning'])}  "
        f"info: {len(by_sev['info'])}"
    )
    lines.append(summary)
    lines.append("")

    for sev, prefix in (("error", "✗"), ("warning", "⚠"), ("info", "•")):
        bucket = by_sev.get(sev, [])
        if not bucket:
            continue
        lines.append(f"{prefix} {sev.upper()} ({len(bucket)})")
        for f in bucket:
            tail = f"  ({f.location})" if f.location else ""
            lines.append(f"  - [{f.check_id}] {f.message}{tail}")
        lines.append("")

    if not findings:
        lines.append("✓ No findings. Workspace looks healthy.")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd")

    lint = sub.add_parser("lint", help="Lint a workspace")
    lint.add_argument("--workspace", required=True,
                      help="Path to the dev-design-<id>-<slug> folder")
    lint.add_argument("--json", action="store_true",
                      help="Emit JSON instead of human-readable output")
    lint.add_argument("--strict", action="store_true",
                      help="Promote warnings to errors (exit 3 if any)")
    lint.add_argument("--no-mermaid", action="store_true",
                      help="Skip Mermaid diagram validation")
    lint.add_argument("--only", action="append", default=[],
                      help="Run only this check (repeatable)")
    lint.add_argument("--skip", action="append", default=[],
                      help="Skip this check (repeatable)")

    sub.add_parser("list-checks", help="Print every check id with a description")

    args = p.parse_args()
    if args.cmd is None:
        p.print_help()
        return 0

    if args.cmd == "list-checks":
        for cid in ALL_CHECK_IDS:
            print(f"  {cid:<22} {CHECK_DESCRIPTIONS[cid]}")
        return 0

    # cmd == "lint"
    ws = Path(args.workspace).resolve()
    if not ws.exists():
        print(json.dumps({"error": "workspace not found", "path": str(ws)}),
              file=sys.stderr)
        return 2

    only = set(c.upper() for c in (args.only or []))
    skip = set(c.upper() for c in (args.skip or []))
    for c in only | skip:
        if c not in ALL_CHECK_IDS:
            print(json.dumps({"error": f"unknown check id: {c}",
                              "available": ALL_CHECK_IDS}), file=sys.stderr)
            return 2

    if only:
        enabled = only
    else:
        enabled = set(ALL_CHECK_IDS) - skip

    findings = run_lint(ws, enabled, skip_mermaid=args.no_mermaid)

    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    n_info = sum(1 for f in findings if f.severity == "info")

    if args.json:
        payload = {
            "workspace": str(ws),
            "summary": {"errors": n_err, "warnings": n_warn, "info": n_info},
            "checks": [f.to_dict() for f in findings],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_human(ws, findings), end="")

    if n_err:
        return 3
    if n_warn and args.strict:
        return 3
    if n_warn:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
