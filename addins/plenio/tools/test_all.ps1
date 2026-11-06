# Every check of the Plenio add-in, in one run:
#
#   pwsh addins/plenio/tools/test_all.ps1 [-Full] [-Live] [-Plenio <Plenio checkout>]
#
#   - SoundCraft's gates that the add-in touches: fmt, clippy, layers, assets
#   - the add-in's Rust tests and the seams' tests in SoundCraft (model, engine, ui-egui)
#   - the wrapper's Python tests, with ComfyUI's Python
#   - the copy of Plenio: unchanged (VENDOR.sha256) and, with -Plenio, Plenio's own unit tests run against it
#   - the fork: no ArtCraft marks, updates from its own releases
#   - with -Full: SoundCraft's whole test suite (after a merge from upstream)
#   - with -Live: the studio and the Plenio Player started for real (needs ComfyUI; a few seconds of GPU)
param(
    [switch]$Full,
    [switch]$Live,
    [string]$Plenio = "",
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
# A program that fails stops its step, also in the middle of one with several commands.
$PSNativeCommandUseErrorActionPreference = $true
Set-Location (Resolve-Path "$PSScriptRoot/../../..")
$failed = @()
function Step([string]$name, [scriptblock]$run) {
    Write-Host "== $name"
    try {
        & $run
    } catch {
        Write-Host $_
        $script:failed += $name
    }
}
$crates = @("-p", "soundcraft-plenio-project", "-p", "soundcraft-plenio-backend", "-p", "soundcraft-plenio-commands", "-p", "soundcraft-plenio-ui")

Step "fmt" { cargo fmt --all -- --check }
Step "clippy (add-in and seams)" { cargo clippy @crates -p soundcraft-model -p soundcraft-engine -p soundcraft-ui-egui -p soundcraft --all-targets -- -D warnings }
Step "layers" { cargo xtask layers }
Step "assets" { cargo xtask assets }
Step "add-in tests" { cargo test @crates }
Step "seam tests" { cargo test -p soundcraft-model --lib extension; cargo test -p soundcraft-engine --test extension_commands; cargo test -p soundcraft-ui-egui --lib extension }
Step "copy of Plenio unchanged" { python addins/plenio/tools/sync_plenio.py --check }
Step "the app builds, with and without the add-in" { cargo build -p soundcraft; cargo build -p soundcraft --no-default-features }
Step "the fork carries no ArtCraft marks and updates from its own releases" {
    $marks = @(git ls-files docs/brand | Where-Object { $_ -ne "docs/brand/LICENSE-brand.txt" })
    if ($marks.Count -gt 0) { throw "ArtCraft marks in the fork: $($marks -join ', ')" }
    if (Select-String -Path README.md -SimpleMatch "docs/brand/artcraft-" -Quiet) { throw "README.md shows an ArtCraft mark" }
    if (-not (Select-String -Path crates/ui-egui/src/lib.rs -SimpleMatch 'repo: "jplenio/soundcraft-plenio"' -Quiet)) {
        throw "crates/ui-egui/src/lib.rs: the app would update from SoundCraft's releases, which have no add-in"
    }
}
if ($Full) {
    Step "SoundCraft's whole test suite" { cargo test --workspace --exclude soundcraft-cli --no-fail-fast }
    # On Windows a connection to a closed port can time out instead of being refused: these three tests of
    # soundcraft-cli fail there, with or without the add-in. Everything else of it runs.
    $known = if ($IsWindows) {
        @(
            "--skip", "behaviour::app_port_comes_from_the_flag_then_the_environment",
            "--skip", "behaviour::app_takes_an_empty_port_variable_as_unset",
            "--skip", "run::app_reports_a_refused_connection_and_checks_arguments_first"
        )
    } else { @() }
    Step "soundcraft-cli's tests" { cargo test -p soundcraft-cli --no-fail-fast -- @known }
}

if (-not $Python) {
    $start = Join-Path $HOME ".plenio/player/comfyui-start.json"
    if (Test-Path $start) {
        $entry = (Get-Content $start -Raw | ConvertFrom-Json).PSObject.Properties | Select-Object -First 1
        if ($entry) { $Python = $entry.Value.python }
    }
}
if ($Python -and (Test-Path $Python)) {
    Step "wrapper tests" {
        & $Python -I addins/plenio/backend/tests/test_routes.py
        & $Python -I addins/plenio/backend/tests/test_beats.py
    }
    if ($Plenio) {
        $env:PYTHONDONTWRITEBYTECODE = "1"
        $env:PYTHONPATH = Join-Path $Plenio ".devdeps"
        # From a folder of its own: pytest and hypothesis write nothing into the copy.
        $copy = (Resolve-Path addins/plenio/vendor/plenio).Path
        $scratch = New-Item -ItemType Directory -Force (Join-Path ([System.IO.Path]::GetTempPath()) "plenio-tests")
        Push-Location $scratch
        Step "Plenio's unit tests on the copy" { & $Python -m pytest -c "$copy/pyproject.toml" --rootdir $copy "$copy/tests/unit" -q -p no:cacheprovider }
        Pop-Location
        Remove-Item Env:PYTHONPATH
    }
} else {
    Write-Host "(no ComfyUI Python found: the Python tests are skipped; pass -Python)"
}
if ($Live) {
    $env:SCP_TEST_START = "1"
    Step "live: studio and player" { cargo test -p soundcraft-plenio-backend -- --ignored the_studio_starts the_player_starts }
    Remove-Item Env:SCP_TEST_START
}
if ($failed.Count -gt 0) {
    Write-Host "FAILED: $($failed -join ', ')"
    exit 1
}
Write-Host "all Plenio add-in checks passed"
