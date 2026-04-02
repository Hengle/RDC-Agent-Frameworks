# Debugger Framework 深度研究报告

## 概述

本文档是对 RenderDoc/RDC GPU Debug 框架的深度研究分析。该框架是一个面向 GPU 渲染调试的多智能体（Multi-Agent）调试系统，专为诊断和解决 GPU 渲染问题而设计。报告从 Prompt、Context、Harness 三个核心维度对框架进行系统性分析，并评估其设计、流程、缺陷和整体价值。

---

## 一、Prompt 设计分析

### 1.1 Prompt 架构层次

框架采用三层 Prompt 架构：

**第一层：System-Level Prompt（系统级提示）**
- 位于 `AGENT_CORE.md`，定义全局硬约束
- 规定平台真相与 framework 真相边界
- 定义唯一运行模型：`staged_handoff` + `multi_agent` + `single_runtime_single_context`

**第二层：Agent-Level Prompt（智能体级提示）**
- 每个 Agent 拥有独立的 Markdown 文件定义（如 `02_triage_taxonomy.md`）
- 明确定义角色身份、核心工作流、输入输出格式
- 包含硬边界（Hard Boundaries）和禁止行为（Prohibited Behaviors）

**第三层：Task-Level Prompt（任务级提示）**
- 在 `debug_plan` 中动态生成
- 包含 `normalized_goal`、`user_facts`、`capture_inventory` 等运行时上下文

### 1.2 Prompt 设计特点

| 特点 | 说明 | 示例 |
|------|------|------|
| **角色隔离** | 每个 Agent 有明确职责边界 | Triage Agent 只做分类，不做根因推断 |
| **硬约束编码** | 通过 "硬规则"、"禁止行为" 明确限制 | "禁止输出'根因是X'" |
| **输入输出契约** | 严格的 YAML/JSON Schema 约束 | `message_type: TRIAGE_RESULT` |
| **质量门槛内嵌** | 每个 Agent 包含自检清单 | Pass Graph Agent 的 7 项质量检查 |

### 1.3 Agent Prompt 示例分析

**Triage Agent Prompt 核心要素：**
```markdown
## 身份
你是症状分类专家。你的唯一职责是将 Bug 报告转化为结构化分类输出。

## 核心工作流
1. 症状提取 → symptom_tags/trigger_tags
2. 历史案例匹配 → candidate_bug_refs
3. 不变量路由 → candidate_invariants/recommended_sop
4. 置信度评估 → route_confidence/clarification_needed

## 禁止行为
- ❌ 输出"根因是 X"
- ❌ 输出"建议修复方式为 Y"
- ❌ 依据 recommended_investigation_paths 自己分派 specialist
```

**Skeptic Agent Prompt 核心要素：**
```markdown
## 核心规则
你不负责证明结论成立；你负责阻止错误结论被记录为事实。

## 审核顺序
1. reference_contract.readiness_status
2. structural_verification.status
3. semantic_verification.status
4. overall_result
5. challenge / redispatch 是否已经关闭
```

### 1.4 Prompt 设计评价

**优势：**
- 职责边界清晰，避免 Agent 越权
- 通过 "禁止行为" 明确划定能力边界
- 质量门槛内嵌，确保输出一致性

**潜在问题：**
- Prompt 冗长，可能增加 Token 消耗
- 硬约束过多，可能限制 Agent 的灵活推理
- 缺乏动态 Prompt 优化机制

---

## 二、Context 设计分析

### 2.1 Context 架构模型

框架采用 **四层 Context 架构**：

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: Session-level Context                              │
│  - action_chain.jsonl (append-only ledger)                  │
│  - session_evidence.yaml (adjudicated snapshot)             │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Run-level Context                                  │
│  - runtime_session.yaml (runtime generation)                │
│  - runtime_snapshot.yaml (snapshot_rev)                     │
│  - ownership_lease.yaml (lease_epoch)                       │
│  - runtime_failure.yaml (failure tracking)                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Case-level Context                                 │
│  - case_input.yaml (reference_contract)                     │
│  - captures/manifest.yaml (capture inventory)               │
│  - hypothesis_board.yaml (investigation state)              │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Knowledge-level Context                            │
│  - spec/registry/active_manifest.yaml (SOP/Invariant)       │
│  - library/bugcards/ (historical cases)                     │
│  - library/bugfull/ (full case records)                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Context 传递机制

