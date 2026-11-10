# 三方 Agent 开发文档

> 文档版本：1.0.0
>
> 这份文档说明如何使用脚手架创建、配置、发布和排查三方 Agent。

## 三件套职责

## 1. 这份手册给谁用

这份手册面向“要交付一个外置专属 Agent 的用户”，不是平台源码说明。你只需要会改 YAML 和 Python 函数，就可以按本手册从脚手架开始搭一个能挂载、能出现在员工列表、能聊天、能按需绑定平台能力的专属 Agent。

你最终交付的是一个插件目录，不是一个单文件脚本。每个插件固定有下面三件套；只有需要补齐平台未支持文件格式时，才额外加入第 21 节的解析器目录：

```text
your_external_agent/
  manifest.yaml
  bootstrap.py
  agent_definition.py
```

三件套职责必须分开：

| 文件 | 必填 | 放什么 | 不放什么 |
|------|------|--------|----------|
| `manifest.yaml` | 是 | 员工身份、插件身份、展示信息、人设详情、快捷问题 | 意图、能力、记忆、计划、护栏、追问、审批、Trace、输出编排 |
| `bootstrap.py` | 是 | `register_specialized_agent(context)` 启动入口，加载并委托 `agent_definition.py` | 数据库写入、模型调用、业务运行逻辑 |
| `agent_definition.py` | 是 | `create_external_agent(context)` SDK 声明：意图、Memory、CapabilityAsset、Plan、Guardrail、Followup、Output、Pipeline、Hook | 重复写员工身份证字段 |

交付方式：在在线开发完成后保存并发布，或将三件套打包为 zip 上传。平台只会从已校验并激活的受控版本加载 Bundle，不扫描本机或服务器目录；加载时导入 `entrypoint`，调用 `register_specialized_agent(context)`，最终由 SDK 调用 `context.register_bundle(bundle)` 完成注册。

### 1.1 已有二开员工的代码包导出与更新

上传或在线开发的二开员工可以在员工列表的“更多”菜单中使用“导出代码包”和“更新代码包”；内置员工不提供这两个入口。导出的是该员工当前正在使用的正式 Revision，不包含未保存工作区、聊天历史、平台后来追加的工具/技能/解析器/委派配置、模型凭证或其他运行时秘密；`wheels/` 等二进制文件会原样保留。

“更新代码包”只更新用户明确选中的这个员工：系统校验 `plugin_key`、`agent_key`、当前 Revision 和绑定/解析配置版本，保留员工 ID、归属、模型参数、平台来源绑定、历史记录和已发布快照。普通“上传代码包”仍然创建新的共享包或新员工，不会覆盖已有员工；已删除员工也不会通过重新上传自动恢复。更新成功后不会自动对外发布，需重新校验并按平台发布流程发布；代码内容变化时应提升包版本号，同版本仅重新打包而内容等价可以复用原 Revision。

导出的 ZIP 不能用于绕过平台配置：包内声明继续是包来源，平台追加配置由平台保存；更新失败或并发版本冲突会保留原员工和原版本，可关闭弹窗后重新读取再试。随包 Skill/MCP 模板如果被多个员工或其他能力绑定共用，平台会拒绝单员工更新，避免改一个包影响其他员工；此时应先拆分共享模板或统一升级所有使用者。

运行时如果调用方有额外结构化材料，例如页面 JSON、文档 JSON、外部业务对象或前端当前状态，统一放在请求体顶层 `context` 字段。Debug 调试流、Workspace 对话流和 OpenAPI invoke 都走这一入口；页面生成专家会优先读取其中的 `page_json` / `current_page_schema`，专项子编排 handler 里通过 `context.context` 读取它，平台不规定内部结构。

首版已验收的生产路径：外置三件套、SDK、`generic` / `append`、文档分析专家真实 Run、公共 Intent / Intent Family / Plan、Output Pipeline、SSE 与历史消息块重建。`replace` 仅保留注册期 / builder-local 协议，不作为首版真实 E2E 能力。

## 第一次搭建顺序

## 3. 第一次填写顺序

先不要想 SDK 方法名。用户搭建一个专属 Agent，本质上是在回答 7 个问题：

| 顺序 | 先回答什么问题 | 你要判断什么 | 判断结果会影响什么 |
|------|----------------|--------------|--------------------|
| 1 | 这个员工是谁？ | 员工 ID、员工名、职责、人设是否清楚 | 决定员工能不能被平台识别、展示、同步 |
| 2 | 这个员工是不是只换人设？ | 它是否只需要普通聊天、问答、分析、生成 | 如果是，只走最小路径，不需要意图族 |
| 3 | 它是否多了一类专门任务？ | 比如“文档分析”“合同审查”“工单分类”是不是公共意图没有的新任务 | 如果是，需要新增一个意图族 |
| 4 | 这个专门任务命中后怎么回答？ | 是普通文本回答，还是要生成 JSON、报告、文件引用、工作流等机器产物 | 决定是普通文本输出，还是绑定子编排 |
| 5 | 这个插件是否需要 Plan？ | 是否要启用 Plan 模块；新增意图族 / intent 是否会参与 Plan；任务是否涉及多步骤分析、能力选择、风险审查、结构化产物校验 | 决定是否启用 Plan 模块、是否给新增意图族 / intent 补 `planner_hint` |
| 6 | 这个任务是否要用平台能力？ | 是否要调用已有 Skill、Tool、MCP、Native Capability | 决定是否绑定能力中心的 SDK 绑定 ID |
| 7 | 这次运行是否要带额外上下文？ | 是否需要把页面 JSON、文档 JSON、外部业务对象或前端当前状态传给专项 | 决定调用接口时是否传顶层 `context`，以及 handler 内怎么读 `context.context` |

把这 7 个问题想清楚后，再写代码。不要一上来就看所有 SDK 方法，否则会把“能用的选项”误当成“都必须填”。

新建员工或生成人设时，应配套生成并保存“执行提示词” `system_prompt` 和“被委派说明” `delegation_description`，提前为以后被其他员工委派准备说明，不等实际委派时才补写。直接在 manifest 的 `persona.delegation_description` 落盘，或在 `register()` 前调用 `with_persona(system_prompt=..., delegation_description=...)`；包激活时同步到平台员工人设，不能只在回复中给出文案。说明包含适用任务、所需输入、预期输出和不适用范围，trim 后最多 2000 字符；已有准确说明可复用，平台手工修改值在升级/回滚时保留。它不等于 `delegation_agent_ids`；后者只表示本员工可以委派给谁，即使没有向外委派目标也应准备自己的说明。旧包不填不覆盖，显式空字符串清空包维护值；缺说明不阻断普通聊天，但不会成为可委派候选。源码保存、包激活和员工对外更新发布是不同步骤，只能核对工作区时明确写“源码已保存，平台生效待激活核验”。详细写法和完成标准见 manifest 字段说明与 SDK 的“被委派说明与人设生成”。

### 3.1 先选搭建路线

下面按用户目标选路线。先找到你属于哪一行，再去对应章节填字段。

| 你的目标 | 先选哪条路线 | 是否需要意图族 | 是否涉及 Plan | 是否需要子编排 | 是否需要能力 |
|----------|--------------|----------------|--------------|----------------|--------------|
| 只做一个有人设的普通问答 / 分析员工 | 最小普通员工 | 不需要 | 通常不涉及 Plan | 不需要 | 通常不需要 |
| 多识别一种专项任务，但仍然文本回答 | 专项文本员工 | 需要 | 复杂分析时可启用 Plan 模块；若参与 Plan 必须补 `planner_hint` | 不需要 | 需要外部能力时才加 |
| 命中专项任务后要生成 JSON、报告、工作流、文件引用 | 结构化产物员工 | 需要 | 建议启用 Plan 模块；参与 Plan 的新增意图必须补 `planner_hint` | 需要 | 需要外部生成 / 校验能力时加 |
| 命中任务后要调用平台 Skill / Tool / MCP | 能力调用员工 | 可能需要 | 建议启用 Plan 模块；参与 Plan 的新增意图必须补 `planner_hint` | 不一定 | 需要 |
| 完全不用平台公共任务分类，全部自己定义 | 私有路由员工 | 需要完整任务集合 | 视任务复杂度 | 视输出类型 | 视任务需要 |

路线说明：

| 路线 | 先做什么 | 后做什么 | 不要一开始做什么 |
|------|----------|----------|--------------------|
| 最小普通员工 | 先填员工身份、人设、普通文本聊天 | 跑通后再决定要不要加能力或意图族 | 不要写意图族、子编排、Hook |
| 专项文本员工 | 先定义一个意图族，说明它管什么、不管什么 | 如果这些新增意图会参与 Plan，给新增意图族 / intent 补 `planner_hint` | 不要把输出策略写成子编排 |
| 结构化产物员工 | 先定义意图族，再决定哪个 intent 要产物 | 再把该 intent 绑定到子编排，并声明结构化输出 | 不要只写意图族却忘记子编排 |
| 能力调用员工 | 先确认能力中心里有可用能力，并复制 SDK 绑定 ID | 再把能力写进 `planner_hint` 和能力绑定 | 不要直接写能力名称或 ref_id |
| 私有路由员工 | 先完整列出所有意图族和 intent | 再做 builder-local 验证 | 不要承诺首版真实平台 Run E2E |

### 3.2 什么时候需要意图族

意图族就是 `Intent Family`，中文统一叫“意图族”。它不是计划、不是工作流、不是模块，而是一组相关 intent 的分类容器。用户可以把它理解成“这个员工多出来的一类专门任务分类”。如果这个员工只是换人设，比如“更像法务”“更像客服”“更像项目经理”，但用户的问题仍然是普通问答、分析、生成，那么不需要意图族。

需要意图族的情况：

| 情况 | 例子 | 为什么需要 |
|------|------|------------|
| 平台公共意图不能准确区分你的专项任务 | 用户说“审这份合同”，它不是普通聊天，也不是泛泛分析 | 需要让平台知道这是“合同审查”任务 |
| 同一个员工有几个相关专项 intent | 文档总结、文档风险审查、文档结构提取 | 需要把它们放进同一个“文档分析”意图族 |
| 命中后要走不同输出路径 | “总结文档”走文本，“生成工作流”走 JSON 产物 | 需要每个任务声明自己的输出策略 |
| 需要更稳定的弱模型识别 | 用户表达可能很模糊 | 需要正例、反例、边界、触发词帮助识别 |

不需要意图族的情况：

| 情况 | 做法 |
|------|------|
| 只是普通聊天 / 问答 / 分析 / 生成 | 保持最小普通员工 |
| 只是换系统提示词和回答风格 | 写好人设即可 |
| 只是想让员工可以使用某个能力 | 绑定能力即可，不一定需要意图族 |

### 3.3 做意图族时必须连续决定三件事

只写一个意图族还不够。每个意图族至少要连续决定三件事：

| 决策 | 要回答的问题 | 如果不决定会怎样 |
|------|--------------|------------------|
| 意图边界 | 这个意图族管什么？不管什么？ | 弱模型容易把普通聊天误判成专项任务 |
| 输出方式 | 命中某个任务后，是文本回答还是生成机器产物？ | 用户不知道该填普通输出还是子编排 |
| Plan 口径 | 是否启用 Plan 模块？这个新增意图族 / intent 是否会参与 Plan？ | 如果新增意图会参与 Plan 但不补 `planner_hint`，Plan 只能按通用规则猜 |

意图族最少要写清：

| 内容 | 用途 |
|------|------|
| 意图族 key | 给平台稳定识别这组 intent |
| 意图族名称 | 给人看 |
| 意图族说明 | 告诉模型这组 intent 是什么 |
| 意图边界 | 告诉模型哪些算，哪些不算 |
| 回退任务 | 模型不确定时落到哪个任务 |
| 具体任务列表 | 每个任务分别怎么识别、怎么输出 |

### 3.4 什么时候启用 Plan 模块，什么时候补 `planner_hint`

不要把 Plan 相关动作混成一句话。这里分成三件事：是否启用 Plan 模块、是否补 `planner_hint`、本次运行是否实际参与 Plan。

先分清三层：

| 问题 | 正确口径 |
|------|----------|
| 能不能声明 `.use_plan()` | SDK 配置层是否允许启用 Plan 模块。generic、append、replace 都可以声明 |
| 要不要补 `planner_hint` | 外置新增意图族 / intent 如果会参与 Plan，必须补。至少在 family 或关键 intent 上补 |
| 本次运行是否实际参与 Plan | 由运行时根据用户输入、意图、能力、输出策略决定；声明了 `.use_plan()` 不等于每次运行都进入 Plan |

明确规则：

| 情况 | Plan 模块 | `planner_hint` |
|------|-----------|----------------|
| 只用 generic 公共意图，简单问答 / 闲聊 / 普通文本回答 | 通常不用启用 | 不需要 |
| 只用 generic 公共意图，但任务经常需要能力选择、多步骤分析或结构化产物 | 可以启用 | 不强制；公共意图有默认语义，但可按需要补运行配置 |
| 新增了外置意图族 / intent，但这些新增项不参与 Plan，只做简单文本分类 / 回答 | 不必启用 | 不必填 |
| 新增了外置意图族 / intent，并且这些新增项会参与 Plan | 应启用 Plan 模块或确保运行时会使用 Plan | 必填，至少 family 或关键 intent 其中一层要有 `planner_hint` |
| intent 绑定能力调用、结构化产物、风险审查、多步骤执行 | 建议启用 Plan 模块 | 必填或强烈建议按关键 intent 补齐 |

`planner_hint` 要表达的是：这个新增专项语义进入 Plan 时，Plan 应该知道什么。它不是“启用 Plan”，也不是手写执行步骤。

最重要的组合规则如下，三个字段必须按任务真实依赖关系一起填写：

| 任务情况 | `needs_capability` | `candidate_capabilities` | 能力绑定 |
|----------|--------------------|--------------------------|----------|
| 不需要外部能力，平台已有附件内容或模型即可完成 | `False` | `[]` | 不绑定，或只绑定不参与本任务的其他能力 |
| 有能力更好，但没有也能完成 | `None` | 填真实可用的 SDK 绑定 ID | `with_capability_asset(..., required=False)` |
| 没有能力就无法完成 | `True` | 必须填真实可用的 SDK 绑定 ID | `with_capability_asset(..., required=True)` |

这里有两个容易混淆的开关：

- `needs_capability` 控制本次任务规划时是否倾向走能力调用：`False` 不要求能力，`None` 由平台结合上下文判断，`True` 表示任务依赖能力。
- `with_capability_asset(..., required=...)` 控制能力依赖缺失时是否阻断插件：`required=False` 只表示能力可以缺失，不表示 Plan 必须调用它。

因此，`needs_capability=True` 不能和空的 `candidate_capabilities=[]` 一起使用；这会让 Plan 被要求调用能力，却没有可执行候选。只依靠平台已装配的附件解析结果进行文档分析时，应使用 `needs_capability=False`、`candidate_capabilities=[]`；有一个可选的外部整理能力时，才使用 `None` 加候选能力。

| `planner_hint` 字段 | 用途 |
|----------------------|------|
| `needs_capability` | 提示这个 intent 是否可能需要能力 |
| `candidate_capabilities` | 提示候选 SDK 绑定 ID |
| `plan_template_key` | 提示用哪类公共 Plan 模板 |
| `success_criteria` | 告诉 Plan 什么叫完成得好 |
| `risk_level` | 告诉 Plan 这个任务风险高低 |

简单理解：意图族负责“识别用户要做什么”；Plan 负责“本次运行如果进入规划阶段，怎么更稳地完成”；`planner_hint` 负责“外置新增意图进入 Plan 时，不要让 Plan 只靠通用规则猜”。

### 3.5 做意图族时什么时候绑定子编排

子编排只在“命中某个任务后要生成机器产物”时需要。普通文本回答不需要子编排。

| 命中后要什么结果 | 是否需要子编排 | 输出策略怎么理解 |
|------------------|----------------|------------------|
| 一段普通回答 | 不需要 | 使用普通文本输出 |
| Markdown 分析报告 | 视复杂度而定 | 简单可文本，复杂报告建议子编排 |
| JSON 配置 / 工作流 / 页面 schema | 需要 | 任务输出策略要指向一个子编排 key |
| 文件引用 / 二进制引用 | 需要 | 子编排负责生成或引用产物 |
| 多步骤产物生成 | 需要 | 每一步是一个子步骤 |

绑定关系是这样的：

```text
具体任务
  -> 输出策略
  -> 子编排 key
  -> 子步骤列表
  -> 最终结构化产物
```

用户要记住一句话：如果某个任务命中后要生成结构化产物，就把这个任务的输出策略指向一个真实存在的子编排 key，然后在后面定义同名子编排。不要把输出策略写成字面量 `pipeline`，除非你真的定义了一个 key 就叫 `pipeline` 的子编排。

### 3.6 做意图族时什么时候绑定能力

能力不是“意图族必填项”。只有当 intent 需要调用平台能力时才绑定。现在有两种用户可见的能力挂载方式：一种是绑定能力中心已有能力，另一种是把 Skill / MCP 模板随插件包一起带进来。

| 任务是否需要能力 | 怎么判断 | 做法 |
|------------------|----------|------|
| 不需要 | 只靠模型回答就够 | 不绑定能力 |
| 可有可无 | 有能力更准，没有也能回答 | 绑定可选能力 |
| 必须有 | 没有能力就无法完成任务 | 绑定必需能力 |
| 子编排步骤需要能力 | 某一步要由平台产物型能力执行 | 绑定产物型能力 |

两种能力挂载路线：

| 路线 | 用户填什么 | 适合什么情况 | 使用后会怎样 |
|------|------------|--------------|--------------|
| 绑定已有能力 | 能力中心列表里的 `SDK 绑定 ID` | 能力已经在平台存在，用户只需要让这个员工使用它 | SDK 直接按 `capability_id` 绑定；required 缺失 / 未授权会阻断 |
| 随包能力模板 | `skill:<template_key>` 或 `mcp:<template_key>/<remote_tool_name>` | 插件自己携带 Skill / MCP 定义，用户不想先手动去能力中心创建 | 平台加载插件时先把模板投影成原生能力，再解析成 `capability_id` 绑定 |

不要让用户填数据库内部 ID、能力名称、ref_id 或内部对象引用。已有能力填 `SDK 绑定 ID`；随包能力填模板引用。

