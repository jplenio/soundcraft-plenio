# Start the packaged SoundCraft with the Plenio add-in once and check it through its control channel.
#
#   pwsh addins/plenio/tools/smoke_package.ps1 [-Zip <zip>] [-Shot <png>]
#
# Unzips the package (default: the newest in target/plenio-dist) into a temporary folder, starts its
# soundcraft.exe with a control channel and without audio, asks the add-in for its status (its commands
# are registered, its version is the package's), takes a screenshot of the window and quits. A window
# opens for a few seconds. The studio is not started.
param(
    [string]$Zip = "",
    [string]$Shot = ""
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot/../../..").Path
if (-not $Zip) {
    $Zip = (Get-ChildItem (Join-Path $Root "target/plenio-dist") -Filter "*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}
$Version = (Select-String -Path (Join-Path $Root "addins/plenio/crates/ui/Cargo.toml") -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$Dir = Join-Path ([System.IO.Path]::GetTempPath()) "plenio-smoke-$PID"
Expand-Archive -Path $Zip -DestinationPath $Dir -Force
$Exe = Get-ChildItem $Dir -Recurse -Filter "soundcraft.exe" | Select-Object -First 1
if (-not $Exe) { throw "no soundcraft.exe in $Zip" }
$Out = Join-Path $Dir "stdout.txt"
$App = Start-Process -FilePath $Exe.FullName -ArgumentList "--control", "0", "--no-audio" -RedirectStandardOutput $Out -PassThru
try {
    $port = $null
    $deadline = (Get-Date).AddSeconds(60)
    while (-not $port -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 300
        if (Test-Path $Out) {
            $line = Get-Content $Out -ErrorAction SilentlyContinue | Where-Object { $_ -match "^SOUNDCRAFT_CONTROL_PORT=(\d+)" } | Select-Object -First 1
            if ($line -match "=(\d+)") { $port = [int]$Matches[1] }
        }
        if ($App.HasExited) { throw "soundcraft.exe ended at once (exit $($App.ExitCode))" }
    }
    if (-not $port) { throw "no control port within 60 s" }
    $client = [System.Net.Sockets.TcpClient]::new("127.0.0.1", $port)
    $stream = $client.GetStream()
    $writer = [System.IO.StreamWriter]::new($stream)
    $writer.AutoFlush = $true
    $reader = [System.IO.StreamReader]::new($stream)
    function Ask([string]$json) {
        $writer.WriteLine($json)
        return ($reader.ReadLine() | ConvertFrom-Json)
    }
    $status = Ask '{"id":1,"method":"engine.execute","params":{"command":"plenio.status","params":{}}}'
    if (-not $status.ok) { throw "plenio.status failed: $($status | ConvertTo-Json -Compress)" }
    if ($status.result.addin -ne "plenio" -or $status.result.version -ne $Version) {
        throw "plenio.status: $($status.result | ConvertTo-Json -Compress), wanted version $Version"
    }
    Write-Host "ok plenio.status: version $($status.result.version), activated $($status.result.activated)"
    if ($Shot) {
        $path = [System.IO.Path]::GetFullPath($Shot).Replace("\", "/")
        $answer = Ask ('{"id":2,"method":"ui.screenshot","params":{"path":"' + $path + '"}}')
        if (-not $answer.ok) { throw "ui.screenshot failed: $($answer | ConvertTo-Json -Compress)" }
        Write-Host "ok screenshot: $Shot"
    }
    $null = Ask '{"id":3,"method":"app.quit","params":{}}'
    $client.Close()
    if (-not $App.WaitForExit(20000)) { throw "soundcraft.exe did not quit within 20 s" }
    Write-Host "ok the package starts, has the add-in $Version, and quits"
} finally {
    if (-not $App.HasExited) { Stop-Process -Id $App.Id -Force }
    Remove-Item -Recurse -Force $Dir -ErrorAction SilentlyContinue
}
