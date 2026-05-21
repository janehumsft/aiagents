#!/usr/bin/env pwsh
# install.ps1 - Install the dev-design skill into your Copilot CLI profile.
#
# Usage (from the skill source folder):
#   ./install.ps1                  # install into ~/.copilot/skills/dev-design
#   ./install.ps1 -Force           # overwrite existing install
#   ./install.ps1 -Dest <path>     # custom destination
#   ./install.ps1 -Smoke           # run the smoke test after installing
#
# What it does:
#   1. Verifies python is on PATH
#   2. Copies the entire skill folder to the destination
#   3. Removes any cached __pycache__ folders
#   4. Optionally runs scripts/smoke_test.py to verify the install
#
# Teammates can install in one line:
#   git clone <repo> && pwsh -File ./dev-design-skill/install.ps1
[CmdletBinding()]
param(
    [string]$Dest = "",
    [switch]$Force,
    [switch]$Smoke,
    [switch]$Quick
)

$ErrorActionPreference = "Stop"

$src = $PSScriptRoot
if (-not $src) { $src = (Get-Location).Path }
$src = (Resolve-Path $src).Path

if (-not $Dest) {
    $home_dir = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
    $Dest = Join-Path $home_dir ".copilot/skills/dev-design"
}

Write-Host "dev-design skill installer"
Write-Host "  source: $src"
Write-Host "  dest:   $Dest"

# 1. Python check
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    $py = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $py) {
    Write-Warning "python is not on PATH. The skill's helper scripts require Python 3.8+."
    Write-Warning "Continuing anyway — install Python before invoking the skill."
} else {
    $ver = & $py.Source --version 2>&1
    Write-Host "  python: $ver"
}

# 2. Validate source layout
foreach ($required in @("SKILL.md", "template.md", "scripts/init_workspace.py", "scripts/assemble.py")) {
    $p = Join-Path $src $required
    if (-not (Test-Path $p)) {
        throw "Source layout invalid: missing $required (looked under $src)"
    }
}

# 3. Copy
if (Test-Path $Dest) {
    if (-not $Force) {
        throw "Destination already exists: $Dest (re-run with -Force to overwrite)"
    }
    Write-Host "  removing existing install..."
    Remove-Item $Dest -Recurse -Force
}
$parent = Split-Path -Parent $Dest
if (-not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
Copy-Item $src $Dest -Recurse

# 4. Remove __pycache__
Get-ChildItem $Dest -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "  copied $(Get-ChildItem $Dest -Recurse -File | Measure-Object | Select-Object -ExpandProperty Count) files"

# 5. Optional smoke test
if ($Smoke -or $Quick) {
    if (-not $py) {
        Write-Warning "Skipping smoke test — python not on PATH."
    } else {
        Write-Host ""
        Write-Host "Running smoke test ($(if ($Quick) { 'quick' } else { 'full' }))..."
        $args = @((Join-Path $Dest "scripts/smoke_test.py"))
        if ($Quick) { $args += "--quick" }
        & $py.Source @args
        if ($LASTEXITCODE -ne 0) {
            throw "Smoke test failed with exit code $LASTEXITCODE"
        }
    }
}

Write-Host ""
Write-Host "✓ Installed. Open Copilot CLI and run:"
Write-Host "    /skills"
Write-Host "  then ask: 'Use the dev-design skill to draft a doc for ADO #<id>.'"
