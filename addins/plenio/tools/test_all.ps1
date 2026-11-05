# Every check of the Plenio add-in, in one run:
#
#   pwsh addins/plenio/tools/test_all.ps1 [-Live] [-Plenio <Plenio checkout>]
#
#   - SoundCraft's gates that the add-in touches: fmt, clippy, layers, assets
#   - the add-in's Rust tests and the seams' tests in SoundCraft (model, engine, ui-egui)
#   - the wrapper's Python tests, with ComfyUI's Python
#   - the copy of Plenio: unchanged (VENDOR.sha256) and, with -Plenio, Plenio's own unit tests run against it
#   - with -Live: the studio and the Plenio Player started for real (needs ComfyUI; a few seconds of GPU)
param(
    [switch]$Live,
    [string]$Plenio = "",
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot/../../..")
$failed = @()
function Step([string]$name, [scriptblock]$run) {
    Write-Host "== $name"
    & $run
    if ($LASTEXITCODE -ne 0) { $script:failed += $name }
}
$crates = @("-p", "soundcraft-plenio-project", "-p", "soundcraft-plenio-backend", "-p", "soundcraft-plenio-commands", "-p", "soundcraft-plenio-ui")

Step "fmt" { cargo fmt --all -- --check }
Step "clippy (add-in and seams)" { cargo clippy @crates -p soundcraft-model -p soundcraft-engine -p soundcraft-ui-egui -p soundcraft --all-targets -- -D warnings }
Step "layers" { cargo xtask layers }
Step "assets" { cargo xtask assets }
Step "add-in tests" { cargo test @crates }
Step "seam tests" { cargo test -p soundcraft-model --lib extension; cargo test -p soundcraft-engine --test extension_commands; cargo test -p soundcraft-ui-egui --lib extension }
Step "copy of Plenio unchanged" { python addins/plenio/tools/sync_plenio.py --check }

if (-not $Python) {
    $start = Join-Path $HOME ".plenio/player/comfyui-start.json"
    if (Test-Path $start) {
        $entry = (Get-Content $start -Raw | ConvertFrom-Json).PSObject.Properties | Select-Object -First 1
        if ($entry) { $Python = $entry.Value.python }
    }
}
if ($Python -and (Test-Path $Python)) {
    Step "wrapper tests" { & $Python -I addins/plenio/backend/tests/test_routes.py }
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
