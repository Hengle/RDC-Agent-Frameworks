param([switch]$Strict)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Findings = @()

foreach ($artifact in @(".claude", ".github", ".codex", ".agents")) {
 $path = Join-Path $Root $artifact
 if (Test-Path $path) { $Findings += "source root must not contain host artifact: $path" }
}

$syncScript = Join-Path $PSScriptRoot "sync_platform_scaffolds.ps1"
$syncOutput = & $syncScript -Check 2>&1
$syncCode = $LASTEXITCODE
if ($syncCode -ne 0) {
 foreach ($line in $syncOutput) {
 $text = [string]$line
 if ($text -and $text -ne "[platform scaffold findings]") { $Findings += $text }
 }
}

$textExts = @(".md", ".json", ".toml", ".txt", ".yaml", ".yml", ".py")
$forbidden = @("direct-reference", "deprecated", "transitional", "legacy", "本目录直接引用仓库中的共享", "运行时共享文档统一直接引用仓库中的", "禁止复制或镜像 `common/` 内容")
$platformRoot = Join-Path $Root "platforms"
foreach ($file in (Get-ChildItem $platformRoot -Recurse -File -ErrorAction SilentlyContinue)) {
 if ($textExts -notcontains $file.Extension.ToLower()) { continue }
 if ($file.FullName -like "*\common\*") { continue }
 $text = Get-Content $file.FullName -Raw
 foreach ($marker in $forbidden) {
 if ($text.Contains($marker)) { $Findings += "forbidden legacy text in $($file.FullName): $marker" }
 }
}

if ($Findings.Count -gt 0) {
 Write-Output "[platform layout findings]"
 foreach ($row in $Findings) { Write-Output " - $row" }
 if ($Strict) { exit 1 }
 exit 0
}

Write-Output "platform layout validation passed"
