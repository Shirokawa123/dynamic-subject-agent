param(
    [Parameter(Mandatory=$true)][string]$DotnetPath,
    [Parameter(Mandatory=$true)][string]$RuntimeDirectory,
    [Parameter(Mandatory=$true)][string]$BuildReferences,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference='Stop'
$workspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$outputRoot=[IO.Path]::GetFullPath($OutputDirectory)
$artifactRoot=[IO.Path]::GetFullPath((Join-Path $workspace '.artifacts'))+[IO.Path]::DirectorySeparatorChar
if (!$outputRoot.StartsWith($artifactRoot,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $outputRoot)) {
    throw 'Choose a new directory inside this workspace .artifacts; previous candidates are preserved.'
}
$runtimeRoot=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
$referencesRoot=(Resolve-Path -LiteralPath $BuildReferences).Path
$compiler=(Resolve-Path -LiteralPath $DotnetPath).Path
New-Item -ItemType Directory -Path $outputRoot | Out-Null
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
& $compiler build (Join-Path $workspace 'integrations/memorie-companion/MemorieCompanion.csproj') `
    --configuration Release --nologo -v:q `
    "-p:MemorieBepInExDirectory=$runtimeRoot" "-p:MemorieBuildReferences=$referencesRoot" `
    "-p:BaseIntermediateOutputPath=$outputRoot/obj/" "-p:OutputPath=$outputRoot/compiled/" *> (Join-Path $outputRoot 'build.log')
if ($LASTEXITCODE -ne 0) { throw "Plugin build failed; see $outputRoot/build.log" }
$package=Join-Path $outputRoot 'package'
New-Item -ItemType Directory -Path $package | Out-Null
Get-ChildItem -LiteralPath $runtimeRoot -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $package -Recurse
}
$pluginTarget=Join-Path $package 'BepInEx/plugins/MemorieCompanion'
New-Item -ItemType Directory -Path $pluginTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $outputRoot 'compiled/DynamicSubject.MemorieCompanion.dll') -Destination $pluginTarget
$files=@(Get-ChildItem -LiteralPath $package -Recurse -File -Force | Sort-Object FullName | ForEach-Object {
    [pscustomobject]@{path=[IO.Path]::GetRelativePath($package,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
[pscustomobject]@{version='memorie-plugin-package-1';runtime='BepInEx-6.0.0-be.785+6abdba4';game_unity='6000.3.6f1';files=$files} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputRoot 'package-manifest.json') -Encoding utf8
Write-Output "Prepared package only: $package"
Write-Output "Files: $($files.Count); no game installation or startup performed."
