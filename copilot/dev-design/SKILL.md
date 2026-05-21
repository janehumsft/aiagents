---
name: dev-design
description: Interactively author a Dev Design markdown document end-to-end for an Azure DevOps feature. Walks the user section-by-section through a structured architecture template, persists every input and rendered fragment in a workspace folder (./dev-design-<id>-<slug>/) so sessions are resumable and the document can be deterministically reconstructed at any time. Also includes a review mode that lints an existing workspace for missing sections, unresolved TODOs, placeholders, and stale renders. Use this skill when the user asks to draft / write / fill out / create / review / lint a dev design doc, an architecture doc, a design doc, an ADO design template, an E2E feature design, or a feature spec.
---

# Dev Design skill

## When to use

Invoke this skill when the user asks for any of:

- "draft / write / create / fill out a dev design (doc / document / template)"
- "architecture doc" or "feature design doc" or "design doc"
- "dev design for ADO #..." or any Azure DevOps work item reference
- "feature spec" or "E2E design"
- "resume my dev design" / "re-render the dev design"
- "review / lint my dev design" / "is my dev design ready?"

If the user's request is ambiguous, ask one clarifying question before
launching the full procedure.

## What this skill does

Materializes a structured **workspace folder** for the feature at
`./dev-design-<id>-<slug>/`. The workspace is the source of truth — it
contains a manifest, structured user answers, uploaded artifacts, and
one markdown fragment per top-level template section. A deterministic
Python **assembler** combines `template.md` + `workspace/sections/*.md`
into the final `dev-design-[<id>-]<slug>.md` at the root of the workspace
folder.

The flow opens with two short up-front prompts — **artifact upload**
(local files, screenshots, WIP designs that ground the design) and
**authoring mode** (`infer` = fast, agent drafts each section and asks
one short confirmation per section; `detailed` = slow, walks every
question). After ADO / PR / repo context is collected, the skill
**infers a complexity profile** (`simple` vs `phased`) and confirms it
with the user — simple designs render a flat §5 "Implementation" with
no phase H3 blocks, and skip per-phase tables in §9.

Through **Phase 4** the skill drives Q&A via a per-section **walker**
that lets the user skip, defer, or come back to any of the 11 template
sections. It also pulls an Azure DevOps work item via `az boards`, can
review a branch / open PR via `az repos pr` or `gh pr`, and can read a
specific subtree of the local repo **when the user names one** (it no
longer auto-scans for CODEOWNERS or telemetry call sites — those are
user-supplied). All findings seed §1 summary, §2 reviewers, §6/§7
content, and §9 test scenarios. **Feature flag names (§4), telemetry
event names (§7), incident routes (§8), and code owners are never
seeded from any scan — they come from the user only.**

## Authoring principles (apply to every fragment you write)

These rules override anything that follows. Re-read them whenever you
start a new section.

1. **Be succinct and direct.** One to three sentences per paragraph.
   Plain language. Drop adverbs, hedges, and restated context. No
   marketing tone, no "this document describes…" preambles.
2. **Source every fact.** Each filled cell, bullet, or sentence must
   trace to a concrete input: the user's answer, the ADO work item,
   the PR diff / branch under review, an investigation synth file, or
   a file/symbol the agent actually read. If you cannot point at a
   source, do not write it. Never invent names, paths, owners, flag
   names, links, baselines, or numbers.
3. **It's fine to skip.** If the user gives no input for an optional
   section and no source supplies one, either (a) write a fragment
   with body `<!-- OMIT SECTION -->` so the assembler drops the
   section from the final doc (preferred for optional sections), or
   (b) leave the fragment as heading + one
   `<!-- TODO(dev-design): … -->` line. Do **not** pad with template
   boilerplate, "[Item 1]" placeholders, or speculative content.
4. **Tables shrink, not pad.** Drop the example rows when you have no
   real data. A table with one real row is better than one with five
   placeholder rows. If you have zero rows, either drop the table
   entirely or leave it as a single-line TODO.
5. **Required sections still need real content.** Sections marked
   `required: true` in the walker (00, 01, 05, 09) must contain user
   or source-derived content before assemble. If the user truly has
   nothing, surface that as a warning during the Step 2 summary; do
   not invent.

These principles are enforced per-section in Step 3 and in the
question prompts in `prompts/section-questions.json`.

## Skill files (relative to this `SKILL.md`)

```
SKILL.md
template.md
README.md
prompts/
  section-questions.json   # per-section question banks (consumed by walker)
scripts/
  init_workspace.py        # create / repair workspace folder
  assemble.py              # render workspace -> dev-design-*.md
  walker.py                # per-section status tracker + question lookup
  review.py                # 9-check linter for an existing workspace
  mermaid_draft.py         # draft / validate / embed per-phase diagrams
  investigation_init.py    # initialize investigation mode workspace
  investigation_record.py  # record a subagent investigation output
  investigation_synthesize.py  # validate + synthesize investigation outputs
  smoke_test.py            # CI-style sanity check
```

ADO, PR, repo-scan, and telemetry interactions are no longer scripts — the
agent invokes `az`, `gh`, and `git` directly (with explicit user
confirmation), and reads the local repo with Serena MCP or built-in
grep/glob/view. See Steps 1.5–1.7, 1.9, and 6 below.

When invoking scripts, use the absolute path to this skill's folder. The
canonical install paths are:

- Windows: `$HOME\.copilot\skills\dev-design\`
- macOS / Linux: `~/.copilot/skills/dev-design/`
- Repo-local: `./.copilot/skills/dev-design/`

If `python` is unavailable, fall back to **inline assembly** as described in
Step 4 below — the skill is still functional, just not byte-identical
across re-renders.

## Procedure

### Step 0 — orient

Resolve `<skill-dir>` by checking the canonical paths above. Confirm
`<skill-dir>/template.md` and `<skill-dir>/scripts/assemble.py` exist. If
not, tell the user the skill isn't installed correctly and stop.

Check `python --version` (or `python3 --version`). Remember which command
works; use it for all subsequent script invocations.

### Step 1 — detect or create the workspace

1. List the cwd for any `dev-design-*/` folder containing
   `workspace/manifest.json`.
2. **If a workspace exists**, read its `manifest.json` and present these
   choices via `ask_user`:
   - **Resume** — pick up at the first step whose status is `pending` or
     `stale`. Skip steps already `done`.
   - **Re-render only** — invoke `assemble.py` once and exit.
   - **Review only** — run `review.py lint --workspace <ws>` and surface
     the report; do NOT modify anything. See Step 7 for details.
   - **Start fresh** — rename the folder to `<name>.bak-<unix-timestamp>`
     and proceed to create a new workspace.
3. **If no workspace exists**, ask the user (one question per `ask_user`
   call):
   - **Feature / project name** (required, freeform).
   - **Azure DevOps work item ID or URL** (optional). Accept a numeric ID
     or a URL like
     `https://dev.azure.com/<org>/<project>/_workitems/edit/12345`. Parse
     the URL to extract the numeric ID for the folder name, but keep the
     full URL for the metadata block.
