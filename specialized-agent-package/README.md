---
document_type: 外置专属 Agent 说明
purpose: 基于宿主真实能力生成 form-agent.v1 表单设计提案
---

# 表单设计 Agent

该插件严格遵循 `specialized-agent-development-guide.md` 的三件套结构，并以 `form-agent-prompt.md` 为行为基线：

- `manifest.yaml`：员工身份、人设、执行边界和委派说明。
- `bootstrap.py`：平台要求的 `register_specialized_agent(context)` 入口。
- `agent_definition.py`：append 意图、Plan、结构化输出和单一提案 Pipeline。
- `form_generation/proposal.py`：宿主上下文归一化、动作协议编译和安全校验。

## 支持范围

字段生成支持 Schema `1.0.0`、`1.1.0` 的单层 Flow 表单（包括已保存画布）：

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
- `schemaVersion`：`1.0.0` 或 `1.1.0`，必须与 `currentSchema.schemaVersion` 一致；省略时从当前 Schema 推导。
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

## 输出协议

最终产物固定为一个 `form-agent.v1` 提案，状态为 `ready`、`needs_clarification`、`unsupported` 或 `no_change`。

新建完整表单时，`ready` 同时包含：

- `presentation.kind = form_field_list`：ai-chat 在完整 JSON 解析和契约校验后一次性渲染全部字段。
- `result.kind = form_actions`、`mode = replace_empty_form`：设计器事务应用同源 `form.add_component` Actions。
- `validation`：Schema、Action 版本和字段数量摘要。

新增字段只携带 `clientRef`、`componentName` 和合法 `props`，不携带持久化 `id`。已有字段展示保留真实 `id` 和全部原有属性（包括 `options.dataSource`、`identifiers` 等）；设计器保存成功后回传新增字段的 `clientRef -> final ID`。增量编辑使用 `append`，不得将展示快照作为整表覆盖或保存请求。

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

1. 归一化本轮宿主快照，不从历史对话补猜画布状态。
2. Native Capability 只生成受控 IR，根对象统一为 `{"plan_items":[{"capability":"...","slots":{...}}]}`；一个 `proposal.*` 状态，新建时再生成若干 `form.field.define`。
3. Python 编译器完成字段名、选项、组件、可写属性、单层 Flow、已有画布锚点和动作版本校验。平台回调使用文档签名 `(ir_payload, context)`，支持位置和关键字调用。缺失 `currentSchema`、`capabilities` 或 `supportedActionVersions` 时返回 `HOST_CONTEXT_REQUIRED` 澄清，不生成动作；业务校验失败返回 `failed`、`form_proposal_validation_failed` 和具体原因，不把无效提案作为成功结果。未知运行时异常仍交由平台处理。
4. handler 一次性返回完整提案；平台标准 `pipeline.step.output.completed` 可交付最终 output。
5. 额外发布唯一业务事件 `form.proposal.completed`；不发布骨架或逐字段业务事件。
6. ai-chat 一次性展示字段列表，设计器使用独立 Apply 幂等键事务应用、保存并回传 ID 映射。

`/invoke` 的幂等键只防止重复创建 Run，不能代替设计器 Apply 幂等。自定义 `form.proposal.completed` 的透传、持久化和断线补发需在目标平台集成验证；即使不透传，标准步骤完成事件仍携带完整提案。

## 更新包与入口加载

`bootstrap.py` 使用 `from .agent_definition import register_agent`，由平台在固定 Revision 包命名空间中加载；包内模块全部使用相对导入，不手动注册全局模块或改写 `sys.path`。入口应通过平台包加载器导入，不能作为独立脚本执行。

上传 ZIP 根目录包含 `manifest.yaml`、`bootstrap.py`、`agent_definition.py` 和 `form_generation/`。发布包不包含 `tests/`、测试数据、`__pycache__/` 或隐藏文件；测试在源码目录运行。升级保持原 `agent_key`、`plugin_key`，提升包版本，通过“更新代码包”上传并重新校验发布。

## 校验

本地测试无需平台 SDK：

```sh
python3 -m py_compile specialized-agent-package/*.py specialized-agent-package/form_generation/*.py
python3 -m unittest discover -s specialized-agent-package/tests -v
```

回归覆盖四种提案状态、9 种组件、字段列表与 Actions 同源、无持久化 ID、空白 Flow 限制、字段命名、保留名、重复 `clientRef`、选项完整性、可写属性、增量动作目标和唯一最终事件。旧三组件编译器只作为兼容模块保留，不注册为生产 Pipeline，也不参与新建表单输出。

