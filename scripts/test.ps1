$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $repositoryRoot ".venv\Scripts\python.exe"),
    (Join-Path $repositoryRoot ".venv\bin\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    $python = "python"
}
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "dynamic-subject-agent-pytest"
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
& $python -m pytest "--basetemp=$tempRoot" @args
exit $LASTEXITCODE
