#!/usr/bin/env python3
"""
assemble.py — Deterministic assembler for dev-design docs.

Reads:
    <template>                                  (skill's template.md)
    <workspace>/workspace/manifest.json
    <workspace>/workspace/sections/NN-*.md      (fragment per top-level section)

Writes:
    <workspace>/dev-design-[<id>-]<slug>.md     (the assembled document)
    <workspace>/workspace/manifest.json         (updated steps.assemble entry)

Fragment naming convention:
    00-preamble.md          → title + metadata block (replaces everything
                              before "## 1. ...")
    NN-<anything>.md        → replaces template's "## N. ..." section
                              (N is 01..10, zero-padded).

Each fragment that targets a numbered section MUST start with its
"## N. <title>" heading; the assembler substitutes the whole section
atomically. Fragments not provided fall back to the template's original
content, preserving the structure exactly.

A fragment may opt the section OUT of the assembled document by
containing the marker `<!-- OMIT SECTION -->` anywhere in its body.
When that marker is present the assembler emits nothing for the
section (no heading, no body, no template fallback). Use this when the
user has no input for an optional section and you want the final doc
to skip it cleanly rather than render placeholder boilerplate.

Exit codes:
    0  success
    2  malformed workspace or fragments
"""
from __future__ import annotations
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

BANNER = (
    "<!-- GENERATED FILE. Edit workspace/sections/*.md and re-render "
    "with the dev-design skill. -->\n\n"
)

OMIT_MARKER = "<!-- OMIT SECTION -->"

SECTION_HEADING_RE = re.compile(r"^## (\d+)\.\s", re.MULTILINE)
FRAGMENT_NAME_RE = re.compile(r"^(\d{2})-")


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def split_template(text: str):
    """Return (preamble_text, [(section_num:int, section_text:str), ...])."""
    matches = list(SECTION_HEADING_RE.finditer(text))
    if not matches:
        return text, []
    preamble = text[: matches[0].start()]
    sections = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((int(m.group(1)), text[start:end]))
    return preamble, sections


def load_fragments(sections_dir: Path):
    """Return dict {section_index: fragment_text}. Preamble lives at index 0."""
    out = {}
    if not sections_dir.exists():
        return out
    for f in sorted(sections_dir.glob("*.md")):
        m = FRAGMENT_NAME_RE.match(f.name)
        if not m:
            continue
        key = int(m.group(1))
        out[key] = f.read_text(encoding="utf-8")
    return out


def assemble(template_path: Path, workspace_dir: Path, *, check_only: bool = False) -> Path:
    template_text = template_path.read_text(encoding="utf-8")
    manifest_path = workspace_dir / "workspace" / "manifest.json"
    sections_dir = workspace_dir / "workspace" / "sections"

    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found at {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    preamble, template_sections = split_template(template_text)
    fragments = load_fragments(sections_dir)

    parts = []

    if 0 in fragments:
        parts.append(fragments[0].rstrip() + "\n")
    else:
        parts.append(preamble.rstrip() + "\n")

    for sec_num, default_text in template_sections:
        if sec_num in fragments:
            frag = fragments[sec_num]
            if OMIT_MARKER in frag:
                continue
            expected = f"## {sec_num}."
            first_line = frag.lstrip().split("\n", 1)[0]
            if not first_line.startswith(expected):
                raise ValueError(
                    f"Fragment {sections_dir}/{sec_num:02d}-*.md must start with '{expected} ...'; "
                    f"got: {first_line!r}"
                )
            parts.append(frag.rstrip() + "\n")
        else:
            parts.append(default_text.rstrip() + "\n")

    output = BANNER + "\n".join(parts).rstrip() + "\n"

    work_item = manifest.get("workItem") or {}
    wi_id = (work_item.get("id") or "").strip()
    slug = manifest["slug"]
    out_name = f"dev-design-{wi_id}-{slug}.md" if wi_id else f"dev-design-{slug}.md"
    out_path = workspace_dir / out_name

    if check_only:
        existing = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        if existing != output:
            raise ValueError(
                f"rendered output differs from existing {out_path.name}; "
                f"run assemble.py without --check to refresh"
            )
        return out_path

    out_path.write_text(output, encoding="utf-8")

    manifest.setdefault("steps", {})["assemble"] = {
        "status": "done",
        "lastRenderedAt": now_iso(),
        "outputPath": str(out_path.resolve()),
        "fragmentsUsed": sorted(fragments.keys()),
    }
    manifest["updatedAt"] = now_iso()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return out_path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", required=True, help="Path to the dev-design-<id>-<slug> folder")
    p.add_argument("--template", required=True, help="Path to template.md (in the skill folder)")
    p.add_argument("--check", action="store_true",
                   help="Verify the existing rendered .md matches what assemble would produce, "
                        "without writing anything. Exit 2 if drift detected.")
    args = p.parse_args()

    try:
        out_path = assemble(
            Path(args.template).resolve(),
            Path(args.workspace).resolve(),
            check_only=args.check,
        )
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2

    if args.check:
        print(json.dumps({"check": "ok", "output": str(out_path)}))
    else:
        print(json.dumps({"output": str(out_path)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