平台验收仍需提供真实 `specialized.builder` SDK，并验证完整 JSON 交付、ai-chat 一次性渲染、设计器事务执行、Apply 幂等、一次撤销、保存重开、`clientRef -> final ID` 回执、SSE 重连去重、取消和 revision 冲突处理。


## 1.2.0：七组件属性 Agent

新增受控属性 IR 与确定性属性提案编译，支持 `Input`、`Input.TextArea`、`NumberPicker`、`DatePicker`、`TimePicker`、`SelectSingle`、`SelectMulti`。自然语言意图由平台 Native Capability 解析；Python 负责目标、能力、值及输出校验，不依赖独立关键词分类器。

- `proposal.begin.slots.result_kind=property_changes`：后接 `form.property.change`。
- `property_query`：后接 `form.property.query`，只读输出，不要求写动作版本。
- `property_undo`：后接 `form.property.undo`（`transaction_id`）；必须提供宿主真实可撤销事务和已声明动作。
- `property_changes` 还支持 `form.property.rule`（`operation=add/replace/remove`、`rule_type`、`rule_id`、`value`）和 `form.property.linkage`（`operation`、`linkage_type`、`linkage_id`、`value`），目标字段与 change 一致。仅允许宿主已注册的 ruleCatalog/linkageCatalog、结构化 schema 和处理器；没有运行能力时返回 unsupported。
- 查询产物 `form_property_query.v1` 的 status=ready，只有只读 presentation，不包含 result；撤销产物及其动作以实际受控能力定义为准，不能交给普通属性处理器。
- 属性 change 使用 `node_id` 或 `use_selection=true`，也可使用 `node_label/node_name` 唯一匹配；操作包括 `set/clear/unset/reset/copy`，复制提供 `source_node_id/source_property`。
- 属性输出为 `form_property_proposal.v1` + `component_property_checklist`，动作协议 `form_property_actions.v1`、动作 `form.apply_property_change`。
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

在仓库根目录执行。脚本先运行回归测试，再检查 Python 语法，生成 `specialized-agent-package-1.2.6.zip`；上传包根目录为插件入口，不包含测试、缓存或本地资料。


### 规则、联动和撤销上下文约定

`capabilities.ruleCatalog[rule_type]` 和 `capabilities.linkageCatalog[linkage_type]` 需要提供 `handlerId`、`components`、`operations`、`valueSchema`，联动还需 `astOperators`。节点策略 `allowedProperties` 通过 `rule`、`linkage` 分别授权这些扩展操作。已有配置放在顶层 `rules[nodeId]`、`linkages[nodeId]`，每项为 `{id,type,value}`；删除和替换必须引用真实 ID。

宿主声明动作 `form.apply_property_rule`、`form.apply_property_linkage`、`form.undo_property_transaction` 时，`supportedActionVersions[动作名]` 必须包含 `form_property_actions.v1`。撤销需要 `history.current` 或平铺 `history` 中的 `{canUndo:true,transactionId,revision}`，与当前 revision 一致。

属性 reset 需要注册 reset 操作。titleAlign/titlePosition 或 `reset.source=inherited` 删除局部覆盖；其他属性优先读取目录 `default`，其次使用已明确的内置默认值。受保存锁保护的属性必须提供真实保存状态，不能因状态缺失当成新字段。

JSON Schema 仅支持编译器已实现的受控子集，未实现关键字（如 `$ref`、`not`、`format`）会明确拒绝。公式默认值、缺少引用检查的选项删除及未注册规则/联动不生成执行动作，需宿主补齐专用处理器后另行接入。


## 1.2.1：真实设计器协议兼容

- 支持 NumberPicker 的成组 `numericRange` 和 SelectMulti 的 `selectionLimit`。
- `resolvedProperties[nodeId][property].stored` 为宿主提供的语义配置状态；经过结构校验后用于 before。查询有效值使用 `resolvedValue` 与 `source`。
- `textLengthLimit` 的 set 输入为正整数，卡片 after 为 `{enabled:true,maxLength:N}`；clear/reset 不把派生配置再次作为 set 输入校验。TimePicker 动态当前时间支持面板的 `dynamicAnchor="today"`。
- 保留旧包文件，1.2.1 是上传替换的补丁版本；上传发布后仍需宿主和聊天包完成对应协议接入，不能仅更新 Agent 就认为画布执行已就绪。

### Agent 能力更新后宿主需要做什么

