param([switch]$Check)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Common = Join-Path $Root "common"
$ConfigRoot = Join-Path $Common "config"
$RoleManifest = ConvertFrom-Json (Get-Content (Join-Path $ConfigRoot "role_manifest.json") -Raw)
$RolePolicy = ConvertFrom-Json (Get-Content (Join-Path $ConfigRoot "role_policy.json") -Raw)
$ModelRouting = ConvertFrom-Json (Get-Content (Join-Path $ConfigRoot "model_routing.json") -Raw)
$McpServers = ConvertFrom-Json (Get-Content (Join-Path $ConfigRoot "mcp_servers.json") -Raw)
$PlatformTargets = ConvertFrom-Json (Get-Content (Join-Path $ConfigRoot "platform_targets.json") -Raw)
$PlatformCaps = ConvertFrom-Json (Get-Content (Join-Path $ConfigRoot "platform_capabilities.json") -Raw)
$CopyNotice = "若这些路径仍是占位内容，先将顶层 `debugger/common/` 拷入当前平台根目录的 `common/` 后再继续。"
$Specs = @(
 @{ Key = "claude-code"; ManagedDirs = @(".claude", "common", "workspace"); ManagedFiles = @("README.md") },
 @{ Key = "code-buddy"; ManagedDirs = @(".codebuddy-plugin", "agents", "skills", "hooks", "common", "workspace"); ManagedFiles = @("README.md", ".mcp.json") },
 @{ Key = "copilot-cli"; ManagedDirs = @("agents", "skills", "hooks", "common", "workspace"); ManagedFiles = @("README.md", ".mcp.json", ".copilot-plugin.json") },
 @{ Key = "copilot-ide"; ManagedDirs = @(".github", "references", "common", "workspace"); ManagedFiles = @("README.md", "agent-plugin.json") },
 @{ Key = "claude-desktop"; ManagedDirs = @("references", "common", "workspace"); ManagedFiles = @("README.md", "claude_desktop_config.json") },
 @{ Key = "manus"; ManagedDirs = @("references", "workflows", "common", "workspace"); ManagedFiles = @("README.md") },
 @{ Key = "codex"; ManagedDirs = @(".agents", ".codex", "common", "workspace"); ManagedFiles = @("README.md", "AGENTS.md") }
)
$ForbiddenDirs = @("docs", "scripts")

function Normalize([string]$Text) {
 if ($null -eq $Text) { $Text = "" }
 $Text = $Text.Replace("`r`n", "`n").Replace("`r", "`n")
 return ($Text.TrimEnd("`n") + "`n")
}

function Write-Text([string]$Path, [string]$Text) {
 $dir = Split-Path $Path
 if ($dir) { $null = New-Item -ItemType Directory -Force $dir }
 [IO.File]::WriteAllText($Path, (Normalize $Text), [Text.UTF8Encoding]::new($true))
}
function Join-Parts([string[]]$Parts) {
 $path = $Parts[0]
 for ($i = 1; $i -lt $Parts.Count; $i++) { $path = Join-Path $path $Parts[$i] }
 return $path
}

function Package-Root([string]$Key) { return (Join-Path (Join-Path $Root "platforms") $Key) }
function Common-Root([string]$Key) { return (Join-Path (Package-Root $Key) "common") }
function Rel-Path([string]$FromFile, [string]$ToPath) { $fromParts = [IO.Path]::GetFullPath((Split-Path $FromFile -Parent)).TrimEnd("\\").Split("\\"); $toParts = [IO.Path]::GetFullPath($ToPath).TrimEnd("\\").Split("\\"); if ($fromParts[0] -ne $toParts[0]) { return ($ToPath.Replace("\\", "/")) }; $i = 0; while ($i -lt $fromParts.Count -and $i -lt $toParts.Count -and $fromParts[$i] -eq $toParts[$i]) { $i++ }; $parts = @(); for ($j = $i; $j -lt $fromParts.Count; $j++) { $parts += ".." }; for ($j = $i; $j -lt $toParts.Count; $j++) { $parts += $toParts[$j] }; if ($parts.Count -eq 0) { return "." }; return ([string]::Join("/", $parts)) }
function Common-Ref([string]$Key, [string]$FromFile, [string[]]$Parts) { return (Rel-Path $FromFile (Join-Path (Common-Root $Key) (Join-Parts $Parts))) }
function Add-Expected($Table, [string]$Path, [string]$Text) { $Table[$Path] = Normalize $Text }
function Roles() { return @($RoleManifest.roles) }

function Get-Role([string]$AgentId) {
 foreach ($role in (Roles)) { if ($role.agent_id -eq $AgentId) { return $role } }
 throw "missing role: $AgentId"
}

function Platform-Model([string]$PlatformKey, [string]$AgentId) {
 $profile = $ModelRouting.role_profiles.$AgentId
 return $ModelRouting.profiles.$profile.platform_rendering.$PlatformKey
}