4. Invoke `init_workspace.py`:
   ```
   python <skill-dir>/scripts/init_workspace.py \
     --out-dir . \
     --feature-name "<name>" \
     --work-item-id "<id-or-empty>" \
     --work-item-url "<url-or-empty>"
   ```
   Parse the script's JSON stdout to get the workspace path. If the script
   exits 2 ("workspace exists"), surface the existing-workspace prompt from
   step 2 (the user just hit a name collision).

### Step 1.1 — collect uploadable artifacts (NEW, fast)

Run this **immediately after the workspace exists** and before any
ADO / PR / repo work. Skip silently if the user has already provided
artifacts on a previous run (`steps.inputs.artifacts.status == "done"`
or `"skipped"`).

The goal is to capture anything that grounds the design before we
start asking questions: a PM one-pager, a Figma screenshot, an
existing WIP dev design we can take over from, an internal RFC, a
recorded meeting note.

1. Ask once via `ask_user`:
   "Do you have any local files or images that describe this feature
   (PM one-pager, Figma screenshot, WIP dev design, RFC, meeting
   notes)? Local file paths only — online doc links (SharePoint,
   Confluence, Google Docs) are unreliable for me to fetch; if your
   doc is online, please save it locally first or paste the text
   directly." — choices: `Yes — I'll provide paths`,
   `Yes — I'll paste content`, `No, skip`.

2. **`Yes — I'll provide paths`**: ask for the file paths (one per
   line). For each path:
   - **Validate** the file exists. If not, surface the error and skip
     it.
   - **Classify by extension:**
     - `.md` / `.markdown` / `.txt` / `.rst`: read via `view`.
     - `.png` / `.jpg` / `.jpeg` / `.gif` / `.webp` / `.bmp`: read
       via `view` (the tool returns image base64; interpret the
       content directly — describe layout, visible text, components,
       arrows / flows you can see).
     - `.docx`: try the Python `docx` package
       (`python -c "import docx"`). If available, extract text via
       `docx.Document(path).paragraphs`. If not, ask the user to
       install it (`pip install python-docx`) or export the doc to
       `.md` / `.txt` and re-provide the path. Do **not** block on
       install — offer "paste content instead" as an alternative.
     - `.doc` (legacy binary), `.pdf`, `.pptx`, `.xlsx`: tell the
       user we can't read these directly; ask for an exported
       `.md` / `.txt` / image, or for the relevant snippets pasted
       in.
     - Anything else: ask the user what it is and how to read it.
   - **Persist** the artifact: copy the original file to
     `workspace/inputs/artifacts/<safe-name>` (keep the original
     extension). For images, that's just the binary file. For text
     and `.docx`, also write a sibling `<safe-name>.summary.md` with
     (a) the extracted text (truncate over ~4 KB with an ellipsis),
     and (b) a 2-4 sentence agent-written summary of what the
     artifact says about the feature.
   - **Index** the artifact: append an entry to
     `workspace/inputs/artifacts/artifacts-index.json` of the form:
     ```json
     {
       "originalPath": "<abs path the user gave>",
       "storedPath": "workspace/inputs/artifacts/<safe-name>",
       "kind": "text" | "image" | "docx" | "other",
       "summary": "<2-4 sentences>",
       "addedAt": "<iso utc>"
     }
     ```
     Create the index file if it doesn't exist (start it as a JSON
     array `[]`).

3. **`Yes — I'll paste content`**: collect the pasted text via a
   single `ask_user`. Save it to
   `workspace/inputs/artifacts/pasted-<n>.md` (auto-increment `n`).
   Add an index entry with `originalPath: "(pasted)"` and `kind:
   "text"`.

4. **`No, skip`**: write a single index entry with
   `{status: "skipped", reason: "<user reason or 'no artifacts'>"}`
   or leave the index empty; set
   `steps.inputs.artifacts.status = "skipped"`.

5. **Summarize back to the user** in 1-3 short bullets per artifact:
   `Loaded "<filename>" — <2-sentence what-it-is-and-what-it-says>`.
   Confirm "Did I read these correctly? If anything is wrong, paste
   a correction." Update the summary in the index on correction.

6. **Update the manifest** when done: set
   `steps.inputs.artifacts.status = "done"` (or `"skipped"`) with
   `completedAt` and `count = <n>`. Treat the artifacts as
   first-class **suggested-default sources** for §1 summary, §3
   scope, §5 implementation, and §6 tradeoffs — they sit alongside
   ADO / PR / investigation findings in Step 3's suggestion table.

This step is **optional but encouraged**; many users will skip it,
which is fine. The whole point is to give the agent a head start
when the context exists.

### Step 1.2 — choose authoring mode (NEW)

Skip if `manifest.authoringMode` is already set
(`"infer"` or `"detailed"`) from a previous run or from
`init_workspace.py --authoring-mode <mode>`.

1. Ask once via `ask_user`:
   "How should I drive the rest of this? — choices:
   - `Infer mode (fast, Recommended)` — I draft each section from
     what I already have (artifacts + ADO + PR + investigation +
     repo context) and ask you one quick `accept / edit / skip`
     per section. Short bullets, minimal prompting.
   - `Detailed mode (slow)` — I walk every question in the
     section walker and prompt you for each answer. Use this when
     you want full control or when the context is sparse."

2. **Persist** the choice: write `manifest.authoringMode = "infer"`
   or `"detailed"` and set
   `steps.inputs.authoringMode.status = "done"`.

3. **Contract for infer mode** (the agent honors this throughout
   Steps 2 and 3):
   - For each section, draft 3-6 short bullets / a short paragraph
     from the available sources and present them via a single
     `ask_user` with choices `Accept`, `Edit (paste replacement)`,
     `Skip`.
   - **Never invent** values for fields that must come from the
     user: feature flag names (§4), telemetry event names (§7),
     incident routes / code owners (§8), area paths the user hasn't
     confirmed. Surface those as explicit `<!-- TODO(dev-design):
     ... -->` lines and move on — do not guess.
   - On `Edit`, accept the user's pasted replacement verbatim as
     the section content.
   - On `Skip`, mark the section `skipped` per Step 2.

4. **Contract for detailed mode**: behave as documented in Step 2
   below — walk every question, no automatic drafting.

### Step 1.5 — fetch the Azure DevOps work item (optional but recommended)

Skip entirely if no work item ID/URL was supplied in Step 1, or if the user
opts out of ADO calls. Otherwise drive `az` directly — there is no helper
script. Always show the user the exact command you intend to run **before**
running it and proceed only after they confirm (a single bulk confirmation
covering the probe + fetch is fine).

