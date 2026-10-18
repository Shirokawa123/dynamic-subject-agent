param(
    [Parameter(Mandatory=$true)][string]$GameDirectory,
    [Parameter(Mandatory=$true)][string]$CandidateDirectory,
    [Parameter(Mandatory=$true)][string]$PlanPath,
    [switch]$Apply,
    [string]$ApprovalPath
)
$ErrorActionPreference='Stop'
$gameRoot=(Resolve-Path -LiteralPath $GameDirectory).Path
$candidate=(Resolve-Path -LiteralPath $CandidateDirectory).Path
$packageRoot=Join-Path $candidate 'package'
$manifestFile=Join-Path $candidate 'package-manifest.json'
$manifest=Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
if ($manifest.version -ne 'memorie-plugin-package-1' -or !(Test-Path -LiteralPath (Join-Path $gameRoot 'MemoryOfMemorie.exe'))) {
    throw 'Exact Memorie package and installation required.'
}
function ExactChild([string]$root,[string]$relative) {
    if ([IO.Path]::IsPathRooted($relative)) { throw 'Relative package path required.' }
    $full=[IO.Path]::GetFullPath((Join-Path $root $relative))
    if (!$full.StartsWith($root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Package path escaped its root.' }
    $parent=Split-Path -Parent $full
    while ($parent.Length -gt $root.Length) {
        if ((Test-Path -LiteralPath $parent) -and ((Get-Item -LiteralPath $parent).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Reparse-point package targets are not accepted.'
        }
        $parent=Split-Path -Parent $parent
    }
    return $full
}
$manifestSha=(Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash.ToLowerInvariant()
$gameAssembly=Join-Path $gameRoot 'GameAssembly.dll'
$gameSha=(Get-FileHash -LiteralPath $gameAssembly -Algorithm SHA256).Hash.ToLowerInvariant()
$copyPlan=@($manifest.files | ForEach-Object {
    $relative=$_.path.Replace('\','/')
    if ($relative -notmatch '^(BepInEx/|dotnet/|winhttp\.dll$|doorstop_config\.ini$|\.doorstop_version$|changelog\.txt$)') {
        throw 'Unexpected package target.'
    }
    $source=ExactChild $packageRoot $_.path
    $target=ExactChild $gameRoot $_.path
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $_.sha256) { throw 'Package changed.' }
    if ((Test-Path -LiteralPath $target) -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $_.sha256) {
        throw "Target conflict; nothing overwritten: $target"
    }
    [pscustomobject]@{relative=$_.path;source=$source;target=$target;sha256=$_.sha256}
})
if (!$Apply) {
    if (Test-Path -LiteralPath $PlanPath) { throw 'Existing plan preserved; choose a new plan path.' }
    [pscustomobject]@{version='memorie-install-plan-1';game_root=$gameRoot;candidate=$candidate;
        manifest_sha256=$manifestSha;game_assembly_sha256=$gameSha;startup_included=$false;files=$copyPlan} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $PlanPath -Encoding utf8
    Write-Output "Prepared $($copyPlan.Count) file copies; no game file changed."
    exit 0
}
if (!$ApprovalPath -or !(Test-Path -LiteralPath $ApprovalPath)) { throw 'Explicit installation approval receipt required.' }
$approval=Get-Content -LiteralPath $ApprovalPath -Raw | ConvertFrom-Json
$plan=Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json
if ($approval.install_confirmed -isnot [bool] -or !$approval.install_confirmed -or
    $approval.install_plan_sha256 -ne (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -or
    $plan.version -ne 'memorie-install-plan-1' -or $plan.game_root -ne $gameRoot -or $plan.candidate -ne $candidate -or
    $plan.manifest_sha256 -ne $manifestSha -or $plan.game_assembly_sha256 -ne $gameSha -or
    ($plan.files | ConvertTo-Json -Depth 5 -Compress) -ne ($copyPlan | ConvertTo-Json -Depth 5 -Compress)) {
    throw 'Installation approval or source basis mismatch.'
}
if (Get-Process -Name MemoryOfMemorie -ErrorAction SilentlyContinue) { throw 'Game is running; do not stop it automatically.' }
foreach ($item in $copyPlan) {
    if (Test-Path -LiteralPath $item.target) { continue }
    New-Item -ItemType Directory -Path (Split-Path -Parent $item.target) -Force | Out-Null
    [IO.File]::Copy($item.source,$item.target,$false)
}
Write-Output 'Approved new plugin files copied; game not launched, existing files not overwritten.'