function Role-Style([string]$AgentId) {
 $profile = $RolePolicy.roles.$AgentId.model_profile
 return $RolePolicy.model_profiles.$profile
}

function Role-Targets([string]$PlatformKey, [string]$AgentId) {
 $targets = @()
 foreach ($targetId in $RolePolicy.roles.$AgentId.delegates_to) {
 $targetRole = Get-Role $targetId
 $fileName = $targetRole.platform_files.$PlatformKey
 if ($fileName) { $targets += [IO.Path]::GetFileNameWithoutExtension($fileName) }
 }
 return $targets
}

function Yaml-Block($Pairs) {
 $rows = New-Object System.Collections.Generic.List[string]
 $null = $rows.Add("---")
 foreach ($key in $Pairs.Keys) {
 $value = $Pairs[$key]
 if ($null -eq $value) { continue }
 if ($value -is [Array]) {
 if ($value.Count -eq 0) { continue }
 $null = $rows.Add("${key}:")
 foreach ($item in $value) { $null = $rows.Add(" - $item") }
 continue
 }
 if ($value -eq "") { continue }
 $null = $rows.Add("${key}: `"$value`"")
 }
 $null = $rows.Add("---")
 return ($rows -join "`n")
}

function Placeholder-Md([string]$Title, [string]$SourceRel, [string]$Extra) {
@"
# $Title

当前文件是平台本地 `common/$SourceRel` 的占位文件。

正式内容来源：`debugger/common/$SourceRel`。
请先将仓库根目录 `debugger/common/` 整体拷贝到当前平台根目录的 `common/`，覆盖占位内容后再继续。

$Extra
"@
}

function Placeholder-Config() {
 $payload = @{ _placeholder = $true; message = "Copy debugger/common/ into this platform root common/ before using platform-local config."; required_action = "overwrite_this_directory_with_debugger_common" }
 return (ConvertTo-Json $payload -Depth 5)
}

function Placeholder-Hook() {
@"
#!/usr/bin/env python3
import sys

MESSAGE = (
 "当前平台根目录的 common/ 仍然是占位内容。"
 "请先将仓库根目录 debugger/common/ 整体拷贝到当前平台根目录 common/，"
 "覆盖占位文件后再执行 hooks。"
)

print(MESSAGE, file=sys.stderr)
raise SystemExit(2)
"@
}

function Common-Placeholder-Files([string]$PlatformKey) {
 $root = Common-Root $PlatformKey
 $expected = @{}
 Add-Expected $expected (Join-Path $root "README.md") @'
# Platform Local Common Placeholder

当前目录是平台本地 `common/` 的占位骨架，不是正式运行时内容。

使用方式：

1. 选择一个 `debugger/platforms/<platform>/` 模板。
2. 将仓库根目录 `debugger/common/` 整体拷贝到该平台根目录的 `common/`，覆盖当前占位内容。
3. 再在对应宿主中打开该平台根目录使用。

约束：

- 平台内所有 skill、hooks、agents、config 只允许引用当前平台根目录的 `common/`。
- 平台内运行时工作区固定为当前平台根目录同级的 `workspace/`。
- 占位文件只用于稳定路径，不代表最终角色定义、skill 正文、hook 逻辑或配置真相。
'@
 Add-Expected $expected (Join-Path $root "AGENT_CORE.md") (Placeholder-Md "AGENT_CORE Placeholder" "AGENT_CORE.md" "在覆盖前，不要把当前文件当成运行时约束真相。")
 Add-Expected $expected (Join-Path $root "skills\renderdoc-rdc-gpu-debug\SKILL.md") (Placeholder-Md "RenderDoc/RDC GPU Debug Skill Placeholder" "skills/renderdoc-rdc-gpu-debug/SKILL.md" "在覆盖前，遇到此占位 skill 时应先停止并提示用户完成拷贝。")
 Add-Expected $expected (Join-Path $root "config\platform_capabilities.json") (Placeholder-Config)
 Add-Expected $expected (Join-Path $root "docs\platform-capability-model.md") (Placeholder-Md "Platform Capability Model Placeholder" "docs/platform-capability-model.md" "在覆盖前，不要把当前文件当成正式平台能力说明。")
 Add-Expected $expected (Join-Path $root "docs\model-routing.md") (Placeholder-Md "Model Routing Placeholder" "docs/model-routing.md" "在覆盖前，不要把当前文件当成正式模型路由说明。")
 Add-Expected $expected (Join-Path $root "docs\workspace-layout.md") (Placeholder-Md "Workspace Layout Placeholder" "docs/workspace-layout.md" "在覆盖前，不要把当前文件当成正式 workspace 合同。")
 Add-Expected $expected (Join-Path $root "hooks\utils\codebuddy_hook_dispatch.py") (Placeholder-Hook)
 Add-Expected $expected (Join-Path $root "knowledge\proposals\README.md") (Placeholder-Md "Knowledge Proposals Placeholder" "knowledge/proposals/README.md" "在覆盖前，不要把当前文件当成正式 proposal 目录说明。")
 foreach ($role in (Roles)) { Add-Expected $expected (Join-Path $root $role.source_prompt) (Placeholder-Md ("$($role.display_name) Prompt Placeholder") $role.source_prompt "在覆盖前，不要把当前文件当成角色职责真相。") }
 return $expected
}
function Workspace-Placeholder-Files([string]$PlatformKey) {
 $workspaceRoot = Join-Path (Package-Root $PlatformKey) "workspace"
 $expected = @{}
 Add-Expected $expected (Join-Path $workspaceRoot "README.md") @'
# Platform Local Workspace Placeholder

当前目录是平台本地 `workspace/` 运行区骨架。

用途：

- 存放 `case_id/run_id` 级运行现场
- 承载 `captures/`、`screenshots/`、`artifacts/`、`logs/`、`notes/`
- 承载第二层交付物 `reports/report.md` 与 `reports/summary.html`

约束：

- 这里不是共享真相；共享真相仍由同级 `common/` 提供。
- `common/` 中的 shared prompt / skill / docs 应通过 `../workspace` 引用当前目录。
- 模板仓库只保留占位骨架，不提交真实运行产物。
'@
 Add-Expected $expected (Join-Path $workspaceRoot "cases\README.md") @'
# Workspace Cases Placeholder

当前目录用于承载运行时 case。

目录约定：

```text
cases/
  <case_id>/
    case.yaml
    runs/
      <run_id>/
        run.yaml
        artifacts/
        logs/
        notes/
        captures/
        screenshots/
        reports/
```

规则：

- `case_id` 是问题实例/需求线程的稳定标识。
- `run_id` 承担 debug version。
- 第一层 session artifacts 仍写入同级 `common/knowledge/library/sessions/`；`workspace/` 不复制 gate 真相。
'@
 return $expected
}
function Readme([string]$PlatformKey) {
 $caps = $PlatformCaps.platforms.$PlatformKey
 $target = $PlatformTargets.platforms.$PlatformKey
 $surfaces = [string]::Join(", ", $target.native_surfaces)
@"
# $($caps.display_name) Template

当前目录是 $($caps.display_name) 的 platform-local 模板。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

使用方式：

1. 将仓库根目录 `debugger/common/` 整体拷贝到当前平台根目录的 `common/`，覆盖占位内容。
2. 使用当前平台根目录同级的 `workspace/` 作为运行区。
3. 在对应宿主中打开当前平台根目录。
4. 平台内的 skill、hooks、agents、config 只允许引用本地 `common/`。

约束：

- `common/` 默认只保留占位骨架；正式共享正文仍由顶层 `debugger/common/` 提供，并由用户显式拷入。
- `workspace/` 预生成空骨架；真实运行产物在平台使用阶段按 case/run 写入。
- 当前平台状态：`$($caps.status_label)`。
- 当前平台生成面：`$surfaces`。
- 维护者若重跑 scaffold，必须继续产出 platform-local `common/` 占位结构，不得回退到跨级引用。
"@
}

function AgentBody([string]$PlatformKey, $Role, [string]$TargetFile) { $rolePath = Join-Path (Common-Root $PlatformKey) $Role.source_prompt; $p1 = Common-Ref $PlatformKey $TargetFile @("AGENT_CORE.md"); $p2 = Rel-Path $TargetFile $rolePath; $p3 = Common-Ref $PlatformKey $TargetFile @("skills", "renderdoc-rdc-gpu-debug", "SKILL.md")
@"
# RenderDoc/RDC Agent Wrapper

当前文件是 $($PlatformCaps.platforms.$PlatformKey.display_name) 宿主入口。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

本文件只负责宿主入口与角色元数据；共享正文统一从当前平台根目录的 `common/` 读取。

按顺序阅读：

1. $p1
2. $p2
3. $p3

$CopyNotice

运行时工作区固定为：`../workspace`
"@
}

function CodeBuddyAgent($Role, [string]$TargetFile) {
 $front = Yaml-Block ([ordered]@{ agent_id = $Role.agent_id; category = $Role.category; model = (Platform-Model "code-buddy" $Role.agent_id); delegates_to = @($RolePolicy.roles.($Role.agent_id).delegates_to) })
 return ($front + "`n`n" + (AgentBody "code-buddy" $Role $TargetFile))
}

function ClaudeCodeAgent($Role, [string]$TargetFile) {
 $front = Yaml-Block ([ordered]@{ description = $Role.description; model = (Platform-Model "claude-code" $Role.agent_id) })
 return ($front + "`n`n" + (AgentBody "claude-code" $Role $TargetFile))
}

function CopilotIdeAgent($Role, [string]$TargetFile) {
 $front = Yaml-Block ([ordered]@{ description = $Role.description; model = (Platform-Model "copilot-ide" $Role.agent_id); handoffs = @(Role-Targets "copilot-ide" $Role.agent_id) })
 return ($front + "`n`n" + (AgentBody "copilot-ide" $Role $TargetFile))
}

function CopilotCliAgent($Role, [string]$TargetFile) {
 $front = Yaml-Block ([ordered]@{ description = $Role.description })
 return ($front + "`n`n" + (AgentBody "copilot-cli" $Role $TargetFile))
}

function SkillWrapper([string]$PlatformKey, [string]$TargetFile) { $skillRef = Common-Ref $PlatformKey $TargetFile @("skills", "renderdoc-rdc-gpu-debug", "SKILL.md"); $capRef = Common-Ref $PlatformKey $TargetFile @("config", "platform_capabilities.json")
@"
# RenderDoc/RDC GPU Debug Skill Wrapper

当前文件是 $($PlatformCaps.platforms.$PlatformKey.display_name) 的 skill 入口。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

本 skill 只引用当前平台根目录的 `common/`：

- $skillRef
- coordination_mode 与降级边界以 $capRef 的当前平台定义为准。

$CopyNotice

运行时 case/run 现场与第二层报告统一写入：`../workspace`
"@
}

function ClaudeCodeEntry([string]$TargetFile) { $p1 = Common-Ref "claude-code" $TargetFile @("AGENT_CORE.md"); $p2 = Common-Ref "claude-code" $TargetFile @("skills", "renderdoc-rdc-gpu-debug", "SKILL.md"); $p3 = Common-Ref "claude-code" $TargetFile @("docs", "platform-capability-model.md")
@"
# Claude Code Entry

当前目录是 Claude Code 的 platform-local 模板。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

先阅读：

1. $p1
2. $p2
3. $p3

$CopyNotice

运行时工作区固定为：`../workspace`
"@
}

function CopilotInstructions([string]$TargetFile) { $p1 = Common-Ref "copilot-ide" $TargetFile @("AGENT_CORE.md"); $p2 = Common-Ref "copilot-ide" $TargetFile @("skills", "renderdoc-rdc-gpu-debug", "SKILL.md"); $p3 = Common-Ref "copilot-ide" $TargetFile @("docs", "platform-capability-model.md")
@"
# Copilot IDE Instructions

当前目录是 Copilot IDE / VS Code 的 platform-local 模板。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

先阅读：

1. $p1
2. $p2
3. $p3
4. ../references/entrypoints.md

$CopyNotice

运行时工作区固定为：`../workspace`
"@
}

function ReferencesEntry([string]$PlatformKey, [string]$TargetFile) { $p1 = Common-Ref $PlatformKey $TargetFile @("AGENT_CORE.md"); $p2 = Common-Ref $PlatformKey $TargetFile @("docs", "platform-capability-model.md"); $p3 = Common-Ref $PlatformKey $TargetFile @("skills", "renderdoc-rdc-gpu-debug", "SKILL.md")
@"
# $($PlatformCaps.platforms.$PlatformKey.display_name) Entrypoints

当前目录只提供宿主入口提示；运行时共享文档统一从当前平台根目录的 `common/` 读取。

先阅读：

1. $p1
2. $p2
3. $p3

$CopyNotice

运行时工作区固定为：`../workspace`
"@
}

function ManusWorkflow() {
@"
# RenderDoc/RDC GPU Debug Workflow

## 目标

在低能力宿主中，用 workflow 方式完成 RenderDoc/RDC GPU Debug 的最小闭环。

## 阶段

1. `triage`
 - 结构化现象、触发条件、可能的 SOP 入口
2. `capture/session`
 - 确认 `.rdc`、session、frame、event anchor
3. `specialist analysis`
 - 从 pipeline、forensics、shader、driver 四个方向收集证据
4. `skeptic`
 - 复核证据链是否足以支持结论
5. `curation`
 - 生成 BugFull / BugCard，写入 session artifacts

## workflow 约束

- Manus 不承担 custom agents / per-agent model 的宿主能力。
- workflow 的每一阶段都必须引用共享 artifact contract。
- `workflow_stage` 是该平台的协作上限，不模拟 team-agent 实时协作。
- remote 阶段由单一 runtime owner 顺序完成 `rd.remote.connect -> rd.remote.ping -> rd.capture.open_file -> rd.capture.open_replay -> re-anchor -> collect evidence`。
- 若需要跨轮次继续调查，必须依赖可重建的 `runtime_baton`，不得凭记忆续跑 live runtime。
- 如需动态 tool discovery，应停止 workflow 并切回支持 `MCP` 的平台。
"@
}
function Mcp-Payload() {
 $servers = @{}
 foreach ($prop in $McpServers.servers.PSObject.Properties) { $servers[$prop.Name] = @{ command = $prop.Value.command; args = @($prop.Value.args) } }
 return @{ servers = $servers }
}

function CodeBuddyPlugin() {
 return @{ name = "renderdoc-rdc-gpu-debug-agent"; description = "RenderDoc/RDC GPU Debug 的 Code Buddy 参考实现，使用 platform-local common 占位骨架生成 hooks、skills、agents 与 MCP。"; author = @{ name = "RenderDoc/RDC GPU Debug" }; keywords = @("renderdoc", "rdc", "gpu", "debug", "mcp", "agent"); agents = "./agents/"; skills = "./skills/"; hooks = "./hooks/hooks.json"; mcpServers = "./.mcp.json" }
}

function CopilotCliPlugin() {
 return @{ name = "renderdoc-rdc-gpu-debug"; description = "Use RenderDoc/RDC platform tools to debug GPU rendering captures through platform-local agents, skills, hooks, and MCP."; author = @{ name = "RenderDoc/RDC GPU Debug" }; keywords = @("renderdoc", "rdc", "gpu", "debug", "mcp", "capture"); agents = "./agents/"; skills = "./skills/"; hooks = "./hooks/hooks.json"; mcpServers = "./.mcp.json" }
}

function CodeBuddyHooks() {
 $base = '${CODEBUDDY_PLUGIN_ROOT}/common/hooks/utils/codebuddy_hook_dispatch.py'
 return @{
 PostToolUse = @(
 @{ matcher = "Write"; hooks = @(@{ type = "command"; command = "uv run --with pyyaml python `"$base`" write-bugcard"; description = "BugCard contract and schema validation"; timeout = 30000 }) },
 @{ matcher = "Write"; hooks = @(@{ type = "command"; command = "uv run --with pyyaml python `"$base`" write-skeptic"; description = "Skeptic signoff artifact validation"; timeout = 30000 }) }
)
 Stop = @(@{ hooks = @(@{ type = "command"; command = "uv run --with pyyaml python `"$base`" stop-gate"; description = "Finalization gate: causal anchor + counterfactual + skeptic + session artifacts"; timeout = 30000 }) })
 }
}

function CopilotCliHooks() {
 $base = "common/hooks/utils/codebuddy_hook_dispatch.py"
 return @{
 PostToolUse = @(
 @{ matcher = "Write"; hooks = @(@{ type = "command"; command = "uv run --with pyyaml python $base write-bugcard"; description = "Validate BugCard before write" }) },
 @{ matcher = "Write"; hooks = @(@{ type = "command"; command = "uv run --with pyyaml python $base write-skeptic"; description = "Validate skeptic signoff artifact" }) }
)
 Stop = @(@{ hooks = @(@{ type = "command"; command = "uv run --with pyyaml python $base stop-gate"; description = "Finalization gate" }) })
 }
}

function ClaudeCodeSettings() {
 $base = "common/hooks/utils/codebuddy_hook_dispatch.py"
 $servers = @{}
 foreach ($prop in $McpServers.servers.PSObject.Properties) { $servers[$prop.Name] = @{ command = $prop.Value.command; args = @($prop.Value.args) } }
 return @{
 description = "RenderDoc/RDC GPU Debug - Claude Code platform-local common adaptation"
 hooks = @{
 PostToolUse = @(
 @{ matcher = @{ tool_name = "Write"; file_pattern = "**/knowledge/library/**/*bugcard*.yaml" }; hooks = @(@{ type = "command"; command = "uv run --with pyyaml python $base write-bugcard"; description = "Validate tool contract and BugCard schema before library write"; on_failure = "block"; failure_message = "BugCard write blocked: tool contract drift or schema validation failed." }) },
 @{ matcher = @{ tool_name = "Write"; file_pattern = "**/knowledge/library/sessions/**/skeptic_signoff.yaml" }; hooks = @(@{ type = "command"; command = "uv run --with pyyaml python $base write-skeptic"; description = "Validate skeptic signoff artifact format"; on_failure = "warn"; failure_message = "Skeptic signoff file did not pass validation." }) }
)
 Stop = @(@{ matcher = @{ assistant_message_pattern = ".*" }; hooks = @(@{ type = "command"; command = "uv run --with pyyaml python $base stop-gate"; description = "Finalization gate for RenderDoc/RDC GPU Debug (causal anchor + counterfactual + skeptic)"; on_failure = "block"; failure_message = "Finalization blocked by session artifact or contract checks." }) })
 }
 mcpServers = $servers
 }
}

function CopilotIdePlugin() {
 return @{ name = "renderdoc-rdc-gpu-debug-ide"; description = "RenderDoc/RDC GPU Debug 的 Copilot IDE platform-local common 适配包。"; agentsRoot = ".github/agents"; notes = @("Use preferred per-agent models where the IDE host supports them.", "Preserve role routing and evidence gates even when the host ignores model preference.", "Read references/entrypoints.md before attempting a CLI-style flow inside the IDE host.") }
}

function ClaudeDesktopConfig() {
 $servers = @{}
 foreach ($prop in $McpServers.servers.PSObject.Properties) { $servers[$prop.Name] = @{ command = $prop.Value.command; args = @($prop.Value.args) } }
 return @{ mcpServers = $servers }
}
function CodexReadme() {
@"
# Codex Template

当前目录是 Codex 的 workspace-native 模板。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

使用方式：

1. 将仓库根目录 `debugger/common/` 整体拷贝到当前平台根目录的 `common/`，覆盖占位内容。
2. 使用当前平台根目录同级的 `workspace/` 作为运行区。
3. 打开当前目录作为 Codex workspace root。
4. AGENTS.md、.agents/skills/、.codex/config.toml 与 .codex/agents/*.toml 只允许引用当前平台根目录的 common/。

约束：

- common/ 默认只保留占位骨架；正式共享正文仍由顶层 debugger/common/ 提供，并由用户显式拷入。
- workspace/ 预生成空骨架；真实运行产物在平台使用阶段按 case/run 写入。
- multi_agent 当前按 experimental / CLI-first 理解，但共享规则与 role config 已完整生成。
"@
}

function CodexAgentsMd([string]$TargetFile) { $p1 = Common-Ref "codex" $TargetFile @("AGENT_CORE.md"); $p2 = Common-Ref "codex" $TargetFile @("skills", "renderdoc-rdc-gpu-debug", "SKILL.md"); $p3 = Common-Ref "codex" $TargetFile @("docs", "platform-capability-model.md"); $p4 = Common-Ref "codex" $TargetFile @("docs", "model-routing.md")
@"
# Codex Workspace Instructions

当前目录是 Codex workspace-native 模板。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

先阅读：

1. $p1
2. $p2
3. $p3
4. $p4

$CopyNotice

运行时工作区固定为：`../workspace`

角色约束：

- team_lead 负责分派和结案门槛，不直接执行 live 调试。
- 专家角色的共享 prompt 真相保存在 common/agents/*.md；.codex/agents/*.toml 只负责模型、reasoning、verbosity 与 sandbox。
- remote case 继续服从 single_runtime_owner，不得因为 multi_agent 就共享 live runtime。
"@
}

function CodexConfig() {
 $rows = New-Object System.Collections.Generic.List[string]
 foreach ($line in @("model = `"gpt-5.4`"", "model_reasoning_effort = `"high`"", "model_verbosity = `"medium`"", "", "[features]", "multi_agent = true", "", "[windows]", "sandbox = `"elevated`"", "")) { $null = $rows.Add($line) }
 foreach ($prop in $McpServers.servers.PSObject.Properties) {
 $null = $rows.Add("[mcp_servers.$($prop.Name)]")
 $null = $rows.Add("command = `"$($prop.Value.command)`"")
 $quotedArgs = @()
 foreach ($arg in $prop.Value.args) { $quotedArgs += "`"$arg`"" }
 $args = [string]::Join(", ", $quotedArgs)
 $null = $rows.Add("args = [$args]")
 $null = $rows.Add("")
 }
 foreach ($role in (Roles)) {
 $key = $role.platform_files.codex
 $null = $rows.Add("[agents.$key]")
 $null = $rows.Add("config_file = `".codex/agents/$key.toml`"")
 $null = $rows.Add("")
 }
 return (($rows -join "`n").TrimEnd())
}

function CodexRoleConfig($Role, [string]$TargetFile) {
 $style = Role-Style $Role.agent_id
 $promptRef = Common-Ref "codex" $TargetFile @($Role.source_prompt.Split("/"))
@"
# Shared role prompt: $promptRef
model = "$(Platform-Model "codex" $Role.agent_id)"
model_reasoning_effort = "$($style.reasoning_effort)"
model_verbosity = "$($style.verbosity)"

[windows]
sandbox = "elevated"
"@
}
function Expected-Files($Spec) {
 $package = Package-Root $Spec.Key
 $expected = @{}
 foreach ($entry in ((& ${function:Common-Placeholder-Files} $Spec.Key).GetEnumerator())) { $expected[$entry.Key] = $entry.Value }
 foreach ($entry in ((& ${function:Workspace-Placeholder-Files} $Spec.Key).GetEnumerator())) { $expected[$entry.Key] = $entry.Value }
 if ($Spec.Key -eq "codex") { Add-Expected $expected (Join-Path $package "README.md") (CodexReadme) } else { Add-Expected $expected (Join-Path $package "README.md") (Readme $Spec.Key) }
 if (@("claude-code", "code-buddy", "copilot-cli", "copilot-ide") -contains $Spec.Key) {
 foreach ($role in (Roles)) {
 $fileName = $role.platform_files.($Spec.Key)
 if (-not $fileName) { continue }
 if ($Spec.Key -eq "claude-code") { $target = Join-Path $package (Join-Path ".claude\agents" $fileName); Add-Expected $expected $target (ClaudeCodeAgent $role $target) }
 elseif ($Spec.Key -eq "code-buddy") { $target = Join-Path $package (Join-Path "agents" $fileName); Add-Expected $expected $target (CodeBuddyAgent $role $target) }
 elseif ($Spec.Key -eq "copilot-cli") { $target = Join-Path $package (Join-Path "agents" $fileName); Add-Expected $expected $target (CopilotCliAgent $role $target) }
 elseif ($Spec.Key -eq "copilot-ide") { $target = Join-Path $package (Join-Path ".github\agents" $fileName); Add-Expected $expected $target (CopilotIdeAgent $role $target) }
 }
 }
 if ($Spec.Key -eq "code-buddy") {
 $skill = Join-Path $package "skills\renderdoc-rdc-gpu-debug\SKILL.md"
 Add-Expected $expected $skill (SkillWrapper $Spec.Key $skill)
 Add-Expected $expected (Join-Path $package ".codebuddy-plugin\plugin.json") (ConvertTo-Json (CodeBuddyPlugin) -Depth 20)
 Add-Expected $expected (Join-Path $package ".mcp.json") (ConvertTo-Json (Mcp-Payload) -Depth 20)
 Add-Expected $expected (Join-Path $package "hooks\hooks.json") (ConvertTo-Json (CodeBuddyHooks) -Depth 20)
 } elseif ($Spec.Key -eq "copilot-cli") {
 $skill = Join-Path $package "skills\renderdoc-rdc-gpu-debug\SKILL.md"
 Add-Expected $expected $skill (SkillWrapper $Spec.Key $skill)
 Add-Expected $expected (Join-Path $package ".copilot-plugin.json") (ConvertTo-Json (CopilotCliPlugin) -Depth 20)
 Add-Expected $expected (Join-Path $package ".mcp.json") (ConvertTo-Json (Mcp-Payload) -Depth 20)
 Add-Expected $expected (Join-Path $package "hooks\hooks.json") (ConvertTo-Json (CopilotCliHooks) -Depth 20)
 } elseif ($Spec.Key -eq "claude-code") {
 $entry = Join-Path $package ".claude\CLAUDE.md"
 Add-Expected $expected $entry (ClaudeCodeEntry $entry)
 Add-Expected $expected (Join-Path $package ".claude\settings.json") (ConvertTo-Json (ClaudeCodeSettings) -Depth 20)
 } elseif ($Spec.Key -eq "copilot-ide") {
 $skill = Join-Path $package ".github\skills\renderdoc-rdc-gpu-debug\SKILL.md"
 $entry = Join-Path $package ".github\copilot-instructions.md"
 $ref = Join-Path $package "references\entrypoints.md"
 Add-Expected $expected $skill (SkillWrapper $Spec.Key $skill)
 Add-Expected $expected $entry (CopilotInstructions $entry)
 Add-Expected $expected $ref (ReferencesEntry $Spec.Key $ref)
 Add-Expected $expected (Join-Path $package "agent-plugin.json") (ConvertTo-Json (CopilotIdePlugin) -Depth 20)
 Add-Expected $expected (Join-Path $package ".github\mcp.json") (ConvertTo-Json (Mcp-Payload) -Depth 20)
 } elseif ($Spec.Key -eq "claude-desktop") {
 $ref = Join-Path $package "references\entrypoints.md"
 Add-Expected $expected $ref (ReferencesEntry $Spec.Key $ref)
 Add-Expected $expected (Join-Path $package "claude_desktop_config.json") (ConvertTo-Json (ClaudeDesktopConfig) -Depth 20)
 } elseif ($Spec.Key -eq "manus") {
 $ref = Join-Path $package "references\entrypoints.md"
 Add-Expected $expected $ref (ReferencesEntry $Spec.Key $ref)
 Add-Expected $expected (Join-Path $package "workflows\00_debug_workflow.md") (ManusWorkflow)
 } elseif ($Spec.Key -eq "codex") {
 $entry = Join-Path $package "AGENTS.md"
 $skill = Join-Path $package ".agents\skills\renderdoc-rdc-gpu-debug\SKILL.md"
 Add-Expected $expected $entry (CodexAgentsMd $entry)
 Add-Expected $expected $skill (SkillWrapper $Spec.Key $skill)
 Add-Expected $expected (Join-Path $package ".codex\config.toml") (CodexConfig)
 foreach ($role in (Roles)) {
 $key = $role.platform_files.codex
 $target = Join-Path $package (Join-Path ".codex\agents" "$key.toml")
 Add-Expected $expected $target (CodexRoleConfig $role $target)
 }
 }
 return $expected
}
function Compare-Files($Expected) {
 $findings = @()
 foreach ($path in $Expected.Keys) {
 if (-not (Test-Path $path)) { $findings += "missing file: $path"; continue }
 $normPath = $path.Replace("/", "\")
 if ($normPath -like "*\workspace\README.md" -or $normPath -like "*\workspace\cases\README.md") { continue }
 $current = Normalize ([System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8))
 if ($current -ne $Expected[$path]) { $findings += "content drift: $path" }
 }
 return $findings
}

function Compare-ManagedDirs($Spec, $Expected) {
 $findings = @()
 $package = Package-Root $Spec.Key
 foreach ($relDir in $Spec.ManagedDirs) {
 $dir = Join-Path $package $relDir
 $expectedNames = @{}
 foreach ($path in $Expected.Keys) {
 if (-not $path.StartsWith($dir)) { continue }
 $rest = $path.Substring($dir.Length).TrimStart("\")
 if ($rest) { $expectedNames[$rest.Split("\")[0]] = $true }
 }
 if (-not (Test-Path $dir)) { if ($expectedNames.Count -gt 0) { $findings += "missing directory: $dir" }; continue }
 foreach ($child in (Get-ChildItem $dir -Force)) { if (-not $expectedNames.ContainsKey($child.Name)) { $findings += "unexpected scaffold output: $($child.FullName)" } }
 }
 return $findings
}

function Stale-Findings($Spec) {
 $package = Package-Root $Spec.Key
 $findings = @()
 foreach ($rel in $ForbiddenDirs) { $target = Join-Path $package $rel; if (Test-Path $target) { $findings += "forbidden copied shared directory: $target" } }
 foreach ($path in (Get-ChildItem $package -Recurse -Filter "README.copy-common.md" -File -ErrorAction SilentlyContinue)) { $findings += "forbidden copy-common artifact: $($path.FullName)" }
 return $findings
}

function Collect-Findings($Spec) {
 $expected = Expected-Files $Spec
 $rows = @()
 $rows += Compare-Files $expected
 $rows += Compare-ManagedDirs $Spec $expected
 $rows += Stale-Findings $Spec
 return $rows
}

function Remove-PathIfExists([string]$Path) { if (Test-Path $Path) { Remove-Item $Path -Recurse -Force } }

function Sync-Spec($Spec) {
 $package = Package-Root $Spec.Key
 foreach ($rel in $ForbiddenDirs) { Remove-PathIfExists (Join-Path $package $rel) }
 foreach ($rel in $Spec.ManagedDirs) { Remove-PathIfExists (Join-Path $package $rel) }
 foreach ($rel in $Spec.ManagedFiles) { Remove-PathIfExists (Join-Path $package $rel) }
 foreach ($entry in (Expected-Files $Spec).GetEnumerator()) { Write-Text $entry.Key $entry.Value }
}

function Validate-SourceTree() {
 $required = @($Common, (Join-Path $Common "agents"), (Join-Path $Common "skills\renderdoc-rdc-gpu-debug\SKILL.md"), (Join-Path $Common "docs\workspace-layout.md"), (Join-Path $Common "knowledge\proposals\README.md"), (Join-Path $ConfigRoot "role_manifest.json"), (Join-Path $ConfigRoot "role_policy.json"), (Join-Path $ConfigRoot "model_routing.json"), (Join-Path $ConfigRoot "mcp_servers.json"), (Join-Path $ConfigRoot "platform_capabilities.json"), (Join-Path $ConfigRoot "platform_targets.json"))
 $findings = @()
 foreach ($path in $required) { if (-not (Test-Path $path)) { $findings += "missing shared source: $path" } }
 foreach ($role in (Roles)) { $source = Join-Path $Common $role.source_prompt; if (-not (Test-Path $source)) { $findings += "missing shared agent source: $source" } }
 return $findings
}

$sourceFindings = Validate-SourceTree
if ($sourceFindings.Count -gt 0) {
 Write-Output "[platform scaffold findings]"
 foreach ($row in $sourceFindings) { Write-Output " - $row" }
 exit 1
}

$findings = @()
foreach ($spec in $Specs) { $findings += Collect-Findings $spec }
if ($Check) {
 if ($findings.Count -gt 0) {
 Write-Output "[platform scaffold findings]"
 foreach ($row in $findings) { Write-Output " - $row" }
 exit 1
 }
 Write-Output "platform scaffold check passed"
 exit 0
}

foreach ($spec in $Specs) { Sync-Spec $spec }
Write-Output "platform scaffold sync complete"
