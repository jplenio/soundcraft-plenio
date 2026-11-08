# Build SoundCraft with the Plenio add-in for Windows (x64) and pack it as a portable zip for a release.
#
#   pwsh addins/plenio/tools/package_windows.ps1              # build, stage, check, zip, checksums
#   pwsh addins/plenio/tools/package_windows.ps1 -SkipBuild   # pack what target/ already holds
#
# Writes target/plenio-dist/soundcraft-plenio-<add-in version>-windows-x64-portable.zip and SHA256SUMS.txt.
# The zip holds soundcraft.exe and soundcraft-cli.exe (the C runtime linked in, so no redistributable is
# needed), the add-in's Python files beside them in plenio-addin/ (where the add-in looks for them, see
# instance::source_dir), the licences, the notices and a README. It is not signed: Windows SmartScreen asks
# once before the first start. SoundCraft's own installers (packaging/windows) are not used: they still
# install as ArtCraft, which a fork must not (FORK.md).
param(
    [switch]$SkipBuild,
    [string]$Dist = "target/plenio-dist"
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$Root = (Resolve-Path "$PSScriptRoot/../../..").Path
Set-Location $Root

$Version = (Select-String -Path addins/plenio/crates/ui/Cargo.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$Target = "x86_64-pc-windows-msvc"
if (-not $SkipBuild) {
    Write-Host "== cargo build --release ($Target, the C runtime linked in)"
    $env:CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUSTFLAGS = "-C target-feature=+crt-static"
    cargo build --release --locked -p soundcraft -p soundcraft-cli --target $Target
}
$Bin = Join-Path $Root "target/$Target/release"
$Name = "soundcraft-plenio-$Version-windows-x64-portable"
$Stage = Join-Path $Root "target/plenio-package/$Name"

Write-Host "== stage $Name"
Remove-Item -Recurse -Force $Stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Stage | Out-Null
Copy-Item (Join-Path $Bin "soundcraft.exe"), (Join-Path $Bin "soundcraft-cli.exe") $Stage
$Addin = Join-Path $Stage "plenio-addin"
New-Item -ItemType Directory -Force (Join-Path $Addin "backend") | Out-Null
Copy-Item -Recurse addins/plenio/backend/soundcraft_plenio (Join-Path $Addin "backend/soundcraft_plenio")
Copy-Item -Recurse addins/plenio/vendor (Join-Path $Addin "vendor")
Get-ChildItem -Recurse -Directory -Filter __pycache__ $Addin | Remove-Item -Recurse -Force
Copy-Item LICENSE-MIT, LICENSE-APACHE, NOTICE, ATTRIBUTION.md $Stage
Copy-Item addins/plenio/NOTICE.md (Join-Path $Stage "NOTICE-PLENIO.md")
Copy-Item addins/plenio/CHANGELOG.md (Join-Path $Stage "CHANGELOG-PLENIO.md")
$Readme = @"
SoundCraft with the Plenio add-in $Version (alpha), for Windows 10 and 11 (x64)

Start soundcraft.exe. Then: Plenio > Activate Plenio Add-in..., and Plenio > Getting Started.

You need ComfyUI 0.37 or later on this computer (the add-in finds it and runs an instance of its own; your
setup stays as it is), an NVIDIA graphics card with 16 GB, and about 35 GB of disk for the models, which
the add-in downloads (Plenio > Studio and Models).

Keep the folder plenio-addin next to soundcraft.exe: it holds the add-in's Python files and Plenio.
The program is not signed, so Windows SmartScreen asks once ("More info" > "Run anyway").

Songs made with YuE2 are for non-commercial use (CC BY-NC 4.0). Licences: LICENSE-MIT, LICENSE-APACHE,
NOTICE, NOTICE-PLENIO.md. This is an independent fork of SoundCraft, not made or endorsed by its team.

Tutorial and help: https://github.com/jplenio/soundcraft-plenio
"@
Set-Content -Path (Join-Path $Stage "README.txt") -Value $Readme -Encoding utf8

Write-Host "== check"
python addins/plenio/tools/sync_plenio.py --check
foreach ($f in "plenio-addin/backend/soundcraft_plenio/__init__.py", "plenio-addin/vendor/plenio/plenio", "plenio-addin/vendor/VENDOR.sha256", "plenio-addin/vendor/VENDOR.toml") {
    if (-not (Test-Path (Join-Path $Stage $f))) { throw "the package lacks $f" }
}
$want = (Get-ChildItem -Recurse -File addins/plenio/vendor/plenio).Count
$got = (Get-ChildItem -Recurse -File (Join-Path $Addin "vendor/plenio")).Count
if ($want -ne $got) { throw "the package's copy of Plenio has $got files, the repository's $want" }
# Both programs are Windows x64; the app has no console window, the CLI has one.
foreach ($check in @(@("soundcraft.exe", 2), @("soundcraft-cli.exe", 3))) {
    $bytes = [System.IO.File]::ReadAllBytes((Join-Path $Stage $check[0]))
    $pe = [BitConverter]::ToInt32($bytes, 0x3C)
    $machine = [BitConverter]::ToUInt16($bytes, $pe + 4)
    $subsystem = [BitConverter]::ToUInt16($bytes, $pe + 0x5C)
    if ($machine -ne 0x8664 -or $subsystem -ne $check[1]) { throw "$($check[0]): machine 0x$('{0:X}' -f $machine), subsystem $subsystem" }
}
& (Join-Path $Stage "soundcraft-cli.exe") --version

Write-Host "== zip"
New-Item -ItemType Directory -Force $Dist | Out-Null
$Zip = Join-Path $Dist "$Name.zip"
Remove-Item -Force $Zip -ErrorAction SilentlyContinue
Compress-Archive -Path $Stage -DestinationPath $Zip
# Every file of the release in $Dist (other files, such as videos, may be put there to be listed too), but
# not the zip of another version that an earlier run left behind: it is not part of this release.
$release = Get-ChildItem $Dist -File | Where-Object {
    $_.Name -ne "SHA256SUMS.txt" -and ($_.Name -eq "$Name.zip" -or $_.Name -notlike "soundcraft-plenio-*-windows-x64-portable.zip")
}
$sums = $release | ForEach-Object {
    "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $_.Name
}
# Lines end in LF: `sha256sum -c` (Linux, macOS, Git Bash) reads a CR as part of the file's name.
[System.IO.File]::WriteAllText((Join-Path (Resolve-Path $Dist) "SHA256SUMS.txt"), (($sums -join "`n") + "`n"), [System.Text.Encoding]::ASCII)
Write-Host "Done: $Zip ($([math]::Round((Get-Item $Zip).Length / 1MB, 1)) MB)"
