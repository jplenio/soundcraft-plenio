# Merge SoundCraft's upstream into this fork and check that the add-in still fits.
#
#   pwsh addins/plenio/tools/update_soundcraft.ps1 -Preview    # what would come, and does it conflict? Changes nothing.
#   pwsh addins/plenio/tools/update_soundcraft.ps1             # merge, then every check of the add-in
#   pwsh addins/plenio/tools/update_soundcraft.ps1 -Full       # the same with SoundCraft's whole test suite
#   pwsh addins/plenio/tools/update_soundcraft.ps1 -Push       # on success also push the branch and the mirror of upstream
#   pwsh addins/plenio/tools/update_soundcraft.ps1 -Continue   # after conflicts were resolved by hand and committed
#
# This fork is published, so it merges and never rebases: its history stays as others have seen it.
# Conflicts can only come up in the few places where the fork differs from SoundCraft (FORK.md lists
# them). What can be decided without looking is decided here: the README stays the fork's, Cargo.lock
# is upstream's with the add-in's crates added again, and the ArtCraft marks stay out. Resolutions made
# by hand are remembered (git rerere).
param(
    [switch]$Preview,
    [switch]$Continue,
    [switch]$Push,
    [switch]$Full,
    [switch]$NoChecks,
    [string]$Branch = "plenio-addin",
    [string]$Upstream = "upstream",
    [string]$UpstreamBranch = "main",
    [string]$Fork = "origin"
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot/../../..")
$incoming = "$Upstream/$UpstreamBranch"

function Set-Up-Merging {
    # Local settings: they belong to this clone and cannot conflict with anything upstream does.
    git config merge.ours.driver true
    git config rerere.enabled true
    git config rerere.autoupdate true
    $attributes = (git rev-parse --git-path info/attributes).Trim()
    $line = "/README.md merge=ours"
    $known = if (Test-Path $attributes) { Get-Content $attributes } else { @() }
    if ($known -notcontains $line) {
        New-Item -ItemType Directory -Force (Split-Path $attributes) | Out-Null
        Add-Content $attributes $line
    }
}

# The ArtCraft marks that upstream brought (again) into a merge in progress or into the tree.
function Get-Marks {
    git ls-files docs/brand | Where-Object { $_ -ne "docs/brand/LICENSE-brand.txt" }
}

function Resolve-What-Is-Clear {
    $open = @(git diff --name-only --diff-filter=U)
    if ($open -contains "Cargo.lock") {
        git checkout --theirs -- Cargo.lock
        cargo metadata --format-version 1 -q | Out-Null
        git add Cargo.lock
    }
    foreach ($file in $open | Where-Object { $_ -like "docs/brand/*" -and $_ -ne "docs/brand/LICENSE-brand.txt" }) {
        git rm -q -f --ignore-unmatch -- $file
    }
    return @(git diff --name-only --diff-filter=U)
}

$current = (git branch --show-current).Trim()
if ($current -ne $Branch) {
    throw "On branch '$current': this script works on '$Branch'. git switch $Branch"
}
if ((git status --porcelain) -and -not $Preview) {
    throw "The working tree has changes: commit or stash them first."
}

if (-not $Continue) {
    git fetch $Upstream
    if ($LASTEXITCODE -ne 0) { throw "git fetch $Upstream failed." }
    $behind = [int](git rev-list --count "HEAD..$incoming")
    if ($behind -eq 0) {
        Write-Host "Up to date with $incoming."
        if ($Push -and -not $Preview) {
            git push $Fork $Branch
            git push $Fork "${incoming}:refs/heads/$UpstreamBranch"
        }
        exit 0
    }
    Write-Host "$behind new commit(s) in ${incoming}:"
    git log --oneline --no-merges -n 30 "HEAD..$incoming"
    if ($Preview) {
        Write-Host ""
        Set-Up-Merging
        $tree = git merge-tree --write-tree --name-only HEAD $incoming
        if ($LASTEXITCODE -eq 0) {
            Write-Host "The merge would go through without a conflict."
        } else {
            Write-Host "The merge would stop at:"
            $tree | Select-Object -Skip 1 | Where-Object { $_ -and $_ -notmatch "^(Auto-merging|CONFLICT)" } | ForEach-Object { Write-Host "  $_" }
            Write-Host "($($tree | Where-Object { $_ -match '^CONFLICT' } | Measure-Object | Select-Object -ExpandProperty Count) conflict(s); Cargo.lock and docs/brand are resolved by this script.)"
        }
        exit 0
    }
    Set-Up-Merging
    git merge --no-edit $incoming
    if ($LASTEXITCODE -ne 0) {
        $open = Resolve-What-Is-Clear
        if ($open.Count -gt 0) {
            Write-Host ""
            Write-Host "Conflicts that need a person (see addins/plenio/docs/FORK.md):"
            $open | ForEach-Object { Write-Host "  $_" }
            Write-Host "Resolve them, git add them, git commit, then run this script with -Continue."
            Write-Host "To go back to where you were: git merge --abort"
            exit 1
        }
        git commit --no-edit
        if ($LASTEXITCODE -ne 0) { throw "The merge could not be committed." }
    }
}

# Whatever upstream added: no ArtCraft marks in the fork, and the lock file knows the add-in's crates.
$marks = @(Get-Marks)
if ($marks.Count -gt 0) {
    git rm -q -f -- $marks
    git commit -q -m "chore(fork): keep the ArtCraft marks out of the fork"
    Write-Host "Removed $($marks.Count) ArtCraft mark file(s) that upstream brought."
    Write-Host "If upstream's ATTRIBUTION.md lists them, take those rows out too."
}
cargo metadata --format-version 1 -q | Out-Null
if (git status --porcelain Cargo.lock) {
    git add Cargo.lock
    git commit -q -m "chore(fork): Cargo.lock with the add-in's crates"
}

if (-not $NoChecks) {
    $check = @{}
    if ($Full) { $check["Full"] = $true }
    & "$PSScriptRoot/test_all.ps1" @check
    if ($LASTEXITCODE -ne 0) {
        Write-Host "The merge is committed, but checks failed: fix them, or go back with git reset --hard ORIG_HEAD."
        exit 1
    }
}
if ($Push) {
    git push $Fork $Branch
    if ($LASTEXITCODE -ne 0) { throw "git push $Fork $Branch failed." }
    # The fork's main is a plain mirror of SoundCraft: what the add-in changes is the difference between the two.
    git push $Fork "${incoming}:refs/heads/$UpstreamBranch"
    if ($LASTEXITCODE -ne 0) { throw "The mirror of $incoming could not be pushed." }
}
Write-Host "Done: $Branch has SoundCraft $(git rev-parse --short $incoming)."
