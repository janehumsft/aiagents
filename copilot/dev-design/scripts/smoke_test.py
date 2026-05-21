#!/usr/bin/env python3
"""
smoke_test.py - End-to-end sanity check for the dev-design skill helpers.

Phase 1b coverage (init + assemble + idempotency):
  1. init_workspace creates a folder with the expected layout
  2. assemble.py produces a doc identical to the template (modulo banner)
     when no fragments are present
  3. Adding a fragment for section 1 updates only that section
  4. Re-running assemble.py with no fragment changes produces a
     byte-identical .md (idempotent rendering)
  5. A malformed fragment is rejected with exit code 2

Walker / investigation / mermaid / review coverage:
  6. walker.py tracks per-section status transitions and re-promotes the
     render step to stale when sections regress
  7. investigation_init/record/synthesize enforce the 5-H2 contract on
     subagent outputs and provide the re-prompt gate
  8. mermaid_draft generates, validates, and embeds Mermaid blocks
  9. review.py runs the 9-check linter

Usage: python smoke_test.py [--quick]
"""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.resolve()
SKILL_DIR = SCRIPTS_DIR.parent
TEMPLATE = SKILL_DIR / "template.md"
PY = sys.executable


def run(*cmd: str) -> dict:
    proc = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    out = proc.stdout.strip()
    if not out:
        return {"_raw": ""}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        try:
            return json.loads(out.splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return {"_raw": out}


def run_expect(rc: int, *cmd: str):
    proc = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
    assert proc.returncode == rc, (
        f"expected exit {rc}, got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    return proc


def test_phase1b():
    print("Phase 1b - workspace + assembler")
    print("-" * 40)
    with tempfile.TemporaryDirectory(prefix="dd-smoke-1b-") as tmp:
        tmp = Path(tmp)
        init = run(
            PY, str(SCRIPTS_DIR / "init_workspace.py"),
            "--out-dir", str(tmp),
            "--feature-name", "Smoke Test Feature",
            "--work-item-id", "99999",
            "--work-item-url", "https://dev.azure.com/example/_workitems/edit/99999",
        )
        ws = Path(init["workspace"])
        assert ws.exists()
        assert (ws / "workspace" / "manifest.json").exists()
        assert (ws / "workspace" / "inputs" / "answers.json").exists()
        assert (ws / "workspace" / "sections").exists()
        print("  [ok] init_workspace produced expected layout")

        out = run(
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws),
            "--template", str(TEMPLATE),
        )
        md_path = Path(out["output"])
        rendered = md_path.read_text(encoding="utf-8")
        template_text = TEMPLATE.read_text(encoding="utf-8")
        assert rendered.startswith("<!-- GENERATED FILE."), "banner missing"
        assert template_text.strip() in rendered, "template body missing"
        print(f"  [ok] empty-fragments assemble: {md_path.name} ({len(rendered)} bytes)")

        frag = (
            "## 1. Summary and Goals\n\n"
            "Smoke test override of section 1.\n\n"
            "### Phases\n\n"
            "1. **Smoke** -- verifies the assembler.\n"
        )
        (ws / "workspace" / "sections" / "01-summary-and-goals.md").write_text(frag, encoding="utf-8")
        run(
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws),
            "--template", str(TEMPLATE),
        )
        r2 = md_path.read_text(encoding="utf-8")
        assert "Smoke test override of section 1." in r2
        assert "## 2. Signoffs" in r2
        assert "[Describe the current system/behavior" not in r2
        print("  [ok] fragment override applied; other sections preserved")

        run(
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws),
            "--template", str(TEMPLATE),
        )
        r3 = md_path.read_text(encoding="utf-8")
        assert r3 == r2, "re-render is not byte-identical"
        print("  [ok] re-render is byte-identical (deterministic)")

        (ws / "workspace" / "sections" / "02-signoffs.md").write_text(
            "# wrong heading level\n", encoding="utf-8"
        )
        proc = run_expect(
            2,
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws), "--template", str(TEMPLATE),
        )
        assert "must start with" in proc.stderr
        print("  [ok] malformed fragment rejected with exit 2")

        # repair sections/02 so we can test --check
        (ws / "workspace" / "sections" / "02-signoffs.md").write_text(
            "## 2. Signoffs\n\nReviewer A\n", encoding="utf-8"
        )
        run(
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws), "--template", str(TEMPLATE),
        )
        check_ok = run(
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws), "--template", str(TEMPLATE),
            "--check",
        )
        assert check_ok.get("check") == "ok"
        # Mutate a fragment without re-rendering -> --check should fail
        (ws / "workspace" / "sections" / "02-signoffs.md").write_text(
            "## 2. Signoffs\n\nReviewer B (modified)\n", encoding="utf-8"
        )
        proc = run_expect(
            2,
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws), "--template", str(TEMPLATE),
            "--check",
        )
        assert "differs from existing" in proc.stderr
        print("  [ok] assemble.py --check detects drift")