1. **Probe `az` readiness.** Run these four checks (capture stdout, ignore
   non-zero exits — they signal the gap you need to remediate):
   ```
   az --version
   az extension list -o json
   az account show -o json
   az devops configure -l -o json
   ```
   Interpret the results: `azure-devops` must appear in the extension list;
   `az account show` must return a tenant (otherwise the user is not
   logged in); `az devops configure -l` should ideally show
   `organization` (and ideally `project`) defaults. Print a single-line
   readiness summary (e.g., `az ready: cli=2.62.0, ext=azure-devops 1.0.0,
   tenant=…, org=https://dev.azure.com/MyOrg`).

2. **Remediate gaps via `ask_user`.** If anything is missing, offer the
   exact fix as choices, e.g.:
   - missing extension → `az extension add --name azure-devops`
   - not logged in → `az login` (or `az login --tenant <id>`)
   - no org default → `az devops configure --defaults organization=https://dev.azure.com/<org>`
   - skip ADO entirely → set `steps.inputs.workItem.status = "skipped"` in
     the manifest (with a one-line reason) and move on.
   After the user runs the suggested command, re-probe before continuing.

3. **Fetch the work item.** Once ready, show the command and run it:
   ```
   az boards work-item show --id <id> --expand all -o json
   ```
   Write the raw JSON to `workspace/inputs/work-item.json` (UTF-8, no
   reformatting). Do **not** materialize a separate "derived" file — the
   agent reads the raw JSON when rendering sections.

4. **Fetch the parent (if any).** Inspect
   `relations[*].rel == "System.LinkTypes.Hierarchy-Reverse"` in the JSON.
   If a parent exists, extract its id from `url` (trailing integer) and
   fetch it the same way:
   ```
   az boards work-item show --id <parent-id> --expand all -o json
   ```
   Save to `workspace/inputs/work-item-parent.json`. Skip silently if
   none exists.

5. **Summarize back to the user (1–3 sentences).** Read
   `fields["System.Title"]`, `fields["System.State"]`,
   `fields["System.AreaPath"]`, `fields["System.AssignedTo"].displayName`,
   `fields["System.Description"]` (HTML — interpret in your head, don't
   mechanically convert), and
   `fields["Microsoft.VSTS.Common.AcceptanceCriteria"]`. Produce a terse
   confirmation like:
   `Fetched 12345 ("Implement async login", Active, area MyOrg\Team\Foo).
   Description covers the new token refresh flow; 3 acceptance criteria.`

6. **Update the manifest manually.** Set
   `steps.inputs.workItem.status = "done"`, record `completedAt` (ISO
   timestamp), and stamp `source = "az boards work-item show"`. If you
   previously had a completed render, also flip
   `steps.sections.render.status` and `steps.assemble.status` to
   `"stale"` so the next assemble re-renders against the refreshed data.

7. **Errors.** If `az boards work-item show` returns non-zero, show the
   raw stderr to the user, set `steps.inputs.workItem.status = "error"`
   with the error message in `reason`, and ask whether to retry,
   switch orgs, or skip. Do not block Q&A on this — the rest of the
   procedure must still work with no ADO data.

Notes:
- Subsequent invocations on the same workspace: check
  `steps.inputs.workItem.status == "done"` and the `completedAt`
  timestamp before re-fetching. Skip unless the user explicitly asks to
  refresh.
- Treat the raw JSON as the source of truth for §1, §2, §6, and §9
  defaults — don't paraphrase it into another file.

### Step 1.6 — code change / PR review (optional but encouraged)

Designs that ground themselves in actual code-in-flight are far more
useful than speculative ones. Before scanning the broader repo (Step
1.7), ask the user up front whether there is concrete work to look at.

1. Ask once via `ask_user`:
   "Is there a branch, pending change, or open PR I should review to
   ground this design?" — choices:
   - `Yes — Azure DevOps PR`
   - `Yes — GitHub PR`
   - `Yes — local branch / diff`
   - `No, skip`

2. **Azure DevOps PR.** Follow up to collect the PR id (and the
   organization / project if it isn't already in `az devops configure
   --defaults`). Then run:
   ```
   az repos pr show --id <id> --output json
   az repos pr show --id <id> --include-commits --output json   # optional
   ```
   Save the JSON to `workspace/inputs/pr.json`. For the actual diff,
   prefer a local checkout: `git --no-pager diff <base>..<head>`. If
   the user has no local checkout, fall back to `az repos pr show`'s
   `lastMergeSourceCommit` + `lastMergeTargetCommit` and surface
   commit URLs; do **not** try to reconstruct the diff from API blobs.

3. **GitHub PR.** Use `gh` (already in the toolchain):
   ```
   gh pr view <ref> --json number,title,body,author,headRefName,baseRefName,files,additions,deletions
   gh pr diff <ref>
   ```
   Save the JSON metadata to `workspace/inputs/pr.json` and the diff
   to `workspace/inputs/pr-diff.patch`.

4. **Local branch / diff.** Ask for the base branch (default `main`)
   and the head branch (default current `HEAD`). Run:
   ```
   git --no-pager log --oneline <base>..<head>
   git --no-pager diff --stat <base>..<head>
   git --no-pager diff <base>..<head>
   ```
   Save the diff to `workspace/inputs/pr-diff.patch` and write a small
   `pr.json` with `{kind: "local", base, head, commits: [...]}` so
   later steps can reference it uniformly.

5. **Summarize back to the user.** Once the inputs land, read the diff
   and write a 2-4 bullet summary of what the change actually does
   (touched areas, new files, removed code, any obvious flag /
   telemetry / interface changes). Persist the summary to
   `workspace/inputs/pr-summary.md`. Confirm with the user that the
   summary matches their intent before treating it as a source.

6. Add `pr` to the suggested-default sources list (Step 2 / Step 3).
   When the walker reaches §1, §3, §5, §6, or §9, surface PR-derived
   defaults alongside ADO and investigation defaults. For §4 the PR
   diff is allowed to surface **flag references it found** as a
   sub-bullet under the question prompt ("the PR touches
   `FooFeatureFlag` at `src/foo.ts:42` — include?"), but flag rows
   are still only written into the section when the user explicitly
   keeps them (see Authoring principles #2 and the §4 contract in
   Step 3).

7. If the user picks `No, skip`, set
   `steps.inputs.pr.status = "skipped"` (create the key if it doesn't
   exist) and move on. The rest of the flow must work with no PR
   context.

### Step 1.7 — read the local repo (optional, opt-in)

The skill no longer auto-scans the repo. Instead, **ask the user
once whether there's specific code to look at** and only investigate
when they say yes. The goal is to ground §3 (scope) and §5
(implementation) in real code — not to enumerate CODEOWNERS or
telemetry call sites (both are user-supplied in this skill).

Skip this step if Step 1.6 (PR review) already gave you enough
context — the diff is usually the highest-signal source.

1. Ask once via `ask_user`:
   "Is there specific code I should scan to ground this design?
   (e.g., the directory that owns the feature, a config file, a
   service boundary). I'll skip CODEOWNERS and telemetry call sites
   — those are user-supplied in this skill." — choices:
   - `Yes — scan a path I'll provide`
   - `Yes — and it's large; spin up an investigation subagent` (see
     Step 1.8)
   - `No, skip`

2. On `Yes — scan a path I'll provide`: ask for the path (file or
   directory). Validate it exists and is inside a git toplevel
   (`git -C <path> rev-parse --show-toplevel`). Then read it
   directly — there is no helper script.

   - **Prefer Serena MCP when available** (`serena_*` / `mcp_serena_*`
     tools in the session). Use `serena_get_symbols_overview`,
     `serena_find_symbol`, and `serena_find_referencing_symbols` to
     anchor structurally relevant files / symbols.
   - **Fallback**: built-in `glob`, `grep`, and `view`. Limit grep
     patterns to the feature's vocabulary (names from the ADO
     title, PR diff, or artifacts). Do **not** sweep for
     `logEvent`, `TrackEvent`, `emit`, `CODEOWNERS`, or feature-flag
     heuristics.
   - **Stay scoped**: the user named a path for a reason. Don't
     expand beyond it unless you find a concrete cross-reference
     (and even then, surface the expansion to the user before
     reading more).