### 3.7 从用户目标映射到后面的章节

| 用户现在要做什么 | 下一步看哪里 |
|------------------|--------------|
| 先把员工跑起来 | 继续看本节下面的第一遍填写字段 |
| 想新增“文档分析 / 合同审查”这类任务 | 看第 4.2 |
| 想完全自管任务集合 | 看第 4.3，但不要作为首版生产承诺 |
| 想知道 manifest 每个字段怎么填 | 看第 6 节 |
| 想知道每个封装方法的参数 | 看第 9 节 |
| 想生成 JSON / 报告 / 工作流 | 看第 13、14 节 |
| 想确认哪些能力本版不做 | 看第 18 节 |

第一次不要从 `append`、Pipeline、Hook 开始。正确顺序是：先让一个最小员工成功加载和普通聊天，再逐步加专项意图、能力、结构化产物。下面这张表就是用户实际填写顺序。

| 第几步 | 你要做什么 | 改哪个文件 | 必填吗 | 填完后会发生什么 |
|--------|------------|------------|--------|------------------|
| 1 | 给员工起唯一 ID | `manifest.yaml` 的 `agent_key` | 是 | 新建时建议按 `ext_{agent_slug}_{timestamp_id}` 生成；平台用它创建 / 同步同一个员工；后续升级不要改 |
| 2 | 给插件起唯一 ID | `manifest.yaml` 的 `plugin_key` | 是 | 新建时建议用 `agent_key + "_plugin"`；平台用它判断插件冲突和输出诊断；后续升级不要改 |
| 3 | 写员工显示名和职责 | `agent_name`、`agent_description` | 是 | 员工列表和详情能看懂这个员工做什么 |
| 4 | 写人设 | `persona.system_prompt` | 是 | 普通正文会按这段人设回答；不填不能注入可用员工 |
| 5 | 写展示信息 | `profile.position`、`profile.opening_message`、`profile.placeholder`、`profile.empty_state_hint` | 否 | 员工入口更清楚；不填也能加载 |
| 6 | 写快捷问题 | `suggested_questions` | 否 | 员工入口显示最多 3 个快捷问题 |
| 7 | 保持启动入口 | `bootstrap.py` | 是 | 平台能找到 `register_specialized_agent(context)` 并转发到 `agent_definition.py` |
| 8 | 创建 builder | `agent_definition.py` 的 `create_external_agent(context)` | 是 | 后面才能链式声明运行模块 |
| 9 | 先用通用意图 | `agent_definition.py` 的 `.use_generic_intent()` | 推荐 | 不用自己写意图分类，先复用平台已有问答 / 分析 / 生成能力 |
| 10 | 先用文本输出 | `agent_definition.py` 的 `.output_text()` | 推荐 | 先走普通聊天正文，不进入结构化产物链 |
| 11 | 最后提交注册 | `agent_definition.py` 的 `.register()` | 是 | 没有这一步，平台会认为插件没有注册 Bundle |

### 3.8 第一遍只填这些字段

第一遍目标只有一个：插件能被平台加载，员工能出现在列表，并能普通聊天。不要在第一遍就写 `append`、能力、Pipeline、Hook。

| 文件 | 字段 / 方法 | 必填 | 怎么填 | 不填 / 填错会怎样 |
|------|-------------|------|--------|--------------------|
| `manifest.yaml` | `protocol_version` | 是 | 固定写 `"1"` | 版本不兼容或 manifest 校验失败 |
| `manifest.yaml` | `sdk_api_version` | 是 | 固定写 `"1"` | SDK API 不兼容 |
| `manifest.yaml` | `platform_version` | 是 | 先保留 `">=0.1.0"` | 当前主要用于兼容声明和审计 |
| `manifest.yaml` | `agent_key` | 是 | 推荐 `ext_{agent_slug}_{timestamp_id}`，例如 `ext_contract_review_1784532645a7` | 冲突会注册失败；升级同一员工不要改 |
| `manifest.yaml` | `agent_name` | 是 | 用户看到的员工名，例如 `合同审查专家` | 员工列表不可读 |
| `manifest.yaml` | `agent_description` | 是 | 一句话职责，例如 `审查合同风险并给出修改建议` | 员工职责不清楚 |
| `manifest.yaml` | `plugin_key` | 是 | 推荐 `agent_key + "_plugin"`，例如 `ext_contract_review_1784532645a7_plugin` | 冲突会注册失败；升级同一插件不要改 |
| `manifest.yaml` | `version` | 是 | 新建例如 `"0.1.0"`；更新时手动提升 | 加载态和审计缺版本；更新包不提升版本会难以审计 |
| `manifest.yaml` | `entrypoint` | 是 | 通常固定 `bootstrap.py` | 平台找不到启动入口 |
| `manifest.yaml` | `enabled` | 是 | 布尔值 `true`，不是字符串 `"true"` | `false` 不参与加载；写错类型会失败 |
| `manifest.yaml` | `persona.system_prompt` | 是 | 写清“员工是谁、负责什么、边界是什么” | 不会同步为可用员工 |
| `bootstrap.py` | `register_specialized_agent(context)` | 是 | 保持脚手架默认转发 | 缺失会加载失败 |
| `agent_definition.py` | `create_external_agent(context)` | 是 | 第一行创建 builder | 后续 SDK 方法无法调用 |
| `agent_definition.py` | `.use_generic_intent()` | 推荐 | 第一遍固定保留 | 不写也会默认 generic，但显式写更清楚 |
| `agent_definition.py` | `.output_text()` | 推荐 | 第一遍固定保留 | 不写也会默认文本，但显式写更清楚 |
| `agent_definition.py` | `.register()` | 是 | 必须最后调用 | 不调用会报 `bundle_not_registered` |

### 3.8.1 `agent_key` / `plugin_key` 推荐生成规则

这两个 key 是插件包自己声明的稳定身份，不是平台自动分配的数据库 ID。平台只做唯一性和冲突校验；下面规则是给用户、脚手架或模型生成 manifest 时使用的参考规则。

推荐格式：

```yaml
agent_key: ext_{agent_slug}_{timestamp_id}
plugin_key: ext_{agent_slug}_{timestamp_id}_plugin
version: "0.1.0"
```

字段含义：

| 字段 | 怎么填 | 示例 | 说明 |
|------|--------|------|------|
| `ext_` | 建议固定 | `ext_` | 表示这是外置插件，方便管理员识别 |
| `agent_slug` | 用小写英文、数字、下划线描述员工用途 | `contract_review` | 只用于可读性，不保证唯一 |
| `timestamp_id` | 当前 Unix 时间戳 + 随机后缀 | `1784532645a7` | 建议 10 位秒级 Unix 时间戳 + 2 位小写字母或数字随机后缀 |
| `agent_key` | `ext_` + 用途 + 时间戳短 ID | `ext_contract_review_1784532645a7` | 表示“这是哪个专项员工” |
| `plugin_key` | `agent_key` + `_plugin` | `ext_contract_review_1784532645a7_plugin` | 表示“这个员工由哪个插件实现” |
| `version` | 语义化版本号 | `"0.1.0"` | 新建可从 `"0.1.0"` 开始；更新时手动提升 |

使用规则：

- 新建一个插件时，让模型按上方格式生成一组新的 `agent_key` / `plugin_key`。
- 更新同一个插件时，`agent_key` 和 `plugin_key` 必须保持不变，只改 `version`，例如 `"0.1.0"` 升到 `"0.1.1"`。
- 复制旧插件改成新插件时，必须重新生成 `timestamp_id`，否则平台会判定为重复或冲突。
- 这个 ID 只是降低冲突概率的参考，不是安全凭据，也不是权限边界。

### 3.9 第二遍再按需求加模块

最小版加载成功后，再按下面顺序逐个加模块。每加一个模块都先验证一次，不要一次把全部模块打开。

| 加第几类 | 你要增加什么 | 加哪个方法 | 先决条件 | 验证重点 |
|----------|--------------|------------|----------|----------|
| 1 | 记忆 | `.use_memory()` | 员工需要读取平台记忆上下文 | 插件不能自己读写记忆库 |
| 2 | 已有平台能力 | `.with_capability_asset("SDK 绑定 ID")` | 已在能力中心复制 SDK 绑定 ID | required 能力缺失 / 未授权会阻断运行 |
| 3 | 随包能力模板 | `.with_capability_template("skill:...")` / `.with_capability_template("mcp:.../...")` | 插件目录已有 `capabilities/skills` 或 `capabilities/mcp` 模板 | 模板引用能否解析；required 模板缺失会阻断 |
| 4 | Plan 配置 | `.use_plan(...)` 或 `planner_hint(...)` | 需要启用 Plan 模块，或外置新增意图族 / intent 会参与 Plan | `plan_template_key` 枚举是否正确；参与 Plan 的新增 family / intent 是否补了 `planner_hint` |
| 5 | 追加专项意图 | `.use_append_intent(families=[...])` | generic 已跑通，确实需要新增意图族 | `family.key` 不覆盖公共 family，`fallback_intent` 指向当前 intent |
| 6 | 结构化输出 | `.output_structured(...)` | 需要 JSON / Markdown / 文件引用等机器产物 | `kind`、`schema`、`schema_version` 是否清楚 |
| 7 | Output Pipeline | `.pipeline_step(...)` + `.output_pipeline(...)` | intent 的 `output_policy` 要指向 pipeline key | `output_policy` 不能误写成 `pipeline`；step 必须有 handler 或产物型能力 |
| 8 | 护栏 / 追问 / 治理 | `.register_guardrail(...)`、`.register_followup(...)`、`.use_governance()` | 平台已有对应策略或治理需求 | slot、guardrail_key、strategy 是否真实存在 |
| 9 | 审批沙箱 / Trace / Hook | `.use_approval_sandbox()`、`.register_trace_builder(...)`、`on_*` | 高级场景；先完成结构化输出 | 首版没有真实审批确认 / 拒绝，也不验收完整 Trace envelope |

### 3.10 用户最容易填错的顺序

| 错误顺序 | 为什么错 | 正确做法 |
|----------|----------|----------|
| 先写 `.use_append_intent(...)`，还没跑通 generic | 错误点太多，不知道是插件加载错还是意图声明错 | 先 `generic + output_text + register` 跑通 |
| 先写 `output_policy="workflow_pipeline"`，但没注册 `.output_pipeline(key="workflow_pipeline")` | `output_policy` 找不到对应 pipeline | 先注册同名 pipeline，或先用 `text_only` |
| `.register()` 后面继续写 `.with_capability_asset(...)` | 注册后 Bundle 已提交，不能再变更 | 所有声明都写在 `.register()` 前 |
| 把 `memory` 写进 `.with_capability_asset(...)` | Memory 不是 CapabilityAsset | 记忆只能用 `.use_memory()` |
| 在 manifest 里写 `intent`、`memory`、`output` | manifest 只写员工是谁，不写怎么运行 | 运行编排统一写到 `agent_definition.py` |

最小版跑通后，再按需要加模块。不要一次把所有能力都堆上去。

| 你想增加什么 | 加哪句 | 什么时候再加 |
|--------------|--------|--------------|
| 让员工使用平台记忆 | `.use_memory()` | 员工需要记住用户 / 项目上下文时 |
| 让员工能调用已有能力 | `.with_capability_asset("SDK 绑定 ID")` | 你已经在能力中心复制了 `SDK 绑定 ID`，并确认能力可用时 |
| 让插件随包带入 Skill / MCP 能力 | `.with_capability_template("skill:文档模板名")` 或 `.with_capability_template("mcp:服务模板名/工具名")` | 能力定义放在插件目录的 `capabilities/` 下，希望加载插件时自动投影成平台能力时 |
| 让员工多识别一种专项任务 | `.use_append_intent(families=[...])` | 通用意图不够，需要新增“合同审查”“文档分析”等专项意图时 |
| 让员工完全自管意图集合 | `.use_replace_intent(families=[...])` | 高级场景；首版只做注册期 / builder-local，不作为真实 E2E 验收 |
| 让员工生成结构化产物 | `.output_structured(...)` + `.output_pipeline(...)` | 需要 JSON、Markdown 报告、工作流 schema 等机器产物时 |
| 让产物经过审批沙箱 | `.use_approval_sandbox()` | 首版只保留 builder-local pending 诊断，不要当成真实确认 / 拒绝交互 |

### 3.11 Run 级 `context` 怎么传、怎么拿

`context` 是一次请求带进来的自由上下文载荷。它不是插件注册期的 `registry_context`，也不是跨用户、跨会话共享的全局变量。可以把它理解成“这一次 Run 的随身包”。

当前已接通 Debug 调试流、Workspace 对话流和 OpenAPI invoke 三类入口。调用方不传 `context` 时，专项 handler 按空载荷处理；业务上必填的页面 JSON、文档 JSON 或外部对象，需要插件自己在 handler 里检查并给出提示。

在员工面试页调试时，可打开聊天区右上角 `Context`，在 `Run Context JSON` 中填入任意合法 JSON；下一条面试消息会把这段 JSON 原样放进请求体顶层 `context`。该输入不关心页面、文档或其他业务结构，专项代码通过 `context.context` 自行读取。

请求体示例：

```json
{
  "content": "根据当前页面 JSON 修改标题并补一个指标卡",
  "stream": true,
  "context": {
    "page_json": {
      "componentName": "Page",
      "props": {"title": "旧标题"}
    },
    "operation": "modify_page",
    "source": "frontend_editor"
  }
}
```

子编排 handler 里这样拿：

```python
async def build_page_patch(context):
    run_context = context.context or {}
    page_json = run_context.get("page_json") or {}
    operation = run_context.get("operation") or "create_page"
    return await context.native_capability.generate(
        task=f"根据运行上下文执行页面任务：{operation}",
        input_data={
            "user_input": context.inputs.get("user_input"),
            "page_json": page_json,
        },
        allowed_capabilities=[...],
        compiler=compile_page_patch,
        output_type="json",
        output_contract="page_patch.v1",
    )
```

使用规则：

| 规则 | 说明 |
|------|------|
| 顶层字段名固定 | 请求里写 `context`，不要再新增 `page_json`、`document_json` 这类顶层平台字段 |
| 内部结构自由 | 平台不约束 `context` 里面长什么样，专项自己决定怎么用 |
| 本次 Run 内可用 | 同一 Output Pipeline 的各 step 都能通过 `context.context` 读取 |
| 不跨 Run 共享 | 想长期保存请走 Memory、业务库或产物存储，不要把它当全局变量 |
| 唯一入口 | 新插件和新文档都只使用 `context`，不再保留旧专项运行输入字段 |

## 意图模式

## 4. 先选一种意图模式

意图模式决定“用户输入进来后，平台怎么判断这句话属于什么任务”。这是 `agent_definition.py` 里最容易选错的地方。

| 你要的效果 | 选择 | 代码 | 适合谁 |
|------------|------|------|--------|
| 先让员工正常聊天、问答、分析、生成 | 通用意图 | `.use_generic_intent()` | 绝大多数第一版插件 |
| 在通用能力之外，新增一个明确专项任务 | 追加意图 | `.use_append_intent(families=[...])` | 文档分析、合同审查、工单分类等 |
| 完全不用公共意图集合，全部自己声明 | 覆盖意图 | `.use_replace_intent(families=[...])` | 高级插件；首版不做真实 E2E 验收 |

选择规则：

| 问题 | 选什么 |
|------|--------|
| 这个员工只是换了人设和回答风格吗？ | `generic` |
| 这个员工需要识别一种公共意图没有的新任务吗？ | `append` |
| 这个员工连普通问答 / 分析 / 生成的公共分类都不想要吗？ | `replace` |
| 不确定选哪个？ | 先 `generic` |

### 4.1 `generic` 通用意图

这个方法没有参数。它只表示“我不新增专项意图，直接使用平台公共意图集合”。

| 方法 | 字段 | 类型 | 必填 | 默认值 | 做什么 | 使用后会怎样 |
|------|------|------|------|--------|--------|--------------|
| `use_generic_intent()` | 无 | 无 | 否 | 无 | 声明使用平台公共 Intent / Intent Family | 普通问答、分析、生成、闲聊等公共能力仍可用 |

```python
builder.use_generic_intent()
```

使用后：

- 平台公共 Intent / Intent Family 继续工作。
- 普通问答、分析、生成、闲聊等公共能力仍可用。
- 你只需要关注人设、能力和输出。
- 首版生产路径已验收。

### 4.2 `append` 追加意图

`append` 的意思是“公共意图集合还在，我只额外追加我的专项 family / intent”。命中你的新增任务时走专项；没命中时仍回到公共意图，不会把普通聊天弄坏。

#### 4.2.1 `use_append_intent(...)` 字段说明

这个方法本身负责“把新增的 family / intent 挂到公共意图集合后面”。第一次使用时，推荐只填 `families=[...]`，不要碰 `factory`。

| 字段 | 类型 | 必填 | 默认值 | 给用户怎么填 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------------|--------|--------------|
| `factory` | callable / None | 否 | `None` | 普通用户不填 | 高级意图插件工厂 | 填了会注册到 `context.register_intent_plugin`；大多数插件不需要 |
| `plugin_key` | string | 否 | manifest 的 `plugin_key` | 一般不填 | 意图插件标识 | 用于注册与诊断；不填就沿用插件自己的 `plugin_key` |
| `family` | string | 条件必填 | 空 | 不传 `families` 时才填 | family 诊断标识 | 只给旧式 / 高级用法兜底；推荐不用 |
| `families` | list[IntentFamilyDeclaration] | 推荐必填 | `None` | 填 `builder.intent_family(...)` 返回的对象列表 | 声明你新增的意图族和 intent | 平台会校验 family / intent；append 下不能覆盖公共 family |

必填规则：

| 写法 | 是否推荐 | 是否合法 | 说明 |
|------|----------|----------|------|
| `builder.use_append_intent(families=[document_family])` | 推荐 | 合法 | 最清楚，字段都在 family / intent 里 |
| `builder.use_append_intent(family="document_analysis")` | 不推荐 | 合法 | 只适合旧式 factory 插件；用户看不到完整字段 |
| `builder.use_append_intent()` | 不推荐 | 不合法 | 没有 `families` 也没有 `family`，会报错 |

#### 4.2.2 `intent_family(...)` 字段说明