**Staged Handoff 协议：**
- 通过 `ownership_lease` 实现 Agent 间 Context 交接
- Lease 包含：`owner_agent_id`、`lease_epoch`、`allowed_action_classes`
- 每次 handoff 必须更新 `runtime_session` 和 `action_chain`

**Context 引用规则：**
- 跨阶段只允许使用 framework ids（`case_id`、`run_id`、`brief_id`）
- runtime ids（`session_id`、`context_id`）不得作为跨阶段稳定主键
- specialist brief 只允许引用 `runtime_generation + snapshot_rev`

### 2.3 Context 数据结构

**Hypothesis Board Schema：**
```yaml
hypothesis_board:
  session_id: string
  entry_skill: rdc-debugger
  user_goal: string
  intake_state: handoff_ready | triage | investigation | ...
  current_phase: intake | triage | investigation | validation | ...
  active_owner: string
  intent_gate:
    classifier_version: 1
    decision: debugger | analyst | optimizer
    confidence: high | medium | low
  hypotheses: []
```

**Action Chain Event：**
```yaml
schema_version: "2"
event_id: string
ts_ms: integer
run_id: string
session_id: string
agent_id: string
event_type: dispatch | tool_execution | artifact_write | quality_check
status: sent | pass | fail
payload:
  runtime_generation: integer
  snapshot_rev: integer
  owner_agent_id: string
  lease_epoch: integer
  continuity_status: fresh_start | reattached_equivalent | ...
  action_request_id: string
```

### 2.4 Context 设计评价

**优势：**
- 分层清晰，职责分离明确
- 审计追踪完整（action_chain.jsonl 为 append-only）
- 版本控制（runtime_generation、snapshot_rev、lease_epoch）

**潜在问题：**
- Context 文件分散，可能增加 I/O 开销
- 跨层引用复杂，需要维护多层映射关系
- Session 真相方向仍在迁移中（`.current_session` 兼容路径）

---

## 三、Harness 设计分析

### 3.1 Harness 架构

**Shared Harness / Broker 是唯一 enforcement SSOT（Single Source of Truth）。**

核心组件：

```
┌────────────────────────────────────────────────────────────┐
│                    Harness Guard Core                       │
│                  (harness_guard.py)                        │
├────────────────────────────────────────────────────────────┤
│  Entry Gate    │  Intake Gate    │  Dispatch Readiness    │
│  (entry_gate)  │  (intake_gate)  │  (dispatch_readiness)  │
├────────────────────────────────────────────────────────────┤
│              Runtime Broker Core                           │
│              (runtime_broker.py)                           │
├────────────────────────────────────────────────────────────┤
│  Session Mgmt  │  Lease Mgmt     │  Failure Recovery      │
│  (start/close) │  (acquire/      │  (record/recover)      │
│                │   validate/     │                        │
│                │   release)      │                        │
├────────────────────────────────────────────────────────────┤
│              Compliance Audit                              │
│           (run_compliance_audit.py)                        │
└────────────────────────────────────────────────────────────┘
```

### 3.2 Harness 执行流程

**完整执行链：**

```
Preflight → Entry Gate → Accept Intake → Intake Gate → Runtime Start
                                              ↓
Triage → Dispatch Specialist → Specialist Work → Feedback
                                              ↓
Skeptic Review → (Challenge/Redispatch) → Curator Finalize → Final Audit → User Verdict
```

**关键 Harness 检查点：**