3. On `Yes — and it's large; spin up an investigation subagent`:
   jump to **Step 1.8** with the path as a single `local` source
   and a `--focus` derived from the feature name / ADO title. The
   subagent's read-only investigation produces the same kind of
   findings, persisted under `workspace/investigation/`.

4. **Persist findings yourself.** Whether you read it directly or
   delegated to a subagent, write
   `workspace/inputs/repo-scan.json` with the structure:
   ```json
   {
     "status": "done",
     "reader": "serena" | "builtin" | "subagent",
     "root": "<abs path>",
     "relevantFiles": [
       { "path": "<rel path>", "why": "<one-line note>" }
     ],
     "scannedAt": "<iso utc>"
   }
   ```
   The `relevantFiles` list seeds §3 scope and §5 implementation —
   nothing else. No `codeowners`, no `telemetryEvents`, no
   `featureFlags`. If the user picked `No, skip`, write:
   ```json
   { "status": "skipped", "reason": "<user reason or 'no relevant code'>" }
   ```
   and set `steps.inputs.repoScan.status = "skipped"` in the
   manifest. (A skipped file is still persisted so downstream
   scripts like `mermaid_draft.py` know the scan was intentional.)

5. **Confirm with the user** before findings flow into any section.
   Show the `relevantFiles` list as a quick bullet summary and ask
   "Use these in §3 / §5? Drop any?" Update the JSON with their
   choices.

6. Update `steps.inputs.repoScan.status = "done"` (or `"skipped"`)
   in the manifest.

**Never** scan for feature-flag names, telemetry event names,
CODEOWNERS, or incident routes in this step. All four are
user-supplied. If you spot what looks like one, ignore it.

### Step 1.8 — investigation mode (optional, opt-in)

