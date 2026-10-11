param([string]$Python='D:\anaconda3\python.exe')
$ErrorActionPreference='Stop'
$naturalRepository=Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python interpreter unavailable; no entry started.' }
$env:PYTHONPATH=Join-Path $naturalRepository 'src'
$env:TEMP=Join-Path $naturalRepository '.artifacts'
$env:TMP=$env:TEMP
$env:NO_PROXY=(($env:NO_PROXY+',127.0.0.1,localhost,api.deepseek.com').Trim(','))
$naturalLaunchId=[guid]::NewGuid().ToString('N')
$naturalLog=Join-Path $naturalRepository ('.artifacts\s155\launch\'+$naturalLaunchId)
New-Item -ItemType Directory -Path $naturalLog -Force | Out-Null
$naturalArguments=@('-X','utf8',(Join-Path $naturalRepository 'scripts\serve_natural_feedback_chat.py'),'--port','8796')
$naturalProcess=Start-Process -FilePath $Python -ArgumentList $naturalArguments -WorkingDirectory $naturalRepository -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $naturalLog 'entry-stdout.log') -RedirectStandardError (Join-Path $naturalLog 'entry-stderr.log')
Write-Output ('Natural feedback entry dispatched; PID '+$naturalProcess.Id+'. Health still needs verification.')
