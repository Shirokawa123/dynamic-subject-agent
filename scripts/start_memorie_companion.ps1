param(
    [string]$PythonPath = 'D:\anaconda3\python.exe',
    [switch]$OpenGame
)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$artifact = Join-Path $workspace '.artifacts/s160'
$serverScript = Join-Path $PSScriptRoot 'serve_memorie_companion.py'
if (!(Test-Path -LiteralPath $PythonPath) -or !(Test-Path -LiteralPath (Join-Path $artifact 'approval.json'))) {
    throw 'The local Python runtime and exact S160 approval receipt are required.'
}
$listener = Get-NetTCPConnection -State Listen -LocalPort 8798 -ErrorAction SilentlyContinue
if ($listener) {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8798/health' -TimeoutSec 4
    if ($health.application -ne 'memorie-companion-s160' -or $health.protocol -ne 1) {
        throw 'Port 8798 belongs to a different service; it has been preserved.'
    }
} else {
    $runDirectory = Join-Path $artifact ('run-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $runDirectory | Out-Null
    $previousTemp, $previousTmp = $env:TEMP, $env:TMP
    try {
        $env:TEMP = $artifact
        $env:TMP = $artifact
        $process = Start-Process -FilePath $PythonPath -ArgumentList @('-u', ('"{0}"' -f $serverScript)) `
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
            if ($health.application -eq 'memorie-companion-s160' -and $health.protocol -eq 1) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (!$ready) { throw "Backend did not become ready; see $runDirectory" }
}
if ($OpenGame -and !(Get-Process -Name MemoryOfMemorie -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath 'D:\steam\steam.exe' -ArgumentList @('-applaunch', '4337440') -WindowStyle Hidden
}
Write-Output 'Memorie companion ready on 127.0.0.1:8798. No model is called by startup.'