def test_walker():
    print("Phase 4 - walker.py (per-section progress)")
    print("-" * 40)
    with tempfile.TemporaryDirectory(prefix="dd-smoke-4-") as tmp:
        tmp = Path(tmp)
        init = run(
            PY, str(SCRIPTS_DIR / "init_workspace.py"),
            "--out-dir", str(tmp),
            "--feature-name", "Walker Test",
            "--work-item-id", "77777",
        )
        ws = Path(init["workspace"])

        manifest = json.loads((ws / "workspace" / "manifest.json").read_text(encoding="utf-8"))
        assert "sectionStatus" in manifest, "init must seed sectionStatus"
        assert len(manifest["sectionStatus"]) == 11
        assert all(v == "pending" for v in manifest["sectionStatus"].values())
        print("  [ok] init_workspace seeds 11 pending sections")

        listed = run(PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws), "list")
        assert listed["totalSections"] == 11
        assert listed["next"] == "00-preamble"
        assert listed["progress"]["pending"] == 11
        print("  [ok] list returns next=00-preamble, 11 pending")

        nxt = run(PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws), "next")
        assert nxt["next"] == "00-preamble"
        assert isinstance(nxt["questions"], list)
        assert any(q["id"] == "preamble.title" for q in nxt["questions"]), \
            "question bank should be wired in"
        print(f"  [ok] next surfaces {len(nxt['questions'])} questions from the bank")

        # Set 00 -> done, defer 01, skip 02
        r1 = run(PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws), "set",
                 "--section", "00-preamble", "--status", "done")
        assert r1["next"] == "01-summary-and-goals"
        r2 = run(PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws), "set",
                 "--section", "01-summary-and-goals", "--status", "deferred")
        # 01 is deferred, next pending should be 02
        assert r2["next"] == "02-signoffs", r2
        r3 = run(PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws), "set",
                 "--section", "02-signoffs", "--status", "skipped")
        # 02 skipped doesn't count as incomplete; next pending should be 03
        assert r3["next"] == "03-scope", r3
        print("  [ok] set transitions done/deferred/skipped and next() advances correctly")

        # Bad inputs
        proc = run_expect(
            3, PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws),
            "set", "--section", "99-nope", "--status", "done",
        )
        assert "unknown section" in proc.stderr
        proc = run_expect(
            3, PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws),
            "set", "--section", "00-preamble", "--status", "bogus",
        )
        assert "unknown status" in proc.stderr
        print("  [ok] bad section / status rejected with exit 3")

        # Drive all remaining to done; verify steps.sections.render flips to done
        for sid in [
            "01-summary-and-goals", "03-scope", "04-feature-flags",
            "05-implementation-phases", "06-tradeoffs", "07-telemetry",
            "08-ownership", "09-test-scenarios", "10-appendix",
        ]:
            run(PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws),
                "set", "--section", sid, "--status", "done")
        manifest = json.loads((ws / "workspace" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["steps"]["sections.render"]["status"] == "done", manifest["steps"]
        print("  [ok] sections.render flips to done when no section is incomplete")

        # Now defer one -> render should flip back to in-progress
        run(PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws),
            "set", "--section", "06-tradeoffs", "--status", "deferred")
        manifest = json.loads((ws / "workspace" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["steps"]["sections.render"]["status"] == "in-progress"
        print("  [ok] deferring a section flips sections.render back to in-progress")

        summary = run(PY, str(SCRIPTS_DIR / "walker.py"), "--workspace", str(ws), "summary")
        assert summary["totalSections"] == 11
        assert summary["complete"] == 9 + 1  # 9 done + 1 skipped (02-signoffs)
        # 06-tradeoffs is deferred but is not in REQUIRED set, so missingRequired stays empty
        assert summary["missingRequired"] == [], summary
        print(f"  [ok] summary reports complete={summary['complete']} / 11")


VALID_RAW = """# client (local)

## Summary

The client owns the AuthV2 sign-in surface. It currently calls /api/v1/login
synchronously, which blocks the UI thread during retries.

## Key files & symbols

- `src/auth/SignIn.tsx` -- presentational sign-in form
- `src/auth/useLoginMutation.ts` -- legacy login mutation using fetch
- `src/auth/AuthContext.tsx` -- holds the token in memory

## Proposed changes

- **Async login** -- migrate `useLoginMutation` to a worker-thread strategy,
  touching `src/auth/useLoginMutation.ts` and `src/auth/SignIn.tsx`.
- **Telemetry** -- add `auth.login.attempt` event in `useLoginMutation`.

## Risks & unknowns

- Service worker support on legacy iOS may not be available.
- The session refresh code path is not covered by tests.

## Citations

- `src/auth/useLoginMutation.ts` (lines 12-44) -- legacy fetch flow
- `src/auth/SignIn.tsx` (lines 60-110) -- form submission handler
- https://github.com/myorg/client/blob/main/src/auth/AuthContext.tsx -- token storage
"""

INVALID_RAW_NO_CITATIONS = """# service (local)

## Summary

The service handles login at /api/v1/login.

## Key files & symbols

- `Controllers/LoginController.cs`

## Proposed changes

- **Add metrics** -- track login latency.

## Risks & unknowns

- Cache miss rates unknown.

## Citations

"""


def test_investigation():
    print("Phase 5 - investigation (init / record / synthesize)")
    print("-" * 40)
    with tempfile.TemporaryDirectory(prefix="dd-smoke-5-") as tmp:
        tmp = Path(tmp)
        init = run(
            PY, str(SCRIPTS_DIR / "init_workspace.py"),
            "--out-dir", str(tmp),
            "--feature-name", "Investigation Feature",
            "--work-item-id", "88888",
        )
        ws = Path(init["workspace"])

        # --- init ---
        opened = run(
            PY, str(SCRIPTS_DIR / "investigation_init.py"),
            "--workspace", str(ws),
            "--focus", "auth flow",
            "--focus", "telemetry",
            "--source", "local:client:Q:/src/client",
            "--source", "github:service:myorg/service",
            "--max-parallel", "3",
        )
        assert opened["ok"] is True
        assert opened["pendingCount"] == 2
        assert len(opened["sources"]) == 2
        assert opened["focusAreas"] == ["auth flow", "telemetry"]
        assert opened["budget"]["maxParallel"] == 3
        inv_dir = ws / "workspace" / "investigation"
        assert (inv_dir / "scope.json").exists()
        assert (inv_dir / "plan.md").exists()
        assert (inv_dir / "raw").is_dir()
        assert (inv_dir / "synth").is_dir()
        manifest = json.loads((ws / "workspace" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["steps"]["investigation"]["status"] == "in-progress"
        print("  [ok] init created plan + scope + manifest set to in-progress")

        # --- record one as in-progress, one as done ---
        ip = run(
            PY, str(SCRIPTS_DIR / "investigation_record.py"),
            "--workspace", str(ws), "--source", "client",
            "--status", "in-progress", "--agent-id", "explore-1",
        )
        assert ip["status"] == "in-progress"

        # Write a valid raw file and mark done
        (inv_dir / "raw" / "client.md").write_text(VALID_RAW, encoding="utf-8")
        done1 = run(
            PY, str(SCRIPTS_DIR / "investigation_record.py"),
            "--workspace", str(ws), "--source", "client",
            "--status", "done", "--raw-file", "raw/client.md",
        )
        assert done1["status"] == "done"
        print("  [ok] record marks in-progress then done; agent id persisted")

        # --- synthesize with one source still pending (default mode) should fail ---
        proc = run_expect(
            4, PY, str(SCRIPTS_DIR / "investigation_synthesize.py"),
            "--workspace", str(ws),
        )
        err = json.loads(proc.stderr)
        assert err["error"].startswith("some sources are not yet done"), err
        print("  [ok] synthesize refuses incomplete scope without --allow-partial")

        # --- write an invalid raw, then mark service done; synthesize must fail validation ---
        (inv_dir / "raw" / "service.md").write_text(INVALID_RAW_NO_CITATIONS, encoding="utf-8")
        run(
            PY, str(SCRIPTS_DIR / "investigation_record.py"),
            "--workspace", str(ws), "--source", "service",
            "--status", "done", "--raw-file", "raw/service.md",
        )
        proc = run_expect(
            3, PY, str(SCRIPTS_DIR / "investigation_synthesize.py"),
            "--workspace", str(ws),
        )
        err = json.loads(proc.stderr)
        assert "service" in err["problems"], err
        assert any("citations" in p.lower() for p in err["problems"]["service"]), err
        print("  [ok] synthesize rejects raw file with empty citations (exit 3)")

        # --- fix the invalid raw and re-synthesize successfully ---
        (inv_dir / "raw" / "service.md").write_text(
            VALID_RAW.replace("client", "service").replace("(local)", "(github)"),
            encoding="utf-8",
        )
        summary = run(
            PY, str(SCRIPTS_DIR / "investigation_synthesize.py"),
            "--workspace", str(ws),
        )
        assert summary["ok"] is True
        assert set(summary["synthesizedSources"]) == {"client", "service"}
        assert summary["citationCount"] >= 6  # 3 per source
        synth_dir = inv_dir / "synth"
        assert (synth_dir / "findings.md").exists()
        assert (synth_dir / "work-breakdown.md").exists()
        repos = json.loads((synth_dir / "repos.json").read_text(encoding="utf-8"))
        cits = json.loads((synth_dir / "citations.json").read_text(encoding="utf-8"))
        assert len(repos) == 2
        assert any(c.get("url") for c in cits)
        manifest = json.loads((ws / "workspace" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["steps"]["investigation"]["status"] == "done"
        print(f"  [ok] synthesis produced 4 artifacts, {len(cits)} citations")

        # --- idempotent ---
        again = run(
            PY, str(SCRIPTS_DIR / "investigation_synthesize.py"),
            "--workspace", str(ws),
        )
        assert again.get("skipped") is True
        print("  [ok] re-run without --force is idempotent")

        # --- partial mode synthesizes a subset ---
        with tempfile.TemporaryDirectory(prefix="dd-smoke-5b-") as tmp2:
            tmp2 = Path(tmp2)
            init2 = run(
                PY, str(SCRIPTS_DIR / "init_workspace.py"),
                "--out-dir", str(tmp2), "--feature-name", "Partial Test",
            )
            ws2 = Path(init2["workspace"])
            run(
                PY, str(SCRIPTS_DIR / "investigation_init.py"),
                "--workspace", str(ws2),
                "--source", "local:only:Q:/src/only",
                "--source", "github:never:myorg/never",
            )
            (ws2 / "workspace" / "investigation" / "raw" / "only.md").write_text(VALID_RAW, encoding="utf-8")
            run(
                PY, str(SCRIPTS_DIR / "investigation_record.py"),
                "--workspace", str(ws2), "--source", "only",
                "--status", "done", "--raw-file", "raw/only.md",
            )
            partial = run(
                PY, str(SCRIPTS_DIR / "investigation_synthesize.py"),
                "--workspace", str(ws2), "--allow-partial",
            )
            assert partial["partial"] is True
            assert partial["synthesizedSources"] == ["only"]
            print("  [ok] --allow-partial synthesizes only completed sources")


def test_mermaid_draft():
    print("Phase 6 - mermaid_draft.py")
    print("-" * 40)
    with tempfile.TemporaryDirectory(prefix="dd-smoke-6m-") as tmp:
        tmp = Path(tmp)
        init = run(
            PY, str(SCRIPTS_DIR / "init_workspace.py"),
            "--out-dir", str(tmp),
            "--feature-name", "Diagram Feature",
        )
        ws = Path(init["workspace"])

        # Seed phases via answers.json (walker would normally write this)
        ans_path = ws / "workspace" / "inputs" / "answers.json"
        answers = json.loads(ans_path.read_text(encoding="utf-8"))
        answers["phases"] = ["Backend API", "Web UI", "Rollout"]
        ans_path.write_text(json.dumps(answers, indent=2), encoding="utf-8")

        out = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "draft", "--workspace", str(ws),
        )
        assert out["ok"] is True
        assert out["draftedPhases"] == [1, 2, 3]
        files = sorted(out["files"])
        assert files == [
            "phase-1-backend-api.mmd",
            "phase-2-web-ui.mmd",
            "phase-3-rollout.mmd",
        ], files
        diag_dir = ws / "workspace" / "diagrams"
        idx = json.loads((diag_dir / "diagrams.json").read_text(encoding="utf-8"))
        assert len(idx["phases"]) == 3
        body = (diag_dir / "phase-1-backend-api.mmd").read_text(encoding="utf-8")
        assert "flowchart LR" in body
        assert 'subgraph Current["Current state"]' in body
        assert 'subgraph Proposed["Proposed state"]' in body
        assert "TODO" in body
        print("  [ok] draft produced 3 phase files with current/proposed subgraphs")

        manifest = json.loads((ws / "workspace" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["steps"]["diagrams.draft"]["status"] == "done"
        print("  [ok] manifest.diagrams.draft = done")

        # Validate clean files -> ok
        val = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "validate", "--workspace", str(ws),
        )
        assert val["ok"] is True and len(val["files"]) == 3
        print("  [ok] validate accepts generated flowcharts")

        # Validate corrupt file -> exit 3
        (diag_dir / "phase-1-backend-api.mmd").write_text(
            "this is not mermaid\nno keyword on line 1\n",
            encoding="utf-8",
        )
        proc = run_expect(
            3, PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "validate", "--workspace", str(ws),
        )
        err = json.loads(proc.stderr)
        assert "phase-1-backend-api.mmd" in err["problems"], err
        print("  [ok] validate rejects malformed mermaid with exit 3")

        # Sequence style for a single phase, --force
        seq = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "draft", "--workspace", str(ws),
            "--phase", "2", "--style", "sequence", "--force",
        )
        assert seq["draftedPhases"] == [2]
        seq_body = (diag_dir / "phase-2-web-ui.mmd").read_text(encoding="utf-8")
        assert "sequenceDiagram" in seq_body
        assert "autonumber" in seq_body
        print("  [ok] sequence style draft works for a single phase")

        # list subcommand
        listed = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "list", "--workspace", str(ws),
        )
        assert listed["indexExists"] is True
        assert len(listed["files"]) == 3
        print("  [ok] list prints index + files")

        # ---- embed subcommand ----
        # Restore a clean phase-1 file (we corrupted it earlier for validate testing)
        run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "draft", "--workspace", str(ws), "--phase", "1", "--force",
        )

        # Seed section 05 with three different marker forms so we exercise
        # every code path: empty marker (insert), inline "See ..." (replace),
        # and an existing ```mermaid block (replace in place).
        sec = ws / "workspace" / "sections" / "05-implementation-phases.md"
        sec.write_text(
            "## 5. Implementation Phases\n\n"
            "### Phase 1: Backend API\n\nIntro.\n\n"
            "**Current vs. Proposed Flow**:\n\n"
            "**Proposed Changes**:\n\n1. **Foo**\n\n"
            "---\n\n"
            "### Phase 2: Web UI\n\n"
            "**Current vs. Proposed Flow**: See `workspace/diagrams/phase-2-web-ui.mmd`.\n\n"
            "**Validation**: tbd\n\n"
            "---\n\n"
            "### Phase 3: Rollout\n\n"
            "**Current vs. Proposed Flow**:\n\n"
            "```mermaid\nflowchart LR\n    OldA[\"stale\"] --> OldB\n```\n\n"
            "**Validation**: tbd\n",
            encoding="utf-8",
        )

        embed = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "embed", "--workspace", str(ws),
        )
        assert embed["ok"] is True and embed["changed"] is True
        statuses = {r["phase"]: r["status"] for r in embed["results"]}
        assert statuses == {1: "inserted", 2: "replaced", 3: "replaced"}, statuses

        text = sec.read_text(encoding="utf-8")
        assert text.count("```mermaid") == 3, text
        # The "See ..." reference is gone
        assert "See `workspace/diagrams/phase-2-web-ui.mmd`" not in text
        # The stale block from Phase 3 was replaced
        assert "OldA" not in text and "stale" not in text
        # Each phase has the matching mermaid content (sample a TODO marker
        # that mermaid_draft seeds into every drafted file).
        assert text.count('"Component A <!-- TODO: today\'s role -->"') >= 1
        print("  [ok] embed inserts / replaces / overwrites all three marker forms")

        # Idempotency: re-running without --force is a no-op
        embed2 = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "embed", "--workspace", str(ws),
        )
        assert embed2["changed"] is False
        assert all(r["status"] == "unchanged" for r in embed2["results"])
        print("  [ok] embed is idempotent (re-run = unchanged)")

        # --dry-run
        dry = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "embed", "--workspace", str(ws), "--dry-run", "--force",
        )
        assert dry["dryRun"] is True
        # File on disk should not have changed
        text_after_dry = sec.read_text(encoding="utf-8")
        assert text_after_dry == text
        print("  [ok] --dry-run reports intent without writing")

        # Targeted --phase
        # Mutate phase 2's mermaid file so we can detect re-embed
        diag2 = ws / "workspace" / "diagrams" / "phase-2-web-ui.mmd"
        diag2.write_text("flowchart LR\n    UNIQUE_TOKEN_xyz --> done\n", encoding="utf-8")
        targeted = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "embed", "--workspace", str(ws), "--phase", "2", "--force",
        )
        results = {r["phase"]: r["status"] for r in targeted["results"]}
        assert list(results.keys()) == [2], results
        text2 = sec.read_text(encoding="utf-8")
        assert "UNIQUE_TOKEN_xyz" in text2
        print("  [ok] --phase targets a single block and --force re-embeds")

        # No-marker case: a section without the "Current vs. Proposed Flow:" line
        sec.write_text(
            "## 5. Implementation Phases\n\n"
            "### Phase 1: Backend API\n\nNo flow marker here.\n",
            encoding="utf-8",
        )
        noflow = run(
            PY, str(SCRIPTS_DIR / "mermaid_draft.py"),
            "embed", "--workspace", str(ws), "--phase", "1",
        )
        assert noflow["results"][0]["status"] == "no-marker"
        print("  [ok] missing flow marker -> status 'no-marker', no file modification")



