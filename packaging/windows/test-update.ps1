# Loaded by test-package.ps1 on the disposable Windows runner.
function Test-UpdateTransaction([string]$Root, [string]$Portable, [bool]$Broken) {
    $stage = Join-Path (Split-Path -Parent $Root) ('.mochi-update-' + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $stage | Out-Null
    Copy-Item -LiteralPath $Portable -Destination $stage -Recurse
    $candidate = Join-Path $stage 'Mochi'
    $marker = Join-Path $Root 'LISEZ-MOI.txt'
    $before = (Get-FileHash -LiteralPath $marker).Hash
    Set-Content -LiteralPath (Join-Path $candidate 'LISEZ-MOI.txt') -Value 'update fixture'
    if ($Broken) {
        Set-Content -LiteralPath (Join-Path $candidate 'bootstrap.py') -Value 'raise SystemExit(17)'
    }
    $old = Start-Process -FilePath (Join-Path $Root 'Mochi.exe') -ArgumentList '--smoke-test' -PassThru
    $request = Join-Path $stage 'request.json'
    @{root=$Root; pid=0; launcher_pid=$old.Id} | ConvertTo-Json | Set-Content -LiteralPath $request
    $scriptPath = Join-Path $PSScriptRoot '../../src/mochi/windows/update_transaction.ps1'
    $code = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes((Get-Content -LiteralPath $scriptPath -Raw)))
    $env:MOCHI_UPDATE_REQUEST = $request
    try {
        $argsList = @('-NoProfile', '-NonInteractive', '-EncodedCommand', $code)
        $powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
        $worker = Start-Process -FilePath $powershell -ArgumentList $argsList -PassThru
        if (-not $worker.WaitForExit(110000)) {
            & taskkill.exe /PID $worker.Id /T /F | Out-Null
            throw 'Windows update worker timed out.'
        }
    } finally {
        Remove-Item Env:MOCHI_UPDATE_REQUEST -ErrorAction SilentlyContinue
    }
    $worker.Refresh()
    $outcome = Get-Content -LiteralPath (Join-Path $stage 'result.json') -Raw | ConvertFrom-Json
    Copy-Item (Join-Path $stage 'result.json') (Join-Path $reportDir "update-$Broken.json")
    $running = if ($outcome.launcher_pid -gt 0) {
        Get-Process -Id $outcome.launcher_pid -ErrorAction SilentlyContinue
    } else { $null }
    try {
        if ($Broken) {
            if ($worker.ExitCode -ne 1 -or $outcome.status -ne 'failed' -or -not $outcome.restored) {
                throw 'Broken update did not restore the old package.'
            }
            $deadline = [DateTime]::UtcNow.AddSeconds(30)
            while (-not (Test-Path (Join-Path $stage 'previous-ready'))) {
                if (-not $running -or $running.HasExited -or [DateTime]::UtcNow -ge $deadline) {
                    throw 'Restored Mochi did not restart.'
                }
                Start-Sleep -Milliseconds 200
            }
            if ((Get-FileHash -LiteralPath $marker).Hash -ne $before) { throw 'Rollback changed original files.' }
        } else {
            if ($worker.ExitCode -ne 0 -or $outcome.status -ne 'success' -or -not $running) {
                throw 'The verified update did not start.'
            }
            if ((Get-Content -LiteralPath $marker) -ne 'update fixture') { throw 'Candidate was not installed.' }
        }
    } finally {
        if ($running -and -not $running.HasExited) {
            & taskkill.exe /PID $running.Id /T /F | Out-Null
            $running.WaitForExit(10000) | Out-Null
        }
    }
}
