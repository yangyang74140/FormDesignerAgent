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

首期严格限定为 Schema `1.0.0` 的单层 Flow 表单：

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
- `schemaVersion`：首期固定为 `1.0.0`。
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

字段只携带 `clientRef`、`componentName` 和合法 `props`，不携带持久化 `id`。设计器保存成功后回传 `clientRef -> final ID`。增量编辑使用 `form_actions + append`。

## 运行编排

`design_form` intent 指向单一 `form_proposal_generation` Pipeline：

1. 归一化本轮宿主快照，不从历史对话补猜画布状态。
2. Native Capability 只生成受控 IR，根对象统一为 `{"plan_items":[{"capability":"...","slots":{...}}]}`；一个 `proposal.*` 状态，新建时再生成若干 `form.field.define`。
3. Python 编译器完成字段名、选项、组件、可写属性、空白 Flow 和动作版本校验。平台回调使用文档签名 `(ir_payload, context)`，支持位置和关键字调用。缺失 `currentSchema`、`capabilities` 或 `supportedActionVersions` 时返回 `HOST_CONTEXT_REQUIRED` 澄清，不生成动作；业务校验失败返回 `failed`、`form_proposal_validation_failed` 和具体原因，不把无效提案作为成功结果。未知运行时异常仍交由平台处理。
4. handler 一次性返回完整提案；平台标准 `pipeline.step.output.completed` 可交付最终 output。
5. 额外发布唯一业务事件 `form.proposal.completed`；不发布骨架或逐字段业务事件。
6. ai-chat 一次性展示字段列表，设计器使用独立 Apply 幂等键事务应用、保存并回传 ID 映射。

`/invoke` 的幂等键只防止重复创建 Run，不能代替设计器 Apply 幂等。自定义 `form.proposal.completed` 的透传、持久化和断线补发需在目标平台集成验证；即使不透传，标准步骤完成事件仍携带完整提案。

## 校验

本地测试无需平台 SDK：

```sh
python3 -m py_compile specialized-agent-package/*.py specialized-agent-package/form_generation/*.py
python3 -m unittest discover -s specialized-agent-package/tests -v
```

回归覆盖四种提案状态、9 种组件、字段列表与 Actions 同源、无持久化 ID、空白 Flow 限制、字段命名、保留名、重复 `clientRef`、选项完整性、可写属性、增量动作目标和唯一最终事件。旧三组件编译器只作为兼容模块保留，不注册为生产 Pipeline，也不参与新建表单输出。

平台验收仍需提供真实 `specialized.builder` SDK，并验证完整 JSON 交付、ai-chat 一次性渲染、设计器事务执行、Apply 幂等、一次撤销、保存重开、`clientRef -> final ID` 回执、SSE 重连去重、取消和 revision 冲突处理。
