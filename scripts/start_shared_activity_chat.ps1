param(
    [string]$Python = $env:DSA_PYTHON,
    [ValidateSet('baseline', 'natural-expression')][string]$TechnicalVariant = 'baseline',
    [int]$Port = 8790,
    [switch]$NoBrowser,
    [switch]$DirectProvider
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $repositoryRoot 'src'
if ($DirectProvider) {
    # This process only, for the exact existing HTTPS provider. TLS, credential
    # slot and model protocol stay unchanged; system proxy settings remain.
    $env:NO_PROXY = (($env:NO_PROXY + ',127.0.0.1,localhost,api.deepseek.com').Trim(','))
}
$candidates = @()
if ($Python) {
    $candidates = @($Python)
} else {
    $candidates += Join-Path $repositoryRoot '.venv\Scripts\python.exe'
    $candidates += Join-Path $repositoryRoot '.venv\bin\python.exe'
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    if ($env:CONDA_PREFIX) { $candidates += Join-Path $env:CONDA_PREFIX 'python.exe' }
    $candidates += 'D:\anaconda3\python.exe'
    $candidates += Join-Path $env:USERPROFILE 'anaconda3\python.exe'
}
$runtime = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    try {
        $probe = & $candidate -X utf8 -c "import sys,keyring; assert sys.version_info >= (3,12); print('shared-chat-runtime-ready')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $probe -contains 'shared-chat-runtime-ready') {
            $runtime = $candidate
            break
        }
    } catch { }
}
if (-not $runtime) {
    throw 'No working Python 3.12+ with keyring. Specify an existing interpreter with -Python or DSA_PYTHON. No environment was installed or changed.'
}
$arguments = @('-X', 'utf8', (Join-Path $repositoryRoot 'scripts\serve_shared_activity_chat.py'),
    '--port', $Port, '--technical-variant', $TechnicalVariant)
if (-not $NoBrowser) { $arguments += '--open-browser' }
Push-Location -LiteralPath $repositoryRoot
try {
    & $runtime @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
