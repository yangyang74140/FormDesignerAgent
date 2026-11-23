---
document_type: 外置专属 Agent 说明
purpose: 基于宿主真实能力生成 form-agent.v1 表单设计提案
---

# 表单设计 Agent

该插件严格遵循 `specialized-agent-development-guide.md` 的三件套结构，并以 `form-agent-prompt.md` 为行为基线：

- `manifest.yaml`：员工身份、人设、执行边界和委派说明。
- `bootstrap.py`：平台要求的 `register_specialized_agent(context)` 入口。
- `agent_definition.py`：append 意图、Plan、结构化输出和单一提案 Pipeline。
- `form_generation/proposal.py`：统一提案入口、状态路由、字段编译及当前展示投影。
- `form_generation/action_rules/`：表单动作注册表与组件动作、规则/公式动作校验。
- `form_generation/components/`：公共属性定义与统一注册；`definitions/` 按组件名维护属性文件，`definitions/_shared/` 维护实际复用的族处理。
- `form_generation/properties.py`：属性提案编排、宿主授权与批次依赖校验。
- `form_generation/host.py`：宿主组件目录和节点身份读取。
- `specs/`：本 Agent 的动作、属性和组件业务规范。

## 业务规范与维护入口

先读 [规范入口](./specs/README.md)，再按改动阅读 [动作规范](./specs/actions.md)、[公共属性规则](./specs/properties.md) 或 [组件目录](./specs/components/README.md)。组件属性与专有处理放在 `components/definitions/` 下的同名文件，如 `NumberPicker.py`；`Input.TextArea` 使用 `InputTextArea.py`。新增组件复用公共属性，仅将多个组件实际共享的规则和处理提取到 `_shared/`，由 `registry.py` 统一注册，不继续集中到提案编译器。

本次分层保持当前输出与校验行为。本文后续章节描述当前实现，包括 `presentation.fields/changes/items`、`result.actions` 和现有属性动作；根目录 `AGENTS.md` 第 5 节确认的单一 actions 草稿目标尚需后续统一实施。本次没有切换协议、增加兼容层或宣称宿主已部署。

## 支持范围

字段生成支持单层 Flow 表单（包括已保存画布），依据实际结构和宿主能力校验，不限制 FormSchema 版本：

- 根据自然语言一次性生成完整字段列表，例如“员工入职登记表”。
- 支持 `Input`、`Input.TextArea`、`DatePicker`、`TimePicker`、`NumberPicker`、`SelectSingle`、`SelectMulti`、`CheckboxGroup`、`Switch`。
- 从同一份字段定义同时编译 `presentation.fields` 和 `form.add_component` Actions，避免展示与执行数据漂移。
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

例如“生成一个禁用的姓名字段”：姓名可用 `Input`，但没有明确注册的禁用语义及写入规则时，返回“姓名字段可使用 Input，但暂时还不支持禁用，当前没有已声明的禁用属性及写入规则”。不能猜 `disabled/readOnly/edit=false/access` 或用禁止手工编辑替代，也不能忽略禁用后交付 ready。此语义选择通过提示规则和示例约束；确定性校验拦截实际 IR 中的未知属性，真实模型能否完整保留用户要求仍需平台验收。

## 输出协议

字段最终产物固定为一个 `form-agent.v1` 提案，状态为 `ready`、`needs_clarification`、`unsupported` 或 `no_change`。子 Agent 的逻辑最终 output 只为 `{ form_proposal: proposal }`；展示路由放在原提案的 `presentation.kind`，不再附加 `component` 信封或复制 `props.proposal`。完整保留领域 `presentation.fields/changes/items`、标题、快照和 `result.actions/target/validation`，UI 行数据由 ai-chat 本地投影。

新建完整表单时，`ready` 同时包含：

- `presentation.kind = shared.table-field-confirm`：声明已注册字段确认组件；ai-chat 在完整 JSON、ready 状态、领域契约及业务白名单校验通过后投影到现有 Props，一次性渲染全部字段。旧 `form_field_list` 由消费端与宿主继续兼容。
- `result.kind = form_actions`、`mode = replace_empty_form`：设计器事务应用同源 `form.add_component` Actions。
- `validation`：Schema、Action 版本和字段数量摘要。

新增字段只携带 `clientRef`、`componentName` 和合法 `props`，不携带持久化 `id`。`clientRef` 以小写字母开头，其后允许小写字母、数字、下划线或连字符（如 `student_no`、`student-name`），必须唯一且原样贯穿展示、Action 和回执；不会替换字符或自动重命名，避免引用碰撞。业务字段 `name` 另按宿主 `fieldNameRules` 校验。已有字段展示保留真实 `id` 和全部原有属性（包括 `options.dataSource`、`identifiers` 等）；设计器保存成功后回传新增字段的 `clientRef -> final ID`。增量编辑使用 `append`，不得将展示快照作为整表覆盖或保存请求。

