# dev-design skill — filled example

This folder is a **read-only example workspace** that shows what a
properly-filled `dev-design` skill output looks like. Use it as a
reference when authoring your own design, or as a sample for `review.py`
to lint against.

## What's here

- `dev-design-12345-login-retry-policy/` — a complete workspace for a
  fictional "Login Retry Policy" feature.
  - `workspace/manifest.json` — every step marked `done` (no publishing).
  - `workspace/sections/00..10` — all 11 fragments filled with realistic
    content. No unresolved `<!-- TODO(dev-design): -->` markers, no
    unfilled `[bracketed]` placeholders.
  - `workspace/diagrams/phase-1-bootstrap.mmd` — a Mermaid skeleton.
  - `workspace/inputs/answers.json` — structured Q&A state.
  - `dev-design-12345-login-retry-policy.md` — the assembled doc.

## Verify against `review.py`

From the skill folder:

```powershell
python scripts/review.py lint --workspace examples/filled-example/dev-design-12345-login-retry-policy
```

You should see `errors: 0  warnings: 0  info: 2` — the only findings
are `PUBLISH_STATUS` informational entries (publish.ado / publish.pr
intentionally never run in the example).

## Re-render from fragments

If you ever doubt that the assembler is deterministic, copy the example
out and re-render:

```powershell
python scripts/assemble.py `
    --workspace examples/filled-example/dev-design-12345-login-retry-policy `
    --template template.md
```

The resulting `.md` should be byte-identical to the one already on
disk (modulo a fresh `lastRenderedAt` timestamp in the manifest).

## Editing the example

If you change the template, regenerate the example by re-running the
assembler. If you change a fragment, re-run the assembler too — the
example is checked in as a snapshot of "what good looks like."
