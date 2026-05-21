---
name: investigate
description: Use to investigate code AND verify findings. Spawns isolated subagents to prevent bias between investigation and verification. Saves findings to docs/investigations/.
---

# Investigate (Orchestrated with Isolation)

## Overview
Runs investigation and verification in **separate isolated contexts** to prevent confirmation bias. **Saves findings to a persistent document** that the verification agent reads independently.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Orchestrator (this skill)                               │
│   - Spawns agents                                       │
│   - Saves findings to doc file                          │
│   - Verifier reads from doc (not inline)                │
└─────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌──────────────────────┐    ┌──────────────────────────────┐
│ Agent 1: Investigator│    │ Agent 2: Verifier            │
│ (isolated context)   │    │ (isolated context)           │
│                      │    │                              │
│ - Explores code      │    │ - Reads findings FROM FILE   │
│ - Documents findings │    │ - Does NOT see Agent 1's     │
│ - Creates diagrams   │    │   reasoning or search history│
│ - Outputs structured │    │ - Independently verifies     │
│   findings           │    │ - Appends verification to doc│
└──────────────────────┘    └──────────────────────────────┘
```

## Process

### Step 0: Ensure Clean Code State (Master Branch)

**CRITICAL: Always investigate against the latest master branch to ensure findings are accurate.**

Check the current branch and ensure we're on master with latest code:

```bash
# Check current branch
current_branch=$(git branch --show-current)

# Check if we're on master
if [ "$current_branch" != "master" ]; then
  # Option 1: Use worktree (PREFERRED - doesn't disrupt current work)
  # Create a temporary worktree for investigation
  worktree_dir="/tmp/investigate-$(date +%s)"
  git worktree add "$worktree_dir" master
  cd "$worktree_dir"
  git pull origin master

  # Continue investigation in this worktree
  # Remember to clean up: git worktree remove "$worktree_dir" when done

  # Option 2: Switch to master (only if user confirms - disrupts current work)
  # git checkout master
  # git pull origin master
fi

# If already on master, just pull latest
if [ "$current_branch" = "master" ]; then
  git pull origin master