## 已有画布追加与最新列表

宿主每轮发送最新 `currentSchema` 和 `target.revision`，不能只发送上轮新增字段。以 `tests/fixtures/student-form-data.json` 为例，现有字段为姓名、学号、性别、出生日期、班级、联系电话、备注：

- “追加监护人和监护人电话”：生成 `form_fields + append`，省略 `target`；默认插入到最后一个 `componentCategory=field` 的组件之后，缺省 category 视为字段。末尾若有非字段组件，新增字段插入到它之前。
- “在学号后新增监护人和监护人电话”：模型从当前快照定位学号，也可将原样标签交给编译器唯一匹配；编译器按顺序生成 root 下标 `2`、`3` 的新增动作，避免多个字段在同一锚点后插入时顺序颠倒。
- 标签重名、目标不存在、选择为空时返回 `needs_clarification`，没有可执行 `result`；不会静默追加到末尾。可以用 `anchorName` 或真实 `anchorNodeId` 消除歧义，也可以用 `useSelection: true` 引用本轮选中字段。
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

返回提案中的 `presentation.fields` 为预计应用后的**完整组件列表**，`fieldCount` 与该数组长度一致；该例为 8 项。已有组件原样复制，新增组件无持久化 ID。`presentation.changes` 为按执行顺序排列的展示变更：

| operation | 数据 | 含义 |
| --- | --- | --- |
| `insert` | `index`、`field` | 在当前列表指定下标插入新组件 |
| `replace` | `index`、`field` | 用包含原 ID 和保留属性的组件快照更新展示 |
| `remove` | `index`、`field` | 删除该位置组件，field 为删除前快照 |
| `move` | `fromIndex`、`index`、`field` | 先移除 fromIndex，再插入 index |

下标基于本批此前变更已执行后的列表；不是 JSON Patch，也不是独立保存协议。普通属性、选项修改以及插入、删除、移动的 `form_actions` 也会编译最新展示列表。字段类型转换由宿主决定属性迁移及默认值，含转换动作时不返回推测的展示快照，应在应用后刷新宿主 Schema。规则、公式等动作不展开为组件属性，展示快照不能作为完整 FormSchema 使用。

### 宿主接入

1. 收到完整 `form.proposal.completed`（或标准步骤完成事件）后，按 `proposalId` 去重；校验契约和状态，用 `presentation.fields` **替换聊天中的旧组件列表**。已有组件用 `id`、新增组件用 `clientRef` 作为展示 key。不要再次把完整列表 append 到旧列表。也可使用 changes 做展示动画，随后以完整 fields 校正。
2. 将列表标记为“提案预览”；用户应用时只事务执行 `result.actions`，使用 `target.baseRevision` 检查版本和独立 Apply 幂等键。已有节点不能通过新增接口重建。`append` 是增量应用模式，指定位置的动作仍然必须遵守各自的 `payload.target.index`。
3. 保存继续由设计器与现有后端接口处理。仅新增组件分配新 ID；选项的内部 primaryKey 等由宿主适配器构建。保存后用真实 Schema、revision 和执行回执更新 context；聊天列表也以宿主实际结果为准。
4. 遇到 revision conflict 不应用旧下标，刷新 context 后重新生成；`rejected` 或保存失败不能把预览当作已持久化数据。

本仓库实现 Agent 生成、确定性编译及返回协议；聊天列表消费、画布 Action 执行器和保存接口位于宿主项目，需要按以上约定接入。

## 运行编排

`design_form` intent 指向单一 `form_proposal_generation` Pipeline：

