# dev-design — GitHub Copilot CLI skill

An interactive Copilot CLI skill that walks you through authoring a **Dev
Design** markdown document for a feature tracked in Azure DevOps. All inputs
and rendered section fragments are persisted in a **workspace folder** so
sessions are resumable and the document can be deterministically
reconstructed at any time. The assembled `.md` lives at the root of the
workspace folder.

> This is **Phase 8 — Polish & teamability (review mode + examples + installers)**.
> The skill now ships with a `review.py` linter that flags missing sections,
> unresolved TODOs, unfilled placeholders, stale assembler state, and
> malformed Mermaid diagrams; cross-platform `install.ps1` / `install.sh`
> one-line installers; a filled `examples/filled-example/` reference
> workspace that passes `review.py` cleanly; a `--quick` flag on the smoke
> test for fast pre-commit feedback; a `--check` flag on `assemble.py` for
> detecting drift; and a `CONTRIBUTING.md` for teammates. Phases 1-7 still
> apply. **This is the final shipped phase.**

> **Procedure update (post-Phase-8, v0.9):** SKILL.md is the authoritative
> procedure. Recent tweaks: (1) an up-front **authoring mode** prompt
> (`infer` for fast section-by-section drafts with one short confirmation
> each, vs `detailed` for full Q&A); (2) an up-front **artifact upload**
> step — drop local files (PM one-pager, Figma screenshots, WIP dev
> design, RFCs) into `workspace/inputs/artifacts/` and the agent uses
> them as suggested-default sources. Images and `.docx` (best-effort
> via optional `python-docx`) are supported alongside plain text /
> markdown; local files only — online doc links are unreliable. (3) The
> **"Phases" concept is optional** — the skill infers a
> `complexityProfile` (`simple` vs `phased`) from the gathered context
> and confirms it with the user; simple designs render §5 as a flat
> `Implementation` block (no phase H3s) and §9 as a single scenario
> table. (4) **Repo scan is opt-in only** — the skill no longer
> auto-scans; it asks once whether there's specific code to look at and
> only reads what the user names. CODEOWNERS and telemetry-event call
> sites are **no longer scanned at all** — owners, incident routes,
> flag names, and telemetry event names are user-supplied only. (5)
> The telemetry baselines step (Kusto / App Insights probe) has been
> retired with the telemetry scanning.
>
> Carried over from Phase 8: fragments are succinct and source-only; optional
> sections can opt out via `<!-- OMIT SECTION -->`; ADO fetch, PR review,
> and publishing remain inline `az` / `git` / `gh` invocations with explicit
> user confirmation. See `SKILL.md` for the full procedure.

## What you get

- A consistent dev-design template, filled in interactively, with greppable
  `<!-- TODO(dev-design): ... -->` markers on anything you skip.
- A workspace folder per feature that captures **every** input,
  intermediate state, and rendered fragment — handy for resuming sessions
  and for handing off to teammates or subagents.
- A deterministic Python assembler: the final `.md` is always reproducible
  from the workspace.

## Install

The skill is a self-contained folder. The fastest path is the bundled
installer (Phase 8):

### One-line install (recommended)

```powershell
# Windows / PowerShell
pwsh -File .\install.ps1 -Force -Smoke

# macOS / Linux
./install.sh --force --smoke
```

Both installers verify Python, copy the folder to
`~/.copilot/skills/dev-design`, scrub `__pycache__`, and (with `-Smoke`
/ `--smoke`) run the full smoke test to verify the install. Add
`-Quick` / `--quick` for fast pre-commit verification.

### Manual install

If you'd rather skip the installer:

#### Windows (PowerShell)

```powershell
$dest = "$HOME\.copilot\skills\dev-design"
New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse <path-to-this-folder> $dest
```

#### macOS / Linux

```bash
mkdir -p ~/.copilot/skills
rm -rf ~/.copilot/skills/dev-design
cp -R <path-to-this-folder> ~/.copilot/skills/dev-design
```

### Prerequisites

- **Python 3.8+** on `PATH` (used by the workspace init + assembler scripts).
  The skill also works without Python via an inline-assembly fallback, but
  re-renders are not guaranteed to be byte-identical.
