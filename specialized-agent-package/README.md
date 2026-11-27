---
document_type: 外置专属 Agent 说明
purpose: 基于宿主真实能力生成 form-agent.v1 表单设计提案
---

# 表单设计 Agent

该插件遵循[第三方开发指南](../specialized-agent-development-guide.md)的三件套结构；行为边界由 manifest、受控 IR 和本包业务规范共同约束：

- `manifest.yaml`：员工身份、人设、执行边界和委派说明。
- `bootstrap.py`：平台要求的 `register_specialized_agent(context)` 入口。
- `agent_definition.py`：append 意图、Plan、结构化输出和单一提案 Pipeline。
- `form_generation/proposal.py`：统一提案入口、状态路由和字段动作编译。
- `form_generation/drafts.py`：单一动作草稿封装、动作 ID 与依赖结构校验。
- `form_generation/guidance.py`：场景推荐校验、检查点输入与平台等待式澄清、答案映射和取消。
- `form_generation/field_guidance.py`：字段槽位冻结、原生分组回答、补丁整体复验、候选换组和回退。
- `form_generation/action_rules/`：表单动作注册表与组件动作、规则/公式动作校验。
- `form_generation/components/`：公共属性定义与统一注册；`definitions/` 按组件名维护属性文件，`definitions/_shared/` 维护实际复用的族处理。
- `form_generation/properties.py`：属性提案编排、宿主授权与批次依赖校验。
- `form_generation/host.py`：宿主组件目录和节点身份读取。
- `specs/`：本 Agent 的动作、属性和组件业务规范。

## 业务规范与维护入口

先读 [规范入口](./specs/README.md)，再按改动阅读 [动作规范](./specs/actions.md)、[公共属性规则](./specs/properties.md) 或 [组件目录](./specs/components/README.md)。组件属性与专有处理放在 `components/definitions/` 下的同名文件，如 `NumberPicker.py`；`Input.TextArea` 使用 `InputTextArea.py`。新增组件复用公共属性，仅将多个组件实际共享的规则和处理提取到 `_shared/`，由 `registry.py` 统一注册，不继续集中到提案编译器。

本文采用用户已确认的单一 actions 草稿契约，保留模型输入 IR 和既有动作语义。2026-11-23 用户指定的本地设计器已接入 PC Flow 既有属性处理器的最终草稿复验、原子应用和 appliedActionIds 回执；ai-chat 同步读取真实完成事件信封。**本地验证不代表三端已部署，也不扩展未实现的规则、联动、复制或查询/撤销卡片。** 不提供旧格式解析、迁移或结构版本分流。

## 支持范围

字段生成支持单层 Flow 表单（包括已保存画布），依据实际结构和宿主能力校验，不限制 FormSchema 版本：

- 根据自然语言一次性生成完整字段列表，例如“员工入职登记表”。
- 支持 `Input`、`Input.TextArea`、`DatePicker`、`TimePicker`、`NumberPicker`、`SelectSingle`、`SelectMulti`、`CheckboxGroup`、`Switch`。
- 字段定义只编译为顶层 `form.add_component` actions；ai-chat 从同一动作草稿派生展示行，用户编辑直接写回 payload。
- 修改现有字段属性或选项，在根层或真实锚点前后插入，删除、移动组件。
- 仅转换明确标记为未保存的新字段；有损转换先澄清。
- 在宿主明确声明时生成字段/表单规则和公式动作。
- 处理 `applied`、`rejected`、`conflict` 等回执，并区分提案、应用和保存。

首期不支持容器嵌套、槽位、Grid、直接生成持久化节点 ID、直接应用或保存。Agent 不操作 React、DOM、画布、Store 或浏览器存储。

## 宿主上下文

每次 Run 应在顶层 `context` 提供：

- `requestId`：本次业务请求关联 ID。
- `schemaVersion`：可选的 FormSchema 元数据，不设版本白名单，也不要求与 `currentSchema.schemaVersion` 一致；省略时从当前 Schema 推导。Action 契约版本和 `target.revision` 并发检查独立保留。
- `target`：`schemaId`、`formId`、`revision`，可附带 `appId`、`layoutId`。
- `currentSchema`：当前完整 Schema；新建时至少提供空 `fields`。
- `selection`：发送时的真实 `nodeId` 和未保存状态。
- `canvas`：`layoutMode: flow` 和 `isBlank`。
- `capabilities`：组件目录、每个组件的可写属性、动作和可选规则目录。
- `fieldNameRules`：命名正则、最大长度、保留名和可选字段数上限。
- `optionRules`：至少包括选项数量上限。
- `supportedActionVersions`：设计器实际支持的动作协议版本。
- `executionResult`：前次提案的真实执行回执。

缺少 `form.add_component`、动作版本、组件目录或空白画布证明时，编译器拒绝生成完整表单。字段 `name`、`clientRef`、选项值和可写属性均由 Python 编译器校验。