| 检查点 | 职责 | 阻断条件 |
|--------|------|----------|
| `preflight` | 绑定验证、工具契约验证 | binding_findings、tool_findings |
| `entry_gate` | 平台/模式验证、输入验证 | 缺少 .rdc、reference 非 strict_ready |
| `intake_gate` | case/run 初始化验证 | runtime_session 创建失败 |
| `dispatch_readiness` | 调度前状态检查 | active lease、blocked failure |
| `specialist_feedback` | 超时检测 | BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT |
| `final_audit` | 合规性审计 | 缺少必需 artifacts |

### 3.3 Runtime Ownership Model

**Lease-Based Ownership：**

```python
# Lease 结构
{
  "status": "active",
  "owner_agent_id": "pass_graph_pipeline_agent",
  "lease_epoch": 3,
  "issued_at": "2026-04-02T10:00:00Z",
  "expires_at": "2026-04-02T10:30:00Z",
  "allowed_action_classes": ["broker_action", "artifact_write", "submit_brief"]
}
```

**Lease 验证规则：**
- Lease 必须处于 `active` 状态
- `owner_agent_id` 必须与调用者匹配
- `lease_epoch` 必须与 `runtime_session` 同步
- 必须在 `expires_at` 之前
- action_class 必须在 `allowed_action_classes` 中

### 3.4 Failure 处理机制

**Failure 分类：**
- `TOOL_CONTRACT_VIOLATION`：工具契约违反
- `TOOL_RUNTIME_FAILURE`：工具运行时失败（允许一次受控恢复）
- `TOOL_CAPABILITY_LIMIT`：工具能力限制
- `INVESTIGATION_INCONCLUSIVE`：调查无结论

**Recovery 策略：**
- 只有 `TOOL_RUNTIME_FAILURE` 允许 broker 做一次受控恢复
- 恢复成功后 `runtime_generation + 1`
- 连续性判定：`reattached_equivalent`、`reattached_shifted`、`reattach_failed`

### 3.5 Harness 设计评价

**优势：**
- 强一致性保证（SSOT 设计）
- 完善的审计追踪（action_chain.jsonl）
- 细粒度的权限控制（Lease-based）
- 健壮的故障恢复机制

**潜在问题：**
- Harness 逻辑复杂，维护成本高
- 所有检查点都是同步阻塞的
- 缺乏并行调度能力

---

## 四、流程分析

### 4.1 双阶段模型

**Plan / Intake Phase：**
- 职责：意图识别、信息收敛、debug_plan 编译
- 硬边界：不创建 case/run、不写审计产物、不接触 live runtime
- 输出：`debug_plan`（唯一正式输出）

**Audited Execution Phase：**
- 入口：`entry_gate`（严格从此时开始）
- 流程：`entry_gate → accept_intake → intake_gate → triage → specialist loop → skeptic → curator → final_audit`
- 输出：结构化审计产物（artifacts/、reports/）

### 4.2 工作流状态机

**19 个可审计状态：**

```
preflight_pending → intent_gate_passed → awaiting_fix_reference → entry_gate_passed
→ accepted_intake_initialized → triage_needs_clarification → requesting_additional_input
→ intake_gate_passed → waiting_for_specialist_brief → redispatch_pending
→ specialist_reinvestigation → specialist_briefs_collected → expert_investigation_complete
→ skeptic_challenged → fix_verification_complete → skeptic_ready → curator_ready
→ finalized / blocked_specialist_timeout
```

### 4.3 Agent 协作拓扑

**Hub-and-Spoke 模型：**

```
                    ┌─────────────┐
                    │ rdc-debugger │
                    │  (Hub/Orchestrator)
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐      ┌─────▼─────┐      ┌─────▼─────┐
   │ Triage  │      │ Specialist│      │  Skeptic  │
   │ Agent   │      │  Agents   │      │  Agent    │
   └─────────┘      └───────────┘      └───────────┘
                           │
                    ┌─────▼─────┐
                    │  Curator  │
                    │  Agent    │
                    └───────────┘
```

**Specialist Agents：**
- `capture_repro_agent`：捕获与复现
- `pass_graph_pipeline_agent`：Pass Graph 分析
- `pixel_forensics_agent`：像素级取证
- `shader_ir_agent`：Shader IR 分析
- `driver_device_agent`：驱动/设备分析