`intent_family` 表示“一组相关任务”。例如“文档分析”这个 family 下可以有“文档总结”“风险审查”“结构提取”等 intent。

| 字段 | 类型 | 必填 | 默认值 | 给用户怎么填 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------------|--------|--------------|
| `key` | string | 是 | 无 | 小写英文 / 下划线，如 `document_analysis` | family 稳定键 | append 模式不能与公共 family 重名；重名会报错 |
| `name` | string | 是 | 无 | 中文展示名，如 `文档分析` | family 展示名 | 运行详情和诊断更容易看懂 |
| `description` | string | 是 | 无 | 一句话说明这个 family 识别什么意图 | 帮模型判断意图族 | 为空会报错 |
| `fallback_intent` | string | 是 | 无 | 当前 `intents` 里某个 intent 的 `key` | 模型没明确命中时的回退任务 | 不属于当前 family 内 intent 会报错 |
| `intents` | list[IntentDeclaration] | 是 | 无 | 填 `builder.intent(...)` 返回对象列表 | family 下的具体任务集合 | 不能为空 |
| `base_family` | string | 否 | 空 | 普通用户不填 | 继承另一个 family 的输出策略 | 高级用法，避免一开始使用 |
| `boundary` | string | 强烈建议 | 空 | 写“管什么 / 不管什么” | 定义任务边界 | 空值不阻断，但弱模型更容易误判，会产生 warning |
| `trigger_keywords` | list[string] | 否 | `[]` | 关键词，如 `["文档", "总结"]` | 辅助识别 | 让弱模型更稳 |
| `out_of_scope` | list[string] | 否 | `[]` | 不属于本 family 的任务 | 降低误命中 | 例如把“写代码”“生成工作流”排除 |
| `planner_hint` | PlannerHintDeclaration | 否 | 无 | 填 `builder.planner_hint(...)` 返回对象 | family 级 `planner_hint` 字段 | 给公共 Plan 更多信号；参与 Plan 的新增意图族至少要在 family 或关键 intent 一层补齐 |
| `default_output_policy` | string | 否 | `text_only` | 普通文本就保留默认；结构化产物填 pipeline key | family 默认输出策略 | intent 未单独声明时使用 |
| `output_policy` | dict[string,string] | 否 | `{}` | `{intent_key: pipeline_key}` | 给某个 intent 单独指定输出策略 | 同一 intent 不能同时命中多个产物策略 |

#### 4.2.3 `intent(...)` 字段说明

`intent` 表示一个具体任务。它必须放在某个 `intent_family.intents` 里。

| 字段 | 类型 | 必填 | 默认值 | 给用户怎么填 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------------|--------|--------------|
| `key` | string | 是 | 无 | 小写英文 / 下划线，如 `document_summarize` | intent 稳定键 | output policy、fallback、trace 都靠它定位 |
| `name` | string | 是 | 无 | 中文展示名，如 `文档总结` | intent 展示名 | 运行详情和诊断更可读 |
| `description` | string | 是 | 无 | 写清楚什么时候算命中 | 识别说明 | 为空会报错 |
| `examples` | list[string] | 强烈建议 | `[]` | 用户真实会说的话 | 正例 | 空值不阻断，但弱模型稳定性下降，会产生 warning |
| `negative_examples` | list[string] | 否 | `[]` | 容易误判但不该命中的话 | 反例 | 降低误命中 |
| `slots` | list[SlotDeclaration] | 否 | `[]` | 填 `builder.slot(...)` 返回对象 | 声明需要哪些材料 | 可用于材料补齐、校验、追问 |
| `planner_hint` | PlannerHintDeclaration | 否 | 无 | 填 `builder.planner_hint(...)` 返回对象 | intent 级 `planner_hint` 字段 | 优先级比 family 级更贴近具体 intent |
| `output_policy` | string | 否 | `text_only` | 普通文本填 `text_only`；结构化产物填 `output_pipeline.key` | 决定命中后怎么输出 | 非 `text_only` 时必须注册同名 Output Pipeline |
| `confidence_threshold` | float | 否 | 无 | 普通用户不填 | 置信度阈值声明 | 当前作为声明字段透传 |

#### 4.2.4 `output_policy` 怎么填

`output_policy` 不是固定写 `pipeline`。它只有两类正确写法：

| 写法 | 必填依赖 | 使用后会怎样 |
|------|----------|--------------|
| `text_only` | 不需要 pipeline | 只走普通文本输出，不执行 Output Pipeline |
| 某个 `output_pipeline.key` | 必须先注册同名 `.output_pipeline(key=...)` | 命中 intent 后执行该 pipeline，产生 `pipeline.*` 事件 |

正确示例：如果你注册的是 `output_pipeline(key="workflow_pipeline", ...)`，intent 里就写 `output_policy="workflow_pipeline"`。

错误示例：不要写 `output_policy="pipeline"`，除非你真的注册了一个 key 就叫 `pipeline` 的 Output Pipeline。

```python
document_family = builder.intent_family(
    key="document_analysis",
    name="文档分析",
    description="识别用户是否要分析、总结、审查一份文档。",
    fallback_intent="document_summarize",
    boundary="只处理文档总结、结构提取、风险审查；普通聊天和泛问答交给公共意图。",
    trigger_keywords=["文档", "总结", "提取", "审查", "风险"],
    out_of_scope=["生成工作流", "写代码", "模型调试"],
    intents=[
        builder.intent(
            key="document_summarize",
            name="文档总结",
            description="把用户提供的文档或文本总结成结构化摘要。",
            examples=["总结这份合同", "帮我提炼这篇材料的重点"],
            negative_examples=["帮我写一个工作流 JSON"],
            output_policy="text_only",
        ),
    ],
)

builder.use_append_intent(families=[document_family])
```

使用后：

- 不能覆盖公共 family key；如果新增 family 与公共 family 重名，会报错。
- `boundary` 和 `examples` 不填不会阻断注册，但弱模型识别稳定性会下降，会产生 warning。
- `fallback_intent` 必须指向当前 family 里的一个 intent。
- 如果 intent 的 `output_policy` 不是 `text_only`，必须注册同名 Output Pipeline。

### 4.3 `replace` 覆盖意图

`replace` 的意思是“主意图集合由外置插件完整提供”。它不是“在公共意图上再加一点”，而是替换主集合。

#### 4.3.1 `use_replace_intent(...)` 字段说明

`replace` 的参数和 `append` 类似，但语义更重：`families` 不是“新增集合”，而是“完整主集合”。当前版本只建议高级插件做注册期或 builder-local 验证。

| 字段 | 类型 | 必填 | 默认值 | 给用户怎么填 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------------|--------|--------------|
| `factory` | callable / None | 否 | `None` | 普通用户不填 | 替换式意图插件工厂 | 填了会注册到 `context.register_intent_plugin` |
| `plugin_key` | string | 否 | manifest 的 `plugin_key` | 一般不填 | 意图插件标识 | 用于注册与诊断 |
| `family` | string | 条件必填 | 空 | 不传 `families` 时才填 | family 诊断标识 | 只给旧式 / 高级用法兜底 |
| `families` | list[IntentFamilyDeclaration] | 推荐必填 | `None` | 填完整 family 集合 | 完整替换主意图集合 | 注册期校验合法性；首版不做真实平台 Run E2E |

replace 里的 `intent_family(...)`、`intent(...)` 字段含义和 4.2 一样，但有两个额外提醒：

| 规则 | 说明 |
|------|------|
| 必须完整 | 你要自己提供主集合里需要的 family / intent，不能期待公共意图兜底 |
| 不写生产承诺 | 当前不验收 replace 公共事件链真实端到端，不要写进用户交付验收 |

```python
private_family = builder.intent_family(
    key="private_router",
    name="私有路由",
    description="只允许识别插件自定义任务集合。",
    fallback_intent="private_answer",
    boundary="所有输入都必须归入本 family 内的 intent；不使用公共主意图集合。",
    intents=[
        builder.intent(
            key="private_answer",
            name="私有回答",
            description="对插件允许范围内的问题给出回答。",
            examples=["按我的内部规范分析这段内容"],
            output_policy="text_only",
        ),
    ],
)

builder.use_replace_intent(families=[private_family])
```

当前版本效果：

- 注册期会校验 family / intent 集合是否合法。
- builder-local 协议保留，可用于高级样板和单元验证。
- 首版不验收 replace 模式公共事件链真实端到端；不要把它写进生产验收承诺。

## 追加专项意图

### 4.2 `append` 追加意图

`append` 的意思是“公共意图集合还在，我只额外追加我的专项 family / intent”。命中你的新增任务时走专项；没命中时仍回到公共意图，不会把普通聊天弄坏。

#### 4.2.1 `use_append_intent(...)` 字段说明

这个方法本身负责“把新增的 family / intent 挂到公共意图集合后面”。第一次使用时，推荐只填 `families=[...]`，不要碰 `factory`。

| 字段 | 类型 | 必填 | 默认值 | 给用户怎么填 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------------|--------|--------------|
| `factory` | callable / None | 否 | `None` | 普通用户不填 | 高级意图插件工厂 | 填了会注册到 `context.register_intent_plugin`；大多数插件不需要 |
| `plugin_key` | string | 否 | manifest 的 `plugin_key` | 一般不填 | 意图插件标识 | 用于注册与诊断；不填就沿用插件自己的 `plugin_key` |
| `family` | string | 条件必填 | 空 | 不传 `families` 时才填 | family 诊断标识 | 只给旧式 / 高级用法兜底；推荐不用 |
| `families` | list[IntentFamilyDeclaration] | 推荐必填 | `None` | 填 `builder.intent_family(...)` 返回的对象列表 | 声明你新增的意图族和 intent | 平台会校验 family / intent；append 下不能覆盖公共 family |

必填规则：

| 写法 | 是否推荐 | 是否合法 | 说明 |
|------|----------|----------|------|
| `builder.use_append_intent(families=[document_family])` | 推荐 | 合法 | 最清楚，字段都在 family / intent 里 |
| `builder.use_append_intent(family="document_analysis")` | 不推荐 | 合法 | 只适合旧式 factory 插件；用户看不到完整字段 |
| `builder.use_append_intent()` | 不推荐 | 不合法 | 没有 `families` 也没有 `family`，会报错 |

#### 4.2.2 `intent_family(...)` 字段说明

`intent_family` 表示“一组相关任务”。例如“文档分析”这个 family 下可以有“文档总结”“风险审查”“结构提取”等 intent。

| 字段 | 类型 | 必填 | 默认值 | 给用户怎么填 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------------|--------|--------------|
| `key` | string | 是 | 无 | 小写英文 / 下划线，如 `document_analysis` | family 稳定键 | append 模式不能与公共 family 重名；重名会报错 |
| `name` | string | 是 | 无 | 中文展示名，如 `文档分析` | family 展示名 | 运行详情和诊断更容易看懂 |
| `description` | string | 是 | 无 | 一句话说明这个 family 识别什么意图 | 帮模型判断意图族 | 为空会报错 |
| `fallback_intent` | string | 是 | 无 | 当前 `intents` 里某个 intent 的 `key` | 模型没明确命中时的回退任务 | 不属于当前 family 内 intent 会报错 |
| `intents` | list[IntentDeclaration] | 是 | 无 | 填 `builder.intent(...)` 返回对象列表 | family 下的具体任务集合 | 不能为空 |
| `base_family` | string | 否 | 空 | 普通用户不填 | 继承另一个 family 的输出策略 | 高级用法，避免一开始使用 |
| `boundary` | string | 强烈建议 | 空 | 写“管什么 / 不管什么” | 定义任务边界 | 空值不阻断，但弱模型更容易误判，会产生 warning |
| `trigger_keywords` | list[string] | 否 | `[]` | 关键词，如 `["文档", "总结"]` | 辅助识别 | 让弱模型更稳 |
| `out_of_scope` | list[string] | 否 | `[]` | 不属于本 family 的任务 | 降低误命中 | 例如把“写代码”“生成工作流”排除 |
| `planner_hint` | PlannerHintDeclaration | 否 | 无 | 填 `builder.planner_hint(...)` 返回对象 | family 级 `planner_hint` 字段 | 给公共 Plan 更多信号；参与 Plan 的新增意图族至少要在 family 或关键 intent 一层补齐 |
| `default_output_policy` | string | 否 | `text_only` | 普通文本就保留默认；结构化产物填 pipeline key | family 默认输出策略 | intent 未单独声明时使用 |
| `output_policy` | dict[string,string] | 否 | `{}` | `{intent_key: pipeline_key}` | 给某个 intent 单独指定输出策略 | 同一 intent 不能同时命中多个产物策略 |

#### 4.2.3 `intent(...)` 字段说明

`intent` 表示一个具体任务。它必须放在某个 `intent_family.intents` 里。

| 字段 | 类型 | 必填 | 默认值 | 给用户怎么填 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------------|--------|--------------|
| `key` | string | 是 | 无 | 小写英文 / 下划线，如 `document_summarize` | intent 稳定键 | output policy、fallback、trace 都靠它定位 |
| `name` | string | 是 | 无 | 中文展示名，如 `文档总结` | intent 展示名 | 运行详情和诊断更可读 |
| `description` | string | 是 | 无 | 写清楚什么时候算命中 | 识别说明 | 为空会报错 |
| `examples` | list[string] | 强烈建议 | `[]` | 用户真实会说的话 | 正例 | 空值不阻断，但弱模型稳定性下降，会产生 warning |
| `negative_examples` | list[string] | 否 | `[]` | 容易误判但不该命中的话 | 反例 | 降低误命中 |
| `slots` | list[SlotDeclaration] | 否 | `[]` | 填 `builder.slot(...)` 返回对象 | 声明需要哪些材料 | 可用于材料补齐、校验、追问 |
| `planner_hint` | PlannerHintDeclaration | 否 | 无 | 填 `builder.planner_hint(...)` 返回对象 | intent 级 `planner_hint` 字段 | 优先级比 family 级更贴近具体 intent |
| `output_policy` | string | 否 | `text_only` | 普通文本填 `text_only`；结构化产物填 `output_pipeline.key` | 决定命中后怎么输出 | 非 `text_only` 时必须注册同名 Output Pipeline |
| `confidence_threshold` | float | 否 | 无 | 普通用户不填 | 置信度阈值声明 | 当前作为声明字段透传 |

#### 4.2.4 `output_policy` 怎么填

`output_policy` 不是固定写 `pipeline`。它只有两类正确写法：

| 写法 | 必填依赖 | 使用后会怎样 |
|------|----------|--------------|
| `text_only` | 不需要 pipeline | 只走普通文本输出，不执行 Output Pipeline |
| 某个 `output_pipeline.key` | 必须先注册同名 `.output_pipeline(key=...)` | 命中 intent 后执行该 pipeline，产生 `pipeline.*` 事件 |

正确示例：如果你注册的是 `output_pipeline(key="workflow_pipeline", ...)`，intent 里就写 `output_policy="workflow_pipeline"`。

错误示例：不要写 `output_policy="pipeline"`，除非你真的注册了一个 key 就叫 `pipeline` 的 Output Pipeline。

```python
document_family = builder.intent_family(
    key="document_analysis",
    name="文档分析",
    description="识别用户是否要分析、总结、审查一份文档。",
    fallback_intent="document_summarize",
    boundary="只处理文档总结、结构提取、风险审查；普通聊天和泛问答交给公共意图。",
    trigger_keywords=["文档", "总结", "提取", "审查", "风险"],
    out_of_scope=["生成工作流", "写代码", "模型调试"],
    intents=[
        builder.intent(
            key="document_summarize",
            name="文档总结",
            description="把用户提供的文档或文本总结成结构化摘要。",
            examples=["总结这份合同", "帮我提炼这篇材料的重点"],
            negative_examples=["帮我写一个工作流 JSON"],
            output_policy="text_only",
        ),
    ],
)

builder.use_append_intent(families=[document_family])
```

使用后：

- 不能覆盖公共 family key；如果新增 family 与公共 family 重名，会报错。
- `boundary` 和 `examples` 不填不会阻断注册，但弱模型识别稳定性会下降，会产生 warning。
- `fallback_intent` 必须指向当前 family 里的一个 intent。
- 如果 intent 的 `output_policy` 不是 `text_only`，必须注册同名 Output Pipeline。

## manifest.yaml

## 6. `manifest.yaml` 字段说明

### 6.1 顶层必填字段

缺少下列任一字段会报 `manifest_invalid`；`protocol_version` 或 `sdk_api_version` 不兼容会报 `version_incompatible`。

| 字段 | 类型 | 必填 | 当前枚举 / 写法 | 做什么 | 使用后会怎样 |
|------|------|------|-----------------|--------|--------------|
| `protocol_version` | string | 是 | 只支持 `"1"` | 声明 Builder 协议版本 | 平台加载前做协议兼容判断 |
| `sdk_api_version` | string | 是 | 只支持 `"1"` | 声明 SDK API 版本 | 约束 `RegistryContext` 与 Hook 签名 |
| `platform_version` | string | 是 | 如 `">=0.1.0"` | 声明兼容的平台版本范围 | 当前按字符串保留，供兼容判断与审计使用 |
| `agent_key` | string | 是 | 推荐 `ext_{agent_slug}_{timestamp_id}`，例如 `ext_doc_parse_1784532645a7` | 员工稳定唯一键 | 用于创建 / 同步 AgentProfile；升级版本不要改；换了就会被当成另一个员工 |
| `agent_name` | string | 是 | 中文或英文短名称 | 员工展示名 | 出现在员工列表、详情、运行上下文 |
| `agent_description` | string | 是 | 一句话职责说明 | 员工说明 | 用作 Profile 描述，也作为 `persona.role_summary` 默认值 |
| `plugin_key` | string | 是 | 推荐 `agent_key + "_plugin"`，例如 `ext_doc_parse_1784532645a7_plugin` | 插件稳定唯一键 | 用于插件冲突检测、意图插件注册和诊断；升级版本不要改；同名会冲突 |
| `version` | string | 是 | 新建如 `"0.1.0"`；更新时手动提升 | 插件自身版本 | 用于加载态、审计与升级识别 |
| `entrypoint` | string | 是 | 通常 `bootstrap.py` | 启动入口文件 | 平台导入该文件并调用 `register_specialized_agent(context)` |
| `enabled` | boolean | 是 | `true` / `false` | 是否启用插件 | `true` 参与加载；`false` 保留声明但不成为可运行 Bundle；写成 `"true"` 字符串会失败 |

