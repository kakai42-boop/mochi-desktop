# Runs only in an ephemeral GitHub Actions Windows account: installs/uninstalls Mochi.
param([Parameter(Mandatory=$true)][string]$Packages)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'Run this installation test only on a disposable GitHub Actions Windows runner.'
}
$registration = 'HKCU:\Software\MochiDesktopWindows'
if (Test-Path $registration) { throw 'Refusing to modify an existing Mochi installation.' }
$Packages = (Resolve-Path $Packages).Path
$work = Join-Path $env:RUNNER_TEMP ('Mochi QA été ' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $work | Out-Null
$oldLocal = $env:LOCALAPPDATA
$oldRoaming = $env:APPDATA
$env:LOCALAPPDATA = Join-Path $work 'Local'
$env:APPDATA = Join-Path $work 'Roaming'
New-Item -ItemType Directory -Path $env:LOCALAPPDATA,$env:APPDATA | Out-Null
$installed = Join-Path $work 'Application installée'
$reportDir = Join-Path $env:GITHUB_WORKSPACE 'windows-qa-results'
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

function Invoke-Bounded([string]$Exe, [string]$Arguments, [int]$Seconds = 90) {
    $process = Start-Process -FilePath $Exe -ArgumentList $Arguments -PassThru
    if (-not $process.WaitForExit($Seconds * 1000)) {
        # Stop descendants too; killing just the GUI launcher leaves pythonw running.
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        throw "Timed out: $Exe"
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "$Exe exited with $($process.ExitCode)" }
}

function Test-Mochi([string]$Root, [string]$Label) {
    $env:MOCHI_SMOKE_RUN_ID = [guid]::NewGuid().ToString()
    $report = Join-Path $env:LOCALAPPDATA 'mochi-desktop\smoke-test.json'
    Remove-Item $report -ErrorAction SilentlyContinue
    Invoke-Bounded (Join-Path $Root 'Mochi.exe') '--smoke-test'
    if (-not (Test-Path $report)) { throw 'No fresh smoke report was generated.' }
    & (Join-Path $Root 'runtime\bin\python.exe') -I "$PSScriptRoot/verify_smoke.py" $report $env:MOCHI_SMOKE_RUN_ID
    if ($LASTEXITCODE -ne 0) { throw 'Smoke report validation failed.' }
    Copy-Item $report (Join-Path $reportDir "$Label.json")
}

try {
    Expand-Archive (Join-Path $Packages 'Mochi-Windows11-Portable.zip') (Join-Path $work 'Portable')
    Test-Mochi (Join-Path $work 'Portable\Mochi') 'portable'
    $setup = Join-Path $Packages 'Mochi-Windows11-Setup.exe'
    # NSIS /D must be the last parameter and is deliberately not quoted.
    Invoke-Bounded $setup ("/S /D=" + $installed) 300
    if (-not (Test-Path (Join-Path $installed 'Uninstall.exe'))) { throw 'Missing uninstaller.' }
    if ((Get-ItemProperty $registration).InstallDir -ne $installed) { throw 'Wrong registered install location.' }
    Test-Mochi $installed 'installed'

    $preferences = Join-Path $env:APPDATA 'mochi\qa-preserve.txt'
    $pocket = Join-Path $env:LOCALAPPDATA 'mochi-desktop\pocket\qa-preserve.txt'
    foreach ($file in @($preferences, $pocket)) {
        New-Item -ItemType Directory -Force (Split-Path $file) | Out-Null
        Set-Content -LiteralPath $file -Value 'preserve-this-data' -NoNewline
    }
    Invoke-Bounded $setup ("/S /D=" + $installed) 300
    Test-Mochi $installed 'reinstalled'
    # _?= avoids NSIS spawning an untracked temporary uninstaller process.
    Invoke-Bounded (Join-Path $installed 'Uninstall.exe') ("/S _?=" + $installed) 120
    foreach ($file in @($preferences, $pocket)) {
        if ((Get-Content -LiteralPath $file -Raw) -ne 'preserve-this-data') {
            throw 'Uninstall or reinstall changed user data.'
        }
    }
    if (Test-Path (Join-Path $installed 'Mochi.exe')) { throw 'Application was not removed.' }
    if (Test-Path $registration) { throw 'Installation registry key was not removed.' }
    @{installation=$true; reinstallation=$true; uninstallation=$true; data_preserved=$true;
      os=[Environment]::OSVersion.VersionString} | ConvertTo-Json |
        Set-Content (Join-Path $reportDir 'installation.json')
} finally {
    $logs = Join-Path $env:LOCALAPPDATA 'mochi-desktop'
    if (Test-Path $logs) {
        Get-ChildItem $logs -Filter '*.log' | Copy-Item -Destination $reportDir
    }
    $env:LOCALAPPDATA = $oldLocal
    $env:APPDATA = $oldRoaming
    Remove-Item Env:MOCHI_SMOKE_RUN_ID -ErrorAction SilentlyContinue
}