1. 从 handler 的 `step_context.context` 归一化并隔离本轮宿主快照，不从历史对话补猜画布状态。生成器接收快照副本，编译器通过本轮闭包使用同一份权威快照；不再依赖 Native Capability 回调的第二个参数重新读取宿主状态，避免回调结构不同或旧数据造成误报、串单。
2. Native Capability 只生成受控 IR，根对象统一为 `{"plan_items":[{"capability":"...","slots":{...}}]}`；一个 `proposal.*` 状态，新建时再生成若干 `form.field.define`。
3. Python 编译器完成字段名、选项、组件、可写属性、单层 Flow、已有画布锚点和动作版本校验。平台回调仍使用文档签名 `(ir_payload, context)`，支持位置和关键字调用；第二个参数只用于脱敏诊断。handler 快照缺失 `currentSchema` 时返回 `HOST_CONTEXT_REQUIRED` 澄清；已有快照但缺少必要的 `capabilities` 或 `supportedActionVersions` 时返回 `HOST_CAPABILITY_REQUIRED` 的 unsupported。不从回调借用其他上下文，不生成动作；其余业务校验失败返回 `failed`、`form_proposal_validation_failed`、具体原因及 `abort_run: true`，阻止平台继续通用 `final_response`；不把无效提案作为成功结果。未知运行时异常仍交由平台处理。
4. Native Capability 的返回值先归一化为步骤结果字典，兼容普通映射和通过属性暴露 `status/output/diagnostics` 的 SDK 结果对象，避免因非 dict 返回值跳过后处理。失败结果保留 `error_code/artifact_ref` 及原始诊断，统一设置 `abort_run: true`；缺少最终提案也按失败终止。提示词始终约束设计器表单场景，失败后不转问 Excel、CSV 或重复索要已明确的字段。handler 的最终 `output` 仅为 `{ form_proposal: proposal }`；对校验通过且可展示的 `ready` 结果，Python 在原提案的 `presentation.kind` 使用对应注册组件 ID，不复制提案为 `component.props.proposal`，不接受模型任意指定组件 ID。平台标准 `pipeline.step.output.completed` 的事件类型和步骤键不变。
5. 保留原有的单次业务事件 `form.proposal.completed`，`block_id/title/status/proposal` 等原 payload 字段不变，仅移除重复 `component`；每个逻辑 output 或业务 payload 内完整提案只出现一次。不额外发布组件事件、骨架或逐字段事件。
6. ai-chat 对完整文本 JSON、state 快照、标准步骤、自定义业务事件及历史回放统一校验、投影并按 `proposalId` 去重。设计器仍在用户确认后通过独立 Apply 幂等键事务应用，保存和回传 ID 映射由宿主负责。

| 结果 | `presentation.kind` | ai-chat 本地投影的现有 Props |
| --- | --- | --- |
| 已校验的 ready 完整字段列表 | `shared.table-field-confirm` | `proposal`、`proposalId`、`title`、`compact: true`、`fields`、`fieldTypes`、`selectedFieldIds` |
| 已校验的 ready 属性变更清单 | `shared.component-property-checklist` | `proposal`、`proposalId` |
| 查询、撤销、澄清、无变更、失败或无可展示清单 | 保留原状态及领域语义 | 不投影为上述可应用确认卡 |

ready、有效领域契约、匹配 kind、已注册且被当前业务白名单允许必须同时满足。无效、未知或字段/属性错配 kind 不渲染，不因存在 fields/items 而改推其他卡；非 ready 结果不因设置 kind 获得执行资格。旧 `form_field_list`、`component_property_checklist` 由 ai-chat 与设计器类型/校验器继续接受。历史显式 `component` 仍优先：有效声明按既有规则渲染，显式存在但无效时不回退到 proposal 推断；新生产端不再发出该信封。协议、Action、target/revision、幂等和原子应用检查保持不变。

步骤返回的顶层 `diagnostics` 保留平台原有诊断，并追加 `FORM_HOST_CONTEXT_TRACE`：`stage=handler/compiler`、入参类型、提取后的上下文类型、白名单内的协议键名，以及 `requestId/target/currentSchema/capabilities/supportedActionVersions` 的存在标记。compiler 记录 `compile_source=handler_snapshot`。不记录字段值、任意业务键名、Schema 内容、用户输入、业务 ID 或令牌，也不把诊断加入 `output` 或业务事件。可从 `pipeline.step.completed` 的 `diagnostics` 或 `specialized_builder.context.snapshot.output_pipeline_result.step_results[].diagnostics` 检查；事件透传以目标平台实际行为为准。handler 诊断同时记录 `native_result_type`，用于确认原生生成 helper 的实际返回类型。完整提案、业务事件和 handler 诊断同时缺失时，先检查是否运行了包含结果对象兼容修复的版本，再检查平台透传；新版本不再输出独立 component，不能用它的缺失判断异常。handler 完整、compiler 标记缺失时，快照绑定仍可正常编译。每轮缺失上下文仍返回澄清，不用默认画布绕过检查。

字段卡的行由 ai-chat 按提案字段顺序投影为 `{id, name, type, options, option?}`；已有字段用 `id`，新增字段用 `clientRef`。`options` 是展示标签，原始选项值、属性和动作保留在唯一原提案中；本地组件 Props 引用该提案，不从卡片反推执行数据。`/invoke` 的幂等键只防止重复创建 Run，不能代替设计器 Apply 幂等。单提案契约回归结果由实施任务记录；标准步骤与自定义事件透传、状态/历史持久化和断线补发仍需在目标平台验证，本地检查不等于线上已部署。

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