### 6.2 `profile` 展示字段

`profile` 整块选填。不填不会阻断注册，平台按默认值补齐。

| 字段 | 类型 | 必填 | 默认值 | 做什么 | 填了能增加什么 |
|------|------|------|--------|--------|----------------|
| `profile.position` | string | 否 | 空字符串 | 员工职位展示 | 列表 / 详情里更像真实员工 |
| `profile.opening_message` | string | 否 | 空字符串 | 开场白 | 进入面试 / 试用时先给用户一句业务入口提示 |
| `profile.placeholder` | string | 否 | `请输入您的问题...` | 输入框占位 | 告诉用户应该输入哪类任务 |
| `profile.empty_state_hint` | string | 否 | 空字符串 | 空态提示 | 没有消息时显示更明确的起步提示 |

### 6.3 `persona` 人设字段

`persona` 整块推荐填写。其中 `persona.system_prompt` 在 manifest 解析阶段有默认空字符串，但 SDK `register()` 前会强校验；缺失时禁止注入可用员工。

| 字段 | 类型 | 必填 | 默认值 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------|--------------|
| `persona.system_prompt` | string | 实际必填 | 无可用默认 | 定义运行时系统提示词 | 缺失会报 `manifest_invalid`，不会同步为可用员工 |
| `persona.delegation_description` | string | 否，新建员工推荐填写 | 缺省不覆盖已有说明 | 定义其他员工何时适合委派本员工，trim 后最多 2000 字符 | 包激活时同步到人设；空字符串清空包维护值，平台手工值保留；null 非法 |
| `persona.role_summary` | string | 否 | `agent_description` | 角色摘要 | 用于 Profile 人设详情 |
| `persona.employee_task` | string | 否 | 空字符串 | 员工任务 | 让 Profile 更清楚这个员工要完成什么 |
| `persona.expertise_scope` | string | 否 | 空字符串 | 擅长范围 | 让模型和管理侧更明确边界 |
| `persona.tone` | string | 否 | `professional` | 语气风格 | 当前不做枚举限制，作为人设字段传入 |
| `persona.response_style` | string | 否 | 空字符串 | 回答风格 | 指导普通正文输出风格 |
| `persona.forbidden_rules` | list[string] | 否 | `[]` | 禁止事项 | 注入 Profile extra，作为人设约束参考 |

#### 6.3.1 人设与委派适用说明

新建员工或生成人设时，应基于同一份职责、实际能力和禁止事项，配套生成并保存 `system_prompt` 与 `delegation_description`，提前为以后被其他员工委派准备说明，不应等到第一次被委派时才补写。更新人设时应复核已有说明是否仍准确；仅修改无关配置无需重新生成。两者用途不同，不能互相替代：

| 字段 | 回答的问题 | 内容要求 | 当前支持位置 |
|------|------------|----------|--------------|
| `system_prompt` | 我收到任务后如何执行和回答？ | 角色、职责、执行要求、输出与限制 | 包内 `persona.system_prompt` 或 SDK `with_persona(system_prompt=...)` |
| `delegation_description` | 其他主员工何时适合把任务交给我？ | 适用任务、所需输入、预期输出、不适用范围；保存为不超过 2000 个字符的文本 | 包内 `persona.delegation_description` 或 SDK `with_persona(delegation_description=...)`，激活时同步到平台员工人设 |
| `delegation_agent_ids` | 我能把任务委派给哪些员工？ | 平台真实员工 ID 列表，不是工具 ID、服务 ID 或说明文本 | manifest 顶层或 SDK `with_delegation_agents(...)` |

委派适用说明应概括本员工实际职责，不能因为名称叫“全能助手”就声称可以处理所有任务，也不能把关联工具、解析器或子员工的存在解释为无条件可用。不要把 system_prompt 全文复制为说明，也不要写入密钥、连接配置或内部实现细节。推荐在 manifest 中与系统提示词一起落盘：

```yaml
persona:
  system_prompt: 你是文档分析员工，基于用户提供的材料回答，不编造信息。
  delegation_description: |
    适用任务：根据已提供的文档提炼摘要、整理要点并回答相关问题。
    所需输入：可读取的文档内容、具体问题和关注范围。
    预期输出：有依据的摘要、要点或回答；材料不足时说明缺失内容。
    不适用范围：不访问未授权数据，不执行未绑定能力，不提供超出材料依据的结论。
```

交付要求：配套生成内容、通过受支持入口保存、在包版本激活时同步到平台员工人设，并核对平台有效字段中存在非空 `delegation_description`，才算完成二开员工的委派说明配置。仅在回复中给出文案、仅写入系统提示词、仅声明向外委派的目标，均不算完成。即使当前没有 `delegation_agent_ids`，也应提前准备本员工的被委派说明；说明本身不授予访问或委派权限。

保存规则：旧包省略该字段时不清空已有说明；显式空字符串清空未手工维护的说明，manifest 的 null、非字符串或 trim 后超过 2000 字符会校验失败。SDK 省略参数或传 None 保留 manifest 值，显式字符串覆盖 manifest 值，遵循现有人设覆盖规则。平台已标记为手工修改的说明（包括手工清空）在包升级/回滚时保留，包不能修改该标记。用户需要更新手工值时，应走平台支持的确认维护流程，不能借包覆盖。

开发助手应直接修改工作区的 manifest 或 `agent_definition.py`，不能再以“包没有承载位置”为由仅返回文案。交付时分别说明系统提示词和委派说明的落盘位置、是否已激活同步、委派目标是否已声明。工作区内无法读取平台有效值时明确写“源码已保存，平台生效待激活核验”，不伪报已经具备被委派资格。平台人设生成接口仍须开启 `include_delegation_description=true` 才返回配套说明，返回后仍需保存；使用该接口与开发助手直接编写包是两条内容生成入口。

### 6.4 `suggested_questions`

| 字段 | 类型 | 必填 | 默认值 | 限制 | 做什么 |
|------|------|------|--------|------|--------|
| `suggested_questions` | list[string] | 否 | `[]` | 最多保留 3 条 | 作为员工入口快捷问题 |

### 6.5 manifest 禁止字段

下列 Agent 编排字段不能写入 `manifest.yaml`，必须写在 `agent_definition.py`。写入会报 `manifest_invalid`。

```text
intent
capability_assets
capabilities
memory
output
state_runtime
plan
plans
guardrail
guardrails
followup
followups
approval
trace
```

原因：manifest 只回答“这个员工是谁”；`agent_definition.py` 回答“这个员工怎么运行”。

### 6.6 员工资源绑定

工具、解析服务与委派都绑定到整个员工。意图中的提示只缩小候选，不能增加绑定或授予权限。

| 资源 | 声明位置 | 最小写法 |
|------|----------|----------|
| 平台工具或随包能力 | `agent_definition.py` | `.with_capability_asset("能力ID")` 或 `.with_capability_template("mcp:模板名/工具名")` |
| 平台共享解析服务 | `manifest.yaml` | `shared_attachment_parsers.bindings` 中填写 `service_id` |
| 随包解析代码 | `manifest.yaml` | 保持 `attachment_parsers` 的入口、格式检测和依赖声明 |
| 委派员工 | manifest 或 SDK 二选一 | `delegation_agent_ids: ["目标员工ID"]` 或 `.with_delegation_agents(["目标员工ID"])` |

```yaml
shared_attachment_parsers:
  bindings:
    - service_id: "解析服务ID"
    - service_id: "另一个解析服务ID"
      revision_id: "指定修订ID"
      extensions: [".rtf"]
delegation_agent_ids:
  - "目标员工ID"
```

共享解析服务省略版本表示跟随当前已发布版本；显式 `revision_id` 表示固定版本，不填开发版本号。`extensions` 省略时以首次校验获准格式为上限；`null` 或空数组不合法。平台新版本不会自动增加格式或外发权限。详见附件解析器章节。

包声明的定义和绑定结构在面试配置中只读；技能/工具可独立启停，升级或回滚保留存续绑定的开关，移除后重加按包默认值。平台可以追加、启停和移除自己的绑定，工具不再提供参数调整弹窗，解析器版本/格式调整保留。包更新或回滚不删除平台来源。同一稳定资源 ID 分别保留两份来源配置和开关；同名不同 ID 不合并。平台无法把仅包内资源再添加成自己的来源。平台先绑定 C、包后来也声明 C 时形成双来源，包删除 C 后平台 C 仍保留。

委派最多 3 个去重后的目标，停用或暂不可用仍占名额，不可重复或指向自己。manifest 和 SDK 同时声明时必须完全一致；不同声明拒绝保存，不自动合并。目标不存在、不可访问、停用、缺委派描述或模型不可用时，合法声明仍可保存，面试显示诊断；运行时仅把合格目标交给主员工，其他目标不进入模型上下文。子任务不再发起下一层委派。平台修改后，新面试使用新配置，对外服务须更新员工发布。

## SDK 封装方法

## 8. SDK 入口和注册生命周期

统一入口：

```python
from specialized.builder.sdk import create_external_agent
```

生命周期：

```text
create_external_agent(context)
  -> 链式声明 use_* / with_* / output_* / register_*
  -> register()
  -> 校验 persona、output_policy、planner_hint、intent 声明质量
  -> 归一化 builder_blocks / state_machine_config
  -> 构造 SpecializedAgentBundle
  -> context.register_bundle(bundle)
```

重要规则：

- `register()` 是提交点；提交后不能继续追加能力、输出、护栏、Trace。
- 未显式声明意图时，归一化默认 `generic`。
- 未声明输出时，归一化默认普通文本输出；未声明 `output_policy` 时默认 `text_only`。
- `use_*` / `with_*` 是运行语义，不是仅登记：平台会按声明装配模块、能力快照、事件和门禁。

### 8.1 委派目标声明

```python
builder.with_delegation_agents(["目标员工ID", "另一目标员工ID"])
```

返回当前 builder，须在 `register()` 前调用。也可用 manifest 顶层 `delegation_agent_ids`；两者使用同一声明槽，相同规范化列表幂等，不同列表拒绝，不取并集。空列表表示包不声明委派，`null`、重复、自引用和超过 3 个目标均不合法，不能放到 `with_profile(extra=...)` 绕过检查。

声明不等于授权：当前不存在或不可委派的目标会保留为管理诊断，运行时逐项排除，不阻断主员工普通聊天或其他合格目标。子任务仅执行单层委派。包内目标只读，面试中可另外追加或移除平台自己的目标。

### 8.2 被委派说明与人设生成

`with_delegation_agents(...)` 只声明“我委派给谁”，不会生成或保存“我适合被委派什么任务”的 `delegation_description`。本员工没有向外委派目标，也应在创建时提前准备被委派说明。仅增加委派目标且不改变职责时，无需重写已有准确说明；若职责或实际能力发生变化，应复核说明是否仍准确。

新建员工或生成 `system_prompt` 时，应配套生成并保存委派适用说明，为以后被委派做好准备，不等用户已经发起委派才补写。按“适用任务、所需输入、预期输出、不适用范围”四项描述，全文不超过 2000 个字符。系统提示词面向执行，委派说明供主员工筛选目标，不能用其中一个替代另一个。已有手工说明不能被重新生成人设静默覆盖。

`with_persona()` 已支持 `delegation_description: str | None = None`，在 `register()` 前调用，随现有人设同步链路生效。也可以直接填写 manifest 的 `persona.delegation_description`，推荐选择一处维护；两处都有时 SDK 显式字符串覆盖 manifest，SDK 省略或 None 保留 manifest 值。

```python
builder.with_persona(
    system_prompt="你是文档分析员工，基于提供的材料回答，不编造信息。",
    delegation_description=(
        "适用任务：文档摘要和问答。\n"
        "所需输入：可读取的文档及问题。\n"
        "预期输出：有依据的摘要或回答。\n"
        "不适用范围：材料外的推断和未授权数据访问。"
    ),
)
```

说明 trim 后最多 2000 字符，非字符串或超限拒绝；空字符串表示清空包维护值，省略不清空旧值。平台标记为手工修改的说明在包升级/回滚时保留，包不能重置手工标记。不要臆造 `with_delegation_description()`，也不需要绕到 `with_profile(extra=...)`。

开发助手应实际修改 manifest 或 `agent_definition.py`，不能以“包内没有保存位置”为由只输出文案。完成平台配置还须激活包并核对有效 `delegation_description` 非空；只读得到工作区时，应报告“源码已保存，平台生效待激活核验”。已有平台手工值被保留时，不能宣称包内新文案已覆盖生效。

包校验通过只代表声明符合结构约束，不证明目标当前可委派。目标缺少非空委派说明时会被运行候选过滤，平台还会检查目标启用状态、模型和实际调用主体的授权。缺失或不合格目标不阻断主员工普通聊天；不要要求用户先消除全部管理诊断才允许保存合法包。代码保存、包版本激活、员工对外更新发布是不同步骤，不能用“源码已修改”代替“平台已生效”。

## Memory、Skill 和 MCP 配置

## 12. Memory、Capability、Plan 与治理模块

| 方法 | 必填 | 参数 | 做什么 | 使用后会怎样 |
|------|------|------|--------|--------------|
| `.use_memory()` | 否 | 无 | 启用平台记忆模块 | 写入运行模块配置，复用员工记忆绑定；不允许插件直接读写记忆库 |
| `.with_capability_asset(capability_id, required=True)` | 否 | SDK 绑定 ID、是否必需 | 声明公共能力层依赖 | required 缺失 / 未授权会被门禁阻断；optional 只诊断 |
| `.with_capability_template(template_ref, required=True)` | 否 | 随包模板引用、是否必需 | 声明插件随包 Skill / MCP 模板依赖 | 平台先把模板投影成原生能力，再归一成 `capability_id` 绑定 |
| `.with_artifact_capability_asset(capability_id, required=True)` | 否 | 产物型 SDK 绑定 ID、是否必需 | 声明仅供 Output Pipeline 使用的产物型能力 | 只允许 `asset_type=artifact_capability` 且 `invocation_scope=output_pipeline` 的能力进入子编排 |
| `.use_state_runtime(runtime_line="composable", enabled_modules=None, entry_config=None)` | 否 | 运行线、模块、入口配置 | 启用可组装运行时入口配置 | 写入 `state_machine_config.entry_config` |
| `.use_plan(plan_template_key="", strategy="intent_family", enabled=True)` | 否 | 计划模板、策略、开关 | 声明公共 Plan 配置 | 自动调用 `use_state_runtime()`，计划元数据写入 `builder_runtime.plan` |
| `.use_guardrail_module()` | 否 | 无 | 启用护栏模块 | 只声明模块，执行由平台 Guardrail Runtime 托管 |
| `.register_guardrail(slot, guardrail_key)` | 否 | 护栏插槽、护栏 key | 声明护栏插槽 | 启用 guardrail 模块；真实审批 / 中断按平台策略 |
| `.use_governance()` | 否 | 无 | 启用治理模块 | 写入 Builder 板块与运行模块 |
| `.register_followup(strategy, enabled=True, count=None)` | 否 | 策略、开关、数量 | 声明后置追问策略 | 写入 `entry_config.postprocess.followup` 与 `builder_runtime` |

CapabilityAsset 统一表示公共能力资产。Skill、Tool、MCP、Native Capability 只是能力资产内部 `asset_type`，外置插件不直接 import 或调用底层服务。

这些声明生成包内绑定，定义、权限、参数和删除在面试中只读，但技能/工具允许平台启停。包升级或回滚保留存续绑定的开关选择，移除后重加按新声明默认值。平台可在同一员工上追加独立有效的工具或能力，并单独启停和移除平台部分；工具不提供参数调整弹窗，已有参数保持原值，包升级不覆盖平台来源。相同能力 ID 只向运行时暴露一次，启用来源的权限取更严格限制；各来源独立启停，关闭一个来源不关闭另一个启用来源。平台仅绑定后由包后续引用同一 ID 时形成双来源；包移除该引用不删除原平台绑定。同名但不同 ID 仍是两项，名称不能作为身份。

平台追加的工具会进入能力层可规划、可调用的集合；意图提示与固定产物管线不会因此自动新增依赖或扩大权限。已发布服务须更新员工发布后使用新的绑定，既有全局停用、主体授权和调用确认规则继续生效。

### 12.1 自动候选提取是员工级设置

`.use_memory()` 只声明装配平台记忆模块，并复用该员工已有的记忆绑定和 active 记忆读取能力；它不声明、也不覆盖自动候选记忆提取策略。

自动候选提取由员工已保存的运行配置控制：

```json
{
  "state_machine_config": {
    "entry_config": {
      "memory": {
        "writeback": {
          "enabled": false
        }
      }
    }
  }
}
```

- 外置三方 Agent 的 `state_machine_config.entry_config.memory.writeback.enabled` 缺失时默认 `false`；通用、平台内置专项和已有历史 Profile 缺失时保持默认 `true`。该字段只接受 JSON boolean。
- `false` 只关闭每次 Run 完成后自动生成 candidate 记忆的步骤。
- 关闭后不影响 active 记忆检索、记忆注入或显式 `memory.write`。
- 这是员工级运行设置，在员工详情的“开始面试”区域保存；外置开发者不要把它写入 `manifest.yaml` 或 `agent_definition.py`。
- 外置 Bundle 的 `.use_memory()` 与入口默认配置不能替代该开关。外置 Agent 需要自动提取时，必须由员工详情显式保存 `true`；员工已保存的 `true` 或 `false` 均优先于 Bundle 默认值。

### 12.2 SDK 绑定 ID 怎么找

用户在能力中心列表里复制 `SDK 绑定 ID`，然后填到 SDK：

```python
builder.with_capability_asset("f84aaff3-f130-4160-83ad-ec1775562f9e")
```

不要让普通用户查数据库。当前能力中心列表已经展示 `SDK 绑定 ID` 并提供复制按钮。

字段口径：

| 字段 | 给谁用 | 是否推荐用户填写 |
|------|--------|------------------|
| `capability_id` / `SDK 绑定 ID` | SDK 绑定、绑定表、运行门禁 | 推荐 |
| `ref_id` / 引用对象 | 原始 Tool / Skill / MCP 对象引用 | 不作为用户主填写口径 |
| `name` | 能力名称 | 代码兼容查找，但不稳定，不推荐 |

