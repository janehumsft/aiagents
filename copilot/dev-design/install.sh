#!/usr/bin/env bash
# install.sh - Install the dev-design skill into your Copilot CLI profile.
#
# Usage (from the skill source folder):
#   ./install.sh                  # install into ~/.copilot/skills/dev-design
#   ./install.sh --force          # overwrite existing install
#   ./install.sh --dest <path>    # custom destination
#   ./install.sh --smoke          # run the full smoke test after installing
#   ./install.sh --quick          # run only the quick checks after installing
#
# What it does:
#   1. Verifies python3 is on PATH
#   2. Copies the entire skill folder to the destination
#   3. Removes any cached __pycache__ folders
#   4. Optionally runs scripts/smoke_test.py to verify the install
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST=""
FORCE=0
SMOKE=0
QUICK=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dest) DEST="$2"; shift 2 ;;
        --force) FORCE=1; shift ;;
        --smoke) SMOKE=1; shift ;;
        --quick) QUICK=1; shift ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$DEST" ]]; then
    DEST="${HOME}/.copilot/skills/dev-design"
fi

echo "dev-design skill installer"
echo "  source: $SRC"
echo "  dest:   $DEST"

# 1. Python check
PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done
if [[ -z "$PY" ]]; then
    echo "Warning: python is not on PATH. The skill's helper scripts require Python 3.8+." >&2
    echo "Continuing anyway — install Python before invoking the skill." >&2
else
    echo "  python: $("$PY" --version 2>&1)"
fi

# 2. Validate source layout
for required in SKILL.md template.md scripts/init_workspace.py scripts/assemble.py; do
    if [[ ! -e "$SRC/$required" ]]; then
        echo "Source layout invalid: missing $required (looked under $SRC)" >&2
        exit 2
    fi
done

# 3. Copy
if [[ -e "$DEST" ]]; then
    if [[ "$FORCE" -ne 1 ]]; then
        echo "Destination already exists: $DEST (re-run with --force to overwrite)" >&2
        exit 2
    fi
    echo "  removing existing install..."
    rm -rf "$DEST"
fi
mkdir -p "$(dirname "$DEST")"
cp -R "$SRC" "$DEST"

# 4. Remove __pycache__
find "$DEST" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

file_count="$(find "$DEST" -type f | wc -l | tr -d ' ')"
echo "  copied $file_count files"

# 5. Optional smoke test
if [[ "$SMOKE" -eq 1 || "$QUICK" -eq 1 ]]; then
    if [[ -z "$PY" ]]; then
        echo "Warning: skipping smoke test — python not on PATH." >&2
    else
        echo ""
        if [[ "$QUICK" -eq 1 ]]; then
            echo "Running smoke test (quick)..."
            "$PY" "$DEST/scripts/smoke_test.py" --quick
        else
            echo "Running smoke test (full)..."
            "$PY" "$DEST/scripts/smoke_test.py"
        fi
    fi
fi

echo ""
echo "✓ Installed. Open Copilot CLI and run:"
echo "    /skills"
echo "  then ask: 'Use the dev-design skill to draft a doc for ADO #<id>.'"
