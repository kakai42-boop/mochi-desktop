# The packaged Python app invokes this external worker after verifying the archive.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$requestPath = $env:MOCHI_UPDATE_REQUEST
Remove-Item Env:MOCHI_UPDATE_REQUEST
$workspace = Split-Path -Parent $requestPath
$request = Get-Content -LiteralPath $requestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$root = $request.root
$candidate = Join-Path $workspace 'Mochi'
$backup = Join-Path $workspace 'previous'
$exe = Join-Path $root 'Mochi.exe'
$ready = Join-Path $workspace 'ready'
$managed = @('assets', 'runtime', 'src', 'bootstrap.py', 'native_checks.py',
             'LICENSE', 'LISEZ-MOI.txt', 'build-info.json', 'Mochi.exe')
$oldMoved = [Collections.Generic.List[string]]::new()
$newMoved = [Collections.Generic.List[string]]::new()
$child = $null
$lock = $null

function Write-Outcome($Result) {
    $json = $Result | ConvertTo-Json -Compress
    $json | Set-Content -LiteralPath (Join-Path $workspace 'result.json') -Encoding UTF8
    $local = Join-Path $env:LOCALAPPDATA 'mochi-desktop'
    [IO.Directory]::CreateDirectory($local) | Out-Null
    $path = Join-Path $local 'update-result.json'
    $json | Set-Content -LiteralPath ($path + '.tmp') -Encoding UTF8
    Move-Item -LiteralPath ($path + '.tmp') -Destination $path -Force
}

function Wait-ForExit([int]$Id) {
    if ($Id -le 0) { return }
    $process = Get-Process -Id $Id -ErrorAction SilentlyContinue
    if ($process -and -not $process.WaitForExit(30000)) {
        throw 'Mochi did not close for the update.'
    }
}

function Move-Entry([string]$Source, [string]$Destination) {
    # Directory.Move is a single same-volume rename. Move-Item can fall back
    # to recursively moving the children, leaving a partially moved directory.
    $directory = [IO.Directory]::Exists($Source)
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        try {
            if ($directory) { [IO.Directory]::Move($Source, $Destination) }
            else { [IO.File]::Move($Source, $Destination) }
            return
        } catch {
            if ([DateTime]::UtcNow -ge $deadline -or -not (Test-Path -LiteralPath $Source)) {
                throw
            }
            Start-Sleep -Milliseconds 250
        }
    } while ($true)
}

try {
    if ((Split-Path -Parent $root) -ne (Split-Path -Parent $workspace) -or
        -not (Test-Path -LiteralPath $exe -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $candidate 'Mochi.exe') -PathType Leaf)) {
        throw 'The Windows update paths are invalid.'
    }
    $lock = [IO.File]::Open((Join-Path $root '.mochi-update.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    Wait-ForExit $request.pid
    Wait-ForExit $request.launcher_pid
    New-Item -ItemType Directory -Path $backup | Out-Null

    # Remove the old launcher first and publish the new launcher last.
    foreach ($name in (@('Mochi.exe') + @($managed | Where-Object { $_ -ne 'Mochi.exe' }))) {
        $entry = Join-Path $root $name
        if (Test-Path -LiteralPath $entry) {
            Move-Entry $entry (Join-Path $backup $name)
            $oldMoved.Add($name)
        }
    }
    foreach ($name in $managed) {
        Move-Entry (Join-Path $candidate $name) (Join-Path $root $name)
        $newMoved.Add($name)
    }
    $child = Start-Process -FilePath $exe -ArgumentList ('--update-ready-file "' + $ready + '"') -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while (-not (Test-Path -LiteralPath $ready -PathType Leaf)) {
        if ($child.HasExited -or [DateTime]::UtcNow -ge $deadline) {
            throw 'The updated Mochi did not reach startup readiness.'
        }
        Start-Sleep -Milliseconds 200
    }
} catch {
    $failure = $_.Exception.Message
    $restored = $false
    $previous = $null
    try {
        if ($child -and -not $child.HasExited) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $child.Id /T /F | Out-Null
            if (-not $child.WaitForExit(10000)) { throw 'Updated process is still running.' }
        }
        foreach ($name in $newMoved) {
            Move-Entry (Join-Path $root $name) (Join-Path $candidate $name)
        }
        foreach ($name in $managed) {
            if ($oldMoved.Contains($name)) {
                Move-Entry (Join-Path $backup $name) (Join-Path $root $name)
            }
        }
        $restored = $oldMoved.Count -gt 0
        if ($restored) {
            $previousReady = Join-Path $workspace 'previous-ready'
            $previous = Start-Process -FilePath $exe -ArgumentList ('--update-ready-file "' + $previousReady + '"') -PassThru
        }
    } catch {
        $failure += ' Recovery files remain in ' + $workspace + ': ' + $_.Exception.Message
    } finally {
        if ($lock) { $lock.Dispose() }
    }
    $previousId = if ($previous) { $previous.Id } else { 0 }
    Write-Outcome @{status='failed'; restored=$restored; error=$failure; launcher_pid=$previousId}
    if ($restored) {
        try { Remove-Item -LiteralPath $candidate -Recurse -Force } catch { }
    }
    exit 1
}

if ($lock) { $lock.Dispose() }
Write-Outcome @{status='success'; restored=$false; launcher_pid=$child.Id}
# Cleanup failure cannot undo a healthy update.
try { Remove-Item -LiteralPath $backup -Recurse -Force } catch { }