代码兼容按 `capability_id`、`ref_id`、`name` 查找，但文档和脚手架统一要求用户填 `SDK 绑定 ID`。

### 12.3 随包能力模板怎么写

当插件要自己带 Skill / MCP 定义时，不用先去能力中心手动建能力。你把模板文件放进插件目录，再在 `agent_definition.py` 里用 `.with_capability_template(...)` 引用。

脚手架已经内置两个可填写文件：

| 文件 | 用途 | 引用写法 |
|------|------|----------|
| `capabilities/skills/your-skill-template.yaml` | 填写一个随包 Skill 能力 | `skill:your-skill-template` |
| `capabilities/mcp/your-mcp-template.yaml` | 填写一个远程 MCP Server | `mcp:your-mcp-template/remote_tool_name` |

目录固定这样放：

```text
your_external_agent/
├── capabilities/
│   ├── skills/
│   │   └── your-skill-template.yaml
│   └── mcp/
│       └── your-mcp-template.yaml
├── agent_definition.py
├── bootstrap.py
└── manifest.yaml
```

引用规则：

| 模板类型 | 文件位置 | `template_ref` 写法 | 使用后会怎样 |
|----------|----------|---------------------|--------------|
| Skill 模板 | `capabilities/skills/your-skill-template.yaml` | `skill:your-skill-template` | 平台投影成原生 Skill 和 CapabilityAsset，再绑定到员工 |
| MCP 模板 | `capabilities/mcp/your-mcp-template.yaml` | `mcp:your-mcp-template/remote_tool_name` | 平台投影成 MCP Server，发现远端工具后绑定对应 CapabilityAsset |

`template_key` 不是文件里的字段，而是平台按文件相对路径自动生成的稳定键：

| 文件名 | 自动生成的 `template_key` | 引用写法 |
|--------|---------------------------|----------|
| `capabilities/skills/document-organizer.yaml` | `document-organizer` | `skill:document-organizer` |
| `capabilities/skills/doc/organizer.yaml` | `doc/organizer` | `skill:doc/organizer` |
| `capabilities/mcp/amap-weather.yaml` | `amap-weather` | `mcp:amap-weather/maps_weather` |

路径必须是 `capabilities/skills` 或 `capabilities/mcp` 下面的安全相对路径。不要写绝对路径、`../`、隐藏路径或空目录片段。`document-reader.yaml` 和 `document-reader.json` 会得到同一个 `template_key=document-reader`，所以不能同时存在。

`template_version` 可以不写。默认取 `manifest.yaml` 里的插件版本。只有当你明确要让某个模板单独带版本时，才在模板文件里写 `template_version: "1.0.0"`。

Skill 模板必须写清 4 个字段：

| 字段 | 必填 | 怎么填 |
|------|------|--------|
| `name` | 是 | Skill 展示名称，例如“文档整理助手” |
| `description` | 否 | 一句话说明这个 Skill 负责什么 |
| `instruction` | 是 | Skill 执行说明，写清目标、步骤、输出要求和禁止事项 |
| `capability_contract` | 否 | 有就按契约执行；省略、留空或写 `{}` 时，平台根据 `name`、`description` 和 `instruction` 自动推导 |

Skill 模板顶层只写上面这些业务字段和可选的 `template_version`。不要在模板顶层写 `api_key`、`secret`、`password`、`token` 等敏感字段；这些会被平台拒绝加载。随包模板是能力定义，不是密钥仓库。

最小 Skill 模板示例：

```yaml
name: 文档总结
description: 提取文档重点并形成摘要
instruction: |
  阅读用户提供的内容，提取主题、关键事实和待办事项。
capability_contract:
  capability_type: skill
  task_triggers:
    - 文档总结
    - 提取重点
  accepted_input_scopes:
    - paragraph
    - long_text
    - document
  supported_output_shapes:
    - plain_summary
    - bullet_points
  side_effect_level: readonly
```

`capability_contract` 用来补充说明“什么时候该把这个 Skill 放进能力判断里、它吃什么输入、产出什么形态、有没有副作用”。它不是注入式 Skill 的硬性前置：缺失、留空或 `{}` 时，平台会使用 Skill 的名称、描述和指令自动推导最小能力描述；填写有效契约时，契约字段优先。契约存在但 JSON 或字段值非法时仍会校验失败，不会静默吞掉真正的配置错误。普通管理台和二开 Agent 共用这套回退口径。

`capability_contract` 支持 13 个字段。小白开发者最少也要写清触发词、输入粒度、输出形态和副作用；拿不准的收窄字段可以先不填。

| 字段 | 必填性 | 默认值 | 怎么理解 |
|------|--------|--------|----------|
| `capability_type` | 可选 | `skill` | 固定写 `skill`，表示这是 Skill 能力契约 |
| `task_triggers` | 推荐 | `[]` | 用户怎么说时可能需要这个 Skill，例如“文档分析”“提取重点” |
| `input_descriptors` | 推荐 | `[]` | 适合处理什么输入，例如“长文本”“会议记录”“页面内容” |
| `accepted_input_scopes` | 推荐 | `[]` | 输入粒度白名单，会影响能力选择和 `invocation_policy` 的 key |
| `output_descriptors` | 推荐 | `[]` | 会产出什么业务结果，例如“简短总结”“待办事项” |
| `supported_output_shapes` | 推荐 | `[]` | 输出形态白名单，帮助计划理解产物类型 |
| `invocation_requirement` | 可选 | `optional` | 全局调用要求，通常保持默认 |
| `invocation_policy` | 推荐 | `{}` | 按输入粒度写调用策略，例如 `document: required` |
| `side_effect_level` | 可选 | `readonly` | 副作用级别，分析整理类一般都是只读 |
| `input_contract` | 可选 | `{}` | 输入结构约束；普通文本 Skill 可以不填 |
| `output_contract` | 可选 | `{}` | 输出结构约束；需要稳定 JSON 或表格时再填 |
| `supported_intent_families` | 可选 | `[]` | 限定适配哪些意图族；不填表示不额外限制 |
| `supported_task_modes` | 可选 | `[]` | 限定适配哪些任务模式；不填表示不额外限制 |

平台受控枚举只能写下面这些值：

| 字段 | 枚举值 | 含义 | 什么时候用 |
|------|--------|------|------------|
| `capability_type` | `skill` | 固定表示 Skill 能力契约 | 注入式 Skill 只能写这个 |
| `accepted_input_scopes` | `short_text` | 短文本输入，例如一句话、短问题、短指令 | 短句润色、短问答、轻量提炼 |
| `accepted_input_scopes` | `paragraph` | 段落级输入，例如一段说明、几段笔记 | 段落总结、改写、重点提取 |
| `accepted_input_scopes` | `long_text` | 长文本输入，例如多段正文、长会议记录 | 长文总结、长材料分析 |
| `accepted_input_scopes` | `document` | 文档级输入，例如文件解析后的正文或完整文档 | 上传文档、报告、知识材料分析 |
| `accepted_input_scopes` | `conversation_span` | 会话片段输入，例如历史聊天或上下文片段 | 聊天记录整理、对话复盘 |
| `accepted_input_scopes` | `multi_content` | 多内容源输入，例如多个文本块、多个文档或混合材料 | 跨材料归纳、对比、合并分析 |
| `supported_output_shapes` | `plain_summary` | 普通文本摘要或自然语言结论 | 一段话总结、解释、分析 |
| `supported_output_shapes` | `bullet_points` | 条目列表输出 | 重点、待办、风险、清单 |
| `supported_output_shapes` | `outline` | 分层大纲输出 | 章节结构、文档框架、方案大纲 |
| `supported_output_shapes` | `table` | 表格输出，可是 Markdown 表格或结构化表格语义 | 对比、盘点、字段清单、数据整理 |
| `supported_output_shapes` | `chart_description` | 图表解读或图表生成建议的文字描述 | 趋势说明、指标解读；不是渲染图表 |
| `invocation_requirement` | `optional` | 不强制调用，是否调用交给触发词、输入粒度和策略判断 | 默认推荐，大多数 Skill 用它 |
| `invocation_requirement` | `required` | 命中契约时倾向进入能力调用主链 | 必须靠该 Skill 才能稳定完成时用 |
| `invocation_requirement` | `forbidden_text_substitution` | 不应把该 Skill 当作普通文本替换器或最终正文替代器 | 普通外置 Skill 不建议用，偏治理语义 |
| `invocation_policy` 的 value | `optional` | 该输入粒度只是候选 | 弱相关输入粒度 |
| `invocation_policy` 的 value | `preferred` | 该输入粒度优先考虑调用，但可跳过 | 调用会更好但不是硬要求 |
| `invocation_policy` 的 value | `required` | 该输入粒度应进入能力调用主链 | 强相关输入粒度，例如文档分析对 `document` |
| `invocation_policy` 的 value | `disabled` | 该输入粒度禁用这个 Skill | 容易误触发或不适合处理的输入 |
| `side_effect_level` | `readonly` | 只读，不修改外部状态 | 总结、分析、整理、阅读类 Skill |
| `side_effect_level` | `mutating` | 会修改平台内资源或产生状态变更 | 写入、更新、删除平台数据 |
| `side_effect_level` | `external_effect` | 会调用外部系统并可能产生外部影响 | 发消息、下单、提交工单、调用外部写接口 |

`invocation_policy` 的 key 必须是 `accepted_input_scopes` 里的输入粒度枚举；value 必须是 `optional / preferred / required / disabled`。如果某个输入粒度没有写 policy，它不会单独形成调用强信号。

MCP 模板只支持远程服务。你需要写这些字段：

| 字段 | 必填 | 可选值 / 格式 | 怎么填 | 使用后会怎样 |
|------|------|---------------|--------|--------------|
| `name` | 是 | string | MCP 服务展示名称，例如“高德天气 MCP” | 管理台里显示这个服务名 |
| `description` | 否 | string | 说明服务提供哪些工具 | 能力中心和管理台展示 |
| `connection_type` | 是 | `sse` / `streamable_http` | 按远程 MCP 服务实际协议填写 | 非这两个值会拒绝加载 |
| `endpoint` | 是 | URL | 远程 MCP 地址，例如 `https://example.com/mcp` | 平台用它连接远端服务 |
| `headers` | 否 | object 或 JSON 对象字符串 | 远端服务需要请求头时填写 | 会写入 MCP Server 配置 |
| `enabled` | 否 | bool，默认 `true` | 是否导入后启用 | `false` 时不会作为可执行能力注入 |

MCP 模板不支持本地进程配置。不要写 `stdio`、`command`、`args`、`env`、`npx`、`npm`、`node`。写了会直接拒绝加载。

`headers` 可以写普通非敏感请求头。敏感 header 只能写占位符，不能写真实密钥：

```yaml
headers:
  Authorization: ${AMAP_MCP_TOKEN}
  X-Trace-Source: specialized-plugin
```

下面这种会被拒绝，因为它把真实 token 放进了模板：

```yaml
headers:
  Authorization: Bearer real-token
```

受控敏感 header 包括 `Authorization`、`X-API-Key`、`X-Auth-Token`、`API-Key`、`token`。如果你需要密钥，优先让部署环境或平台配置注入 `${ENV_NAME}` 这类占位符。

代码示例：

```python
builder.with_capability_template("skill:your-skill-template", required=True)
builder.with_capability_template("mcp:your-mcp-template/remote_tool_name", required=False)
```

`required=True` 表示这个模板必须能解析成可用能力；模板文件不存在、MCP 远端工具没发现或投影失败时会阻断。`required=False` 表示缺失只进入诊断，不阻断普通运行。

随包能力模板和已有能力绑定最终都会归一成平台 `capability_id`，所以运行门禁、授权、快照、审计和调用记录走同一套公共能力链路。

模板加载后的生命周期：

| 情况 | 平台行为 | 用户会看到什么 |
|------|----------|----------------|
| 第一次加载插件 | 模板投影成平台原生 Skill / MCP 资源，并生成能力中心 `capability_id` | 能力列表出现“插件托管”和来源信息 |
| 模板内容没变 | `source_hash` 相同，不重复写入资源 | 能力 ID 和绑定保持不变 |
| 模板内容升级 | 复用原 `resource_id` 和 `capability_id`，更新定义 | 已绑定员工继续指向同一个能力 |
| 删除模板文件后 reload / 重启 | 来源标记为 `source_removed`，托管资源软失活 | 新 Run 不再注入；required 会阻断，optional 只 warning；历史快照保留执行时信息 |
| 恢复同一路径模板 | 复用原 ID 并重新激活来源 | 原绑定可恢复使用 |
| 转为平台自管副本 | 深复制出新的自管能力 | 新副本不再受原模板删除 / 恢复影响 |

## Output Pipeline

## 14. Output Pipeline 模块

### 14.1 `pipeline_step(...)`

| 参数 | 类型 | 必填 | 默认值 | 枚举 / 限制 | 做什么 |
|------|------|------|--------|-------------|--------|
| `key` | string | 是 | 无 | pipeline 内唯一 | step 稳定键 |
| `title` | string | 否 | `key` | 无 | 展示标题 |
| `output_type` | string | 条件必填 | 继承 pipeline | 见枚举 | step 输出类型 |
| `output_contract` | string | 条件必填 | 空 | `text` / `markdown` / `internal` 可省略，其余不可省略 | step 输出契约 |
| `output_schema` | string | 否 | 空 | `output_contract` 兼容别名 | 等价于 `output_contract` |
| `handler` | callable | 二选一 | 无 | 与 `capability_id` 不能同时存在 | Python step 处理函数 |
| `capability_id` | string | 二选一 | 空 | 只能填产物型 SDK 绑定 ID | 通过产物型能力门面执行 step |
| `running_title` | string | 否 | `正在{title}` | 无 | 运行中文案 |
| `completed_title` | string | 否 | `{title}已完成` | 无 | 完成中文案 |
| `failed_title` | string | 否 | `{title}失败` | 无 | 失败中文案 |
| `output_visibility` | string | 否 | 中间 step `internal`，最终 step `final_artifact` | 见枚举 | 机器输出是否进入 trace / 预览 / 最终产物 |
| `reasoning_visibility` | string | 否 | `preview` / `final_artifact` 默认 `visible`，其余默认 `trace_only` | 见枚举 | 模型 reasoning 展示范围 |
| `retry_policy` | string | 否 | `none` | 当前仅作为声明 | 重试策略 |
| `timeout_ms` | int | 否 | `0` | `0` 表示无显式超时 | 异步 handler / 能力调用超时 |
| `input_from` | string | 否 | `previous_step` | 见枚举 | 当前 step 输入来源 |

#### 14.1.1 在 step handler 里调用第三方 HTTP 接口

Output Pipeline handler 可以通过 `context.http` 调用第三方 HTTP/HTTPS 接口，再把响应组装成 step 输出。推荐优先使用这个平台门面，而不是在插件里直接 import `httpx`、`requests` 或 `aiohttp`。

最小示例：

```python
async def fetch_weather(step_context):
    run_context = step_context.context or {}
    city = run_context.get("city", "Shanghai")
    response = await step_context.http.get(
        "http://example-third-party.local/weather",
        params={"city": city},
        headers={"Authorization": "Bearer ${secret:weather_api_token}"},
        timeout_ms=5000,
        follow_redirects=False,
    )
    payload = response.json()
    return {
        "status": "completed",
        "output": {
            "city": city,
            "summary": payload.get("summary", ""),
            "temperature": payload.get("temperature"),
            "source_status": response.status_code,
        },
        "diagnostics": [response.diagnostics],
    }


builder.output_structured(kind="weather_report", schema="weather.v1", schema_version="1")
builder.pipeline_step(
    key="fetch_weather",
    title="查询第三方天气接口",
    output_type="json",
    output_contract="weather.v1",
    handler=fetch_weather,
    input_from="original_input",
    output_visibility="final_artifact",
)
builder.output_pipeline(
    key="weather_pipeline",
    artifact_kind="weather_report",
    output_type="json",
    steps=["fetch_weather"],
    final_contract="weather.v1",
)
```

`context.http` 是平台封装的受控 HTTP 门面，调用风格接近 `httpx`，但不是完整 `httpx.AsyncClient` 透传。以这里列出的参数为准：

| 方法 | 签名 | 说明 |
|------|------|------|
| `await context.http.request(...)` | `request(method, url, *, params=None, headers=None, json=None, data=None, timeout_ms=None, follow_redirects=False)` | 发起任意 HTTP 方法请求 |
| `await context.http.get(...)` | `get(url, **kwargs)` | 等价于 `request("GET", url, **kwargs)` |
| `await context.http.post(...)` | `post(url, **kwargs)` | 等价于 `request("POST", url, **kwargs)` |

请求参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `method` | string | `request` 必填 | 无 | HTTP 方法，会转成大写；`get/post` 快捷方法不需要传 |
| `url` | string | 是 | 无 | 第三方 HTTP/HTTPS URL；请求从平台后端运行时网络发出 |
| `params` | Any | 否 | `None` | 查询参数；支持 dict/list/tuple/string 等可由底层 HTTP 客户端编码的值，字符串可包含 `${secret:name}` |
| `headers` | dict[str, Any] | 否 | `{}` | 请求头；支持 `${secret:name}`，不得写真实 token |
| `json` | Any | 否 | `None` | JSON 请求体；支持递归解析 `${secret:name}` |
| `data` | Any | 否 | `None` | 表单、文本或 bytes 请求体；支持递归解析 `${secret:name}` |
| `timeout_ms` | int / None | 否 | 平台默认 5000 | 本次请求超时毫秒数；超过平台上限会自动压到上限并记录 `timeout_over_limit` 风险标记 |
| `follow_redirects` | bool | 否 | `False` | 是否跟随重定向；超过平台跳转上限会失败为 `http_redirect_limit_exceeded` |

返回对象 `PlatformHttpResponse`：

| 字段 / 方法 | 类型 | 说明 |
|-------------|------|------|
| `status_code` | int | 第三方响应状态码；4xx / 5xx 默认不抛错 |
| `headers` | dict[str, str] | 响应头字典 |
| `text` | string | 响应文本；受平台响应大小上限保护 |
| `diagnostics` | dict[str, Any] | 脱敏诊断，适合写入 step `diagnostics` |
| `is_success` | bool property | `200 <= status_code < 400` |
| `json()` | method | 解析 `text` 为 JSON；失败时抛 `PlatformHttpError(error_code="http_response_json_invalid")` |

