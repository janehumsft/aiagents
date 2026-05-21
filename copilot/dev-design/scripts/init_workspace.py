#!/usr/bin/env python3
"""
init_workspace.py — Create a fresh dev-design workspace folder.

Creates:
    <out-dir>/dev-design[-<id>]-<slug>/
        README.md
        workspace/
            manifest.json
            inputs/
                answers.json
                notes.md
            sections/        # empty; populated by the skill
            investigation/   # empty; populated by Phase 5 only

On success prints a single JSON object to stdout:
    {"workspace": "<abs path>", "slug": "<slug>", "folder": "<folder name>"}

Exit codes:
    0  success
    2  workspace already exists (use --force to overwrite)
"""
from __future__ import annotations
import argparse
import datetime
import json
import re
import sys
import unicodedata
from pathlib import Path

SCHEMA_VERSION = 1
SKILL_VERSION = "0.9.0"

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


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "untitled"


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


WORKSPACE_README = """# Dev Design workspace — {feature}

* Slug: `{slug}`
* Work item: `{work_item}`

This folder was created by the **dev-design** Copilot CLI skill. It contains
all inputs, investigation findings, and rendered section fragments that
combine into `dev-design-*.md` at the root of this folder.

## Source of truth

`workspace/sections/*.md` is authoritative. The `.md` at the top of this
folder is a **generated artifact** — re-running the assembler always
reproduces it from the sections. **Edit fragments, not the .md.**

## Layout

```
workspace/
├── manifest.json        # state and step tracking
├── inputs/
│   ├── answers.json     # structured Q&A answers
│   ├── notes.md         # freeform notes
│   ├── work-item.json   # ADO work item (Phase 2)
│   ├── repo-scan.json   # repo scan results (Phase 3, optional)
│   └── artifacts/       # uploaded artifacts (one-pagers, screenshots, WIP docs)
├── investigation/       # Phase 5 outputs (only if opt-in)
└── sections/
    ├── 00-preamble.md
    ├── 01-summary-and-goals.md
    ├── ... etc ...
    └── 10-appendix.md
```

## Resume

Re-invoke the dev-design skill from the parent folder of this workspace and
it will detect the existing state from `manifest.json` and offer to resume,
re-render, or start fresh.
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", required=True, help="Parent dir for the workspace folder (typically cwd)")
    p.add_argument("--feature-name", required=True, help="Human-readable feature/project name")
    p.add_argument("--work-item-id", default="", help="Azure DevOps work item ID (optional)")
    p.add_argument("--work-item-url", default="", help="Azure DevOps work item URL (optional)")
    p.add_argument("--work-item-title", default="", help="ADO work item title (optional; defaults to feature-name)")
    p.add_argument("--slug", default="", help="Override slug (auto-derived from feature-name if omitted)")
    p.add_argument(
        "--authoring-mode", default="", choices=["", "infer", "detailed"],
        help="Authoring mode: 'infer' (fast, agent drafts each section then asks one quick confirmation per section) "
             "or 'detailed' (slow, walks every question). Leave empty to decide interactively."
    )
    p.add_argument("--force", action="store_true", help="Overwrite existing workspace folder")
    args = p.parse_args()

    slug = args.slug.strip() or slugify(args.feature_name)
    folder_name = (
        f"dev-design-{args.work_item_id}-{slug}" if args.work_item_id else f"dev-design-{slug}"
    )

    out_dir = Path(args.out_dir).resolve()
    ws = out_dir / folder_name

    if ws.exists():
        if not args.force:
            print(json.dumps({"error": "workspace exists", "path": str(ws)}))
            return 2
        import shutil
        shutil.rmtree(ws)

    (ws / "workspace" / "inputs").mkdir(parents=True, exist_ok=True)
    (ws / "workspace" / "inputs" / "artifacts").mkdir(parents=True, exist_ok=True)
    (ws / "workspace" / "sections").mkdir(parents=True, exist_ok=True)
    (ws / "workspace" / "investigation").mkdir(parents=True, exist_ok=True)

    work_item: dict = {}
    if args.work_item_id or args.work_item_url:
        work_item = {
            "id": args.work_item_id,
            "url": args.work_item_url,
            "title": args.work_item_title or args.feature_name,
        }

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "skillVersion": SKILL_VERSION,
        "featureName": args.feature_name,
        "slug": slug,
        "workItem": work_item,
        "authoringMode": args.authoring_mode or "",
        "complexityProfile": {
            "value": "",
            "source": "",
            "confirmed": False,
            "rationale": "",
        },
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "steps": {
            "inputs.artifacts":         {"status": "pending"},
            "inputs.authoringMode":     {"status": "done" if args.authoring_mode else "pending"},
            "inputs.qna":               {"status": "pending"},
            "inputs.workItem":          {"status": "pending" if args.work_item_id else "skipped"},
            "inputs.repoScan":          {"status": "pending"},
            "inputs.complexity":        {"status": "pending"},
            "investigation":            {"status": "pending"},
            "diagrams.draft":           {"status": "pending"},
            "sections.render":          {"status": "pending"},
            "assemble":                 {"status": "pending"},
            "publish.ado":              {"status": "pending"},
            "publish.pr":               {"status": "pending"},
        },
        "sectionStatus": {sid: "pending" for sid in SECTION_IDS},
        "warnings": [],
    }

    (ws / "workspace" / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    answers = {
        "featureName": args.feature_name,
        "summary": "",
        "phases": [],
        "reviewers": [],
        "areaPath": "",
        "incidentRoute": "",
        "inScope": [],
        "outOfScope": [],
        "featureFlags": [],
        "tradeoffs": [],
        "testScenarios": [],
        "artifacts": [],
    }
    (ws / "workspace" / "inputs" / "answers.json").write_text(
        json.dumps(answers, indent=2) + "\n", encoding="utf-8"
    )

    (ws / "workspace" / "inputs" / "notes.md").write_text(
        "<!-- Freeform notes. Paste anything here that the skill should know about. -->\n",
        encoding="utf-8",
    )

    (ws / "README.md").write_text(
        WORKSPACE_README.format(
            feature=args.feature_name,
            work_item=args.work_item_id or "(none)",
            slug=slug,
        ),
        encoding="utf-8",
    )

    print(json.dumps({"workspace": str(ws), "slug": slug, "folder": folder_name}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