def test_review():
    print("Phase 8 - review.py")
    print("-" * 40)
    with tempfile.TemporaryDirectory(prefix="dd-smoke-review-") as tmp:
        tmp = Path(tmp)
        init = run(
            PY, str(SCRIPTS_DIR / "init_workspace.py"),
            "--out-dir", str(tmp),
            "--feature-name", "Review Test",
            "--work-item-id", "55555",
        )
        ws = Path(init["workspace"])

        # list-checks always exits 0 and prints every id
        proc = subprocess.run(
            [PY, str(SCRIPTS_DIR / "review.py"), "list-checks"],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 0
        for cid in ("SECTIONS_PRESENT", "TODOS_RESOLVED", "MERMAID_VALID",
                    "PUBLISH_STATUS"):
            assert cid in proc.stdout, f"check id {cid} missing from list"
        print("  [ok] list-checks reports every check id")

        # Empty workspace: expect MANY warnings (no fragments) and exit 2
        proc = subprocess.run(
            [PY, str(SCRIPTS_DIR / "review.py"), "lint",
             "--workspace", str(ws), "--json"],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 2, (
            f"expected exit 2 on empty ws, got {proc.returncode}\n{proc.stderr}"
        )
        payload = json.loads(proc.stdout)
        assert payload["summary"]["warnings"] >= 8, (
            f"expected >=8 warnings for empty ws, got {payload['summary']}"
        )
        # SECTIONS_PRESENT should be the dominant source of warnings
        sec_present = [c for c in payload["checks"]
                       if c["id"] == "SECTIONS_PRESENT"
                       and c["severity"] == "warning"]
        assert len(sec_present) >= 10, (
            f"expected most sections flagged as missing, got {len(sec_present)}"
        )
        print("  [ok] empty workspace -> warnings on missing fragments, exit 2")

        # Add a fragment with a TODO + a placeholder; reassemble; lint again
        (ws / "workspace" / "sections" / "01-summary-and-goals.md").write_text(
            "## 1. Summary and Goals\n\n"
            "We will ship the [Project/Feature Name] revamp.\n\n"
            "<!-- TODO(dev-design): finalize success metric -->\n\n"
            "### Phases\n\n1. **Bootstrap** -- start.\n",
            encoding="utf-8",
        )
        for sid in ("02-signoffs", "03-scope", "04-feature-flags",
                    "05-implementation-phases", "06-tradeoffs",
                    "07-telemetry", "08-ownership", "09-test-scenarios",
                    "10-appendix"):
            num = int(sid.split("-", 1)[0])
            title_part = sid.split("-", 1)[1].replace("-", " ").title()
            (ws / "workspace" / "sections" / f"{sid}.md").write_text(
                f"## {num}. {title_part}\n\nFilled by smoke test.\n",
                encoding="utf-8",
            )
        (ws / "workspace" / "sections" / "00-preamble.md").write_text(
            "# Dev Design: Review Test\n\n"
            "<!-- metadata -->\n\n"
            "Work item: 55555\n"
            "Slug: review-test\n",
            encoding="utf-8",
        )
        run(
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws), "--template", str(TEMPLATE),
        )

        proc = subprocess.run(
            [PY, str(SCRIPTS_DIR / "review.py"), "lint",
             "--workspace", str(ws), "--json"],
            capture_output=True, text=True, check=False,
        )
        # Should still warn about the TODO + placeholder, but no missing sections
        assert proc.returncode == 2, (
            f"expected exit 2 (warnings), got {proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
        payload = json.loads(proc.stdout)
        todo_hits = [c for c in payload["checks"] if c["id"] == "TODOS_RESOLVED"]
        placeholder_hits = [c for c in payload["checks"]
                            if c["id"] == "PLACEHOLDERS_FILLED"]
        missing_section_hits = [c for c in payload["checks"]
                                if c["id"] == "SECTIONS_PRESENT"
                                and c["severity"] == "warning"]
        assert len(todo_hits) >= 1, "TODO not detected"
        assert len(placeholder_hits) >= 1, "Placeholder not detected"
        assert not missing_section_hits, (
            f"unexpected SECTIONS_PRESENT warnings: {missing_section_hits}"
        )
        # TODO finding must include line number
        assert todo_hits[0]["location"].endswith(":4") or ":" in todo_hits[0]["location"]
        print("  [ok] TODO + placeholder findings reported with locations")

        # --only TODOS_RESOLVED filters everything else out
        proc = subprocess.run(
            [PY, str(SCRIPTS_DIR / "review.py"), "lint",
             "--workspace", str(ws), "--json",
             "--only", "TODOS_RESOLVED"],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 2
        payload = json.loads(proc.stdout)
        ids = {c["id"] for c in payload["checks"]}
        assert ids == {"TODOS_RESOLVED"}, f"--only leak: {ids}"
        print("  [ok] --only filters to a single check id")

        # --skip drops a check
        proc = subprocess.run(
            [PY, str(SCRIPTS_DIR / "review.py"), "lint",
             "--workspace", str(ws), "--json",
             "--skip", "TODOS_RESOLVED", "--skip", "PLACEHOLDERS_FILLED"],
            capture_output=True, text=True, check=False,
        )
        payload = json.loads(proc.stdout)
        ids = {c["id"] for c in payload["checks"]}
        assert "TODOS_RESOLVED" not in ids
        assert "PLACEHOLDERS_FILLED" not in ids
        print("  [ok] --skip drops the named checks")

        # Resolve the TODO + placeholder, re-assemble, lint should pass (exit 0)
        (ws / "workspace" / "sections" / "01-summary-and-goals.md").write_text(
            "## 1. Summary and Goals\n\n"
            "We will ship the new login flow.\n\n"
            "### Phases\n\n1. **Bootstrap** -- start.\n",
            encoding="utf-8",
        )
        run(
            PY, str(SCRIPTS_DIR / "assemble.py"),
            "--workspace", str(ws), "--template", str(TEMPLATE),
        )
        proc = subprocess.run(
            [PY, str(SCRIPTS_DIR / "review.py"), "lint",
             "--workspace", str(ws), "--json"],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 0, (
            f"expected exit 0 after fixes, got {proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
        payload = json.loads(proc.stdout)
        assert payload["summary"]["errors"] == 0
        assert payload["summary"]["warnings"] == 0
        print("  [ok] clean workspace returns exit 0 with no warnings")

        # Stale assemble: touch a fragment after rendering, expect ASSEMBLE_FRESH warn
        import time
        time.sleep(1.1)
        (ws / "workspace" / "sections" / "01-summary-and-goals.md").write_text(
            "## 1. Summary and Goals\n\nUpdated copy.\n\n"
            "### Phases\n\n1. **Bootstrap** -- start.\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [PY, str(SCRIPTS_DIR / "review.py"), "lint",
             "--workspace", str(ws), "--json"],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 2
        payload = json.loads(proc.stdout)
        stale = [c for c in payload["checks"]
                 if c["id"] == "ASSEMBLE_FRESH" and c["severity"] == "warning"]
        assert stale, "expected ASSEMBLE_FRESH warning after fragment edit"
        print("  [ok] ASSEMBLE_FRESH catches stale rendered doc")

        # --strict promotes the stale warning to error -> exit 3
        proc = subprocess.run(
            [PY, str(SCRIPTS_DIR / "review.py"), "lint",
             "--workspace", str(ws), "--strict", "--json"],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 3
        print("  [ok] --strict promotes warnings to errors (exit 3)")


def main() -> int:
    import argparse as _argparse
    ap = _argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true",
                    help="Run only the foundational checks (phase1b + walker + review). "
                         "Useful for fast pre-commit validation.")
    args = ap.parse_args()

    print("dev-design skill smoke test")
    print("=" * 40)
    if not TEMPLATE.exists():
        print(f"FAIL: template not found at {TEMPLATE}")
        return 1
    test_phase1b()
    print()
    if args.quick:
        test_walker()
        print()
        test_review()
        print()
        print("=" * 40)
        print("QUICK CHECKS PASSED")
        return 0
    test_walker()
    print()
    test_investigation()
    print()
    test_mermaid_draft()
    print()
    test_review()
    print()
    print("=" * 40)
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