不支持把 `httpx` 高级参数完整透传。不要依赖 `cookies`、`auth`、`files`、`stream`、`verify`、`cert`、`proxies`、`event_hooks`、自定义 client / transport 等参数；后续如需开放，必须先进入平台治理口径。

使用规则：

| 规则 | 说明 |
|------|------|
| 默认允许任意 HTTP/HTTPS 地址 | 生产默认治理模式是 `observe`，显式配置可切到 `warn`；`http://`、`https://`、公网、内网、本地测试地址默认不强阻断 |
| 请求从后端运行时发出 | `localhost`、`127.0.0.1` 指向平台后端运行时所在机器或容器，不是调用者浏览器，也不一定是开发者电脑 |
| 4xx / 5xx 不算传输失败 | 会返回 `PlatformHttpResponse`，由你的 handler 决定是降级、提示用户还是继续组装输出 |
| 网络 / DNS / TLS / 超时等算受控失败 | 会抛 `PlatformHttpError`，平台把它归一成 `http_*` error_code 的 failed step |
| `${secret:name}` 发送前解析 | 可放在 headers、params、json、data 的标量值里；不要写真实密钥，解析失败不会发送原始占位值 |
| 请求和响应都有大小上限 | 大请求会在发送前失败为 `http_request_too_large`，大响应会失败为 `http_response_too_large` |
| 首版不自动重试 | 事件里的 `retry_count` 固定为 `0`；POST / PUT / PATCH / DELETE 不会被平台默认重试 |
| 诊断只记录元数据 | 事件和 diagnostics 只含 method、scheme、host、path、状态码、耗时、大小、风险标记等，不记录 query、正文、完整 headers 或 token |

常见错误码：

| error_code | 什么时候出现 |
|------------|--------------|
| `http_secret_reference_invalid` | `${secret:name}` 格式非法 |
| `http_secret_resolver_unavailable` | 当前环境没有可用 secret resolver |
| `http_secret_not_found` | secret 不存在或无权读取 |
| `http_transport_failed` | DNS、TLS、连接重置或非法 URL 等非超时传输失败 |
| `http_timeout` | 请求超时 |
| `http_request_too_large` | 请求超过平台大小上限 |
| `http_response_too_large` | 响应超过平台大小上限 |
| `http_redirect_limit_exceeded` | 重定向超过平台上限 |
| `http_response_json_invalid` | 调用 `response.json()` 时响应不是合法 JSON |

#### 14.1.2 `PlatformHttpError`：主动失败与降级

`PlatformHttpError`（平台 HTTP 受控异常）是 handler 可直接使用的异常类型：

```python
from specialized.builder import PlatformHttpError
```

它接收三个参数：

```python
PlatformHttpError(
    error_code="http_upstream_status_error",
    message="第三方天气接口暂不可用。",
    diagnostics=[response.diagnostics],
)
```

- `error_code`（错误码）：建议使用 `http_` 前缀；平台自动失败使用上表中的标准错误码。对于业务语义上的 4xx / 5xx，可使用 `http_upstream_status_error`。
- `message`（错误说明）：面向用户或运行详情展示的简短说明；不得拼接 token、secret、完整响应正文或完整 headers。
- `diagnostics`（脱敏诊断）：可传 `response.diagnostics` 或已有脱敏诊断列表；不得自行放入 query、请求体、响应体、Authorization、Cookie 或密钥。

网络、超时、secret、大小限制和 JSON 解析失败会由 `context.http` 自动抛出 `PlatformHttpError`。4xx / 5xx 则会先返回 `PlatformHttpResponse`，由 handler 按业务语义决定是否让当前子编排失败：

```python
from specialized.builder import PlatformHttpError


async def fetch_weather(step_context):
    response = await step_context.http.get(
        "https://api.example.com/weather",
        timeout_ms=5000,
    )
    if not response.is_success:
        raise PlatformHttpError(
            error_code="http_upstream_status_error",
            message=f"第三方天气接口返回异常状态：{response.status_code}。",
            diagnostics=[response.diagnostics],
        )

    return {
        "status": "completed",
        "output": response.json(),
    }
```

Output Pipeline 会捕获该异常，把当前 step 与当前 pipeline 标记为 failed，并保留 `error_code`、`message` 和脱敏 diagnostics。`PlatformHttpError` **不会直接终止整个 Agent Run**；它当前只表达子编排失败。若接口失败后仍希望继续回答，handler 应捕获异常并返回一个 completed 的降级结果：

```python
from specialized.builder import PlatformHttpError


async def fetch_weather(step_context):
    try:
        response = await step_context.http.get("https://api.example.com/weather")
        if not response.is_success:
            raise PlatformHttpError(
                "http_upstream_status_error",
                f"第三方天气接口返回异常状态：{response.status_code}。",
                [response.diagnostics],
            )
        return {"status": "completed", "output": response.json()}
    except PlatformHttpError as exc:
        return {
            "status": "completed",
            "output": {
                "source_status": "degraded",
                "message": "实时天气暂不可用，已跳过第三方数据。",
            },
            "diagnostics": exc.diagnostics,
        }
```

#### 14.1.3 `PlatformRunAbort`：显式终止整个 Agent Run

当业务上已经确认当前 Run 不能继续时，handler 可以主动抛出 `PlatformRunAbort`。它和 `PlatformHttpError` 的区别是：`PlatformHttpError` 只让当前 step / pipeline failed；`PlatformRunAbort` 会让平台停止后续 pipeline step、基座模型正文、followup 和 Memory 写回，并把 Run 统一收为 failed。

```python
from specialized.builder import PlatformRunAbort


async def fetch_order(step_context):
    response = await step_context.http.get(
        "https://api.example.com/orders/123",
        timeout_ms=5000,
    )
    if response.status_code == 404:
        raise PlatformRunAbort(
            "order_not_found",
            "订单不存在，已终止当前查询。",
            [response.diagnostics],
        )
    return {"status": "completed", "output": response.json()}
```

使用口径：

| 场景 | 推荐做法 |
|------|----------|
| 接口超时、网络错误、JSON 解析失败，只想让当前子编排失败 | 让 `context.http` 抛 `PlatformHttpError`，或主动抛 `PlatformHttpError` |
| 第三方 4xx / 5xx 后仍能降级展示 | handler 捕获异常并 return `status="completed"` 的降级结果 |
| 业务确认无法继续整个 Agent Run | 主动抛 `PlatformRunAbort(error_code, message, diagnostics)` |

`PlatformRunAbort` 的 diagnostics 仍必须脱敏，不得包含 Authorization、Cookie、token、secret、URL query、完整 headers、请求正文或响应正文。外置 handler 不应直接调用 RunService、数据库、SSE writer 或 runtime 内部方法改 Run 状态；终止只能通过这个异常表达。

### 14.2 `output_pipeline(...)`

| 参数 | 类型 | 必填 | 默认值 | 枚举 / 限制 | 做什么 |
|------|------|------|--------|-------------|--------|
| `key` | string | 是 | 无 | 不得为 `text_only` | output_policy 引用的 pipeline key |
| `artifact_kind` | string | 是 | 无 | 与 `output_structured.kind` 对齐 | 产物类型 |
| `output_type` | string | 是 | 无 | 见枚举 | pipeline 最终输出类型 |
| `steps` | list[string] | 是 | 无 | 非空、不可重复 | 串行 step key 列表 |
| `final_contract` | string | 否 | 空 | 结构化类型建议填写 | 最终输出契约 |
| `final_schema` | string | 否 | 空 | `final_contract` 兼容别名 | 等价于 `final_contract` |
| `failure_policy` | string | 否 | `fail_fast` | 见枚举 | 失败策略 |

#### 14.2.1 `artifact_kind`、最终产物和 `specialized_state.update`

如果你的专项只回答普通文本，不需要 Output Pipeline，也不会产生最终结构化产物状态。只有当 intent 的 `output_policy` 指向某个 `output_pipeline.key` 时，平台才会执行子编排，并在子编排结束后把最终产物同步到专项状态。

`artifact_kind` 的作用不是控制模型怎么生成内容，而是告诉平台“这个 pipeline 最后产出的东西属于哪一类产物”。平台会用它作为 `specialized_state` 里的字段名：

| 你填写的 `artifact_kind` | 平台最终状态字段 | 适合什么专项 |
|--------------------------|------------------|--------------|
| `workflow` | `specialized_state.workflow` | 工作流 JSON 生成 |
| `document_analysis_markdown` | `specialized_state.document_analysis_markdown` | 文档解析 Markdown 报告 |
| `contract_review_report` | `specialized_state.contract_review_report` | 合同审查报告 |

所以 `artifact_kind` 不是固定写法。请按自己的业务产物命名，例如 `workflow`、`report`、`analysis_result`、`document_outline`。名字确定后不要随便改，因为历史恢复、状态读取、归档和前端消费都会按这个 key 找最终产物。

一次结构化输出的事件顺序通常是：

```text
pipeline.started
pipeline.step.started
pipeline.step.output.completed
pipeline.step.completed
pipeline.completed
specialized_state.update
```

前五类 `pipeline.*` 是子编排事件，用来展示“子编排开始、步骤运行、步骤输出、子编排完成”。最后的 `specialized_state.update` 不是子编排事件，它是平台状态同步事件，表示“最终产物已经写回专项运行状态”。

`specialized_state.update` 的典型结构如下：

```json
{
  "event_type": "specialized_state.update",
  "payload": {
    "specialized_intent": "workflow_create",
    "specialized_intent_family": "workflow_generation",
    "specialized_state": {
      "workflow": {
        "status": "completed",
        "schema_version": "1",
        "name": "报销流程",
        "nodes": [],
        "edges": []
      }
    }
  }
}
```

用户开发时要记住三件事：

| 问题 | 正确理解 |
|------|----------|
| 我要不要自己发 `specialized_state.update`？ | 通常不要。你只需要声明 `output_pipeline.artifact_kind`，并让最后一步返回最终产物；平台会自动同步。 |
| `specialized_state.update` 是不是子编排的一部分？ | 不是。它发生在 `pipeline.completed` 之后，属于专项运行状态同步。 |
| 我能不能输出自己的产物类型？ | 可以。请按业务命名，例如 `workflow`、`report`、`analysis_result`、`document_outline`。 |
| 最后一步返回的东西会去哪里？ | 一方面会按 `output_visibility` 进入可见输出或 trace；另一方面会按 `artifact_kind` 写入 `specialized_state.{artifact_kind}`。 |
| `output_structured.kind` 和 `output_pipeline.artifact_kind` 为什么建议一致？ | 一个声明“这个专项支持什么产物”，一个声明“这个 pipeline 最后提交什么产物”。一致后用户、平台、归档和排障都能对上。 |

### 14.3 Output Pipeline 枚举

`output_type` 表示这个 step 或 pipeline 产出的“内容形态”：

| 枚举值 | 中文含义 | 适合输出什么 | 是否通常需要 `output_contract` |
|--------|----------|--------------|-------------------------------|
| `json` | JSON 对象 / 数组 | 工作流 schema、页面 schema、结构化配置 | 需要 |
| `text` | 普通文本 | 一段说明、短结论、纯文本摘要 | 可省略 |
| `markdown` | Markdown 文档 | 分析报告、大纲、说明书、富文本摘要 | 可省略 |
| `code` | 代码 | Python、TypeScript、SQL 等代码片段 | 需要，建议说明语言或 schema |
| `yaml` | YAML 配置 | 配置文件、声明式资源 | 需要 |
| `table` | 表格数据 | 行列结构、对比表、清单 | 需要 |
| `file_ref` | 文件引用 | 已生成文件的路径、URI、引用 ID | 需要 |
| `binary_ref` | 二进制引用 | 图片、压缩包、二进制对象引用 | 需要 |
| `internal` | 内部中间结果 | 只给后续 step 消费，不给用户看 | 可省略 |

可省略 `output_contract` 的类型：

```text
text
markdown
internal
```

`output_visibility` 表示输出给谁看：

| 枚举值 | 中文含义 | 主聊天可见吗 | 适合什么 |
|--------|----------|--------------|----------|
| `internal` | 内部结果 | 不可见 | 给下一个 step 用的中间数据 |
| `trace` | 追踪可见 | 主聊天不可见 | 排障、运行详情里需要看，但不想打扰用户 |
| `preview` | 预览可见 | 可见 | 中间草稿、大纲、预览结果 |
| `final_artifact` | 最终产物 | 可见 | 用户最终需要消费的报告、JSON、文件引用 |

`reasoning_visibility` 表示模型深度思考怎么展示：

| 枚举值 | 中文含义 | 主聊天展示吗 | 适合什么 |
|--------|----------|--------------|----------|
| `visible` | 用户可见 | 展示真实 reasoning | 用户需要看到分析过程的产物生成 step |
| `trace_only` | 只进追踪 | 不在主聊天展示 | 内部校验、转换、提取等过程 |
| `hidden` | 隐藏原始 reasoning | 不展示原始 reasoning | 安全、权限、策略判断等敏感过程 |

`failure_policy` 表示 pipeline 出错后怎么办：

| 枚举值 | 中文含义 | 适合什么 | 当前行为提示 |
|--------|----------|----------|--------------|
| `fail_fast` | 立即失败 | schema 错误、关键 step 失败时不能继续 | 默认值；失败后停止后续 step |
| `fallback_to_text` | 降级文本 | 产物失败但还能给用户普通说明 | 首版保留策略字段，实际要看运行接线 |
| `require_user_fix` | 需要用户修正 | 缺输入、格式不对、需要用户补材料 | 首版保留策略字段，真实交互需后续完善 |

`input_from` 表示当前 step 从哪里拿输入：

| 枚举值 | 中文含义 | 适合什么 |
|--------|----------|----------|
| `previous_step` | 上一步输出 | 默认串行流水线 |
| `original_input` | 用户原始输入 | 第一个 step 需要直接处理用户输入 |
| `run_input` | 运行输入 | 与 `original_input` 同类，用于运行入口输入 |
| `intent_context` | 意图上下文 | 需要读取 intent、family、slots 等语义结果 |
| `memory_context` | 记忆上下文 | 需要读取平台注入的只读记忆上下文 |
| `step:<step_key>` | 指定某一步输出 | 当前 step 需要跳过上一 step，读取更早的中间产物 |

`PipelineStepResult.status` 表示 step 执行结果：

| 枚举值 | 中文含义 | 使用后会怎样 |
|--------|----------|--------------|
| `completed` | 已完成 | 继续后续 step |
| `failed` | 已失败 | 按 `failure_policy` 处理；默认停止 pipeline |
| `skipped` | 已跳过 | 表示 step 被主动跳过；首版主要作为结果信封枚举 |
| `needs_user_input` | 需要用户补充 | 表示缺用户输入；真实多轮修正交互不作为首版验收 |

标准事件：

| 事件 | 中文含义 | 什么时候出现 |
|------|----------|--------------|
| `pipeline.started` | 子编排开始 | 命中 pipeline policy 后 |
| `pipeline.step.started` | 某一步开始 | 每个 step 执行前 |
| `pipeline.step.completed` | 某一步完成 | step 返回 `completed` 后 |
| `pipeline.step.failed` | 某一步失败 | step 返回失败或异常转换为失败后 |
| `pipeline.completed` | 子编排完成 | 全部 step 成功后 |
| `pipeline.failed` | 子编排失败 | 任一关键 step 失败并停止后 |
| `artifact.created` | 产物已创建 | 有 `artifact_ref` 时才产生 |

`artifact.created` 只有拿到 `artifact_ref` 时才产生。当前首版没有真实持久化 artifact store 验收，只有 builder-local 受控写入与事件。

主聊天里的展示行为：

| 你怎么配置 / 返回 | 主聊天会看到什么 | 自动展开 / 收起行为 |
|-------------------|------------------|----------------------|
| `reasoning_visibility="visible"` | step 的模型推理以 `reasoning.delta` 流式展示 | 推理进行中自动展开；遇到 step 输出、状态更新或最终正文后自动收起 |
| `reasoning_visibility="trace_only"` | 推理只进运行追踪，不在主聊天展示 | 主聊天不出现推理块 |
| handler 直接返回完整 `output` | 前端收到 `pipeline.step.output.completed` | 子编排输出块显示“已完成”，默认收起，用户可手动展开查看完整产物 |
| handler 流式返回 delta | 前端收到 `pipeline.step.output.delta` | 输出生成中自动展开，完成后自动收起 |
| `output_visibility="preview"` | 中间产物在主聊天可见 | 适合大纲、草稿、预览结果 |
| `output_visibility="final_artifact"` | 最终产物在主聊天可见 | 适合最终报告、JSON、文件引用 |
| `output_visibility="internal"` / `trace` | 主聊天不展示产物正文 | 适合只给后续 step 使用或仅排障查看 |

最常见组合：

| 目标 | 推荐配置 |
|------|----------|
| 想让用户看到模型思考过程，但产物不要边生成边刷屏 | `reasoning_visibility="visible"`，handler 最后一次性返回完整 `output` |
| 想让用户只看到最终产物，不看到思考过程 | `reasoning_visibility="trace_only"`，`output_visibility="final_artifact"` |
| 想展示一个中间大纲，再展示最终报告 | 大纲 step 用 `output_visibility="preview"`，最终 step 用 `output_visibility="final_artifact"` |
| 想让中间结果只给下一步用 | 中间 step 用 `output_visibility="internal"`，下一步 `input_from="previous_step"` |

### 14.4 当前内置 contract

代码内置校验的结构化 contract 只有 `workflow_schema.v1`。它要求输出为 JSON object，至少包含：

| 字段 | 要求 |
|------|------|
| `schema_version` | 必须为 `"1"` |
| `name` | 非空 |
| `nodes` | 非空数组 |
| `edges` | 数组 |
| node | 必须有非空 `id`；不能重复 |
| node type | 必须包含 `start` 和 `end` |
| edge | `source` / `target` 必须引用已存在 node |

### 14.5 handler 内优先使用 `context.native_capability.generate(...)`

当 Output Pipeline step 需要让模型生成结构化 JSON 时，小白用户优先使用 `context.native_capability.generate(...)`。它不是新的能力挂载方式，也不会出现在能力中心；它只是 handler 里面的受控模型调用 helper。

它适合放在 `pipeline_step(..., handler=你的函数)` 指向的 handler 里，不要写在 `manifest.yaml`、`with_capability_asset(...)` 或 `with_capability_template(...)` 里。

