---
name: explore-new-codebase
description: Use when the user has just cloned a new codebase and wants to understand its structure, architecture, dependencies, and how to run it locally. Triggers on phrases like "I just cloned", "help me understand this repo", "what is this project", "how do I run this", or "explore this codebase".
---

# Explore New Codebase

## Overview

Thoroughly explore an unfamiliar codebase without assumptions. Read all documentation, map the structure, and produce a clear diagram plus local-run instructions.

**Core principle:** Read first, conclude second. Never guess at structure or purpose.

## What to Produce

1. **Project structure diagram** (ASCII tree)
2. **Architecture summary** (what each layer/module does)
3. **How to run locally** (bullet-point steps)

---

## Step 1: Read All Documentation First

Before touching source code, read every doc file that exists.

```
Priority order:
1. README.md / README.rst / README (root level)
2. docs/ folder — all .md files
3. CONTRIBUTING.md, DEVELOPMENT.md, SETUP.md, INSTALL.md
4. Wiki links referenced in README
5. .github/ folder (workflows reveal build process)
6. Inline comments at top of main entry-point files
7. Package manifests: package.json, pyproject.toml, Cargo.toml, go.mod, pom.xml, etc.
```

**Do not skip this step.** Docs explain intent; code only shows implementation.

---

## Step 2: Map the File Structure

Use Glob to scan the full tree. Do not assume a layout from the language or framework.

```
Glob patterns to run:
- "**/*" (all files, to see overall shape)
- "src/**/*", "lib/**/*", "app/**/*", "packages/**/*"
- "**/index.*", "**/main.*", "**/app.*" (entry points)
- "**/*.config.*", "**/*.toml", "**/*.yaml", "**/*.json" (config)
- "**/*test*", "**/*spec*", "__tests__/**" (test layout)
```

Note:
- Top-level folders and what they contain
- Entry points (main file, index, CLI, server start)
- Test locations and test framework used
- Config files and what they configure
- Build output directories (dist/, build/, target/, .next/, etc.)

---

## Step 3: Understand the Architecture

After mapping, read the key files to understand how the pieces connect:

- **Entry point** — what starts the app?
- **Core modules** — what are the main packages/namespaces?
- **Data flow** — where does data enter, transform, and exit?
- **External dependencies** — what does it call out to (APIs, DBs, queues)?
- **Configuration** — env vars, config files, secrets?

Read source files; do not infer from filenames alone.

---

## Step 4: Produce the Structure Diagram

Generate an ASCII tree showing the real layout (not a generic template):

```
project-root/
├── src/
│   ├── api/          # REST endpoints (Express routes)
│   ├── services/     # Business logic layer
│   ├── models/       # DB schemas (Mongoose)
│   └── utils/        # Shared helpers
├── tests/
│   ├── unit/
│   └── integration/
├── docs/             # Architecture docs
├── .github/
│   └── workflows/    # CI/CD pipelines
├── package.json      # Node 18, npm workspaces
└── docker-compose.yml
```

Add a **one-line annotation** per folder explaining its role. Base annotations only on what you actually read — do not guess.

---

## Step 5: Determine Local Run Requirements

Search for evidence of how to run the project locally:

**Look for:**
- `scripts` section in package.json / Makefile / Taskfile
- `docker-compose.yml` or `Dockerfile`
- `.env.example` or `.env.sample` (required env vars)
- CI workflow files (`.github/workflows/*.yml`) — they run the app in a clean environment, revealing exact steps
- Any `start`, `dev`, `run`, `serve` commands

**Check prerequisites:**
- Language runtime and version (`.nvmrc`, `.python-version`, `go.mod`, `rust-toolchain`)
- Package manager (npm/yarn/pnpm/pip/cargo/etc.)
- External services needed (database, Redis, message queue)
- Required env vars (scan `.env.example` or README)

---

## Step 6: Produce Local Run Instructions

Output as a numbered bullet list:

**Prerequisites:**
- [ ] Node.js 18+ (or Python 3.11+, Go 1.21+, etc.)
- [ ] Docker & Docker Compose (if needed)
- [ ] PostgreSQL 15 running locally OR use Docker

**Steps:**
1. Copy env file: `cp .env.example .env`
2. Fill in required values in `.env`: `DATABASE_URL`, `API_KEY` (see README §Configuration)
3. Install dependencies: `npm install`
4. Run migrations: `npm run db:migrate`
5. Start dev server: `npm run dev`
6. Open: `http://localhost:3000`

**If local run is not supported or unclear**, say so explicitly and explain what evidence led to that conclusion (e.g., "No local dev setup found — project appears to be deployed-only via CI").

---

## Output Format

Deliver results in this order:

```
## What is this project?
<1-2 sentence summary of purpose>

## Project Structure
<ASCII tree with annotations>

## Architecture
<How the main pieces connect — 3-10 bullet points>

## Dependencies & Tech Stack
<Language, framework, major libraries, external services>

## Running Locally
<Numbered steps or "Not supported locally" with explanation>

## Open Questions
<Anything that is genuinely unclear after reading all available docs>
```

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Assuming MVC layout from language | Always Glob first, confirm actual structure |
| Skipping package manifests | They reveal exact runtime versions and scripts |
| Guessing env vars | Read `.env.example`; never invent variable names |
| Saying "run `npm start`" without verifying | Check `scripts` in package.json first |
| Annotating folders without reading them | Read at least the index/main file of each key folder |
| Saying "I can't run locally" before checking Docker | Docker Compose is often the intended local path |

---

## Red Flags (Stop and Re-Read)

- You wrote an annotation but haven't read a file in that folder
- You listed a run command that doesn't appear in any config or doc
- You said "this uses X pattern" based only on the folder name
- Your diagram uses generic names (`controllers/`, `models/`) without confirming they exist