| Agent 更新类型 | 设计器 / ai-chat 所需操作 |
| --- | --- |
| 提示词、同义词、错别字识别优化，输出契约不变 | 更新 Agent 发布版本，复测真实请求与旧案例；通常无需修改宿主代码 |
| 新组件或新属性，宿主已有同语义处理器 | 核对组件范围、类型、默认/清空/继承语义、保存锁和布局条件；测试通过后才加入当前能力目录 |
| 新复合属性或新执行效果 | 先实现并测试宿主处理器、预览和事务差异，再更新目录/策略/解析值；Agent 不得仅靠 writableProps 宣称支持 |
| 新动作、新展示或破坏性契约变化 | 同步升级 ai-chat 解析/卡片、设计器动作分派/执行器，协商新版本；未知版本明确拒绝，保留旧协议兼容路径 |
| 新规则、公式、联动、远程校验 | 先接通真实运行时/服务、字段引用校验及权限，再注册 capability；无运行时继续返回不支持 |

发布前至少验证：宿主当前 context → 生产 Python 编译器 → 完整 SSE 卡片 → 勾选子集 → 真实 Store 与回执 → 下一轮新 Schema/revision。覆盖手工编辑冲突、重复应用、清空/重置、撤销以及原有新增字段流程。应用成功只表示未保存的画布更新；持久化仍须单独验证保存回读。目录是宿主真实支持能力的交集，Agent 升级不得自动开放尚未实现的属性。


## 1.2.2：字段生成与属性能力共存、双 Schema 兼容

本版仅修改 Agent，不修改 ai-chat 或设计器。Schema `1.1.0` 保留 `1.0.0` 的原有单层 Flow 字段新建、已有画布追加和增量编辑能力；同一 context 可以声明字段生成和属性编辑。按本轮意图分派，不把不同动作协议混在一个结果中。

### 版本分层与选择规则

| 输出字段 | 含义 | 选择规则 |
| --- | --- | --- |
| proposal.schemaVersion | 当前画布 Schema 版本 | 原样保留宿主的 `1.0.0` 或 `1.1.0`，不强制降级 |
| proposal.contractVersion | 本轮提案契约 | 字段生成用 `form_agent_proposal.v1`，属性修改用 `form_property_proposal.v1` |
| result.schemaVersion | 本批动作协议 | 只从本批实际动作的版本集合协商，禁止借用其他动作版本 |

例如 context 同时包含 `form.add_component:["1.0"]` 和 `form.apply_property_change:["form_property_actions.v1"]`：字段生成返回动作版本 `1.0`，属性修改返回 `form_property_actions.v1`。旧增量批次包含多个动作时，必须有共同版本，否则拒绝。继续兼容旧宿主全局版本列表/布尔版本表；旧增量协议可选集合为 `1.0`、`form_actions.v1`、`form_actions.v2`，未知版本不会因字符串排序较大就被采用。

### 新增组件白名单

新增动作优先读取组件 `create.writableProps`，未提供时兼容旧 `writableProps/ editableProps`；显式空数组表示不能写入任何属性。根层组件目录优先于嵌套辅助属性快照，避免重复目录覆盖新增限制。

- Switch 仅声明 label/name 时，字段定义中的缺省或 false 必填不再自动写入 required；明确请求 required=true 仍拒绝，不静默丢弃。
- 其他字段未声明 required 且用户未请求时，不主动写入未授权默认属性。
- 字段定义和直接 `form.add_component` 都执行同一新增白名单检查。

### 验证与宿主边界

新增回归覆盖双 Schema、混合能力、已有画布追加、批次共同版本、缺失/未知动作版本、创建白名单及属性动作隔离。另使用用户实际设计器 context 编译九类字段，通过并保留画布版本1.1.0，新增动作版本为1.0。

宿主及聊天解析器仍必须支持返回的画布版本：若旧代码硬编码只接受 proposal.schemaVersion=1.0.0，需要由对应项目另行兼容1.1.0。本版不会伪造1.0.0输出绕过旧解析器。测试覆盖确定性编译和模拟平台SDK入口，不等于目标平台真实模型/SSE网络联调已完成。


## 固定发布版本配置

包内 `release_config.json` 记录本次指定的发布标识：

```json
{
  "release_id": "d4d9ebc4-98a1-4d83-be4a-21344de9d036"
}
```

该文件随 ZIP 交付，用于调用配置对照；不作为 manifest 字段，也不自动改变平台 Release。`release_id` 的选择在 Agent 执行之前由平台完成，调用方需要在 `/invoke` 请求顶层（与 input、stream、context 同级）传入上述值，不要放入 context。平台会检查其属于目标 service_id 且可用，包内记录不代表已验证远程发布状态。后续发布新版本时，应核对并更新调用方的固定 release_id，否则请求仍固定到旧发布快照。