先判断是否应该用它：

| 你的 step 要做什么 | 是否推荐用 `context.native_capability.generate(...)` | 原因 |
|--------------------|-----------------------------------------------|------|
| 让模型填写一组固定字段，再生成 Markdown 报告 | 推荐 | 模型只填 slots，compiler 负责拼最终报告，弱模型更稳 |
| 一次生成多个组件、动作、配置项 | 推荐 | 开启 `allow_plan_items=True` 后可以输出多个受控 item |
| 生成页面 schema、工作流 schema、结构化配置 | 推荐 | 能校验 capability 白名单、slots_schema 和禁止字段 |
| 只要一段普通自然语言回答 | 不推荐 | 直接普通文本输出更简单 |
| 你已经自己写好了 JSON 解析、校验、修复和 compiler | 可不用 | 自由模型调用仍可用，但错误处理要自己承担 |

一句话理解：`allowed_capabilities` 是“允许模型选择的受控动作菜单”，`slots_schema` 是“每个动作要填的表单”，`compiler` 是“把填好的表单变成最终展示产物的硬编码函数”。

运行顺序：

```text
pipeline_step(handler=build_page_skeleton)
-> build_page_skeleton(context)
-> context.native_capability.generate(...)
-> 模型只输出 {"capability": "...", "slots": {...}}
-> 平台校验 JSON、capability 白名单、slots_schema 和 forbidden_fields
-> 平台调用 compiler
-> compiler 返回的结果才是用户看到的最终产物
```

handler 的入参 `context` 是 `PipelineStepContext`。常用字段是：`context.inputs`（当前 step 输入）、`context.intent_context`（意图上下文）、`context.memory_context`（记忆上下文）和 `context.context`（请求顶层传入的自由上下文）。

用户真正要写的只有三块：

| 要写什么 | 写在哪里 | 必填 | 作用 |
|----------|----------|------|------|
| `pipeline_step(...)` | builder 链式声明 | 是 | 告诉平台这个 step 叫什么、输入从哪里来、输出怎么展示、handler 是哪个 |
| `context.native_capability.generate(...)` | step handler 函数内部 | 是 | 调模型生成受控 IR，并做校验 |
| `compiler` 函数 | `agent_definition.py` 普通 Python 函数 | 是 | 把模型 IR 编译成用户最终看到的 output |

不要把 `compiler` 理解成平台外部配置。它就是你自己写的 Python 函数，可以硬编码规则、补默认值、过滤不可信字段、拼 Markdown、组装 JSON schema。模型返回的 JSON 不直接展示，compiler 返回的 `output` 才展示。

最小示例：

```python
async def build_page_skeleton(context):
    return await context.native_capability.generate(
        task="根据用户需求生成页面骨架",
        input_data={
            "step_input": context.inputs,
            "run_context": context.context,
        },
        allow_plan_items=True,
        allowed_capabilities=[
            {
                "capability": "page.create",
                "semantics": "创建页面，填写页面标题。",
                "slots_schema": {
                    "type": "object",
                    "required": ["title"],
                    "properties": {"title": {"type": "string"}},
                },
            },
            {
                "capability": "page.add_card",
                "semantics": "添加一个卡片组件。",
                "slots_schema": {
                    "type": "object",
                    "required": ["title", "variant"],
                    "properties": {
                        "title": {"type": "string"},
                        "variant": {"type": "string", "enum": ["metric", "plain"]},
                    },
                },
            },
        ],
        forbidden_fields=["page_schema_json", "children", "id", "action", "name", "arguments"],
        compiler=compile_page_skeleton,
        output_type="json",
        output_contract="page_schema.v1",
    )


def compile_page_skeleton(ir_payload, context):
    items = ir_payload.get("plan_items") or [ir_payload]
    title = "未命名页面"
    cards = []
    for item in items:
        if item["capability"] == "page.create":
            title = item["slots"]["title"]
        if item["capability"] == "page.add_card":
            cards.append({"componentName": "Card", "props": item["slots"]})
    return {"componentName": "Page", "props": {"title": title}, "layout": cards}
```

#### 14.5.1 非流式产物 + 流式推理怎么写

如果你想要“推理过程流式展示，但子编排产物一次性完成后收起”，按下面写：

```python
(
    builder.use_append_intent(families=[document_family])
    .output_structured(
        kind="document_analysis_markdown",
        schema="document_analysis_markdown.v1",
        schema_version="1",
    )
    .pipeline_step(
        key="document.outline.generate",
        title="生成文档大纲",
        output_type="markdown",
        handler=generate_document_outline,
        input_from="original_input",
        output_visibility="preview",
        reasoning_visibility="trace_only",
    )
    .pipeline_step(
        key="document.brief_analysis.generate",
        title="生成文档简洁解析",
        output_type="markdown",
        handler=generate_brief_analysis,
        input_from="previous_step",
        output_visibility="final_artifact",
        reasoning_visibility="visible",
    )
    .output_pipeline(
        key="document_analysis_brief",
        artifact_kind="document_analysis_markdown",
        output_type="markdown",
        steps=[
            "document.outline.generate",
            "document.brief_analysis.generate",
        ],
    )
)
```

这段配置的效果：

| 配置 | 效果 |
|------|------|
| `document.outline.generate` 用 `input_from="original_input"` | 第一步直接读取用户原始输入 |
| 大纲 step 用 `output_visibility="preview"` | 主聊天会出现一个“生成文档大纲已完成”的预览块 |
| 大纲 step 用 `reasoning_visibility="trace_only"` | 大纲生成的推理不打扰主聊天，只进追踪 |
| 简洁解析 step 用 `input_from="previous_step"` | 第二步拿第一步的大纲作为输入 |
| 简洁解析 step 用 `output_visibility="final_artifact"` | 主聊天会出现最终产物块 |
| 简洁解析 step 用 `reasoning_visibility="visible"` | 用户能看到模型分析过程流式展示 |
| handler 最后一次性 return | 前端收到 `pipeline.step.output.completed`，产物块默认收起，用户点开查看 |

`generate_brief_analysis` 可以这样写：

```python
async def generate_brief_analysis(context):
    outline = str(context.inputs or "").strip()
    return await context.native_capability.generate(
        task="基于文档大纲生成简洁解析的结构化填槽结果。",
        input_data={
            "outline": outline,
            "analysis_focus": "重点提炼主题、关键信息、风险和建议。",
        },
        allowed_capabilities=[
            {
                "capability": "document.brief_analysis.compose",
                "semantics": "基于文档大纲填写主题、重点、风险和建议。",
                "slots_schema": {
                    "type": "object",
                    "required": ["theme", "key_points", "risks", "suggestions"],
                    "properties": {
                        "theme": {
                            "type": "string",
                            "description": "一句话判断文档主题；信息不足时写明信息不足。",
                        },
                        "key_points": {
                            "type": "array",
                            "description": "文档重点列表，建议 2 到 5 条。",
                            "items": {"type": "string"},
                        },
                        "risks": {
                            "type": "array",
                            "description": "风险或不确定性列表，没有明确风险时给出信息不足提示。",
                            "items": {"type": "string"},
                        },
                        "suggestions": {
                            "type": "array",
                            "description": "下一步建议列表，建议 1 到 4 条。",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        ],
        forbidden_fields=[
            "markdown",
            "final_markdown",
            "content",
            "children",
            "id",
            "action",
            "name",
            "arguments",
            "function_call",
            "tool_calls",
        ],
        compiler=compile_brief_analysis_markdown,
        output_type="markdown",
        prompt_rules=[
            "只填写 slots，不要直接生成 Markdown 正文。",
            "不要编造大纲没有的信息；信息不足时在对应 slot 中说明信息不足。",
        ],
        examples=[
            {
                "input": "会议纪要大纲，关注行动项。",
                "output": {
                    "capability": "document.brief_analysis.compose",
                    "slots": {
                        "theme": "会议围绕项目排期和责任分工展开。",
                        "key_points": ["已明确目标和时间节点", "需要继续确认负责人"],
                        "risks": ["部分依赖未给出截止时间"],
                        "suggestions": ["补齐负责人和截止时间", "形成后续跟踪清单"],
                    },
                },
            }
        ],
    )
```

`compiler` 可以这样写：

```python
def compile_brief_analysis_markdown(ir_payload, context):
    slots = ir_payload.get("slots") if isinstance(ir_payload, dict) else {}
    slots = slots if isinstance(slots, dict) else {}
    outline = str(context.inputs or "").strip()
    theme = str(slots.get("theme") or "信息不足，暂无法判断文档主题。").strip()
    key_points = normalize_list(slots.get("key_points"), "信息不足，暂无法提炼明确重点。")
    risks = normalize_list(slots.get("risks"), "未发现明确风险；仍建议结合完整原文人工复核。")
    suggestions = normalize_list(slots.get("suggestions"), "补充完整文档原文、目标读者和关注点。")
    output = "\n".join(
        [
            "## 文档简洁解析",
            "",
            "### 1. 主题判断",
            f"- {theme}",
            "",
            "### 2. 重点提炼",
            *[f"- {item}" for item in key_points],
            "",
            "### 3. 风险提示",
            *[f"- {item}" for item in risks],
            "",
            "### 4. 下一步建议",
            *[f"- {item}" for item in suggestions],
            "",
            "### 附：文档大纲",
            outline or "- 暂无可用大纲。",
        ]
    )
    return {
        "status": "completed",
        "summary": "已生成文档简洁解析。",
        "output": output,
    }


def normalize_list(value, fallback):
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item or "").strip()]
        return items or [fallback]
    text = str(value or "").strip()
    return [text] if text else [fallback]
```

这个例子里，模型只能输出：

```json
{
  "capability": "document.brief_analysis.compose",
  "slots": {
    "theme": "...",
    "key_points": ["..."],
    "risks": ["..."],
    "suggestions": ["..."]
  }
}
```

模型不能直接输出 Markdown。Markdown 是 `compile_brief_analysis_markdown(...)` 生成的，所以弱模型即使不会稳定写完整报告，也只要会填字段。

`generate(...)` 字段：

| 字段 | 类型 | 必填 | 默认值 | 填什么 | 使用后会怎样 |
|------|------|------|--------|--------|--------------|
| `task` | string | 是 | 无 | 当前 step 要模型完成的任务 | 进入 prompt，帮助模型选择 capability |
| `input_data` | JSON 可序列化数据 | 是 | 无 | `context.inputs`、上一步输出或整理后的 dict | 平台序列化后给模型看；不要传 DB session、service、client |
| `allowed_capabilities` | list[dict] | 是 | 无 | 模型允许选择的 Native Capability 菜单 | 模型只能输出这里声明的 capability |
| `allow_plan_items` | bool | 否 | `False` | 是否允许模型一次输出多个 item | `False` 只接受单个 `{capability, slots}`；`True` 可生成多个组件 / 动作 |
| `max_plan_items` | int | 否 | `8` | 最多允许几个 item | 超过会失败为 `native_capability_plan_too_long` |
| `forbidden_fields` | list[string] | 否 | 平台默认旧协议字段 | 禁止模型输出的字段 | 顶层、item 顶层、slots 内递归出现都会失败或进入 repair |
| `compiler` | callable | 是 | 无 | 处理模型 JSON IR 的函数 | 校验通过后才调用；它返回的结果才是最终 output |
| `output_type` | string | 建议必填 | 当前 step 的 `output_type` | 最终 output 类型 | 用于事件、展示和结果归一 |
| `output_contract` | string | 条件必填 | 当前 step 的 `output_contract` | 最终 output 契约 | 结构化 / 文件型产物建议填写 |
| `prompt_rules` | string / list[string] | 否 | 平台基础规则 | 额外提示，比如“只输出严格 JSON” | 提高弱模型稳定性 |
| `examples` | list | 否 | `[]` | 给模型看的正例 | 提高弱模型稳定性，不作为硬校验 |
| `repair_enabled` | bool | 否 | `True` | 是否允许一次受控修复 | 只能修复成合法 IR，不能修成最终产物 |

`allowed_capabilities` 每一项字段：

| 字段 | 类型 | 必填 | 填什么 | 使用后会怎样 |
|------|------|------|--------|--------------|
| `capability` | string | 是 | 能力名，例如 `page.add_card` | 模型必须原样输出；大小写漂移不会自动猜 |
| `semantics` | string | 是 | 告诉模型什么时候用这个能力 | 进入 prompt，帮助弱模型选择 |
| `slots_schema` | dict | 是 | 这个能力要填哪些 slots | 平台按 JSON Schema 子集校验，失败不调用 compiler |
| `examples` | list | 否 | 这个能力的正例 | 只给模型参考 |
| `negative_examples` | list | 否 | 这个能力的反例 | 只给模型参考 |

`slots_schema` 首版支持：

| 字段 | 用途 |
|------|------|
| `type` | 字段类型，支持 `object/array/string/number/integer/boolean/null` |
| `required` | object 下哪些字段必填 |
| `properties` | object 下每个字段的 schema |
| `description` | 给模型看的字段说明 |
| `enum` | 限定可选值 |
| `items` | array 每一项的 schema |

模型允许输出单个 item：

```json
{"capability":"page.create","slots":{"title":"客户管理"}}
```

开启 `allow_plan_items=True` 后，模型可以一次输出多个 item：

```json
{
  "plan_items": [
    {"capability":"page.create","slots":{"title":"客户管理"}},
    {"capability":"page.add_card","slots":{"title":"客户数","variant":"metric"}},
    {"capability":"page.add_card","slots":{"title":"成交额","variant":"metric"}}
  ]
}
```

同一个 capability 可以重复出现，用来一次生成多个同类组件。每个组件需要的字段不一样时，就把它们拆成不同 capability，每个 capability 写自己的 `slots_schema`。

`compiler` 是处理模型 JSON 的函数。模型只负责选择 capability 和填写 slots；compiler 负责把这些 IR 变成最终页面 schema、工作流 schema、Markdown、文件引用等产物。

compiler 可以是同步函数，也可以是异步函数：

```python
def compile_sync(ir_payload, context):
    return {"result": ir_payload}


async def compile_async(ir_payload, context):
    return {"result": ir_payload}
```

compiler 可以直接返回最终 output，也可以返回完整 `PipelineStepResult` 字典：

```python
return {"componentName": "Page", "props": {"title": "客户管理"}}

return {
    "status": "completed",
    "summary": "已生成页面骨架。",
    "output": {"componentName": "Page", "props": {"title": "客户管理"}},
}
```

错误码：

| 错误码 | 说明 | 用户该怎么改 |
|--------|------|--------------|
| `native_capability_json_parse_failed` | 模型输出不是严格 JSON | 增加 `examples`，或保留 `repair_enabled=True` |
| `native_capability_invalid_ir` | 顶层不是 `{capability, slots}` 或合法 `{plan_items:[...]}` | 检查 prompt 和示例 |
| `native_capability_plan_too_long` | item 数超过 `max_plan_items` | 调大 `max_plan_items` 或拆 step |
| `native_capability_forbidden_field` | 输出了禁止字段 | 检查 `forbidden_fields`；合法 slot 不要放进禁止列表 |
| `native_capability_not_allowed` | capability 不在白名单 | 把能力加入 `allowed_capabilities` 或修正模型示例 |
| `native_capability_slots_schema_failed` | slots 缺字段、类型错、enum 错 | 修正 `slots_schema` 或示例 |
| `native_capability_repair_failed` | 修复后仍不合法 | 增加更具体的 `examples` |
| `native_capability_compiler_failed` | compiler 缺失、异常或返回非法状态 | 修 compiler |
| `native_capability_output_contract_failed` | compiler 结果不符合最终契约 | 修 compiler 输出结构 |

和自由模型调用的区别：

| 写法 | 适合什么 | 谁解析模型 JSON | 谁校验 | 谁生成最终 output |
|------|----------|-----------------|--------|-------------------|
| `context.native_capability.generate(...)` | 页面、组件、工作流、结构化配置 | 平台 | 平台 | compiler |
| `context.model.generate(...)` | 自由文本、Markdown、你愿意自己解析的输出 | 你自己 | 你自己 | 你自己 |

自由 `context.model.generate(...)` 仍然可以用，但你要自己处理 JSON 解析、字段校验、错误码和最终 return。小白用户优先用 Native Capability 风格。

## 附件解析器

## 21. 附件解析器

附件解析器只用于补齐平台原生不支持的格式，例如 OFD 或特殊图片。PDF、DOCX、XLSX、CSV、TXT、MD 和常见图片仍由平台原生链路优先处理，不要为它们重复声明解析器。

你只负责提供“这个格式如何转换”；平台负责上传、`attachment_id`、文件存储、格式路由、解析任务、结果保存、大文件按需读取、安全预览、模型输入、配额和清理。

### 21.1 目录和 manifest

在三件套基础上，按固定目录增加解析器：

```text
your_external_agent/
  manifest.yaml
  bootstrap.py
  agent_definition.py
  parsers/
    ofd_parser.py
  parser-requirements.lock
  wheels/                         # 只有依赖第三方库时才需要
    example_ofd_library-1.2.3-py3-none-any.whl
```

`manifest.yaml` 中可选增加 `attachment_parsers`。但只要声明了某个解析器，
`formats` 中的每一个格式项都必须填写 `detection`，不能省略；不同解析器可以覆盖同一格式，同一个解析器不能重复声明相同格式。
后缀必须小写并带 `.`，格式检测只能用固定文件头或 ZIP 内固定条目，不能只相信文件名或浏览器 MIME。
`detection` 只能使用平台规定的 `magic_bytes` 或 `zip_entries` 结构。缺少 `detection`、
使用未知 `kind`，或只填写 `extension` / `mime_type`，都会在校验或发布时失败。

不要创建或打包 `parser_env/`。这是平台在发布期基于已审核 wheel 生成的只读目录；用户随包提交会被拒绝。

```yaml
attachment_parsers:
  - parser_id: ofd-v1
    parser_version: "1.0.0"
    formats:
      - extension: ".ofd"
        mime_type: "application/ofd"
        detection:
          kind: zip_entries
          required_entries:
            - "OFD.xml"
    entrypoint: parsers.ofd_parser:parse
    dependency_lock: parser-requirements.lock
```

固定文件头格式（例如 RTF）必须这样声明：

