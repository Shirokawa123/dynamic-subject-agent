param([string]$Python='D:\anaconda3\python.exe')
$ErrorActionPreference='Stop'
$integratedRepository=Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python interpreter unavailable; no entry started.' }
$env:PYTHONPATH=Join-Path $integratedRepository 'src'
$env:TEMP=Join-Path $integratedRepository '.artifacts'
$env:TMP=$env:TEMP
$env:NO_PROXY=(($env:NO_PROXY+',127.0.0.1,localhost,api.deepseek.com').Trim(','))
$integratedLaunchId=[guid]::NewGuid().ToString('N')
$integratedLog=Join-Path $integratedRepository ('.artifacts\s158\experience-live\launch\'+$integratedLaunchId)
New-Item -ItemType Directory -Path $integratedLog -Force | Out-Null
$integratedArguments=@('-X','utf8',(Join-Path $integratedRepository 'scripts\serve_integrated_character_chat.py'),'--port','8797')
$integratedProcess=Start-Process -FilePath $Python -ArgumentList $integratedArguments -WorkingDirectory $integratedRepository -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $integratedLog 'entry-stdout.log') -RedirectStandardError (Join-Path $integratedLog 'entry-stderr.log')
Write-Output ('Integrated character entry dispatched; PID '+$integratedProcess.Id+'. Health still needs verification.')