fi
```

**Decision Matrix:**
- **Not on master → Use worktree** (default, safe, doesn't disrupt work)
- **On master but not latest → Pull**
- **Already on latest master → Proceed**

**Include worktree path in investigation report** so user knows where code was investigated from.

### Step 1: Generate Investigation File Path

Create a file path for saving findings:
```
docs/investigations/{topic-slug}.md
```

Where `{topic-slug}` is a kebab-case version of the investigation topic (e.g., `meeting-recap-architecture.md`).

### Step 2: Spawn Investigation Agent

Use the Task tool to spawn an isolated agent:

```
Task tool:
  subagent_type: "Explore"
  prompt: |
    You are investigating: [USER'S QUESTION]

    Investigation Context:
    - Working Directory: [current directory - worktree path if applicable]
    - Branch: master
    - Commit: [git rev-parse HEAD output]
    - This investigation is being done on the LATEST MASTER branch

    Follow these rules from /investigation-analyzer:
    [Include full investigation-analyzer instructions]

    Output ONLY structured findings in this format:
    - Claim, Evidence (file, line, code), Dependencies
    - Mermaid diagrams with verification tables

    Do NOT include your search process or reasoning.
    Output ONLY the final structured findings.

    Include the commit hash and branch in your findings so verification
    can confirm they're checking the same code state.
```

### Step 3: Save Findings to Document

**CRITICAL: Save the investigation findings to a file BEFORE spawning the verification agent.**

Use the Write tool to save findings:
```
Write tool:
  file_path: "docs/investigations/{topic-slug}.md"
  content: |
    # Investigation Report: [Topic]

    **Date**: [Current Date]
    **Topic**: [User's Question]
    **Status**: PENDING VERIFICATION
    **Branch**: master (commit: [git commit hash])
    **Worktree**: [path to worktree if used, or "N/A - investigated on master"]

    ## Findings

    [Structured findings from Agent 1]

    ### Component Stack
    [Tables of components, files, purposes]

    ### Architecture Diagram
    [Mermaid diagram]

    ### Claims to Verify
    | Claim | File | Line | Code Evidence |
    |-------|------|------|---------------|
    [List each claim with evidence]

    ---

    ## Verification Results
    <!-- To be filled by verification agent -->
```

### Step 4: Spawn Verification Agent (Reads from File)

Use Task tool to spawn a SECOND isolated agent that **reads from the saved document**:

```
Task tool:
  subagent_type: "Explore"
  prompt: |
    You are a code correctness verifier. Your job is to verify
    that claims in an investigation document are backed by actual code.

    ASSUME THESE CLAIMS MAY BE WRONG. Verify independently.

    Verification Context:
    - Working Directory: [same directory as investigation - worktree path if applicable]
    - Verify you're on the same commit as the investigation
    - Check: git rev-parse HEAD matches the commit in the investigation doc

    ## Step 1: Read the Investigation Document
    Read the file: docs/investigations/{topic-slug}.md

    ## Step 2: Verify Code State Matches
    - Check the commit hash in the doc matches your current HEAD
    - If mismatch, STOP and report: "Cannot verify - code state mismatch"
    - This ensures you're verifying the same code that was investigated

    ## Step 3: For Each Claim in the Document
    1. Check if the file exists (Glob)
    2. Read the file and check the line numbers
    3. Verify function/type names actually exist (Grep)
    4. Check diagram nodes and connections

    ## Step 4: Output Verification Results
    For each claim, output:
    - Claim: [from doc]
    - Status: VERIFIED | INCORRECT | PARTIAL | NOT FOUND
    - Evidence: [what you actually found]
    - Corrections: [if incorrect, what is the actual truth]

    Be adversarial. Find what's wrong.
    Do NOT trust the document - verify everything independently.
```

### Step 5: Update Document with Verification

After verification completes, use Edit tool to update the document:
```
Edit tool:
  file_path: "docs/investigations/{topic-slug}.md"
  old_string: "**Status**: PENDING VERIFICATION"
  new_string: "**Status**: VERIFIED (Trust Level: HIGH/MEDIUM/LOW)"
```

And append verification results:
```
Edit tool:
  file_path: "docs/investigations/{topic-slug}.md"
  old_string: "<!-- To be filled by verification agent -->"
  new_string: |
    | Claim | Status | Notes |
    |-------|--------|-------|
    [Verification results table]

    ### Trust Level: [HIGH/MEDIUM/LOW]
    [Summary of verification]
```

### Step 6: Report to User

Present to user:
1. Location of saved document: `docs/investigations/{topic-slug}.md`
2. Summary of findings
3. Verification results
4. Trust level

## Critical Rules

### Code State Management
- **ALWAYS investigate on master branch with latest code**
- **Prefer worktrees** over branch switching (doesn't disrupt user's work)
- **Record commit hash** in investigation document for reproducibility
- **Verify code state** matches between investigation and verification phases
- **Clean up worktrees** after investigation completes

### Document-Based Isolation
- Agent 1 outputs findings
- Orchestrator saves findings to file
- Agent 2 reads ONLY from the file (not from inline context)
- This ensures complete isolation between agents
- Both agents must work on the SAME commit (verified by hash)

### File Naming Convention
- Use kebab-case: `meeting-recap-architecture.md`
- Include date if multiple investigations on same topic: `meeting-recap-architecture-2026-02-17.md`
- Store in: `docs/investigations/`

### What Goes in the Document

**INCLUDE:**
```yaml
Claim: "X exists at Y"
Evidence:
  File: path/to/file.ts
  Line: 42
  Code: |
    export const X = () => {...}
```

**DO NOT INCLUDE:**
```
I searched for "X" and found it might be in the components folder.
After checking several files, I believe X is at Y because...
```

### Verification Must Be Independent
- Agent 2 reads claims from the document file
- Agent 2 should search for files/functions itself
- Agent 2 should NOT trust file paths - verify they exist
- Agent 2 should read actual code, not trust quoted snippets

## Example Orchestration

```javascript
// Step 0: Ensure clean code state (master branch)
const currentBranch = await Bash("git branch --show-current");
let worktreePath = null;
let commitHash = null;

if (currentBranch !== "master") {
  // Create worktree for investigation
  worktreePath = `/tmp/investigate-${Date.now()}`;
  await Bash(`git worktree add ${worktreePath} master`);
  await Bash(`cd ${worktreePath} && git pull origin master`);
  commitHash = await Bash(`cd ${worktreePath} && git rev-parse HEAD`);
} else {
  // Pull latest on master
  await Bash("git pull origin master");
  commitHash = await Bash("git rev-parse HEAD");
}

// Step 1: Investigation
const findings = await Task({
  subagent_type: "Explore",
  prompt: `Investigate: ${userQuestion}.
    Working directory: ${worktreePath || process.cwd()}
    Branch: master
    Commit: ${commitHash}
    Output only structured findings.`
});

// Step 2: Save to document
const docPath = `docs/investigations/${topicSlug}.md`;
await Write({
  file_path: docPath,
  content: formatInvestigationDoc(findings, commitHash, worktreePath)
});

// Step 3: Verification (reads from file)
const verification = await Task({
  subagent_type: "Explore",
  prompt: `Read ${docPath} and verify each claim independently.
    Ensure you're on commit: ${commitHash}`
});

// Step 4: Update document with verification
await Edit({
  file_path: docPath,
  // Update status and append verification results
});

// Step 5: Cleanup worktree (if created)
if (worktreePath) {
  await Bash(`git worktree remove ${worktreePath}`);
}

// Step 6: Report location to user
return `Investigation saved to: ${docPath}
Investigated on master branch (commit: ${commitHash})`;
```

## Final Document Structure

```markdown
# Investigation Report: [Topic]

**Date**: YYYY-MM-DD
**Topic**: [User's Question]
**Status**: VERIFIED (Trust Level: HIGH)
**Branch**: master (commit: abc123)
**Worktree**: /tmp/investigate-1234567890 (or "N/A - investigated on master")

## Summary
[Brief overview]

## Architecture Diagram
[Mermaid diagram]

## Component Stack
[Table of components, files, purposes]

## Findings
[Detailed findings with code evidence]

---

## Verification Results

| Claim | Status | Notes |
|-------|--------|-------|
| Claim 1 | VERIFIED | Confirmed at file:line |
| Claim 2 | PARTIAL | Method exists but different signature |

### Trust Level: HIGH/MEDIUM/LOW

### Corrections
[If verifier found errors, show corrected information]
```

## Output to User

Always end by telling the user:
```
Investigation saved to: docs/investigations/{topic-slug}.md

[Summary of findings and verification status]

Note: Investigation was performed on master branch (commit: [hash])
[If worktree was used: "Worktree created at: [path] - remember to clean up with: git worktree remove [path]"]
```

### Worktree Cleanup

If a worktree was created for the investigation, remind the user to clean it up:
```bash
git worktree remove /tmp/investigate-1234567890
```

Alternatively, offer to clean it up automatically after presenting findings to the user.