### 4.4 知识演进流程

```
compliant run → auto candidate → replay validation → shadow observation → active / rolled_back
```

**知识对象层级：**
- `spec/`：正式生效的版本化知识（SOP、Invariant、Taxonomy）
- `library/`：run/session 沉淀的共享真相
- `proposals/`：待治理的 candidate 对象

---

## 五、缺陷分析

### 5.1 设计层面缺陷

| 缺陷 | 描述 | 影响 |
|------|------|------|
| **过度工程化** | 多层 Context、复杂的 Lease 机制、19 个状态 | 增加理解和维护成本 |
| **同步阻塞** | 所有 Harness 检查点都是同步的 | 无法并行调度多个 specialist |
| **缺乏弹性** | 硬约束过多，缺乏动态调整机制 | 难以适应边界情况 |
| **Token 消耗** | Prompt 冗长，多层 Context 需要频繁读取 | 增加 LLM 调用成本 |

### 5.2 实现层面缺陷

| 缺陷 | 描述 | 位置 |
|------|------|------|
| **Session 真相混乱** | `.current_session` 兼容路径与新路径并存 | AGENT_CORE.md 第 8 节 |
| **越权检测滞后** | `PROCESS_DEVIATION_MAIN_AGENT_OVERREACH` 只能在事后检测 | harness_guard.py |
| **Timeout 硬编码** | DEFAULT_LEASE_TTL_SECONDS = 1800 固定值 | harness_guard.py:53 |
| **缺乏重试机制** | 除 TOOL_RUNTIME_FAILURE 外无重试 | runtime_broker.py |

### 5.3 流程层面缺陷

| 缺陷 | 描述 | 影响 |
|------|------|------|
| **闭环回转复杂** | redispatch 需要写入 action_chain 和更新 hypothesis_board | 增加实现复杂度 |
| **Skeptic 瓶颈** | 所有结论必须经过 skeptic signoff | 可能成为流程瓶颈 |
| **缺乏早期终止** | 无法在中途确认结论后提前结束 | 浪费计算资源 |

### 5.4 运行层面潜在问题

**基于代码分析的运行时风险：**

1. **Lease 过期竞争条件**
   - 如果 specialist 在 lease 过期前提交，但 broker 在过期后处理，可能导致状态不一致

2. **Action Chain 并发写入**
   - 多个 Agent 同时写入 action_chain.jsonl 可能导致行级冲突

3. **YAML 解析错误**
   - 多处使用 `yaml.safe_load` 但没有处理 YAML 格式错误

4. **路径遍历风险**
   - `_norm()` 函数只是替换反斜杠，没有规范化路径

---

## 六、综合评价

### 6.1 架构评价

**优势：**
- **严谨的审计设计**：action_chain.jsonl 的 append-only 设计确保全程可追溯
- **清晰的职责分离**：Agent 边界明确，避免能力重叠
- **强一致性保证**：SSOT 设计确保状态一致性
- **可扩展的知识系统**：BugCard/BugFull/SOP 三层知识架构

**劣势：**
- **复杂度过高**：对于简单调试场景，框架开销过大
- **学习曲线陡峭**：需要理解多层 Context、Lease 机制、状态机
- **平台绑定较深**：与 RenderDoc 工具链强耦合

### 6.2 工程评价

**代码质量：**
- 类型提示完善（Python 3.9+ 语法）
- 错误处理较为完善（但部分地方使用裸 `except Exception`）
- 文档详尽（几乎每个文件都有详细的 Markdown 说明）

**可维护性：**
- 模块化设计良好（utils、validators、schemas 分离）
- 配置与代码分离（platform_capabilities.json、framework_compliance.json）
- 但文件数量多，目录结构深，导航成本较高

### 6.3 实用性评价

**适用场景：**
- 复杂的 GPU 渲染问题诊断
- 需要多人协作/审计的调试场景
- 需要沉淀知识库的长期项目