Use this step **only** when the user explicitly asks ("investigate",
"research the work", "figure out what's involved", "I don't have a
one-pager"). Skip it otherwise — the default flow is fast.

Prereqs: the workspace exists. ADO data (Step 1.5) and/or a one-pager
make the investigation much more useful but are not required.

**1. Gather scope.** Use `ask_user` to collect:

- **Focus areas** (free-form list). Default to keywords from the ADO
  title + parent feature. Examples: `auth flow`, `telemetry pipeline`,
  `rollout strategy`.
- **Local sources**: paths to repos the user has checked out. Default
  the first to the workspace's parent folder if it's a git repo.
- **GitHub sources**: `owner/repo` refs the user wants research-only
  coverage for.
- **One-pager** (optional): a path to a markdown file. Pass it via
  `--one-pager`; it lands at `workspace/inputs/one-pager.md`.

**2. Initialize.** Run:

```
python <skill-dir>/scripts/investigation_init.py \
  --workspace <ws> \
  --focus "<area>" [--focus ...] \
  --source local:<id>:<path> [--source ...] \
  --source github:<id>:<owner/repo> [--source ...] \
  [--one-pager <path>] [--max-parallel 4] [--areas-per-source 2]
```

This writes `workspace/investigation/plan.md`, `scope.json`, creates
`raw/` and `synth/` folders, and flips
`manifest.steps.investigation.status` to `in-progress`. Re-running with
new sources appends them; existing source runtime state is preserved.

**3. Fan out subagents.** For every source with status `pending`, spawn
one `task` subagent in **background** mode:

- `agent_type: "explore"` for `local` sources (filesystem access).
- `agent_type: "research"` for `github` sources.

Build the subagent prompt from `prompts/investigation-subagent.md` by
filling these placeholders:

| Placeholder | Source |
|-------------|--------|
| `{{feature}}` | `manifest.featureName` |
| `{{workItemId}}` / `{{workItemTitle}}` | `manifest.workItem.id` / `.title` |
| `{{sourceKind}}` | scope source `kind` |
| `{{sourceTarget}}` | source `path` (local) or `ref` (github) |
| `{{sourceName}}` | source `name` |
| `{{focusAreasCommaSeparated}}` | `scope.focusAreas.join(", ")` |

Append: "Write your report to
`<ws>/workspace/investigation/raw/<source-id>.md` (overwrite if it
exists). When done, return that path." After spawning, immediately call:

```
python <skill-dir>/scripts/investigation_record.py \
  --workspace <ws> --source <id> --status in-progress --agent-id <id>
```

Respect the budget — never run more than `scope.budget.maxParallel`
subagents concurrently. Queue extras and start them as slots free up.

**4. Collect.** As each background agent completes (you will be
notified), call `read_agent` once, verify the raw file exists with the
five required H2 headings (`## Summary`, `## Key files & symbols`,
`## Proposed changes`, `## Risks & unknowns`, `## Citations`), then:

```
python <skill-dir>/scripts/investigation_record.py \
  --workspace <ws> --source <id> --status done --raw-file raw/<id>.md
```

If the agent failed or its output is malformed, record
`--status failed --error "<reason>"` and either (a) re-prompt by
spawning a new subagent with corrective instructions, or (b) skip the
source. When the last source lands, the manifest auto-flips to
`synthesizable`.

**5. Synthesize.** Run:

```
python <skill-dir>/scripts/investigation_synthesize.py --workspace <ws>
```

The synthesizer validates every raw file. If it exits **3**, parse the
stderr JSON `problems` map, find the offending source, and re-spawn a
subagent with explicit instructions to fix the missing section
(usually `Citations`). Then mark the source `pending` again with
`investigation_record.py` and repeat from step 3 for that source only.

On success the synthesizer writes:

- `synth/findings.md` — narrative cross-source summary
- `synth/work-breakdown.md` — proposed changes grouped by source
- `synth/repos.json` — machine-readable source list
- `synth/citations.json` — every cited file/URL with its source id

`steps.investigation.status` becomes `done`; `sections.render` and
`assemble` flip to `stale` so Step 4 reruns.

**6. Carry forward to Step 2.** Add the synth artifacts to the
suggested-default sources list. When the section walker reaches §1, §3,
§5, §6, or §7, surface investigation-derived defaults alongside ADO
defaults via `ask_user` (see Step 3 for the new rows).

### Step 1.9 — decide complexity profile (phased vs simple)

Run this **after** Steps 1.5 / 1.6 / 1.7 / 1.8 have settled, and
**before** Step 2 (the section walker) begins. Skip silently on a
resume if `manifest.complexityProfile.confirmed == true`.

The complexity profile decides whether §1 / §5 / §9 render as a
phased doc or a flat one. The skill **infers** a starting value and
**always confirms** with the user.

1. **Infer.** Score the feature on signals you have:
   - ADO description length, acceptance criteria count.
   - PR diff: number of touched files / packages / language
     boundaries (1 package = simple; >1 module + new endpoints =
     phased).
   - Investigation `synth/findings.md` and the artifacts index: do
     they describe a multi-step rollout / parallel workstreams?
   - User's freeform summary so far: does it mention "first", "then",
     "phase", "rollout in waves"?

   Default: **simple** unless at least two signals point to phased.
   Record your rationale in 1-2 sentences for the manifest.

2. **Confirm via `ask_user`:**
   "Based on what I have, this looks like a **<value>** design:
   `<one-sentence rationale>`. Should §5 render as a flat
   `Implementation` section, or as multi-phase `Implementation
   Phases`?" — choices:
   - `Use <inferred> (Recommended)`
   - `Use the other one`
   - `Let me name the phases now` (only offered when inferred =
     simple, in case the user wants to override and supply phase
     names immediately)

3. **Persist** under `manifest.complexityProfile`:
   ```json
   {
     "value": "simple" | "phased",
     "source": "inferred" | "user",
     "confirmed": true,
     "rationale": "<one or two sentences>"
   }
   ```
   Set `steps.inputs.complexity.status = "done"`.

4. **Downstream effects** (the agent honors these in Steps 1.10, 2,
   and 3):
   - `simple`:
     - §1 omits the `### Phases` sub-bullet block.
     - §5 fragment uses heading `## 5. Implementation` (no `### Phase
       N:` blocks). Single motivation paragraph + Proposed Changes
       + Error Handling + Validation.
     - §9 renders as a single (Scenario | Setup | Expected) table —
       no per-phase H3s. Cross-Cutting subsection is still allowed.
     - §4 Feature Flags table drops the `Phase` column; columns
       become (Flag | Purpose | Rollout Notes).
     - Step 1.10 (mermaid drafting) writes a single
       `implementation.mmd` instead of per-phase diagrams.
   - `phased`:
     - All the existing per-phase behavior applies. §5 keeps its
       `## 5. Implementation Phases` heading.

5. **Override later.** The user can flip the profile any time during
   Step 2 by editing `manifest.complexityProfile.value`. On flip,
   delete any phase-specific fragments / diagrams that no longer
   apply and re-render.

### Step 1.10 — draft Mermaid diagrams (conditional)

Run this only when the design has at least one flow worth diagramming.

- **Phased** (`manifest.complexityProfile.value == "phased"`): run once
  the section walker has captured the user's phase names in
  `workspace/inputs/answers.json` under `phases` (i.e., immediately
  after section `01-summary-and-goals` is `done`, OR at the start of
  Step 3 §5 rendering if phases were captured earlier). One diagram
  per phase.
- **Simple** (`value == "simple"`): draft a single
  `workspace/diagrams/implementation.mmd` (or skip entirely if the
  flow is trivial). The embedder inlines it into §5's
  `**Current vs. Proposed Flow**:` marker.

Skipping is fine — fragments fall back to the template's Mermaid
skeleton.

1. **Draft.** Run:
   ```
   python <skill-dir>/scripts/mermaid_draft.py draft --workspace <ws>
   ```
   This reads the phase list, drops `workspace/diagrams/phase-N-<slug>.mmd`
   per phase (flowchart by default, with `subgraph Current` and
   `subgraph Proposed`), and seeds nodes from investigation/repo-scan
   sources when present. Existing files are preserved unless `--force`.
2. For each phase, show the file path to the user and offer:
   `Edit now (open and refine)`, `Use sequence diagram instead`,
   `Keep skeleton`. On "sequence", re-run with
   `--phase N --style sequence --force`.
3. **Validate.** After any edits, run:
   ```
   python <skill-dir>/scripts/mermaid_draft.py validate --workspace <ws>
   ```
   If exit code is 3, parse the stderr JSON `problems` map and surface
   per-file issues. Loop until all files validate (or the user accepts
   that the renderer will fall back to the template skeleton for the bad
   file).
4. **Embed.** Once section `05-implementation-phases.md` exists (the
   walker creates it during Step 2), inline each .mmd into the matching
   `### Phase N:` block as a ` ```mermaid ` fenced code block:
   ```
   python <skill-dir>/scripts/mermaid_draft.py embed --workspace <ws>
   ```
   The embedder finds the `**Current vs. Proposed Flow**:` marker
   inside each phase block and either inserts a fresh fenced block,
   replaces an existing one in place, or replaces a "See
   `workspace/diagrams/...`" reference. It's idempotent — re-runs with
   no .mmd changes are no-ops. Use `--phase N --force` to refresh a
   single phase after editing its .mmd, or `--dry-run` to preview.
   The result lands in the assembled .md the next time `assemble.py`
   runs, and renders as a real diagram in any Mermaid-aware viewer
   (GitHub, VS Code preview, Azure DevOps Wiki, etc.).

### Step 2 — drive Q&A via the section walker

The walker (`scripts/walker.py`) tracks each of the 11 template sections in
`manifest.sectionStatus`. Status values: `pending`, `in-progress`,
`deferred`, `skipped`, `done`. The agent uses the walker as both the
question source and the progress tracker.

**Authoring mode controls how each section is handled:**

- **`authoringMode == "infer"`** (the fast default — short, one
  confirmation per section):
  1. Ask the walker what to work on next (`walker.py next`).
  2. **Draft the section yourself** from available sources
     (`workspace/inputs/artifacts/`, ADO `work-item.json`, PR
     `pr-summary.md`, investigation `synth/findings.md`,
     `repo-scan.json`, user answers so far). Aim for 3-6 bullets or a
     short paragraph. Honor `complexityProfile.value` (simple = no
     phase H3s in §5 / §9; flat tables in §4 / §9).
  3. Present the draft with `ask_user` and three choices: `Accept`,
     `Edit (paste replacement)`, `Skip`.
  4. On `Accept`: write the fragment per Step 3, persist the answer
     to `answers.json`, call `walker.py set --section <id> --status
     done`.
  5. On `Edit`: take the user's pasted replacement verbatim as the
     fragment body (still requires the `## N. <title>` heading).
     Mark `done`.
  6. On `Skip`: see "Skip" behavior below.
  7. **Never infer user-only fields.** If a section needs flag names
     (§4), telemetry event names (§7), incident routes / owners
     (§8), or other user-only data and you don't have it, emit a
     single `<!-- TODO(dev-design): ... -->` line in that subsection
     and move on. Do not guess.

- **`authoringMode == "detailed"`** (the slow path — full Q&A):
  Walk every question in the section's question bank. For each
  question use `ask_user` with the `prompt` field, injecting any
  seed defaults as `Suggested: <value>`. After all answers are in,
  write the fragment per Step 3.

**Loop until no incomplete sections remain:**

1. Ask the walker what to work on next:
   ```
   python <skill-dir>/scripts/walker.py --workspace <ws> next
   ```
   The output JSON has `next` (section id), `title`, `required`, `status`,
   and `questions` — the question bank loaded from
   `prompts/section-questions.json`. If `next` is `null`, exit the loop.

2. **Announce the section.** Tell the user something like:
   `Section 03 - Scope (status: pending).` In infer mode, also show
   your drafted content. In detailed mode, offer `ask_user` with three
   choices: `Answer now (recommended)`, `Skip (leave TODOs)`, `Defer
   (come back later)`.

3. Branch on the user's choice (or the infer-mode `Accept` / `Edit`
   / `Skip`):
   - **Accept / Answer now**: write the fragment (see Step 3 for
     per-section render rules), persist the answer to
     `workspace/inputs/answers.json`, and call:
     `walker.py set --section <id> --status done`.
     The walker auto-flips `steps.sections.render` to `done` once
     all sections are non-incomplete, and back to `in-progress` if
     a section is deferred later.
   - **Skip**: `walker.py set --section <id> --status skipped`. Do **not**
     write a template-default fragment with placeholder rows. Either:
     (a) write a minimal fragment that consists of the `## N. <title>`
     heading followed by a single `<!-- TODO(dev-design): … -->` line
     (preferred for required sections so the warning is visible), or
     (b) write a fragment whose body is just `<!-- OMIT SECTION -->`
     — the assembler will drop the section entirely from the final
     doc (preferred for optional sections, keeps the output lean).
     A missing fragment file falls back to the template default, so
     you must write one of (a) or (b) explicitly when skipping.
   - **Defer**: `walker.py set --section <id> --status deferred`. Do NOT
     write a fragment yet; the assembler will fall back to the template
     default. The deferred section is offered again at the end of the loop.

