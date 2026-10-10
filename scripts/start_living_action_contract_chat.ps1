param(
    [string]$Python = 'D:\anaconda3\python.exe',
    [int]$Port = 8795,
    [switch]$NoBrowser,
    [switch]$DirectProvider
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $repositoryRoot 'src'
if ($DirectProvider) {
    $env:NO_PROXY = (($env:NO_PROXY + ',127.0.0.1,localhost,api.deepseek.com').Trim(','))
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw '指定的Python解释器不存在，未启动入口。' }
$arguments = @('-X', 'utf8', (Join-Path $repositoryRoot 'scripts\serve_living_action_contract_chat.py'), '--port', $Port)
if (-not $NoBrowser) { $arguments += '--open-browser' }
Push-Location -LiteralPath $repositoryRoot
try {
    & $Python @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