**不适用场景：**
- 简单的单次调试任务
- 快速原型验证
- 资源受限的环境（Token 预算有限）

### 6.4 改进建议

1. **简化入门路径**
   - 提供 "快速模式"，跳过部分 Harness 检查
   - 提供交互式初始化向导

2. **增加异步支持**
   - 支持多个 specialist 并行执行
   - 异步 Lease 续期机制

3. **优化 Token 消耗**
   - 提供 Prompt 压缩选项
   - Context 缓存机制

4. **增强可观测性**
   - 提供流程可视化工具
   - 实时监控 Dashboard

5. **改进错误恢复**
   - 更细粒度的重试策略
   - 自动降级机制

---

## 七、运行后情况分析

### 7.1 预期运行行为

**正常流程：**
1. 用户提交 `.rdc` 文件和症状描述
2. Plan Phase 生成 `debug_plan`
3. Execution Phase 依次执行各 Agent
4. 最终输出 `report.md` 和 `visual_report.html`

**产物结构：**
```
cases/<case_id>/
├── case.yaml
├── case_input.yaml
├── inputs/
│   ├── captures/manifest.yaml
│   └── references/manifest.yaml
├── artifacts/
│   └── entry_gate.yaml
└── runs/<run_id>/
    ├── run.yaml
    ├── capture_refs.yaml
    ├── artifacts/
    │   ├── intake_gate.yaml
    │   ├── runtime_session.yaml
    │   ├── runtime_snapshot.yaml
    │   ├── ownership_lease.yaml
    │   ├── runtime_failure.yaml
    │   ├── fix_verification.yaml
    │   ├── run_compliance.yaml
    │   └── user_verdict.yaml
    ├── notes/
    │   └── hypothesis_board.yaml
    └── reports/
        ├── report.md
        └── visual_report.html
```

### 7.2 异常运行情况

**可能的阻塞场景：**

| 场景 | 阻断码 | 处理方式 |
|------|--------|----------|
| 缺少 .rdc | BLOCKED_MISSING_CAPTURE | 要求用户上传 |
| Reference 未就绪 | BLOCKED_MISSING_FIX_REFERENCE | 回到 Plan Phase |
| Specialist 超时 | BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT | Freeze run |
| Runtime 失败 | BLOCKED_RUNTIME_FAILURE_OPEN | 尝试恢复 |
| Agent 越权 | PROCESS_DEVIATION_MAIN_AGENT_OVERREACH | 记录偏差 |

### 7.3 性能预期

**时间开销估算：**
- Plan Phase：1-3 轮澄清，每轮 1-2 分钟
- Triage：30-60 秒
- 每个 Specialist：2-10 分钟（取决于问题复杂度）
- Skeptic Review：1-2 分钟
- Curator：1-2 分钟

**总预期时间：** 简单问题 5-10 分钟，复杂问题 30-60 分钟

---

## 八、总结

Debugger 框架是一个设计严谨、架构复杂的多智能体调试系统。其核心优势在于：

1. **严谨的审计机制**：确保每个决策都可追溯
2. **清晰的职责分离**：避免 Agent 越权和重复工作
3. **可扩展的知识系统**：支持知识沉淀和复用

但同时也存在复杂度过高、开销较大、学习曲线陡峭等问题。该框架更适合：
- 需要严格审计的企业级场景
- 复杂的 GPU 渲染问题诊断
- 需要长期维护知识库的项目

对于简单场景，建议考虑轻量级替代方案或提供 "快速模式" 简化流程。

---

## 九、全面改进空间分析（补充章节）

基于更深入的代码审查，以下是框架各维度的详细改进建议：

### 9.1 模型路由与资源配置改进

**当前问题：**
- 模型路由配置分散在 `model_routing.json` 和 `role_policy.json` 两个文件
- 缺乏动态模型降级机制（当首选模型不可用时）
- 没有 Token 预算管理和预警机制

**改进建议：**