- **Azure CLI (`az`) 2.30+** with the `azure-devops` extension, for the
  optional ADO work-item fetch and ADO publishing (Steps 1.5 and 6).
  Install with:
  ```bash
  az extension add --name azure-devops
  az login
  az devops configure --defaults organization=https://dev.azure.com/<your-org> project=<your-project>
  ```
  The agent probes for these inline and surfaces the exact remediation
  command if anything is missing. ADO integration is optional — the
  skill works fine without it (you just answer the questions manually).
- **GitHub CLI (`gh`)** for the optional Step 6 PR publish path.
  Authenticate once with `gh auth login`. If `gh` isn't installed, the
  agent marks the PR step `skipped` with the install hint and the skill
  continues; the ADO publish path works without `gh`.
- **ADO write access** for the optional Step 6 ADO publish path. The
  agent piggybacks on your `az login` token; no PAT needed for the
  default modes. Falls back from `attachment` to `comment` if the org
  disables attachments (403).
- **`python-docx` (optional)** for reading `.docx` files in the
  Step 1.1 artifact upload. Install with `pip install python-docx` if
  you commonly hand the skill PM one-pagers as Word docs. Without it,
  the skill asks you to paste the contents instead or export the
  document to `.md` / `.txt`. Plain images (`.png` / `.jpg` etc.) and
  text / markdown work out of the box.
- **Serena MCP (optional but strongly recommended)** for the repo read
  (Step 1.7) and investigation mode (Step 1.8). Serena's symbol-aware
  tools (`find_symbol`, `get_symbols_overview`, `find_referencing_symbols`)
  are dramatically more accurate than regex sweeps and cost fewer
  tokens — especially on large or unfamiliar codebases. Install once,
  globally:
  ```bash
  # 1. install uv (https://docs.astral.sh/uv/getting-started/installation/)
  # 2. install Serena
  uv tool install -p 3.13 serena-agent@latest --prerelease=allow
  serena init
  # 3. register Serena as an MCP server in Copilot CLI
  copilot
  > /mcp                                    # add a server pointing at `serena start-mcp-server`
  > /exit                                   # then restart so the tools load
  ```
  The skill detects Serena automatically and falls back to built-in
  `grep` / `glob` / `view` when it's not available — so this is not
  a hard prerequisite. If a teammate starts the skill without Serena,
  Step 1.7 will offer to defer the repo scan so they can install and
  re-run. **MCP servers in Copilot CLI are loaded at session startup**;
  installing mid-session requires restarting `copilot` before the
  Serena tools become callable.

### Verify

```
copilot
> /skills
```

You should see `dev-design` listed. Then invoke it with any of:

- "Use the dev-design skill to draft an architecture doc for my new feature."
- "Fill out a dev design doc for ADO #12345."
- "Resume my dev design."

Optionally run the smoke test to validate the helpers:

```bash
python ~/.copilot/skills/dev-design/scripts/smoke_test.py
```

## Workspace layout

Every run materializes (or resumes) a folder shaped like this in the cwd:

```
./dev-design-<id>-<slug>/
├── dev-design-<id>-<slug>.md          # ⚠️ generated; do not hand-edit
├── README.md                          # workspace-specific quick reference
└── workspace/
    ├── manifest.json                  # state + step tracking (incl. authoringMode + complexityProfile)
    ├── inputs/
    │   ├── answers.json               # structured Q&A answers
    │   ├── notes.md                   # freeform notes you can drop in
    │   ├── work-item.json             # ADO work item (Phase 2)
    │   ├── repo-scan.json             # opt-in repo scan results (Phase 3)
    │   ├── one-pager.md               # optional, Phase 5
    │   └── artifacts/                 # uploaded artifacts (Step 1.1)
    │       ├── artifacts-index.json   # one entry per uploaded file
    │       ├── <name>.<ext>           # copied verbatim (incl. images)
    │       └── <name>.summary.md      # extracted text + agent summary
    ├── diagrams/                      # per-phase mermaid skeletons (phased)
    │   ├── diagrams.json              # or `implementation.mmd` (simple)
    │   └── phase-<N>-<slug>.mmd
    ├── investigation/                 # Phase 5 outputs (opt-in only)
    │   ├── plan.md                    # what is being investigated and why
    │   ├── scope.json                 # focus areas + per-source status
    │   ├── raw/                       # one markdown report per subagent
    │   └── synth/
    │       ├── findings.md            # narrative cross-source summary
    │       ├── work-breakdown.md      # proposed changes grouped by source
    │       ├── repos.json             # canonical source list
    │       └── citations.json         # every cited file / URL
    └── sections/
        ├── 00-preamble.md             # `# Dev Design: ...` + metadata
        ├── 01-summary-and-goals.md
        ├── 02-signoffs.md
        ├── 03-scope.md
        ├── 04-feature-flags.md
        ├── 05-implementation-phases.md
        ├── 06-tradeoffs.md
        ├── 07-telemetry.md
        ├── 08-ownership.md
        ├── 09-test-scenarios.md
        └── 10-appendix.md
