# Bring SoundCraft's upstream changes into the add-in's branch and check that the add-in still fits.
#
#   pwsh addins/plenio/tools/update_soundcraft.ps1            # rebase onto upstream/main
#   pwsh addins/plenio/tools/update_soundcraft.ps1 -Merge     # merge instead (keeps the history as it is)
#
# Conflicts can only come up in the few places SoundCraft has the add-in's entry points (see
# addins/plenio/docs/PLAN.md, "Die einzigen Änderungen an SoundCraft"): session.rs, cmd.rs, extension.rs and
# its call sites, apps/soundcraft, the workspace Cargo.toml and xtask. Cargo.lock is not merged by hand:
# take upstream's and let cargo add the add-in's crates again.
param(
    [switch]$Merge,
    [string]$Upstream = "upstream",
    [string]$Branch = "main"
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot/../../..")

if (git status --porcelain) {
    throw "The working tree has changes: commit or stash them first."
}
git fetch $Upstream
if ($Merge) {
    git merge "$Upstream/$Branch"
} else {
    git rebase "$Upstream/$Branch"
}
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Conflicts. For Cargo.lock: git checkout --ours Cargo.lock (rebase) or --theirs (merge), then cargo metadata -q > `$null."
    Write-Host "Resolve the rest, then: git rebase --continue (or git commit), and run this script's checks: pwsh addins/plenio/tools/test_all.ps1"
    exit 1
}
# The lock file gets the add-in's crates again.
cargo metadata --format-version 1 -q | Out-Null
& "$PSScriptRoot/test_all.ps1"