| 优先级 | 改进项 | 具体措施 |
|--------|--------|----------|
| 高 | 统一模型路由 | 合并 `model_routing.json` 和 `role_policy.json` 为单一配置源 |
| 高 | 动态降级 | 实现 fallback_order 的自动执行逻辑 |
| 中 | Token 预算 | 添加 per-run Token 限制和实时用量追踪 |
| 中 | 成本估算 | 在 Plan Phase 预估总成本，超出预算时预警 |
| 低 | 模型性能基准 | 建立各模型在各 Agent 角色上的性能基准数据库 |

### 9.2 配置管理改进

**当前问题：**
- 配置分散在多个 JSON/YAML 文件
- 缺乏配置验证和版本兼容性检查
- 平台配置与框架核心耦合

**改进建议：**

```yaml
# 建议的统一配置结构
config/
  ├── v1/                    # 版本化配置
  │   ├── framework.yaml     # 框架核心配置
  │   ├── agents.yaml        # Agent 角色配置
  │   ├── models.yaml        # 模型路由配置
  │   └── platforms/         # 平台特定配置
  │       ├── claude-code.yaml
  │       └── codex.yaml
  └── schema/                # 配置 JSON Schema
      ├── framework.schema.json
      └── agent.schema.json
```

### 9.3 测试与验证体系改进

**当前缺失：**
- 没有单元测试覆盖 Harness 核心逻辑
- 缺乏集成测试验证完整工作流
- 没有性能基准测试

**建议测试体系：**

```
tests/
├── unit/                    # 单元测试
│   ├── test_harness_guard.py
│   ├── test_runtime_broker.py
│   └── test_validators/
├── integration/             # 集成测试
│   ├── test_full_workflow.py
│   ├── test_failure_recovery.py
│   └── test_multi_agent_handoff.py
├── fixtures/                # 测试数据
│   ├── sample.rdc
│   ├── sample_case/
│   └── sample_knowledge/
└── benchmarks/              # 性能基准
    ├── test_token_usage.py
    └── test_latency.py
```

### 9.4 可观测性与监控改进

**当前问题：**
- 缺乏实时监控 Dashboard
- 没有性能指标收集
- 错误追踪依赖文件日志

**改进建议：**

| 维度 | 当前状态 | 改进目标 |
|------|----------|----------|
| 指标收集 | 仅文件日志 | 结构化指标输出（Prometheus/OpenTelemetry） |
| 可视化 | 无 | Web Dashboard 展示运行状态 |
| 告警 | 无 | 关键错误实时通知 |
| 追踪 | 文件级 | 分布式追踪（OpenTelemetry Trace） |

**建议的监控指标：**
- Agent 调用延迟分布（P50/P95/P99）
- Token 消耗 per Agent/per Run
- Harness 检查点通过率
- Lease 获取/释放成功率
- Runtime 恢复成功率

### 9.5 知识管理改进

**当前问题：**
- 知识演进流程依赖手动触发
- 缺乏知识冲突检测
- BugCard 检索效率未优化

**改进建议：**

1. **自动化知识演进**
   ```python
   # 当前：手动触发
   # 改进：自动检测 compliant run 并生成 candidate
   class KnowledgeEvolutionPipeline:
       def on_run_compliant(self, run_id):
           candidate = self.auto_extract_knowledge(run_id)
           if self.validate_candidate(candidate):
               self.propose_to_shadow(candidate)
   ```

2. **向量检索支持**
   - 为 BugCard/BugFull 添加向量嵌入
   - 支持语义相似度检索，不仅依赖标签匹配
   - 实现 RAG（Retrieval-Augmented Generation）增强

3. **知识冲突检测**
   - 检测相互矛盾的 BugCard
   - 标记过时的 SOP
   - 自动提示知识库维护需求

### 9.6 安全性改进

**当前风险：**
- 路径遍历风险（`_norm()` 函数仅替换反斜杠）
- YAML 解析没有限制递归深度
- 没有输入文件大小限制

**改进建议：**