```

### Source of truth

**`workspace/sections/*.md` is authoritative.** The rendered `.md` at the
top of the workspace is a derived artifact. Editing the `.md` directly is
discouraged — your edits get clobbered on the next re-render. Edit the
section fragments instead, then ask the skill to re-render (or invoke the
assembler directly).

### Resume

Re-invoke the skill from the parent folder of an existing workspace. It
detects the `manifest.json`, then offers:

- **Resume** — pick up at the first incomplete step.
- **Re-render only** — rebuild the `.md` from current fragments and exit.
- **Start fresh** — archive the existing folder to `*.bak-<timestamp>` and
  start over.

### `manifest.json` shape (v1)

```json
{
  "schemaVersion": 1,
  "skillVersion": "0.9.0",
  "featureName": "...",
  "slug": "...",
  "workItem": { "id": "12345", "url": "...", "title": "..." },
  "authoringMode": "infer",
  "complexityProfile": {
    "value": "simple",
    "source": "inferred",
    "confirmed": true,
    "rationale": "Single-package change, 4 files in the PR diff, no rollout dependencies."
  },
  "createdAt": "2026-05-13T19:00:00Z",
  "updatedAt": "2026-05-13T19:42:00Z",
  "steps": {
    "inputs.artifacts":     { "status": "done",    "completedAt": "...", "count": 2 },
    "inputs.authoringMode": { "status": "done",    "completedAt": "..." },
    "inputs.qna":           { "status": "done",    "completedAt": "..." },
    "inputs.workItem":      { "status": "done",    "completedAt": "...", "id": "12345" },
    "inputs.repoScan":      { "status": "skipped", "reason": "no relevant code" },
    "inputs.complexity":    { "status": "done",    "completedAt": "..." },
    "investigation":        { "status": "pending" },
    "sections.render":      { "status": "done",    "completedAt": "..." },
    "assemble":             { "status": "done",    "lastRenderedAt": "...",
                              "outputPath": "...", "fragmentsUsed": [0,1,2,...] }
  },
  "sectionStatus": {
    "00-preamble": "done",
    "01-summary-and-goals": "done",
    "02-signoffs": "deferred",
    "03-scope": "skipped",
    "04-feature-flags": "done",
    "05-implementation-phases": "in-progress",
    "06-tradeoffs": "pending",
    "07-telemetry": "pending",
    "08-ownership": "done",
    "09-test-scenarios": "pending",
    "10-appendix": "pending"
  },
  "warnings": []
}
```

Status values: `pending`, `in-progress`, `done`, `skipped`, `stale`,
`error` (for `steps.*`); `pending`, `in-progress`, `deferred`, `skipped`,
`done` (for `sectionStatus.*`).

### Subagent / resumed-session contract

Any subagent (Phase 5 investigation, Phase 8 review-mode lint, etc.) reads
only from `workspace/inputs/` and `workspace/investigation/`, writes only
to its assigned files (or new files in those directories), and updates
`manifest.json` step status when complete. File-level isolation = safe
parallel work.

## Helper scripts

All scripts live under `<skill-dir>/scripts/` and are pure stdlib Python.
The remaining set covers only the deterministic kernel — workspace state,
template assembly, section walking, diagram drafting, investigation
validation, and review linting. ADO, PR, repo-scan, artifact upload,
and publishing interactions are driven inline by the agent via `az`,
`git`, `gh`, Serena MCP (or built-in grep/glob/view), and the `view`
tool for image/text artifacts — with explicit user confirmation on
every side-effecting command.

| Script | Purpose |
|--------|---------|
| `init_workspace.py` | Create a fresh workspace folder (manifest + dirs + empty `answers.json` + empty `inputs/artifacts/`). Seeds the per-section status map under `manifest.sectionStatus`, the empty `authoringMode` / `complexityProfile` fields, and the `inputs.artifacts` / `inputs.authoringMode` / `inputs.complexity` step entries. Accepts `--authoring-mode infer\|detailed` to skip the up-front prompt. |
| `assemble.py` | Deterministic assembler: `template.md` + `sections/*.md` -> `dev-design-*.md`. Rejects malformed fragments. Sections whose fragment contains `<!-- OMIT SECTION -->` are dropped entirely from the rendered doc. |
| `walker.py` | Per-section progress tracker. Subcommands: `list`, `next`, `set --section <id> --status <pending\|in-progress\|deferred\|skipped\|done>`, `show --section <id>`, `summary`. Loads `prompts/section-questions.json` and surfaces the right questions for the current section. |
| `investigation_init.py` | Opt-in. Initialize `workspace/investigation/` with a `plan.md`, a `scope.json` of focus areas + local/GitHub sources, and create the `raw/` and `synth/` folders. Supports `--focus`, `--source local:id:path` / `--source github:id:owner/repo`, `--one-pager`, `--max-parallel`, `--areas-per-source`, `--force`. Re-running merges new sources while preserving in-flight state. |
| `investigation_record.py` | Update one source's status as subagents progress (`pending` → `in-progress` → `done` / `failed`). Tracks agent IDs and raw file paths; rolls up `statusCounts` into the manifest and auto-flips `steps.investigation` to `synthesizable` once every source is resolved. |
| `investigation_synthesize.py` | Validate every `raw/*.md` against the strict 5-section template (`Summary` / `Key files & symbols` / `Proposed changes` / `Risks & unknowns` / `Citations`) and emit `synth/findings.md`, `synth/work-breakdown.md`, `synth/repos.json`, and `synth/citations.json`. Refuses to run with missing citations (exit 3) so the orchestrator re-prompts. Supports `--allow-partial` and `--force`. |
| `mermaid_draft.py` | Draft, validate, and embed per-phase Mermaid diagrams. Subcommands: `draft [--phase N] [--style flowchart\|sequence] [--force]` writes `workspace/diagrams/phase-N-<slug>.mmd`; `validate [--file <name>]` checks every .mmd; `list` prints the index; `embed [--phase N] [--force] [--dry-run]` inlines each .mmd into the matching `### Phase N:` block of `sections/05-implementation-phases.md` as a `` ```mermaid `` fenced block (idempotent, handles missing-marker / existing-block / inline-"See" reference forms). Diagrams render in any Mermaid-aware viewer (GitHub, VS Code, ADO Wiki). |
| `review.py` | Lints an existing workspace. Subcommands: `lint --workspace <ws> [--json] [--strict] [--no-mermaid] [--only <check>] [--skip <check>]` and `list-checks`. Checks: `SECTIONS_PRESENT`, `SECTIONS_NONEMPTY`, `TODOS_RESOLVED`, `PLACEHOLDERS_FILLED`, `MANIFEST_VALID`, `ASSEMBLE_FRESH`, `MERMAID_VALID`, `SECTION_STATUS`, `PUBLISH_STATUS`. Exit codes: 0 clean, 2 warnings, 3 errors (or `--strict` warnings). |
| `smoke_test.py` | Self-contained CI-style sanity check covering init, render, override, idempotency, `--check` drift detection, malformed-input rejection, walker state transitions, the full investigation init/record/synthesize loop, mermaid draft + validate (both styles), and review.py (every check, `--only`, `--skip`, `--strict`). Add `--quick` to run only the foundational checks (phase1b + walker + review). |

The `prompts/section-questions.json` file holds the per-section question
banks. Edit it to change the questions a teammate is asked when filling
out a particular section, add new question kinds, or wire up new
seed-source pointers.

`prompts/investigation-subagent.md` is the strict template Phase 5
subagents follow. It enforces the five required H2 sections and the
citation requirement that the synthesizer validates.

Run any script with `--help` for flags.

## Customize the template

`template.md` inside the skill folder is the canonical template the
assembler reads at runtime. Edit it freely — add sections, change column
headers, adjust the Mermaid skeleton — and the skill will follow your
changes. **Constraints:**

- Top-level numbered sections must use the form `## N. <title>` (regex
  `^## \d+\. `). The assembler keys off this.
- Section numbers must be unique and zero-padded section fragments
  (`01-...md` ... `10-...md`) must match.
- The H1 title (`# Dev Design: ...`) is preserved as the preamble; replace
  it via `sections/00-preamble.md`.

If you renumber or rename sections structurally, update `SKILL.md` Step 3
accordingly so the renderer writes fragments that match.

## Roadmap

| Phase | What lands | Status |
|-------|------------|--------|
| 1 | MVP scaffold — interactive Q&A, single-file output | ✅ Shipped |
| 1b | Workspace + reconstruction layer (manifest, fragments, deterministic assembler) | ✅ Shipped |
| 2 | `az boards` integration — work-item fetch via direct `az boards work-item show` calls (Step 1.5) | ✅ Shipped |
| 3 | Repo-aware pre-fill — agent reads the repo via Serena MCP or built-in grep/glob/view (Step 1.7) when the user names a specific path. Now opt-in only; CODEOWNERS and telemetry-event call-site scanning have been removed | ✅ Shipped |
| 4 | Section walker — reusable question banks per section, skip/defer/come-back-later UX, per-section progress in `manifest.sectionStatus` | ✅ Shipped |
| 5 | Investigation mode (opt-in) — hybrid local + GitHub research subagents write `investigation/raw/`, the synthesizer produces `findings.md` / `work-breakdown.md` / `repos.json` / `citations.json`, and the walker surfaces those as defaults for §1/§3/§5/§6/§7 | ✅ Shipped |
| 6 | Mermaid diagrams (per-phase when phased, single `implementation.mmd` when simple) | ✅ Shipped |
| 7 | Back-linking & publishing (opt-in) — single up-front prompt after the summary, then direct `az boards work-item update --discussion` (comment) or `az rest` attachment, and/or `git` + `gh pr create` PR flow into `docs/dev-designs/` | ✅ Shipped |
| 8 | Polish & teamability — `review.py` linter, `examples/filled-example/`, `install.ps1` / `install.sh`, `CONTRIBUTING.md`, `--quick` smoke flag, `--check` assemble flag | ✅ Shipped |
| **9** | **Faster authoring — Step 1.1 artifact upload (local files, images, optional .docx via python-docx), Step 1.2 authoring-mode prompt (`infer` / `detailed`), Step 1.9 complexity-profile inference (`simple` / `phased`), removal of CODEOWNERS + telemetry call-site scanning + Kusto/AppInsights baseline probe** | ✅ This release |

## Conventions

- All TODO markers use the prefix `<!-- TODO(dev-design): ... -->`.
- The skill never stores secrets. Future ADO integration relies on your own
  `az login`. Future GitHub research uses your existing Copilot CLI auth.
- Heading levels, section numbering, and template HTML comments are
  preserved verbatim so the doc round-trips cleanly through reviewers.
- Output is markdown + JSON only — no binary state, no databases.

## Sharing with teammates

This folder is self-contained — zip it, push it to an internal git repo, or
publish it to your team's tools repository. Have teammates install it with
the steps above. They need only Python 3.8+ for the deterministic path.

For full contributor guidelines (adding a new helper, smoke-test
expectations, style rules), see `CONTRIBUTING.md`.

## Review mode

After Phase 8, the skill can lint an existing workspace without modifying
it. Useful for a quick "is my design ready?" sanity check before sharing,
or as a CI gate in a docs repo.

```powershell
python scripts/review.py lint --workspace path/to/dev-design-12345-my-feature

# Strict (treat warnings as errors)
python scripts/review.py lint --workspace <ws> --strict --json

# Show all checks
python scripts/review.py list-checks
```

Checks:

| Check | What it flags |
|-------|---------------|
| `SECTIONS_PRESENT`    | Section fragment files missing for non-skipped sections |
| `SECTIONS_NONEMPTY`   | Fragments that contain only headings / comments / placeholders |
| `TODOS_RESOLVED`      | Unresolved `<!-- TODO(dev-design): … -->` markers |
| `PLACEHOLDERS_FILLED` | Template `[Bracketed]` placeholders that weren't replaced |
| `MANIFEST_VALID`      | `manifest.json` exists, parses, has required fields |
| `ASSEMBLE_FRESH`      | Rendered .md is up to date with the fragments |
| `MERMAID_VALID`       | Every `.mmd` in `workspace/diagrams/` parses |
| `SECTION_STATUS`      | Sections left `deferred` (warn) or `skipped` (info) |
| `PUBLISH_STATUS`      | Current state of `publish.ado` / `publish.pr` (info) |

Exit codes: `0` = clean, `2` = warnings, `3` = errors (or warnings under
`--strict`). Use `--only <CHECK>` and `--skip <CHECK>` (both repeatable)
to filter.

A complete reference workspace lives at
`examples/filled-example/dev-design-12345-login-retry-policy/` — it
passes `review.py` cleanly (only `PUBLISH_STATUS` info findings) and is
worth skimming as a "what good looks like" sample.

## Troubleshooting

- **The skill isn't auto-discovered**: confirm `~/.copilot/skills/dev-design/SKILL.md` exists and that the frontmatter has `name: dev-design`. Restart your Copilot CLI session.
- **"Template not found" error**: ensure `template.md` is in the same folder as `SKILL.md`. If you moved one, move both (the scripts resolve `template` via an explicit `--template` flag).
- **`assemble.py` exits 2 with "must start with"**: a section fragment doesn't begin with its `## N. ...` heading. Open the named file and add (or fix) the heading.
- **Re-rendering keeps clobbering my edits**: you're editing the rendered `.md` instead of `workspace/sections/*.md`. The `.md` is regenerated every run. Move your edits into the matching fragment.
- **Folder name collision**: `init_workspace.py` refuses to overwrite by default. Either delete / rename the existing folder or invoke with `--force`.
- **`az boards work-item show` fails**: common causes are (a) the work item ID does not exist in the configured org/project, (b) `az devops configure --defaults` is missing or points at the wrong org, or (c) network/proxy issues. Re-run with `--organization https://dev.azure.com/<org>` and `--project <name>` to override. If you want to skip ADO entirely, just set `steps.inputs.workItem.status = "skipped"` in `manifest.json` and continue.
- **Refresh ADO data after the work item changed**: just re-run `az boards work-item show --id <id> --expand all -o json` and overwrite `workspace/inputs/work-item.json`. Then manually flip `steps.sections.render` and `steps.assemble` in the manifest to `"stale"` so the next assemble picks up the change.
- **Repo read finds nothing useful**: confirm Serena MCP is connected (if available) or that you're running grep/glob from inside the right local clone. Repo scans are opt-in only as of v0.9 — the skill asks once whether to look at code and only reads what you name. Files under `test/`, `tests/`, `__tests__/`, `spec/`, files with `.test.<ext>` / `.spec.<ext>` suffixes, and minified bundles (`.min.js` / `.min.css`) should be filtered out manually. CODEOWNERS, telemetry event call sites, and feature-flag names are **not** scanned for — supply those yourself.
- **`.docx` artifact upload fails**: the skill uses `python-docx` (optional) to read `.docx`. Install with `pip install python-docx`, then re-add the file. If installing isn't an option, export the doc to `.md` / `.txt` or paste the contents directly when prompted.

## Maintainers' notes

- Schema version is in `init_workspace.py` (`SCHEMA_VERSION`) and the
  manifest. Bump it when you make breaking changes to `manifest.json` or
  to the fragment layout. Add a migration path if you do.
- Skill version (`SKILL_VERSION`) is independent; bump per release.
- Keep scripts stdlib-only for portability.
- Run `python scripts/smoke_test.py` before publishing changes.