组件候选按本地九种组件与本轮宿主可用目录取交集，组件级 `supported:false` 不开放。字段生成、原始新增和转换缺少组件目录时返回 `unsupported`；生成、原始新增、属性或选项更新缺少明确且非空的 `writableProps/editableProps` 时也拒绝。字段定义未知槽位、生命周期动作未知 payload 字段不再静默忽略；具体原因写入 summary 和 diagnostics，不交付部分动作。其余非法字段值或引用继续按校验失败中止。

目录授权针对本轮新增或修改，不要求完整快照中的未修改节点也在新增目录中。例如画布已有 `DepartmentSelect`，用户要求“生成学生信息表：字段有姓名”时，保留部门节点，仅追加已授权的 `Input` 姓名字段；不能因此整批拒绝，也不生成额外部门字段。既有节点仍须满足单层结构、非空组件名与唯一非空 ID，命名、位置、字段数和非空画布禁止覆盖等检查保留。请求新增或修改未授权组件仍明确拒绝。详见[组件动作边界](./specs/actions.md#组件动作)。

例如“生成一个禁用的姓名字段”：姓名可用 `Input`，但没有明确注册的禁用语义及写入规则时，返回“姓名字段可使用 Input，但暂时还不支持禁用，当前没有已声明的禁用属性及写入规则”。不能猜 `disabled/readOnly/edit=false/access` 或用禁止手工编辑替代，也不能忽略禁用后交付 ready。此语义选择通过提示规则和示例约束；确定性校验拦截实际 IR 中的未知属性，真实模型能否完整保留用户要求仍需平台验收。

## PC 双确认（2026-11-25）

本节规定当前唯一可写契约。新建经 supportedPresentationKinds 协商后使用 `shared.form-create-confirm`，保持 `form_agent_proposal.v1`、动作版本 `1.0` 和 `replace_empty_form`，只含 add。已有表单经三项能力协商后统一使用 `form_change_proposal.v1` / `form_change_actions.v1` / `append` / `shared.form-change-confirm`，支持字段动作与既有节点的属性 change 单项或混合；纯 append、纯属性也升级。缺少任何必需能力均明确拒绝，包括纯字段与纯属性路径。

混合输入为 `proposal.begin.result_kind=form_changes`（位于 slots），保持 IR 项目和输出 actions 的相对顺序。未指定位置的新增字段可以与删除已有字段同批，编译器按执行顺序计算追加下标及动作依赖。目标必须含 schemaId/baseRevision，属性还需 catalogVersion。新节点属性由已授权新增 props 表达。聚合与分组由 UI 投影，不增加第二份执行数据。查询与撤销保持独立；属性 rule/linkage 暂无新协议，明确拒绝。完整协商字段、保守冲突限制和真实编译 JSON 见[动作规范](./specs/actions.md#2026-11-25-pc-双确认与统一变更)。不提供旧卡片、旧可写属性包装器、旧字段动作版本或 result 格式兼容。

## 输出协议

逻辑最终 output 固定为 `{form_proposal: proposal}`，只含一份完整提案，不另包 component 或复制 props.proposal。保留 `protocol=form-agent.v1` 与既有 contractVersion；新建为 `form_agent_proposal.v1`，所有已有表单修改为 `form_change_proposal.v1`，查询为 `form_property_query.v1`。状态为 ready、needs_clarification、unsupported 或 no_change；非 ready 不带执行动作或可应用确认卡。

修改提案的共同结构：

- 顶层 `mode`：完整空白表单为 replace_empty_form，增量为 append；不得覆盖非空画布。
- 顶层 `actionVersion`：新建固定 1.0，已有表单修改固定 form_change_actions.v1；撤销单独使用 form_property_actions.v1。顶层 schemaVersion 仅是可选 FormSchema 元数据，不设白名单。
- 顶层 `actions`：每项为 `{actionId,action,payload,dependsOn,display}`，display.selectedByDefault 是布尔值。动作 ID 唯一稳定，依赖使用本批其他 actionId 且无环；引用本批新节点须依赖在前创建动作。
- 属性变更的 `preconditions.before={exists,value?}` 是原状态；新值只在 payload.value。set/copy 带 value，clear/unset/reset 不带 value，不附 after。可选 display.effects 仅说明派生影响。
- 普通修改确认的 `presentation` 仅含 kind/title：新建为 shared.form-create-confirm，已有表单变更为 shared.form-change-confirm。没有 result、validation，也没有重复的 fields/items/changes 或动作副本。

查询保留 readOnly 的 component_property_query presentation.items，无 actions；撤销保留 component_property_undo 的事务展示与顶层 actions，二者均不进入普通确认卡。完整字段和属性 JSON 示例见[三端接入说明](../doc/ai-chat-property-edit-integration.md)。

新增字段 payload 保留 clientRef、componentName、合法 props 和 target，不带持久化 ID。clientRef 以小写字母开头，其后允许小写字母、数字、下划线或连字符，唯一且原样贯穿动作和回执；它是新节点身份，UI 勾选使用 actionId。业务 name 另按 fieldNameRules 校验。已有节点以真实身份修改并保留无关属性；宿主分配新节点真实 ID 后回传 clientRef 映射，不由聊天构造。增量 append 不表示追加旧卡片列表，更不表示保存。

## 已有画布追加与最新列表

宿主每轮发送最新 `currentSchema` 和 `target.revision`，不能只发送上轮新增字段。以 `tests/fixtures/student-form-data.json` 为例，现有字段为姓名、学号、性别、出生日期、班级、联系电话、备注：

- “追加监护人和监护人电话”：输入 IR 使用 `form_fields + append` 并省略定位 target；默认插入到最后一个 `componentCategory=field` 的组件之后，缺省 category 视为字段。编译后的新增动作有明确 root index；末尾若有非字段组件，新增字段插入到它之前。
- “在学号后新增监护人和监护人电话”：模型从当前快照定位学号，也可将原样标签交给编译器唯一匹配；编译器按顺序生成 root 下标 `2`、`3` 的新增动作，避免多个字段在同一锚点后插入时顺序颠倒。
- 标签重名、目标不存在、选择为空时返回 `needs_clarification`，没有执行动作；不会静默追加到末尾。可以用 `anchorName` 或真实 `anchorNodeId` 消除歧义，也可以用 `useSelection: true` 引用本轮选中字段。
- 新增字段 name、clientRef 不得与已有字段冲突；`maxFields` 对已有字段加新增字段的总数生效。即使 `canvas.isBlank=true`，非空 `currentSchema.fields` 也不能被 `replace_empty_form` 覆盖。

受控 IR 示例：

```json
{
  "plan_items": [
    {
      "capability": "proposal.begin",
      "slots": {
        "summary": "在学号后新增监护人字段。",
        "result_kind": "form_fields",
        "mode": "append",
        "target": {"kind": "relative", "anchorLabel": "学号", "position": "after"}
      }
    },
    {
      "capability": "form.field.define",
      "slots": {
        "client_ref": "guardian",
        "component_name": "Input",
        "label": "监护人",
        "name": "guardian",
        "required": false
      }
    }
  ]
}
```

返回提案只包含本次动作，不附已有画布的完整快照或第二份展示变更列表。字段编译器输出明确 root index，按执行顺序递增；原始 root 动作省略 index 表示物理根列表末尾，与字段 IR 默认插入在末尾非字段之前不同。标签匹配、目标选择仍是输入 IR 的解析行为，最终动作固定真实目标。

ai-chat 从 actions 派生预览并维护唯一草稿。取消或删除新增建议是移除草稿动作；删除画布已有节点是 form.remove_component，同样使用字段卡且默认选中，名称和类型从宿主快照读取。纯删除卡点击“删除”后才提交所选动作并由宿主移除字段，点击前不改画布；成功提示尚未保存并保留宿主撤销。引用本批新 clientRef 的动作须依赖创建动作 actionId，缺选依赖不得静默代选。只选择连续新增中的部分项时须复验位置；仅可对整批纯新增、显式 root index 连续且可证明独立的序列按保留顺序重算 index，其他复杂位置子集拒绝或重新生成。完整规则见[动作规范](./specs/actions.md)。

类型转换的默认值、属性迁移与有损决定交给已支持处理器，不能从展示投影伪造完成。应用后刷新真实 Schema；规则、公式和选项的完整引用校验也依赖宿主实际处理器。

### 宿主接入要求（本地既有属性处理器已接入，其他能力须逐项验证）

1. 完整提案到达后校验状态、contractVersion、actionVersion、kind 与业务白名单，按 proposalId 去重。普通确认从 actions 派生展示，以 actionId 勾选；选项保留真实 value，不能以展示标签重建动作。
2. 用户编辑直接写入唯一草稿的 payload。提交 `{proposal: 最终已编辑且已选择的提案}`，不另传选择 ID、edits 或未编辑原载荷。Apply 幂等键通过宿主独立通道传递；/invoke 幂等不能替代 Apply。
3. 宿主把提交草稿作为待验证请求，重新检查固定目标、target.baseRevision、真实能力、动作版本、before、依赖、引用、位置顺序与最终候选。生成时校验不授权编辑后的动作；不允许仅因它属于原提案就跳过校验。
4. 在副本上由受支持处理器验证全部语义后原子提交，记录独立 Apply 幂等、提案消费状态和一个撤销事务。遇到冲突刷新 context 重生成，不能应用旧下标。
5. 应用只更新画布。保存由设计器与既有后端接口完成；真实 Schema、revision、unsaved 状态及新增 ID 映射由宿主回传，聊天展示以真实结果为准。

本仓库负责 Agent 生成、确定性编译和返回协议。ai-chat 已交付真实 context 的 formDraftCapabilities 支持；属性前端直接调用 `bridge.apply({proposal, applyRequestId})`，按 appliedActionIds 读取回执，无 register 步骤。applyRequestId 独立于 proposal，生成校验不授权编辑后的载荷。指定本地设计器已接入 PC Flow 既有属性处理器的新解析、草稿复验、原子应用和回执；保存仍走独立链路，其他能力不因本次接入自动开放，不能将本地验证视为三端已部署证明。

## 运行编排

`design_form` intent 指向单一 `form_proposal_generation` Pipeline，依次执行 `form_requirement_preparation`（内部生成并冻结提案或问题）、`form_requirement_confirmation`（平台等待式澄清）、原 `form.proposal.generate` 最终步骤（交付或根据答案重新编译）。前两步只输出 internal 数据，最终仍只有 `{form_proposal: proposal}` 与一次 `form.proposal.completed`。具体步骤 key 以注册常量为准。

### 场景引导与槽位补齐

“生成一个审批表单”等缺少业务用途、也没有明确字段清单的请求，模型返回 `proposal.needs_clarification`，以 `scenario_options` 提供三个符合当前语境的 `{label,description}`。编译器检查数量、非空、重复和保留入口，分配稳定 ID 并追加“其他”，形成四项 `clarificationOptions`。审批场景示例为请假、采购、报销；其他主题动态生成，不能照搬审批菜单。语境匹配由模型规则和示例约束，真实模型效果须平台验收。明确用途或字段时直接生成；属性、目标歧义不强制凑四项，继续使用已有 question/choices。能力不足仍 unsupported，不静默缩减需求。

等待步骤使用 SDK `context.clarification.request`，稳定 key 为 `form_requirement`，最多配置三轮。选择“其他”时在独立 key `form_requirement_other` 收集文本；这是第二次请求，仍允许自由文本。候选在前置检查点冻结，等待步骤重入只重放同一问题与答案，不调用模型。普通选择只按冻结候选 ID 解析标签，不能提交候选 value 覆盖语义。回答和原始输入一起交给原生成器，最新可获得的本轮宿主 context 仍是编译依据。用户取消返回非执行 no_change（平台若已终止 Run 则不会继续 handler）。

场景分支支持一个引导问题及可选的“其他”文本补充；补齐后若仍有新歧义，最终返回非执行 needs_clarification，不无限追问或猜测。缺失宿主上下文不向业务用户追问技术参数。SDK 未提供澄清入口时保留非执行提案，消费端可展示问题，不假装已创建 interrupt。原始需求、问题和答案只通过步骤检查点传递，不使用模块全局会话状态、不自行创建新 Run。

平台负责 `interrupt.waiting(type=clarification)`、resolve、轮次、终态和恢复；表单 Agent 不自行发布这些事件。回答只确认需求，最终 actions 仍须用户另行确认后由宿主验证应用。原 Run 恢复不保证画布实时刷新，宿主必须继续校验 revision；冲突时刷新上下文重生成。resolve 在接口参考中标为部分可用，本地 SDK 替身测试不代表线上链路已部署。

### 字段级分组引导（1.2.17）

已有非空单层 Flow 表单插入字段组合，且字段槽位存在歧义时，模型应提供 `proposal.needs_clarification.slots.field_draft`。`field_guidance.py` 冻结一句话预填、完整字段组合、插入位置及真实候选；按字段将语义、控件类型、校验、数据来源、字段属性分别分组，只显示有歧义的组。明确需求继续直通；场景推荐仍为三个加其他。

语义未定（如“添加一个字段”）推荐完整字段名称、控件和有依据的属性；手机号等语义明确时仅展示实际歧义槽位。完整语义候选与属性组不可重叠写入，跨控件残留属性只允许显式 unset 并整体复验。前置生成后检查结构化 clarification_kind；未分类普通澄清或字段引导缺草稿时，宿主上下文齐备才允许一次受控修复，再失败明确中止；等待重入不重跑模型。缺上下文明确报告，分类依赖受控模型语义判断，不以简单关键词替代。

候选携带 Agent 内部结构化 patch，标签为最终结果、最长16字，不以选择/设置/配置开头。每页最多5条真实推荐（通常3至5条，候选不足如实少给），另有自定义入口；不为凑数造能力。原生 SDK 仅接收冻结的 id/label，完整分组一次提交；回答查表合并，整体复验后直接调用 `form.field.define` 编译链，不再调用自然语言生成器。自定义采用当前槽位 JSON 对象；不支持自由文本转义为规则。

目前字段定义七槽位的实际边界不变：校验仅能表达 required，数据来源组仅能表达有依据的静态 options，字段属性组仅 placeholder；不能设置动态数据源、11位/正则、禁用或其他字段属性。明确要求无法表达时必须 unsupported，不能通过更换类型或省略值降级。未明确的必填不自动设为 true，类型标签不能成为规则依据。

分组回答后提供独立复核操作：生成提案、回退上次修改、重新生成推荐。重新生成在已冻结且已验证的候选池中换一组，保留确认值并提供保留当前值入口；候选不足不会凭空追加。回退恢复本轮回答前的字段值与确认状态；四次分组修改为上限，超限失败关闭。所有问题/选项均绑定确定性的草稿 ID 与递增版本；重入只重放原生澄清记录，不重跑模型，旧版本回答、缺题和宿主快照变化均拒绝。具体 IR、接入限制及示例见[动作规范](./specs/actions.md#字段槽位草稿)和[三端接入说明](../doc/ai-chat-property-edit-integration.md#22-字段级槽位引导agent-1217)。

这不是已实现的 ai-chat chip UI：当前实际可运行的是平台原生分组澄清加独立复核题。缺少 request_group 时保留非执行提案，不降级逐槽位追问。最终仍是唯一 actions 草稿，选择推荐或生成提案均不授权应用或保存。

### 生成与交付约束

1. 从 handler 的 `step_context.context` 归一化并隔离本轮宿主快照，不从历史对话补猜画布状态。生成器接收快照副本，编译器通过本轮闭包使用同一份权威快照；不再依赖 Native Capability 回调的第二个参数重新读取宿主状态，避免回调结构不同或旧数据造成误报、串单。
2. Native Capability 只生成受控 IR，根对象统一为 `{"plan_items":[{"capability":"...","slots":{...}}]}`；一个 `proposal.*` 状态，新建时再生成若干 `form.field.define`。
3. Python 编译器完成字段名、选项、组件、可写属性、单层 Flow、已有画布锚点和动作版本校验。平台回调仍使用文档签名 `(ir_payload, context)`，支持位置和关键字调用；第二个参数只用于脱敏诊断。handler 快照缺失 `currentSchema` 时返回 `HOST_CONTEXT_REQUIRED` 澄清；已有快照但缺少必要的 `capabilities` 或 `supportedActionVersions` 时返回 `HOST_CAPABILITY_REQUIRED` 的 unsupported。不从回调借用其他上下文，不生成动作；其余业务校验失败返回 `failed`、`form_proposal_validation_failed`、具体原因及 `abort_run: true`，阻止平台继续通用 `final_response`；不把无效提案作为成功结果。未知运行时异常仍交由平台处理。
4. Native Capability 的返回值先归一化为步骤结果字典，兼容普通映射和通过属性暴露 `status/output/diagnostics` 的 SDK 结果对象，避免因非 dict 返回值跳过后处理。失败结果保留 `error_code/artifact_ref` 及原始诊断，统一设置 `abort_run: true`；缺少最终提案也按失败终止。提示词始终约束设计器表单场景，失败后不转问 Excel、CSV 或重复索要已明确的字段。handler 的最终 `output` 仅为 `{ form_proposal: proposal }`；对校验通过且可展示的 `ready` 结果，Python 在原提案的 `presentation.kind` 使用对应注册组件 ID，不复制提案为 `component.props.proposal`，不接受模型任意指定组件 ID。平台标准 `pipeline.step.output.completed` 的事件类型和步骤键不变。
5. 保留原有的单次业务事件 `form.proposal.completed`，`block_id/title/status/proposal` 等原 payload 字段不变，仅移除重复 `component`；每个逻辑 output 或业务 payload 内完整提案只出现一次。不额外发布组件事件、骨架或逐字段事件。
6. ai-chat 对完整文本 JSON、state 快照、标准步骤、自定义业务事件及历史回放统一校验、投影并按 `proposalId` 去重。设计器仍在用户确认后通过独立 Apply 幂等键事务应用，保存和回传 ID 映射由宿主负责。

| 结果 | `presentation.kind` | ai-chat 行为 |
| --- | --- | --- |
| ready 新建 | `shared.form-create-confirm` | 从 actions 派生展示行，按 actionId 勾选并编辑同一草稿 |
| ready 已有表单变更（字段/属性/混合） | `shared.form-change-confirm` | 从 payload、preconditions 和 display 派生属性行 |
| 只读查询 | `component_property_query` | 保留 readOnly/items，不提供修改入口 |
| 事务撤销 | `component_property_undo` | 使用专用撤销入口，不能进入普通确认卡 |
| 澄清、无变更或失败 | 保留状态与领域语义 | 不渲染可应用确认卡 |

ready、有效契约、匹配 kind、注册组件与当前业务白名单必须同时满足。无效、未知或字段/属性错配 kind 不渲染，也不尝试另一种卡片兜底；kind 不授予执行资格。旧展示 kind、显式 component、result.actions 和旧字段/属性列表均不进入本次单一契约解析，不维护双格式历史分支。

步骤返回的顶层 `diagnostics` 保留平台原有诊断，并追加 `FORM_HOST_CONTEXT_TRACE`：`stage=handler/compiler`、入参类型、提取后的上下文类型、白名单内的协议键名，以及 `requestId/target/currentSchema/capabilities/supportedActionVersions` 的存在标记。compiler 记录 `compile_source=handler_snapshot`。不记录字段值、任意业务键名、Schema 内容、用户输入、业务 ID 或令牌，也不把诊断加入 `output` 或业务事件。可从 `pipeline.step.completed` 的 `diagnostics` 或 `specialized_builder.context.snapshot.output_pipeline_result.step_results[].diagnostics` 检查；事件透传以目标平台实际行为为准。handler 诊断同时记录 `native_result_type`，用于确认原生生成 helper 的实际返回类型。完整提案、业务事件和 handler 诊断同时缺失时，先检查是否运行了包含结果对象兼容修复的版本，再检查平台透传；新版本不再输出独立 component，不能用它的缺失判断异常。handler 完整、compiler 标记缺失时，快照绑定仍可正常编译。每轮缺失上下文仍返回澄清，不用默认画布绕过检查。

字段行和属性行都是唯一 actions 草稿的 UI 投影，不单独持有执行副本。选项标签用于展示，真实 value 与其他配置在 payload 中保留；用户编辑写回 payload，不能由卡片文案反推操作。/invoke 幂等键只防重复创建 Run，不能替代 Apply 幂等。标准步骤与业务事件透传、状态/历史持久化、SSE 断线补发及三端应用仍须在目标平台验证，本地检查不等于线上部署。

## 更新包与入口加载

`bootstrap.py` 使用 `from .agent_definition import register_agent`，由平台在固定 Revision 包命名空间中加载；包内模块全部使用相对导入，不手动注册全局模块或改写 `sys.path`。入口应通过平台包加载器导入，不能作为独立脚本执行。

上传 ZIP 根目录包含 `manifest.yaml`、`bootstrap.py`、`agent_definition.py`、`README.md`、`form_generation/` 及 `specs/`；递归包含动作和组件子包源码、业务规范。发布包不包含 `tests/`、测试数据、`__pycache__/` 或隐藏文件；测试在源码目录运行。升级保持原 `agent_key`、`plugin_key`，提升包版本，通过“更新代码包”上传并重新校验发布。

请使用仓库根目录的 `python3 -B package_agent.py` 生成上传包，避免直接压缩整个源码文件夹。脚本将已读取并校验的 UTF-8 文本写入 ZIP，再直接检查 ZIP 条目的文本编码、Python 语法和相对导入依赖；任一失败都不会替换正式产物。回归测试直接从 ZIP 原始字节加载两个独立 Revision 的入口，并通过 SDK 接口替身验证注册调用；真实 SDK 的兼容性仍需在平台校验。

遇到 `bootstrap_load_failed` 时，应检查 ZIP **内部原始字节**。本机能打开或解压后能执行，不能证明平台拿到的是可执行源码：文件透明加密可能让压缩条目包含 `%TSD-Header-###%`、空字节等二进制内容，导致平台报 `source code string cannot contain null bytes`。这类条目应通过上述脚本从可读取的源码重新打包，不应通过修改相对导入规避。

## 校验

本地测试无需平台 SDK：

```sh
python3 -B -m unittest discover -s specialized-agent-package/tests -q
```

回归须覆盖四种提案状态、9 种生成组件、唯一 actions 草稿、无重复快照、无持久化 ID、空白 Flow 限制、字段命名、保留名、重复 clientRef、选项完整性、可写属性、增量动作目标、依赖及位置选择子集和唯一最终事件。`test_capability_refusal.py` 额外覆盖缺失/空能力目录、禁用及未知属性拒绝、整批拒绝、真实权限保留、宿主候选交集与最终拒绝事件。`test_output_preview.py` 的单提案回归需验证字典、通用映射、属性对象和不可变 dataclass 返回值均只输出一次完整提案、唯一业务事件及诊断，并保留失败对象的错误码和中止标记；本次结果由实施会话回填。`test_host_context.py` 额外验证不同形态与过期 compiler 上下文、本轮快照隔离、并发运行互不串单、缺失 handler 快照仍拒绝动作，以及上下文诊断脱敏和原生失败诊断保留。旧三组件编译器只作为兼容模块保留，不注册为生产 Pipeline，也不参与新建表单输出。

平台验收仍需提供真实 `specialized.builder` SDK，并验证完整 JSON 交付、ai-chat 一次性渲染、设计器事务执行、Apply 幂等、一次撤销、保存重开、`clientRef -> final ID` 回执、SSE 重连去重、取消和 revision 冲突处理。


## 七组件属性能力

属性路径使用既有受控 IR 与确定性提案编译，支持 `Input`、`Input.TextArea`、`NumberPicker`、`DatePicker`、`TimePicker`、`SelectSingle`、`SelectMulti`。自然语言意图由平台 Native Capability 解析；Python 负责目标、能力、值及输出校验，不依赖独立关键词分类器。

- `proposal.begin.slots.result_kind=property_changes`：后接 `form.property.change`。
- `property_query`：后接 `form.property.query`，只读输出，不要求写动作版本。
- `property_undo`：后接 `form.property.undo`（`transaction_id`）；必须提供宿主真实可撤销事务和已声明动作。
- `property_changes` 还支持 `form.property.rule`（`operation=add/replace/remove`、`rule_type`、`rule_id`、`value`）和 `form.property.linkage`（`operation`、`linkage_type`、`linkage_id`、`value`），目标字段与 change 一致。仅允许宿主已注册的 ruleCatalog/linkageCatalog、结构化 schema 和处理器；没有运行能力时返回 unsupported。
- 查询产物 form_property_query.v1 的 status=ready，保留 component_property_query 的 readOnly/items，无 actions；撤销保留 form_property_proposal.v1 / form_property_actions.v1 和 component_property_undo 专用展示，顶层 actions 中使用 form.undo_property_transaction，不能交给普通属性处理器。
- 属性 change 使用 `node_id` 或 `use_selection=true`，也可使用 `node_label/node_name` 唯一匹配；操作包括 `set/clear/unset/reset/copy`，复制提供 `source_node_id/source_property`。
- 属性输出保留 form_change_proposal.v1；presentation 仅含 shared.form-change-confirm 的 kind/title。顶层 actionVersion=form_change_actions.v1；form.apply_property_change 名称和语义不变；属性 rule/linkage 暂时拒绝，before、依赖和派生影响位于对应动作，不附 items 或 after。
- 读取并保留顶层 `resolvedProperties`、`history`、`rules`、`linkages`；支持直接 context 映射或平台 StepContext。目录 `capabilities.components.<component>.properties`、`catalogVersion`、`nodePolicies` 应与宿主执行器保持一致。
- 目录需明确每个属性的 `valueSchema`、`operations`、默认/重置语义、复合 handler。未声明能力不生成可执行结果；不存在/歧义目标进入澄清。
- 宿主负责将语义动作交给属性 helper，执行 revision/before 检查、逐项勾选、事务、撤销和保存；本包不修改真实画布，也不宣称规则服务或保存已经接通。

示例受控 IR：

```json
{
  "plan_items": [
    {"capability": "proposal.begin", "slots": {"result_kind": "property_changes", "summary": "设置当前字段为必填"}},
    {"capability": "form.property.change", "slots": {"use_selection": true, "property": "required", "operation": "set", "value": true, "selected": true}}
  ]
}
```

宿主待办、context、字段/属性 JSON 示例和最终草稿提交见[三端接入说明](../doc/ai-chat-property-edit-integration.md)。平台仍使用同一个 Pipeline 的 form_agent_proposal.v1 结构化输出通道，内部保留既有 contractVersion；此次只调整业务提案结构，不新增平台接口、事件或 SDK 能力，实际透传仍需联调。

打包使用 Python 标准库：

```sh
python3 package_agent.py
```

在仓库根目录执行。脚本先运行回归测试，再检查 Python 语法和最终 ZIP 条目，按 manifest 版本生成上传包；当前版本为 `1.2.20`（`specialized-agent-package-1.2.20.zip`），修复既有未授权组件误阻止追加字段的问题，生成或上传不代表三端已部署。上传包根目录为插件入口，不包含测试、缓存或本地资料。


### 规则、联动和撤销上下文约定

规则/联动尚无已约定的新可写协议，旧目录和旧动作版本不能授权这些操作。受控属性能力清单仅发布 change/query/undo；收到旧 rule/linkage IR 时明确拒绝。

属性规则/联动暂不支持。撤销动作 form.undo_property_transaction 继续要求 supportedActionVersions[动作名] 包含 form_property_actions.v1，并要求真实 history.current 或平铺 history 中的 {canUndo:true,transactionId,revision} 与当前 revision 一致。撤销保持 form_property_proposal.v1 专用信封，不是普通属性可写建议。

属性 reset 需要注册 reset 操作。titleAlign/titlePosition 或 `reset.source=inherited` 删除局部覆盖；其他属性优先读取目录 `default`，其次使用已明确的内置默认值。受保存锁保护的属性必须提供真实保存状态，不能因状态缺失当成新字段。

JSON Schema 仅支持编译器已实现的受控子集，未实现关键字（如 `$ref`、`not`、`format`）会明确拒绝。公式默认值、缺少引用检查的选项删除及未注册规则/联动不生成执行动作，需宿主补齐专用处理器后另行接入。


## 1.2.1：真实设计器协议兼容

- 支持 NumberPicker 的成组 `numericRange` 和 SelectMulti 的 `selectionLimit`。
- `resolvedProperties[nodeId][property].stored` 为宿主提供的语义配置状态；经过结构校验后用于 before。查询有效值使用 `resolvedValue` 与 `source`。
- `textLengthLimit` 的 set 输入遵守宿主数值 schema；clear/reset 不把内部派生配置作为 set 输入校验。原状态在 action.preconditions.before，新值只在 payload，不输出 after。TimePicker 动态当前时间支持面板的 `dynamicAnchor="today"`。
- 以上修复已整合到当前 `1.2.19` 包和单一 actions 契约；上传发布后仍需宿主和聊天包完成对应协议接入，不能仅更新 Agent 就认为画布执行已就绪。

### Agent 能力更新后宿主需要做什么

| Agent 更新类型 | 设计器 / ai-chat 所需操作 |
| --- | --- |
| 提示词、同义词、错别字识别优化，输出契约不变 | 更新 Agent 发布版本，复测真实请求与旧案例；通常无需修改宿主代码 |
| 新组件或新属性，宿主已有同语义处理器 | 核对组件范围、类型、默认/清空/继承语义、保存锁和布局条件；测试通过后才加入当前能力目录 |
| 新复合属性或新执行效果 | 先实现并测试宿主处理器、预览和事务差异，再更新目录/策略/解析值；Agent 不得仅靠 writableProps 宣称支持 |
| 新动作、新展示或破坏性契约变化 | 同步升级 ai-chat 解析/卡片、设计器动作分派/执行器，未知动作或版本明确拒绝；本次单一 actions 契约不维护旧输出兼容路径 |
| 新规则、公式、联动、远程校验 | 先接通真实运行时/服务、字段引用校验及权限，再注册 capability；无运行时继续返回不支持 |

发布前至少验证：宿主当前 context → 生产 Python 编译器 → 完整 SSE 卡片 → 勾选子集 → 真实 Store 与回执 → 下一轮新 Schema/revision。覆盖手工编辑冲突、重复应用、清空/重置、撤销以及原有新增字段流程。应用成功只表示未保存的画布更新；持久化仍须单独验证保存回读。目录是宿主真实支持能力的交集，Agent 升级不得自动开放尚未实现的属性。


## 字段生成与属性能力共存

当前合并包保留远端的动作版本隔离修复，不修改 ai-chat 或设计器。单层 Flow 字段新建、已有画布追加和增量编辑按实际结构与能力判断，不限制画布 Schema 版本；同一 context 可以声明字段生成和属性编辑。按本轮意图分派，不把不同动作协议混在一个结果中。

### 版本分层与选择规则

| 输出字段 | 含义 | 选择规则 |
| --- | --- | --- |
| proposal.schemaVersion | 可选画布 Schema 元数据 | 原样保留宿主值，不设版本白名单 |
| proposal.contractVersion | 本轮提案契约 | 字段生成用 `form_agent_proposal.v1`，属性修改用 `form_change_proposal.v1` |
| proposal.actionVersion | 本批动作协议 | 只从本批实际动作的版本集合协商，禁止借用其他动作版本 |

新建仅接受明确声明的 1.0；变更仅接受三项协商后的 form_change_actions.v1。capabilities.supportedActionVersions 存在时优先，显式空值不回退；仅该键缺省才读取 context 顶层。旧字段版本及旧属性写动作版本不能授权当前可写提案。

### 新增组件白名单

新增动作优先读取组件 `create.writableProps`，未提供时兼容旧 `writableProps/ editableProps`；显式空数组表示不能写入任何属性。根层组件目录优先于嵌套辅助属性快照，避免重复目录覆盖新增限制。

- Switch 仅声明 label/name 时，字段定义中的缺省或 false 必填不再自动写入 required；明确请求 required=true 仍拒绝，不静默丢弃。
- 其他字段未声明 required 且用户未请求时，不主动写入未授权默认属性。
- 字段定义和直接 `form.add_component` 都执行同一新增白名单检查。

### 验证与宿主边界

新增回归覆盖双 Schema、混合能力、已有画布追加、批次共同版本、缺失/未知动作版本、创建白名单及属性动作隔离。另使用用户实际设计器 context 编译九类字段，通过并保留画布版本1.1.0，新增动作版本为1.0。

宿主及聊天解析器应依据结构和真实能力处理可选 schemaVersion 元数据，不能硬编码仅接受 1.0.0 或 1.1.0，也不能伪造降级输出绕过检查。测试覆盖确定性编译和模拟平台 SDK 入口，不等于目标平台真实模型/SSE 网络联调已完成。


## 固定发布版本配置

包内 `release_config.json` 记录本次指定的发布标识：

```json
{
  "release_id": "d4d9ebc4-98a1-4d83-be4a-21344de9d036"
}
```

该文件随 ZIP 交付，用于调用配置对照；不作为 manifest 字段，也不自动改变平台 Release。`release_id` 的选择在 Agent 执行之前由平台完成，调用方需要在 `/invoke` 请求顶层（与 input、stream、context 同级）传入上述值，不要放入 context。平台会检查其属于目标 service_id 且可用，包内记录不代表已验证远程发布状态。后续发布新版本时，应核对并更新调用方的固定 release_id，否则请求仍固定到旧发布快照。
