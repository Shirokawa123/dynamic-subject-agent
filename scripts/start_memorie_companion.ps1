param(
    [string]$PythonPath = 'D:\anaconda3\python.exe',
    [ValidateSet('baseline','intent')][string]$Policy = 'intent',
    [switch]$OpenGame
)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$artifact = Join-Path $workspace '.artifacts/s160'
$serverScript = Join-Path $PSScriptRoot 'serve_memorie_companion.py'
$expectedSubject = [string][char]0x6885 + [char]0x83AB + [char]0x8389
if (!(Test-Path -LiteralPath $PythonPath) -or !(Test-Path -LiteralPath (Join-Path $artifact 'approval.json'))) {
    throw 'The local Python runtime and exact S160 approval receipt are required.'
}
$description = & $PythonPath $serverScript --policy $Policy --describe-entry
if ($LASTEXITCODE -ne 0) { throw 'Exact entry description failed; no service was started.' }
$expected = ($description -join "`n") | ConvertFrom-Json
$expectedVersion, $expectedEntryKey = $expected.contract_version, $expected.entry_key
if ($expectedEntryKey -notmatch '^[0-9a-f]{64}$') { throw 'Verified entry description required.' }
$listener = Get-NetTCPConnection -State Listen -LocalPort 8798 -ErrorAction SilentlyContinue
if ($listener) {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8798/health' -TimeoutSec 4
    if ($health.application -ne 'memorie-companion-s160' -or $health.protocol -ne 1 -or $health.contract_version -ne $expectedVersion -or $health.entry_key -ne $expectedEntryKey) {
        throw 'Port 8798 is already serving a different or unverified policy; the existing process has been preserved.'
    }
} else {
    $runDirectory = Join-Path $artifact ('run-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $runDirectory | Out-Null
    $previousTemp, $previousTmp = $env:TEMP, $env:TMP
    try {
        $env:TEMP = $artifact
        $env:TMP = $artifact
        $process = Start-Process -FilePath $PythonPath -ArgumentList @('-u', ('"{0}"' -f $serverScript), '--policy', $Policy) `
            -WorkingDirectory $workspace -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $runDirectory 'stdout.log') `
            -RedirectStandardError (Join-Path $runDirectory 'stderr.log')
        $process.Id | Set-Content -LiteralPath (Join-Path $runDirectory 'pid.txt')
    } finally {
        $env:TEMP, $env:TMP = $previousTemp, $previousTmp
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8798/health' -TimeoutSec 1
            if ($health.application -eq 'memorie-companion-s160' -and $health.protocol -eq 1 -and $health.contract_version -eq $expectedVersion -and $health.entry_key -eq $expectedEntryKey) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (!$ready) { throw "Backend did not become ready; see $runDirectory" }
}
$state = Invoke-RestMethod -Uri 'http://127.0.0.1:8798/status' -TimeoutSec 4
if ($state.ready -ne $true -or $state.subject_name -ne $expectedSubject) { throw 'The exact character entry is not ready; no model call was made.' }
if ($OpenGame -and !(Get-Process -Name MemoryOfMemorie -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath 'D:\steam\steam.exe' -ArgumentList @('-applaunch', '4337440') -WindowStyle Hidden
}
Write-Output 'Memorie companion ready on 127.0.0.1:8798. No model is called by startup.'