| 风险 | 改进措施 |
|------|----------|
| 路径遍历 | 使用 `pathlib.Path.resolve()` 规范化路径，限制在 workspace 目录 |
| YAML 炸弹 | 设置 YAML 解析的递归深度限制和文件大小限制 |
| 文件大小 | 限制 `.rdc` 文件大小（如 500MB），超大文件需要显式确认 |
| 命令注入 | 所有外部命令调用使用参数列表而非字符串拼接 |
| 敏感信息 | 添加 PII/凭证检测，防止意外记录敏感信息 |

### 9.7 性能优化改进

**当前瓶颈：**
- 同步阻塞的 Harness 检查点
- 频繁的 YAML 文件 I/O
- 没有缓存机制

**优化建议：**

1. **异步化改造**
   ```python
   # 当前：同步阻塞
   def run_dispatch_readiness(...): ...
   
   # 改进：异步非阻塞
   async def run_dispatch_readiness(...): ...
   ```

2. **缓存层引入**
   - 缓存频繁读取的 spec 对象
   - 缓存 action_chain 的内存视图
   - 实现写缓冲，批量写入磁盘

3. **并行执行**
   - 支持多个 specialist 并行执行
   - 并行化独立的 Harness 检查点

### 9.8 开发者体验改进

**当前问题：**
- 调试困难，缺乏详细的错误上下文
- 没有交互式开发工具
- 文档分散

**改进建议：**

| 改进项 | 描述 |
|--------|------|
| Debug Mode | 添加 `--debug` 模式，输出详细的中间状态 |
| CLI 工具 | 提供统一的 `rdc-cli` 命令行工具 |
| REPL 环境 | 提供交互式调试环境 |
| 文档聚合 | 生成统一的 HTML 文档站点 |
| VS Code 插件 | 提供语法高亮、Schema 验证、跳转支持 |

### 9.9 平台适配改进

**当前问题：**
- 平台适配代码分散
- 新增平台需要修改多处文件
- 平台能力检测不够自动化

**改进建议：**

```python
# 平台适配抽象层
class PlatformAdapter(ABC):
    @abstractmethod
    def detect_capabilities(self) -> PlatformCapabilities:
        pass
    
    @abstractmethod
    def render_config(self, framework_config: dict) -> PlatformConfig:
        pass
    
    @abstractmethod
    def inject_hooks(self, hooks: list[Hook]) -> None:
        pass

# 自动检测和适配
adapter = PlatformAdapterFactory.create_for_current_env()
capabilities = adapter.detect_capabilities()
```

### 9.10 容错与恢复改进

**当前限制：**
- 只有 `TOOL_RUNTIME_FAILURE` 允许恢复
- 恢复逻辑硬编码在 `runtime_broker.py`
- 缺乏优雅降级策略

**改进建议：**

1. **分级恢复策略**
   ```yaml
   recovery_policies:
     TOOL_RUNTIME_FAILURE:
       max_attempts: 3
       backoff: exponential
       fallback: degraded_mode
     
     TOOL_CONTRACT_VIOLATION:
       max_attempts: 1
       fallback: skip_and_notify
     
     INVESTIGATION_INCONCLUSIVE:
       max_attempts: 0
       fallback: escalate_to_human
   ```

2. **检查点机制**
   - 在关键阶段保存完整状态
   - 支持从任意检查点恢复
   - 实现"时间旅行"调试

3. **优雅降级**
   - 当 specialist 不可用时降级到简化版本
   - 当模型不可用时切换到备用模型
   - 保持核心功能可用

### 9.11 用户体验改进

**当前问题：**
- 用户需要理解复杂的框架概念
- 缺乏进度可视化
- 错误信息过于技术化

**改进建议：**

| 场景 | 当前体验 | 改进目标 |
|------|----------|----------|
| 提交问题 | 需要准备多个文件 | 支持自然语言描述，自动提取信息 |
| 等待结果 | 黑盒等待 | 实时进度条和中间结果展示 |
| 查看报告 | 阅读 Markdown | 交互式可视化报告 |
| 理解结论 | 技术术语 | 分层展示（摘要/详细/技术） |