回归覆盖四种提案状态、9 种组件、字段列表与 Actions 同源、无持久化 ID、空白 Flow 限制、字段命名、保留名、重复 `clientRef`、选项完整性、可写属性、增量动作目标和唯一最终事件。`test_capability_refusal.py` 额外覆盖缺失/空能力目录、禁用及未知属性拒绝、整批拒绝、真实权限保留、宿主候选交集与最终拒绝事件。`test_output_preview.py` 的单提案回归需验证字典、通用映射、属性对象和不可变 dataclass 返回值均只输出一次完整提案、唯一业务事件及诊断，并保留失败对象的错误码和中止标记；本次结果由实施会话回填。`test_host_context.py` 额外验证不同形态与过期 compiler 上下文、本轮快照隔离、并发运行互不串单、缺失 handler 快照仍拒绝动作，以及上下文诊断脱敏和原生失败诊断保留。旧三组件编译器只作为兼容模块保留，不注册为生产 Pipeline，也不参与新建表单输出。

平台验收仍需提供真实 `specialized.builder` SDK，并验证完整 JSON 交付、ai-chat 一次性渲染、设计器事务执行、Apply 幂等、一次撤销、保存重开、`clientRef -> final ID` 回执、SSE 重连去重、取消和 revision 冲突处理。


## 1.2.0：七组件属性 Agent

新增受控属性 IR 与确定性属性提案编译，支持 `Input`、`Input.TextArea`、`NumberPicker`、`DatePicker`、`TimePicker`、`SelectSingle`、`SelectMulti`。自然语言意图由平台 Native Capability 解析；Python 负责目标、能力、值及输出校验，不依赖独立关键词分类器。

- `proposal.begin.slots.result_kind=property_changes`：后接 `form.property.change`。
- `property_query`：后接 `form.property.query`，只读输出，不要求写动作版本。
- `property_undo`：后接 `form.property.undo`（`transaction_id`）；必须提供宿主真实可撤销事务和已声明动作。
- `property_changes` 还支持 `form.property.rule`（`operation=add/replace/remove`、`rule_type`、`rule_id`、`value`）和 `form.property.linkage`（`operation`、`linkage_type`、`linkage_id`、`value`），目标字段与 change 一致。仅允许宿主已注册的 ruleCatalog/linkageCatalog、结构化 schema 和处理器；没有运行能力时返回 unsupported。
- 查询产物 `form_property_query.v1` 的 status=ready，只有只读 presentation，不包含 result；撤销产物及其动作以实际受控能力定义为准，不能交给普通属性处理器。
- 属性 change 使用 `node_id` 或 `use_selection=true`，也可使用 `node_label/node_name` 唯一匹配；操作包括 `set/clear/unset/reset/copy`，复制提供 `source_node_id/source_property`。
- 属性输出为 `form_property_proposal.v1`，`presentation.kind = shared.component-property-checklist`；保留完整 `items` 与动作，旧 `component_property_checklist` 由消费端和宿主兼容。动作协议 `form_property_actions.v1`、动作 `form.apply_property_change` 不变。
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

新属性契约的宿主待办、context 和最终展示/执行分层见仓库 `doc/ai-chat-property-edit-integration.md`。平台仍使用同一个 Pipeline 外层 `form_agent_proposal.v1` 结构化输出通道，内部 `form_proposal.contractVersion` 按属性修改/查询/撤销区分；上线前需验证平台输出契约允许这些新增产物。原有字段生成输出不变。

打包使用 Python 标准库：

```sh
python3 package_agent.py
```

在仓库根目录执行。脚本先运行回归测试，再检查 Python 语法和最终 ZIP 条目，按 manifest 版本生成上传包；本次目标版本为 `1.2.10`（`specialized-agent-package-1.2.10.zip`）；上传包根目录为插件入口，不包含测试、缓存或本地资料。


### 规则、联动和撤销上下文约定

`capabilities.ruleCatalog[rule_type]` 和 `capabilities.linkageCatalog[linkage_type]` 需要提供 `handlerId`、`components`、`operations`、`valueSchema`，联动还需 `astOperators`。节点策略 `allowedProperties` 通过 `rule`、`linkage` 分别授权这些扩展操作。已有配置放在顶层 `rules[nodeId]`、`linkages[nodeId]`，每项为 `{id,type,value}`；删除和替换必须引用真实 ID。

宿主声明动作 `form.apply_property_rule`、`form.apply_property_linkage`、`form.undo_property_transaction` 时，`supportedActionVersions[动作名]` 必须包含 `form_property_actions.v1`。撤销需要 `history.current` 或平铺 `history` 中的 `{canUndo:true,transactionId,revision}`，与当前 revision 一致。

属性 reset 需要注册 reset 操作。titleAlign/titlePosition 或 `reset.source=inherited` 删除局部覆盖；其他属性优先读取目录 `default`，其次使用已明确的内置默认值。受保存锁保护的属性必须提供真实保存状态，不能因状态缺失当成新字段。

JSON Schema 仅支持编译器已实现的受控子集，未实现关键字（如 `$ref`、`not`、`format`）会明确拒绝。公式默认值、缺少引用检查的选项删除及未注册规则/联动不生成执行动作，需宿主补齐专用处理器后另行接入。
