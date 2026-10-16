[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [string]$TargetPath = (Split-Path -Parent $PSScriptRoot),
    [ValidatePattern('^[A-Za-z0-9_-]{1,48}$')]
    [string]$ImportName = 'legacy'
)
$ErrorActionPreference = 'Stop'
$importScript = Join-Path $PSScriptRoot 'import_reference.py'
if (-not (Test-Path -LiteralPath $importScript -PathType Leaf)) {
    throw 'import_reference.py must be next to this script.'
}
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $importScript --source $SourcePath --target $TargetPath --name $ImportName
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $importScript --source $SourcePath --target $TargetPath --name $ImportName
} else {
    throw 'Python 3.9 or later is required. Install Python, then run again.'
}
if ($LASTEXITCODE -ne 0) {
    throw 'Import did not finish successfully. Check the local manifest; no files were pushed.'
}
Write-Host 'Local reference prepared. Review import-manifest.json before sharing. Nothing was pushed.'