4. After every section transition, run `walker.py next` again. **Do not
   re-ask sections whose status is `done` or `skipped`.** Deferred
   sections come back around once all pending sections are resolved.

5. **Required sections.** `00-preamble`, `01-summary-and-goals`,
   `05-implementation-phases`, and `09-test-scenarios` are marked
   `required: true` in the walker output. If the user tries to skip one,
   warn them once via `ask_user` ("This section is marked required;
   skipping leaves the doc incomplete. Continue?"). If they confirm,
   honor the skip — never block.

6. **Resume.** When restarting a session, run `walker.py list` once; pick
   up at the first incomplete section. Already-done sections are not
   re-asked.

When the loop exits, run:
```
python <skill-dir>/scripts/walker.py --workspace <ws> summary
```
and surface the `missingRequired` array to the user; if it is non-empty,
offer one final pass.

Update `steps.inputs.qna` to `done` once the loop completes (regardless
of skips / defers — the walker tracks the granular state separately).

### Step 3 — section render rules

Each section fragment **must start with its `## N. <title>` heading** (or,
for `00-preamble.md`, the `# Dev Design: <name>` heading). The assembler
substitutes the entire section atomically.

**Suggested-default sources.** Read these once at the top of Step 2 and
re-use throughout Step 3:

| Suggestion target | Field | Primary source |
|-------------------|-------|----------------|
| One-paragraph summary | `descriptionMarkdown` (truncate to ~3 sentences) | ADO derived |
| One-paragraph summary | artifact summaries | `inputs/artifacts/artifacts-index.json` |
| PR context summary | `pr-summary.md` bullets | PR review (Step 1.6) |
| Goals / current vs proposed | per-source `## Summary` blocks | investigation `synth/findings.md` |
| Reviewers / signoffs | `assignedTo` + `parent.assignedTo` | ADO derived |
| Area path | `areaPath` | ADO derived |
| Test scenarios | `acceptanceCriteriaItems` (one bullet per item) | ADO derived |
| Implementation / proposed changes | per-source `## Proposed changes` + PR diff hunks + `relevantFiles` | investigation + PR + repo-scan |
| Tradeoffs / risks | aggregated `## Risks & unknowns` | investigation `synth/findings.md` |
| Repos in scope | sources with kind/target | investigation `synth/repos.json` |
| Mermaid skeleton | `phase-N-<slug>.mmd` (phased) or `implementation.mmd` (simple) | `workspace/diagrams/` |

**The following fields are user-supplied ONLY — never seeded from any
scan or LLM guess:** feature flag names (§4), telemetry event names
(§7), code owners (any section), incident routes (§8). PR-diff flag
references may be surfaced to the user as a suggestion but only become
rows in §4 after explicit confirmation.

Always surface the suggestion to the user via `ask_user`; never silently
accept it. The user is the final authority.

Per-section render contract:

| File | Contents |
|------|----------|
| `00-preamble.md` | `# Dev Design: <feature>` + `<!-- workitem: ... -->` metadata block. When ADO data exists, expand the metadata block to include `id`, `url`, `type`, `state`, `areaPath`, `iterationPath`, `assignedTo`, `parentId`, `parentTitle`, `tags`. |
| `01-summary-and-goals.md` | One short summary paragraph (user answer, or ADO `descriptionMarkdown` truncated to ~3 sentences if the user accepted it, or distilled from artifact summaries). **Phased**: include a `### Phases` sub-list with the user's phase names. **Simple**: omit the `### Phases` subsection entirely. No filler sentences. |
| `02-signoffs.md` | Signoffs table. Seed the first row with the ADO assignee + parent assignee if present (role = `Assignee` / `Parent owner`). Append user-provided rows. Drop the table entirely if no real rows exist; the section can be a single TODO line in that case. Same for Contacts. |
| `03-scope.md` | Real in-scope categories + out-of-scope bullets only. Drop the "Current vs Proposed" subsection unless the user (or the PR diff) actually supplied a comparison; leaving a TODO comment is fine but do not invent rows. |
| `04-feature-flags.md` | Feature Flags table. **Rows come from the user's typed input only** (and, when the user explicitly confirmed them in Step 1.6, from PR-diff flag references the user kept). Never seed rows from a repo read. **Phased**: columns `Flag \| Purpose \| Phase \| Rollout Notes`. **Simple**: drop the `Phase` column — columns `Flag \| Purpose \| Rollout Notes`. If the user supplied zero flags, write a single `<!-- TODO(dev-design): flags to be added by author -->` line in place of the table — do not emit placeholder rows. |
| `05-implementation-phases.md` | **Phased**: heading stays `## 5. Implementation Phases`; one `### Phase N: <name>` subsection per user phase. Keep the template's per-phase structure (motivation, `**Current vs. Proposed Flow**:` marker, Proposed Changes, Error Handling, Rollout Plan, Validation checklist) but drop any subsection the user has no input for rather than padding it with `[Change description]` placeholders. **Simple**: heading becomes `## 5. Implementation` (no "Phases"); render a single flat block — motivation paragraph + `**Current vs. Proposed Flow**:` marker + Proposed Changes bullets + Error Handling + Validation checklist — with NO `### Phase N:` subheadings. Always leave the marker line + a blank line for the Mermaid embedder. Run `mermaid_draft.py validate` before `mermaid_draft.py embed --workspace <ws>`; on invalid files, skip embedding for that block. |
| `06-tradeoffs.md` | Tradeoffs table populated from user input only (with suggestions from investigation `Risks & unknowns` when present). If the user supplied none, replace the table with a single TODO line. |
| `07-telemetry.md` | Subsections 7.1–7.4. **All content is user-supplied** — the skill does not scan for events. §7.1 goals from user input; §7.2 existing events the user names; §7.3 new events the user adds; §7.4 dashboards / alerts the user names. Drop any subsection without real content. Never invent baselines or event names. |
| `08-ownership.md` | Area path (user answer or ADO `areaPath`) + incident route if the user provided one. **Owners are user-supplied** — do not append "Code owners (from CODEOWNERS):" anything; the skill no longer scans CODEOWNERS. If neither area path nor incident route exist, the section is a single TODO line. |
| `09-test-scenarios.md` | **Phased**: per-phase H3 tables. Use the union of user-provided scenarios and ADO `acceptanceCriteriaItems` (de-duplicate by case-insensitive text match; prefer the user's wording). Round-robin distribute across phases. **Simple**: a single (Scenario \| Setup \| Expected) table with no H3 subheadings; the union goes into one list. In both cases, append a `Cross-Cutting` subsection with the template's default rows (all flags off, offline) only if at least one table has real rows. |
| `10-appendix.md` | Only the subsections the user actually filled. If the user supplied nothing for §10, write a fragment whose body is just `<!-- OMIT SECTION -->` and the assembler will drop §10 from the final doc. |

For each fragment you write:

1. Use the `view` tool to load `workspace/inputs/answers.json`, parse, set
   the relevant key (`summary`, `phases`, `reviewers`, etc.), and write it
   back with `edit` / `create`. Keep it valid JSON (indent=2, trailing
   newline).
2. Write the fragment to `workspace/sections/<id>.md` using the `create` /
   `edit` tool.
3. Call `walker.py set --section <id> --status done` (or `skipped` for a
   skip-only fragment).

Hard rules:

- **Preserve heading levels, section numbering, and HTML
  comments** from the template verbatim when you DO emit a section.
- **You may omit optional sections / subsections / table rows** when no
  user input or source supplies content. Prefer omission or a single
  `<!-- TODO(dev-design): … -->` line over template-default boilerplate
  ("[Item 1]", "[Description]", placeholder columns).
- **Required sections** (00, 01, 05, 09) must contain real content. If
  the user can't supply any, surface it as a warning during the Step 5
  summary; never invent.
- **Never invent facts** (names, flag values, area paths, telemetry
  events, file paths, baselines, links, owners). **Feature flag
  names, telemetry event names, code owners, and incident routes
  come from the user only** — never from a repo read, never from an
  LLM guess, never from "looks like a flag / owner" heuristics.
  PR-diff flag references may be surfaced to the user but only
  become rows in §4 after the user confirms them.

When all sections are non-incomplete, the walker auto-flips
`steps.sections.render` to `done`.

### Step 4 — assemble

Invoke the assembler:

```
python <skill-dir>/scripts/assemble.py \
  --workspace <workspace-path> \
  --template <skill-dir>/template.md
```

The script writes `<workspace>/dev-design-[<id>-]<slug>.md` and updates the
manifest's `steps.assemble` entry.

**If Python is unavailable** (fallback path):

1. `view` the template at `<skill-dir>/template.md`.
2. Split it at `^## (\d+)\. ` headings into a preamble + 10 numbered
   sections.
3. For preamble and each section, if a fragment exists under
   `workspace/sections/`, use it (validate it starts with the expected
   `## N. ...` heading); otherwise use the template's default text.
4. Concatenate with `\n` between parts.
5. Prepend the banner:
   `<!-- GENERATED FILE. Edit workspace/sections/*.md and re-render with the dev-design skill. -->\n\n`
6. Write the result with the `create` tool. Manually patch
   `workspace/manifest.json` to record the assembly.

### Step 5 — summary

Print a concise summary in plain text (no tool calls needed):

- ✅ **Workspace**: absolute path.
- ✅ **Output**: absolute path to the assembled `.md`.
- ✅ **Filled sections** with TODO counts (e.g.,
  `§5 Implementation Phases (3 phases, 7 TODOs)`).
- ⚠️ **Open TODOs** total — grep
  `<!-- TODO(dev-design):` across `workspace/sections/`.
- 🔄 **Resume**: "Re-run the skill from this folder. Pick *Resume* to pick
  up where you left off, or *Re-render only* to rebuild the .md after
  editing fragments."
- ✏️ **Edit**: "Edit `workspace/sections/<NN>-*.md`. Then ask me to
  re-render."

### Step 6 — publish (optional, opt-in)

Phase 7 is **gated behind a single up-front `ask_user`** after the Step 5
summary. Default behavior: skip. There are no publish helper scripts —
the agent drives `az`, `git`, and `gh` directly and gets explicit user
confirmation before each side-effecting command.

1. **Check publish state.** Read `manifest.steps.publish.ado.status` and
   `manifest.steps.publish.pr.status`. If either is already `done` and
   the doc has been re-assembled since (`assemble.completedAt` newer
   than the publish step's `completedAt`), collapse the prompt to
   `Re-publish to refresh? Yes / Skip` and re-run the relevant
   sub-flow below.

2. **Ask once** with these choices (in this order):
   - `Skip publishing (Recommended)`
   - `Post to ADO only`
   - `Open a PR only`
   - `Both`
   - `Configure each separately`

   On `Skip publishing`, set both
   `steps.publish.ado.status = "skipped"` and
   `steps.publish.pr.status = "skipped"` with a reason
   (`"user opted out at summary"`), print "Publishing skipped.", and end.

3. **ADO publish sub-flow** (when chosen):
   1. Ask `Mode? Comment (Recommended) / Attachment`.
   2. Confirm work item id (`steps.inputs.workItem.id` if present).
   3. **Comment mode.** Show the user the rendered markdown that will
      be posted (the body should be the full doc, or the §1 summary +
      a link if the org disallows long comments). Then run, after
      confirmation:
      ```
      az boards work-item update --id <id> \
         --discussion "<body>" -o json
      ```
      Capture the response, extract the comment URL (or work-item URL
      if no per-comment URL is returned), and persist it.
   4. **Attachment mode.** Confirm, then upload the rendered file as
      an attachment and link it:
      ```
      az rest --method POST \
         --url "https://dev.azure.com/<org>/<project>/_apis/wit/attachments?fileName=<name>.md&api-version=7.0" \
         --resource "499b84ac-1321-427f-aa17-267ca6975798" \
         --body @<path-to-doc> \
         --headers "Content-Type=application/octet-stream"
      ```
      Take the returned `url` and patch it onto the work item:
      ```
      az rest --method PATCH \
         --url "https://dev.azure.com/<org>/<project>/_apis/wit/workitems/<id>?api-version=7.0" \
         --headers "Content-Type=application/json-patch+json" \
         --body '[{"op":"add","path":"/relations/-","value":{"rel":"AttachedFile","url":"<attachment-url>","attributes":{"comment":"Dev design doc"}}}]'
      ```
      On HTTP 403 (attachment endpoint disabled), ask the user whether
      to fall back to **Comment mode** and re-run that path.
   5. Set `steps.publish.ado.status = "done"`, store the resulting
      URL under `steps.publish.ado.url`, and stamp `completedAt`.

4. **PR publish sub-flow** (when chosen):
   1. Ask the follow-ups: `Draft PR? (Recommended) Yes / No`,
      `Target branch?` (default `main`),
      `Docs folder?` (default `docs/dev-designs`).
   2. Confirm the local repo is a git checkout
      (`git rev-parse --show-toplevel`); if not, surface the error and
      mark the step `skipped` with that reason.
   3. Show the user the full sequence of commands, then run them one
      at a time (stop on any non-zero exit and ask before retrying):
      ```
      git fetch origin
      git checkout -b dev-design/<id>-<slug> origin/<target>
      # copy <workspace>/dev-design-<id>-<slug>.md into <docs-folder>/
      ```
      Merge the new entry into `<docs-folder>/INDEX.md` with `view` +
      `edit` (do not regenerate the file from scratch). Then:
      ```
      git add <docs-folder>/dev-design-<id>-<slug>.md <docs-folder>/INDEX.md
      git commit -m "Dev design: <title> (<id>)"
      ```
      Show the diff via `git --no-pager show --stat HEAD` and confirm
      before pushing:
      ```
      git push -u origin dev-design/<id>-<slug>
      ```
   4. Check whether a PR already exists with
      `gh pr view --json url,number,state 2>$null`. If yes and the
      user picked "Re-publish to refresh", run `gh pr edit` to update
      the body. Otherwise:
      ```
      gh pr create [--draft] --base <target> --head dev-design/<id>-<slug> \
                   --title "Dev design: <title> (<id>)" \
                   --body-file <workspace>/dev-design-<id>-<slug>.md
      ```
   5. Set `steps.publish.pr.status = "done"`, store the PR URL under
      `steps.publish.pr.url`, and stamp `completedAt`. If `gh` isn't
      installed, mark the step `skipped` with the install hint
      (`winget install GitHub.cli` / `brew install gh`) as the reason.

5. **Both / Configure each separately.** Run the sub-flows back-to-back
   (Both) or ask `Post to ADO? Yes / Skip` then `Open a PR? Yes / Skip`
   (Configure each). Apply the same confirmation rules to each.

6. **After publishing.** Append a single-line metadata trailer into
   `sections/00-preamble.md` of the form
   `<!-- published: ado=<url> pr=<url> -->` (omit either side if not
   applicable) and re-run `assemble.py` so the rendered doc reflects
   the publish state. Surface the URLs to the user as the final output
   of Step 6.

7. **Failure handling.** Any non-zero exit from `az` / `git` / `gh`:
   show the stderr, ask `Retry? / Skip this one / Skip both`, and
   record the chosen path in the manifest. Never silently swallow
   errors — the user needs to know what went wrong before deciding.

8. **Resume awareness.** On a re-invocation, re-ask the up-front prompt
   only if both publish steps are `pending` or `skipped`. If either is
   `done`, jump straight to the "Re-publish to refresh?" collapsed
   prompt in step 1.

### Step 7 — review (Phase 8 entry point)

The skill can also lint an **existing** workspace without modifying it.
This is the entry point when the user says "review my dev design", "is
my dev design ready?", "lint my workspace", etc.

1. **Find the workspace.** Resolve a path one of three ways (ask the
   user if ambiguous):
   - explicit path the user provided,
   - the only `dev-design-*/` folder in cwd, or
   - the one with the most recent `manifest.json` mtime.

2. **Run the linter.**
   ```
   <python> <skill-dir>/scripts/review.py lint --workspace <ws> --json
   ```
   Capture stdout — it's the structured report.

3. **Surface the report.** Render a concise summary first:
   - `errors: N  warnings: N  info: N` headline
   - Group findings by `check_id` (so the user sees "5 unresolved
     TODOs" not 5 individual rows when they're all the same check).
   - For each finding, print the message + the `location` (truncate
     long messages to ~120 chars).
   - If the report is clean (`errors == 0 && warnings == 0`), say
     "Workspace is ready — no findings." and stop.

4. **Offer next actions** via a single `ask_user` with choices tailored
   to what was found:
   - When unresolved TODOs or placeholders exist: include
     `Open the walker on the affected sections` (drives Step 2 of the
     main flow restricted to those section ids).
   - When `ASSEMBLE_FRESH` is warning: include
     `Re-render the assembled .md`.
   - When `MERMAID_VALID` is error: include
     `Open the failing diagram for editing` (use `view`).
   - Always include `Skip — I'll fix manually`.

5. **Strict mode.** If the user said something like "is this ready to
   publish?" or "is this PR-ready?", re-run with `--strict` so warnings
   are promoted to errors. A non-zero strict exit blocks the
   recommendation to publish.

6. **review-only invocation.** If the user opened the skill via Step 1's
   "Review only" choice, run this step and then exit — do NOT proceed
   to the walker, publish, or anything else.

## Conventions

- TODO markers use `<!-- TODO(dev-design): ... -->` (greppable by Step 7
  review mode via `review.py`).
- The **workspace is the source of truth**. The rendered `.md` is a
  generated artifact — never hand-edit it; edit
  `workspace/sections/*.md` and re-render.
- Manifest is updated after every completed step so resume is reliable.
- No secrets are stored. ADO integration relies on the user's own
  `az login`; GitHub PR publishing relies on the user's `gh auth`.
- Output is plain markdown + JSON only. No binary state, no databases.

## Out of scope for Phase 8 (see README for the full roadmap)

This is the final shipped phase. Everything in the original roadmap is
now in place: workspace + assembler, ADO integration, repo scan, walker,
investigation mode, diagrams + telemetry, publishing helpers, review
mode, examples + installers. Future enhancements (e.g., richer review
checks, auto-fix mode, multi-doc rollups) live outside this skill.
