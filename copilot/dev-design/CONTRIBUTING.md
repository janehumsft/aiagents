# Contributing to the `dev-design` skill

This skill is meant to be **shared** — teammates clone the folder, run
`install.ps1` / `install.sh`, and start using it within their own Copilot
CLI profile. Contributions that make the skill more reliable or more
useful for that shared audience are very welcome.

## Quick start

```bash
# 1. Clone the repo containing this skill
git clone <your-repo>
cd <your-repo>/dev-design-skill

# 2. Install into your local Copilot CLI profile (creates ~/.copilot/skills/dev-design)
pwsh -File ./install.ps1 -Force -Smoke
# or, on macOS/Linux:
./install.sh --force --smoke

# 3. Verify the helpers work
python scripts/smoke_test.py        # full suite (~15 buckets)
python scripts/smoke_test.py --quick  # foundational checks only

# 4. Lint an existing workspace
python scripts/review.py lint --workspace path/to/dev-design-12345-my-feature
```

## Layout

```
dev-design-skill/
├── SKILL.md                # the skill's instructions (what Copilot follows)
├── template.md             # the canonical dev-design template
├── README.md               # human docs / roadmap
├── CONTRIBUTING.md         # you are here
├── install.ps1 / install.sh
├── prompts/                # bundled prompt assets
│   ├── investigation-subagent.md
│   └── section-questions.json
└── scripts/                # python helpers
    ├── init_workspace.py
    ├── assemble.py
    ├── walker.py
    ├── investigation_init.py
    ├── investigation_record.py
    ├── investigation_synthesize.py
    ├── mermaid_draft.py
    ├── review.py
    └── smoke_test.py
```

## Design principles

1. **Workspace is the source of truth.** The assembled `.md` is a
   generated artifact — never edit it directly. Edit fragments under
   `workspace/sections/` and re-render. `assemble.py --check` will tell
   you if the rendered doc has drifted from the fragments.
2. **No secrets.** Every integration relies on the user's own `az
   login` / `gh auth login`. The skill never asks for PATs or stores
   credentials.
3. **Offline fallback.** Every helper that touches an external service
   must work in `--mock` / `--skip` mode so the MVP path works with zero
   setup. Add a `_mock_response` shape to your helper and corresponding
   smoke-test coverage.
4. **Deterministic output.** Template ordering, headings, HTML comments,
   and table column layouts must round-trip exactly. The smoke test
   asserts re-renders are byte-identical.
5. **TODO markers** use `<!-- TODO(dev-design): … -->` so `review.py`
   can grep for unresolved bits.
6. **Manifest updates after every completed step**, so resume from a
   half-finished workspace is reliable.

## Adding a new helper script

1. Drop a `scripts/<name>.py` with a top-level docstring describing
   subcommands, flags, exit codes, and what manifest entries it touches.
2. Use exit code `0` for success, `2` for invalid input / setup, `3`
   for assertion failures / lint errors. Helpers that talk to a service
   should expose a `--mock-response <path>` (or `--mock`) flag and a
   `--skip --reason <text>` flag that records the skip in the manifest.
3. Add a `test_<name>()` bucket to `scripts/smoke_test.py`. The
   suggested checks are: happy path, idempotency (re-run = no-op
   unless `--force`), `--skip` behavior, an error case (exit 2 or 3),
   plus any helper-specific edge cases.
4. Document the script in `README.md`'s helper table and (if it's a
   user-visible step) in `SKILL.md`.

## Style

* **Python 3.8 baseline.** No walrus inside f-strings, no `match`. Use
  `from __future__ import annotations` so type hints don't load at
  runtime.
* **No third-party dependencies.** Stdlib only. The skill must work on
  a fresh laptop with nothing but Python + `az` + `gh` installed.
* **Atomic file writes** — never leave a partial manifest on disk.
  Read, mutate, then write once.
* **JSON on stdout for machine-readable results.** Human-readable
  output goes to stderr or behind a `--quiet` / `--json` toggle.
* **Use `<!-- TODO(dev-design): … -->` for any TODO** so review mode
  can pick it up.

## Running the smoke test

Always run `python scripts/smoke_test.py` before opening a PR. New
helpers should be covered by a new bucket; new flags on existing
helpers should be covered by an additional sub-check inside the
existing bucket.

For fast pre-commit feedback, `python scripts/smoke_test.py --quick`
runs only:
* Phase 1b — init + assemble + idempotency + `--check` drift
* Phase 4 — walker state transitions
* Phase 8 — review lint (TODO / placeholder / stale assemble / strict)

## Publishing the skill folder

Two options for sharing with teammates:

1. **Commit it to a team repo.** Teammates clone and run the
   installer. The `install.ps1` / `install.sh` scripts are idempotent
   when run with `-Force` / `--force`, so pulling updates and
   reinstalling is one command.
2. **Bundle as a zip** if you want to send a snapshot without git
   access. Drop the unzipped folder anywhere and run the installer.

The skill stores no per-user state inside its own folder — all state
goes into the dev-design workspaces the user creates. That means the
installed copy is purely read-only, and you can safely overwrite it
when a new version drops.