```yaml
formats:
  - extension: ".rtf"
    mime_type: "application/rtf"
    detection:
      kind: magic_bytes
      offset: 0
      bytes_hex: "7B5C727466"
```

ZIP 格式使用 `zip_entries`，并填写至少一个必须存在的固定条目；非 ZIP 格式使用
`magic_bytes`，填写文件头偏移和十六进制字节。不能用“没有固定检测规则”作为省略
`detection` 的理由；如果无法提供这两类检测规则，就不能把该格式声明为外置解析器格式。

### 21.2 解析函数

共享解析服务无需复制解析代码，可直接在 manifest 引用：

```yaml
shared_attachment_parsers:
  bindings:
    - service_id: "解析服务ID"
    - service_id: "另一解析服务ID"
      revision_id: "固定修订ID"
      extensions: [".rtf"]
      priority: 10
      enabled: true
```

只填 `service_id` 默认跟随服务当前已发布版本，显式 `revision_id` 固定对应修订。省略 `extensions` 使用首次成功校验的获准格式作为上限；显式格式必须为该版支持的非空子集，`null`、`[]` 均不合法。省略版本不能写成 `revision_id: null`。服务发布新版本后，跟随员工的新附件使用新版，不必逐员工更新发布；历史附件和重试仍使用原版本。固定绑定不自动升级。

在线开发先校验并保存草稿，再发布；上传包先预览确认引用，界面自动提交匹配的确认记录。内容或员工配置改变后需重新校验，不能手工伪造基线。首次导入另一环境须重新确认当地服务 ID，不按同名替换。新版没有获准格式、增加外发目标、被停用或无发布指针时显示不可用，不扫描旧版本兜底；增加格式或外发权限须重新确认。面试分别展示绑定策略、当前实际版本和最新发布版本，固定旧版不会被最新版本标签替代。

包内绑定只读，平台可追加自己的共享解析服务；包更新不删除平台绑定。同服务双来源分别保留版本策略和上限，启用包策略优先，包来源移除后恢复平台原策略。不同解析器覆盖同一格式时，系统先筛选资格和授权，再优先内置，其次二开，二开按优先级从高到低、稳定身份排序；用户无需手工选择。执行失败不自动换解析器重跑。

入口只能是同步函数 `parse(input, output)`。`input.path` 是当前文件的只读临时路径；不要读取其他路径，不要访问网络、数据库、对象存储、模型、会话或附件 ID。

```python
def parse(input, output):
    source = open(input.path, "rb").read()
    text = extract_text_from_ofd(source)
    output.add_text(text, locator={"unit": "page", "index": 1})
    output.finish()
```

只能通过 `output` 返回四类受控内容：

| 方法 | 用途 | 上限 |
|------|------|------|
| `add_text(text, locator=...)` | 原文或 OCR 文本 | 最多 512 块，单块 16,384 字符 |
| `add_table(columns=..., rows=..., locator=...)` | 表格 | 最多 20 张表，单表最多 500 行、100 列 |
| `add_field(name, value, locator=...)` | 票据或表单字段 | 最多 200 个字段 |
| `create_preview_path(filename)` | 获取当前容器 tmpfs 内的预览写入路径 | 文件名只能是 PNG/JPEG/WebP 单文件名 |
| `add_preview_file(path, mime_type=..., locator=...)` | 提交 PNG/JPEG/WebP 临时预览 | 最多 10 张，单张最多 1 MiB |

文字、表格单元格和字段值合计最多 20 万字符。`locator` 只允许 `unit`、`index`、可选 `label` 和仅 sheet 可用的 `range`；不要在其中塞 JSON、路径、身份或业务数据。

文档解析至少输出 `text`、`table`、`field` 之一；图片解析至少输出 `preview`。最后必须调用 `output.finish()`。不要手写 JSON、Base64、下载链接、对象路径或自定义返回字段。

图片解析器不负责“看懂图片”。它只把平台暂不支持的图片格式转换为安全预览；平台会重新校验、去元数据并规范化保存，之后是否送给视觉模型仍由模型能力和数据外发策略决定。

图片解析器写预览的最小方式：

```python
from pathlib import Path


def parse(input, output):
    png_bytes = convert_to_png(Path(input.path).read_bytes())
    preview_path = output.create_preview_path("page-1.png")
    Path(preview_path).write_bytes(png_bytes)
    output.add_preview_file(
        preview_path,
        mime_type="image/png",
        locator={"unit": "page", "index": 1},
    )
    output.finish()
```

### 21.3 离线依赖

`parser-requirements.lock` 是整个 Bundle 唯一共享的依赖锁文件，不是每个解析器各自的
依赖清单。一个 Bundle 中的所有 `attachment_parsers` 都必须引用这个固定文件；它描述的是
整个 Bundle 解析环境需要的第三方依赖闭包。

如果 Bundle 内所有解析器都只使用 Python 标准库，`parser-requirements.lock` 可以为空，且不需要
创建 `wheels/`。只要其中任一解析器需要第三方依赖，依赖就必须放进共享的 `wheels/`，并在
共享的 `parser-requirements.lock` 固定名称、版本和 SHA-256：

```text
example-ofd-library==1.2.3 --hash=sha256:<wheel_sha256>
```

当需要核对当前 Workspace 中的 `.whl` 哈希时，开发助手应调用
`workspace_get_file_hash`。该工具由平台还原 Workspace 内部保存的二进制内容后，
直接对原始字节计算 SHA-256，只返回文件路径、大小、版本和哈希，不返回 Base64 正文。
不要用 `workspace_read_file` 的 `content_hash`，也不要对 TsStudio 内部二进制文本表示自行计算哈希。

例如 OFD 解析器只使用标准库，而 RTF 解析器使用 `striprtf` 时，两者仍共同引用同一份非空
`parser-requirements.lock`。这表示 Bundle 环境中预置了 `striprtf`，是合法配置；OFD 没有
import 它只是冗余依赖，不是校验失败。平台不会逐个分析解析器是否 import 了 lock 中的每一项。

真正会导致依赖校验失败的是共享 lock 与 `wheels/` 不一致，例如缺少或多出 wheel、名称或版本不一致、
wheel 不是 `py3-none-any`、包含禁止内容，或 lock 中的 SHA-256 与还原后的原始 wheel 字节不一致。
TsStudio 中 `.whl` 的内部二进制文本表示不是 wheel 原始字节，不能对那段表示文本计算 SHA-256。

只接受 `py3-none-any` 的纯 Python wheel。不要提交源码包、原生扩展、平台专用 wheel、`.pth`，也不要在解析时下载依赖、执行 `pip install` 或编译。

平台在发布/激活时离线校验依赖和解析器：先安全展开审核通过的 wheel 为只读 `parser_env`，再在同一套受控容器隔离中只导入解析器模块，不调用 `parse`。解析任务只加载这个预构建环境，不会联网、`pip install`、编译或重复安装依赖。依赖、声明、隔离环境或探针任一不通过时，该版本不会启用解析器；上传文件不会绕过平台改为直接执行你的代码。

仓内有一个可复制的零依赖样例：

可复制的附件解析器样例请从控制台接口文档页下载“脚手架”后，按本节增加解析器目录。

它只处理自定义 `.sampledoc` 文件，用于展示目录、manifest、`parse(input, output)`
和输出方法；它不假装支持 OFD。需要 OFD 时，把真实离线 pure-Python 依赖放进
`wheels/` 并替换格式鉴别和解析函数。

### 21.4 你不能做的事

- 不能生成、读取或回传 `attachment_id`。
- 不能指定 Parser、Bundle Revision、对象路径、Grant 或模型输入。
- 不能直接保存 Artifact、预览、索引或数据库记录。
- 不能在 `bootstrap.py`、`agent_definition.py`、提示词或前端直接调用解析器。
- 不能访问网络、外部解析服务、宿主机命令或其他用户文件。

### 21.5 TsStudio 在线开发边界

TsStudio 的在线工作区可以直接创建和编辑 `manifest.yaml`、`parsers/*.py` 与空的
`parser-requirements.lock`，也可以通过顶栏上传、目录右键上传或文件树拖拽上传文件。
因此零依赖解析器可以直接在工作台中开发；第三方纯 Python wheel 可上传到 `wheels/`
目录，再编辑 lock 文件填写固定版本和哈希。

上传支持多文件，文本文件可在编辑器中打开；`.whl`、图片等二进制文件只作为包资源保存，
不能在文本编辑器中打开或在线重命名。平台会在发布/校验打包时还原二进制原始字节。不要
尝试在解析器运行时联网下载、`pip install` 或编译依赖。

本地开发验收时，平台可以用独立 Python 子进程执行当前工作区的解析器，不需要给后端
Docker 权限。只有下面三项同时满足时才启用这个模式：

```env
APP_ENV=dev
ATTACHMENT_PARSE_WORKER_ENABLED=true
ATTACHMENT_BUNDLE_PARSER_ENABLED=true
ATTACHMENT_PARSER_EXECUTION_MODE=local
```

本地模式仍使用相同的输入协议、`parse(input, output)`、结果校验、超时、输出上限和临时
目录清理；它没有 Docker 的网络隔离、seccomp、非 root、只读根文件系统和 cgroup 硬限制，
只用于本地开发和功能验收。生产或其他非开发环境必须使用：

```env
ATTACHMENT_PARSER_EXECUTION_MODE=sandbox
ATTACHMENT_BUNDLE_PARSER_ENABLED=true
```

生产模式还必须完成 Linux Docker、镜像、seccomp、cgroup v2 和真实隔离探针验收；平台
不会把本地模式作为生产环境的自动回退。

## Builder SDK 标准契约

## 3A. 外置 SDK 简化入口

外置开发者优先通过 `create_external_agent(context)` 声明专项，而不是直接拼装 `SpecializedAgentBundle`。该入口必须只封装现有 `RegistryContext` 能力，不绕过能力治理和运行前门禁。

最小链式入口：

```python
create_external_agent(context).use_generic_intent().output_text().register()
```

决策边界：

| 需求 | SDK 方法 |
|------|----------|
| 使用通用意图 | `use_generic_intent()` |
| 在通用意图集合后追加外置 family / intent，并为新增项配置槽位 / 校验 / 澄清 | `use_append_intent(factory, family="...")` |
| 替换为专项自定义意图 | `use_replace_intent(factory, family="...")` |
| 启用记忆模块 | `use_memory()` |
| required / optional 能力资产 | `with_capability_asset("capability_id", required=True/False)` |
| 输出声明 | `output_text()` / `output_structured(...)` |
| 普通聊天正文 | `persona.system_prompt` + 平台基座模型 |
| 可选结构化专项产物 | `on_generate_artifact(handler)`；兼容期受限保留 `on_generate(handler)` |

外置专项注入 `AgentProfile` 前必须提供 `persona.system_prompt`。推荐由 manifest 提供；SDK 的 `with_persona(system_prompt=...)` 仅作为高级代码覆盖入口。

## Pipeline 最小协议

### 5.3.3 Output Policy / Pipeline 最小协议

`OutputPolicy` 解析顺序固定为：

```text
intent.output_policy
→ family.output_policy[intent_key]
→ family.default_output_policy
→ base_family.output_policy
→ text_only
```

`text_only` 不得携带 `pipeline_key`。artifact policy 必须指向已注册 `OutputPipeline`，且 `artifact_kind`、`output_type` 与 pipeline 一致。

Pipeline Step handler 只能接收 `PipelineStepContext` 受控上下文；上下文可包含 run / agent 身份、intent_context、只读 memory、能力快照、输入、previous step、平台模型门面、产物型能力门面、`http` 受控 HTTP 门面、artifact_store、diagnostics 与 pipeline 事件出口，不得暴露 DB session、底层 service、ToolExecutor、MCP client 或 provider client。

## 外置脚手架运行编排

## 运行编排怎么选

| 目标 | 改 `agent_definition.py` 的哪一块 |
|------|-----------------------------------|
| 只做普通专属问答员工 | 保留 `.use_generic_intent()` 和 `.output_text()` |
| 新增文档分析、合同审查等专项任务 | 把 `.use_generic_intent()` 改成 `.use_append_intent(families=[...])` |
| 完全自管意图集合 | 使用 `.use_replace_intent(families=[...])`；当前不作为真实平台 Run E2E 验收 |
| 绑定平台已有能力 | 在能力中心列表复制“SDK 绑定 ID”，填入 `.with_capability_asset("...")` |
| 随插件带入 Skill / MCP 能力 | 在插件目录新增 `capabilities/skills/*.yaml` 或 `capabilities/mcp/*.yaml`，再用 `.with_capability_template("skill:...")` 或 `.with_capability_template("mcp:.../...")` 引用 |
| 生成 JSON / Markdown / 工作流 schema | 参考文档示例补 `.output_structured(...)`、`.pipeline_step(...)`、`.output_pipeline(...)` |
| 在子编排里调第三方接口 | 在 Output Pipeline handler 中使用 `step_context.http.get(...)` / `post(...)` / `request(...)` |

## 通用文本 Agent 示例

# 示例 01：通用意图 + 普通文本

适合第一版专属员工：只需要换人设、能聊天、能问答、能分析，不需要新增专项意图。

```python
"""
@file: agent_definition.py
@description: 最小通用文本外置 Agent 示例

主要功能:
    - 复用平台公共意图
    - 使用普通文本输出
    - 提交外置专属 Agent Bundle
"""

from __future__ import annotations

from typing import Any

from specialized.builder.sdk import create_external_agent


def register_agent(context: Any) -> None:
    """
    注册外置专属 Agent

    作用：声明最小可运行的 generic + text 员工。
    主要功能：复用平台公共意图，使用普通正文输出，不绑定额外能力。
    """
    (
        create_external_agent(context)
        .use_generic_intent()
        .output_text()
        .register()
    )
```

运行效果：

- 用户输入仍走平台公共 Intent / Intent Family。
- 回复走普通聊天正文。
- 不执行 Output Pipeline。
- 不需要 SDK 绑定 ID。

## 追加文档分析示例

# 示例 02：追加文档分析专项意图

适合“公共意图还要保留，但我要新增文档分析任务”的定制。

```python
"""
@file: agent_definition.py
@description: append 文档分析外置 Agent 示例

主要功能:
    - 在公共意图集合上追加 document_analysis family
    - 声明可选文档整理能力
    - 使用普通文本输出
"""

from __future__ import annotations

from typing import Any

from specialized.builder.sdk import create_external_agent


DOCUMENT_ORGANIZE_SDK_BINDING_ID = "替换为能力中心复制的 SDK 绑定 ID"


def register_agent(context: Any) -> None:
    """
    注册文档分析专家

    作用：新增文档分析专项意图，同时保留公共问答、分析、生成等通用意图。
    主要功能：命中文档分析时专项优先，未命中时公共意图兜底。
    """
    builder = create_external_agent(context)

    document_summary_intent = builder.intent(
        key="document_summarize",
        name="文档总结",
        description="用户希望总结、提炼或归纳一份文档或长文本。",
        examples=[
            "帮我总结这份文档",
            "提炼这篇材料的重点",
            "把下面内容整理成摘要",
        ],
        negative_examples=[
            "帮我生成一个工作流 JSON",
            "解释一下什么是 MCP",
        ],
        planner_hint=builder.planner_hint(
            # 文档分析本身依靠平台已装配的附件内容即可完成；
            # 外部整理能力只是可选增强，不能强制 Plan 调用。
            needs_capability=None,
            candidate_capabilities=[DOCUMENT_ORGANIZE_SDK_BINDING_ID],
            plan_template_key="standard_analysis",
            success_criteria=[
                "先说明文档主题",
                "列出关键结论",
                "指出信息不足或风险点",
            ],
            risk_level="normal",
        ),
        output_policy="text_only",
    )

    document_risk_intent = builder.intent(
        key="document_risk_review",
        name="文档风险审查",
        description="用户希望找出文档中的风险、缺口、矛盾或待确认事项。",
        examples=[
            "检查这份合同有什么风险",
            "帮我找出这份方案里的问题",
        ],
        negative_examples=[
            "把这段话翻译成英文",
        ],
        slots=[
            builder.slot(
                "document_text",
                required=True,
                ask="请提供需要审查的文档内容或附件。",
                extract_examples=["以下是合同正文：..."],
                validation_rule="必须包含可审查的文本内容。",
            )
        ],
        planner_hint=builder.planner_hint(
            # 风险审查同样不依赖外部能力；这里保留可选能力候选。
            needs_capability=None,
            candidate_capabilities=[DOCUMENT_ORGANIZE_SDK_BINDING_ID],
            plan_template_key="standard_analysis",
            success_criteria=[
                "按风险等级分组",
                "每条风险给出依据",
                "给出下一步建议",
            ],
            risk_level="medium",
        ),
        output_policy="text_only",
    )

    document_family = builder.intent_family(
        key="document_analysis",
        name="文档分析",
        description="识别用户是否要总结、审查、提炼或分析一份文档。",
        fallback_intent="document_summarize",
        boundary="只处理文档总结、文档风险审查、结构提取；普通问答、写代码、工作流生成交给公共意图。",
        trigger_keywords=["文档", "合同", "总结", "提炼", "审查", "风险"],
        out_of_scope=["工作流搭建", "页面生成", "模型调试"],
        intents=[document_summary_intent, document_risk_intent],
        default_output_policy="text_only",
    )

    (
        builder
        .use_append_intent(families=[document_family])
        .with_capability_asset(DOCUMENT_ORGANIZE_SDK_BINDING_ID, required=False)
        .use_plan(plan_template_key="standard_analysis")
        .output_text()
        .register()
    )
```

运行效果：

- 文档总结 / 风险审查会优先命中 `document_analysis`。
- 其他普通问题仍由公共意图兜底。
- `needs_capability=None` 表示能力只是可选增强；Plan 会结合上下文决定是否使用，不会因为该字段强制调用。
- `.with_capability_asset(..., required=False)` 表示能力缺失不阻断插件；它和 `needs_capability` 是两个独立开关。
- 如果能力必须存在，把 `required=False` 改为 `required=True`，并把两个 `planner_hint` 中的 `needs_capability` 改为 `True`；同时必须保留有效的 `candidate_capabilities`。
- 如果完全不需要外部能力，则删除 `.with_capability_asset(...)`，并把两个 `planner_hint` 改为 `needs_capability=False`、`candidate_capabilities=[]`。

文档内容来源版本：builder-runtime-knowledge-1.3.3
