param([switch]$Check)
$ErrorActionPreference = "Stop"

$core = Join-Path $PSScriptRoot "sync_platform_scaffolds.core.ps1"
if (-not (Test-Path $core)) {
 throw "missing scaffold core: $core"
}

$lines = Get-Content $core
if ($lines.Count -lt 2) {
 throw "invalid scaffold core: $core"
}

$checkLiteral = if ($Check) { '$true' } else { '$false' }
$body = ($lines[1..($lines.Count - 1)] -join [Environment]::NewLine)
$bootstrap = @(
 "`$PSScriptRoot = '$PSScriptRoot'"
 "`$Check = $checkLiteral"
 $body
) -join [Environment]::NewLine

& ([scriptblock]::Create($bootstrap))
exit $LASTEXITCODE