### 9.12 生态集成改进

**当前局限：**
- 仅支持 RenderDoc
- 缺乏 CI/CD 集成
- 没有 API 接口

**改进建议：**

1. **多工具支持**
   - 支持 PIX、Nsight Graphics 等其他 GPU 调试工具
   - 抽象工具接口，实现工具无关的 Agent 逻辑

2. **CI/CD 集成**
   ```yaml
   # GitHub Actions 示例
   - uses: rdc-framework/action@v1
     with:
       capture-path: './test-captures/'
       baseline-path: './baselines/'
       fail-on-regression: true
   ```

3. **REST API**
   - 提供异步任务提交接口
   - 支持 Webhook 回调
   - 实现查询和下载接口

### 9.13 数据驱动改进

**当前缺失：**
- 没有收集运行数据用于改进
- 缺乏 A/B 测试框架
- 没有性能回归检测

**改进建议：**

1. **匿名数据收集**
   - Agent 调用成功率
   - 常见错误模式
   - 用户满意度反馈

2. **持续优化**
   - 基于数据优化 Prompt
   - 自动调整模型路由
   - 识别需要新增 Agent 的场景

---

## 十、改进优先级矩阵

| 改进维度 | 影响范围 | 实施难度 | 优先级 | 预期收益 |
|----------|----------|----------|--------|----------|
| 安全性加固 | 高 | 低 | P0 | 防止安全事故 |
| Token 预算管理 | 高 | 低 | P0 | 控制成本 |
| 测试体系 | 高 | 中 | P1 | 提高稳定性 |
| 异步化改造 | 高 | 高 | P1 | 性能提升 |
| 可观测性 | 中 | 中 | P1 | 运维效率 |
| 知识管理增强 | 中 | 中 | P2 | 调试效果 |
| CI/CD 集成 | 中 | 低 | P2 | 易用性 |
| 多工具支持 | 高 | 高 | P3 | 生态扩展 |
| REST API | 中 | 中 | P3 | 集成能力 |

---

## 十一、实施路线图建议

### 第一阶段（1-2 个月）：基础加固
- 安全性加固（路径遍历、YAML 限制）
- Token 预算管理
- 基础测试覆盖

### 第二阶段（2-3 个月）：性能与稳定性
- 异步化改造
- 缓存层引入
- 可观测性建设

### 第三阶段（3-4 个月）：智能化增强
- 知识管理增强
- 自动模型路由
- 智能降级策略

### 第四阶段（4-6 个月）：生态扩展
- CI/CD 集成
- REST API
- 多工具支持

---

## 附录：核心文件索引

| 文件 | 用途 |
|------|------|
| `common/AGENT_CORE.md` | 全局硬约束入口 |
| `common/docs/intake/README.md` | Intake Contract 定义 |
| `common/docs/runtime-coordination-model.md` | 运行协调模型 |
| `common/docs/model-routing.md` | 模型路由策略 |
| `common/docs/truth_store_contract.md` | 真相存储契约 |
| `common/hooks/utils/harness_guard.py` | Harness 核心实现 |
| `common/hooks/utils/runtime_broker.py` | Runtime Broker 实现 |
| `common/hooks/utils/run_compliance_audit.py` | 合规审计实现 |
| `common/hooks/utils/intake_gate.py` | Intake Gate 实现 |
| `common/hooks/utils/spec_store.py` | Spec 存储管理 |
| `common/hooks/validators/skeptic_signoff_checker.py` | Skeptic 签署验证 |
| `common/config/platform_capabilities.json` | 平台能力配置 |
| `common/config/model_routing.json` | 模型路由配置 |
| `common/agents/*.md` | Agent Prompt 定义 |

---

*报告生成时间：2026-04-02*
*研究范围：debugger/common/ 目录下的全部核心文件*
*补充分析：配置管理、模型路由、安全性、测试体系、可观测性、知识管理、性能优化、开发者体验、平台适配、容错恢复、用户体验、生态集成、数据驱动*
