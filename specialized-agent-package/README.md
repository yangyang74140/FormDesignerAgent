---
document_type: 外置专属 Agent 说明
purpose: 根据自然语言生成或增量编辑表单设计器的 PC flow FormAction
---

# 通用表单生成 Agent

这是一个严格按 `specialized-agent-development-guide.md` 实现的外置三件套插件：

- `manifest.yaml`：员工身份、人设和展示信息。
- `bootstrap.py`：平台启动入口。
- `agent_definition.py`：append 意图、Plan、Native Capability、Output Pipeline 和 Action 编译器。

## 支持范围

创建表单复用页面专家的节点事件展示：先发送 `page_output.skeleton` 表单骨架，再批量生成字段配置并逐个发送携带完整字段 JSON 的 `page_output.node.completed`，最后发送 `page_output.completed` 完整 FormSchema。创建事件的 `block_id` 统一为 `page_output`，不再同时发送旧 `form_output.*` 创建事件，避免重复节点。

骨架和字段生成步骤使用 `output_visibility="preview"`，主聊天会展示表单骨架和字段生成结果的完整 JSON；平台也可使用节点事件展示“骨架生成 → 组件1…组件N → 表单结构已校验”的流程。最终校验步骤仍使用 `final_artifact` 输出完整 FormSchema。

这里只复用展示事件协议，不把表单转换为页面 Schema：`output_structured.kind` 和 pipeline 的 `artifact_kind` 仍为 `form_output`，最终数据仍位于 `specialized_state.form_output.form_schema_json`。修改表单的 `form_output.completed` 事件和 Action 输出保持不变。

修改表单仍输出 `form_actions.v1` 小 JSON，由前端 Action Reducer 按真实 `fieldId` 修改当前大 Schema；不会重新生成未修改字段。

首版只生成 PC `flow` 布局的三种字段：

| 用户可说的组件 | Schema `componentName` | `title` |
|---|---|---|
| 单行文本 | `Input` | `单行文本` |
| 下拉单选 | `SelectSingle` | `下拉单选` |
| 复选框 | `CheckboxGroup` | `复选框` |

不生成移动端、Grid、容器嵌套、`Input.TextArea`、`NumberPicker`、`Radio.Group`、`SelectMulti` 或发布/保存动作。

## 已确认的 Schema 规则

当前表单设计器的根结构使用 `packages/form-schema/src/types.ts` 的实际 `FormSchema`：

```json
{
  "schemaVersion": "1.1.0",
  "id": "form_generated", 
  "props": {
    "description": "",
    "columns": 2,
    "labelPosition": "left",
    "labelWidth": 80,
    "textAlign": "left",
    "rowHeight": "16px"
  },
  "layoutMode": "flow",
  "fields": []
}
```

每个字段节点统一为 `{ id, componentName, componentCategory, title, props }`，`componentCategory` 不可缺失。设计器 Schema 的分类类型为 `"field" | "container" | "system" | "helper" | "custom"`；当前支持的 `Input`、`SelectSingle`、`CheckboxGroup` 在各自 meta 中均为 `"field"`。编译器在骨架、字段补全和最终输出阶段固定补齐 `componentCategory: "field"`，不交给模型生成，最终裁剪也会保留该属性。组件身份和默认值来自：

- `packages/form-designer/src/configs/component-metas/basic/input.meta.ts`
- `packages/form-designer/src/configs/component-metas/basic/select-single.meta.ts`
- `packages/form-designer/src/configs/component-metas/basic/checkbox-group.meta.ts`
- `packages/form-designer/src/configs/component-metas/utils/default-complex-options.ts`
- `packages/form-designer/src/modules/property-panel/sharedProperties.ts`

三种字段的编译结果规则：

### `Input`

`props` 包含 `label`、`required`、`name`、`placeholder`、`defaultValueConfig: "undefined"`、`defaultValue`、`allowClear`、`showLimitHint`、`textMaxLength`、`enableQuickCopy`、`enableLinkParser`、`format: "none"`、`isUnique: false`，以及共享默认值 `enableCustomTitle: false`、`customTitle: ""`、`extra: ""`、`extraType: "icon"`、`hideTitle: false`、`readOnlyDisplay: false`、`size: "medium"` 和 `identifiers.name`。

### `SelectSingle`

`props` 包含 `label`、`required`、`name`、`placeholder: "请选择"`、`defaultValue`、`options`、`showSearch: false`、`allowClear: true`、`popupMatchSelectWidth: false`、`enableColor: false`、共享默认值和 `identifiers.name`。

### `CheckboxGroup`

`props` 包含 `label`、`required`、`name`、`defaultValue: []`、`options`、`direction: "horizontal"`、`supportReverseSelect: true`、共享默认值和 `identifiers.name`。

`options` 固定编译为：

```json
{
  "dataSource": [
    {"primaryKey":"1","value":"1","label":"选项1","activeKey":false,"color":null,"disabled":false}
  ],
  "isColor": false,
  "nextValueSeed": 2
}
```

模型只提交 `value` / `label` 等受控槽位；编译器补齐 `primaryKey`、`activeKey`、`color`、`disabled` 和 `nextValueSeed`，并过滤非法默认值。

## 运行编排

创建意图 `create_form` 的 `output_policy` 指向 `form_generation` pipeline：

1. `form.skeleton.generate`：模型只生成表单标题、布局和字段占位符，编译器分配稳定字段 ID，并发送 `page_output.skeleton`。
2. `form.field.hydrate`：模型一次性生成所有字段的业务配置，编译器合并到骨架，然后按字段顺序发送 `page_output.node.completed`。
3. `form.schema.validate`：裁剪并校验最终 FormSchema，发送 `page_output.completed`。

创建事件载荷与页面专家的对应关系：

| 事件 | 关键字段 |
|---|---|
| `page_output.skeleton` | `block_id: "page_output"`、`skeleton_json`（FormSchema 骨架）、`skeleton_source: "external_native_capability"` |
| `page_output.node.completed` | `node_id`、`component_name`、从 1 开始的 `component_index`、`component_total`、`node`（完整字段） |
| `page_output.completed` | `output_kind: "form_schema_json"`、`form_schema_json`、`validation.field_count` |

所有创建事件均带 `title` 和 `status`。前两种状态为 `generating`，最终状态为 `completed`；字段生成失败时不会发送成功节点或最终完成事件。最终事件不包含 `page_schema_json`，消费方应按 `output_kind` 区分表单和页面产物。

修改意图 `modify_form` 的 `output_policy` 指向 `form_action_generation` pipeline，只生成一个 `form_actions.v1` Action。Native Capability 只允许受控的创建配置、字段添加、修改、修改选项、移动和删除动作，避免模型直接伪造 `id`、`componentName`、`children` 或完整 Schema。

调用方如果传入运行上下文，按开发文档放在请求体顶层 `context`；本插件读取其中的 `current_page_schema`，编辑时只输出目标字段的增量 Action，并始终将输出限制为 PC `flow`。

## 校验

本地回归测试不依赖平台 SDK，使用 SDK 替身检查步骤的 preview / final_artifact 配置，并通过真实编译器验证骨架、三种组件的完整属性与选项、页面节点事件顺序和最终 FormSchema 没有丢失，同时覆盖失败分支、事件发布方式与修改分支兼容性：

```sh
python3 -m unittest discover -s specialized-agent-package/tests -v
```

在能够提供 `specialized.builder` SDK 的平台环境中，还需运行插件包校验和真实 Run。当前工作区没有该运行时依赖，本地测试不替代平台验收；源码更新后需重新激活插件，验证主聊天按页面专家展示骨架、逐字段节点和校验完成节点，并确认平台能从 `page_output.completed` 的 `form_schema_json` 消费最终表单。如果平台将此事件硬编码为页面 Schema，需要在平台侧按 `output_kind` 适配；本包不包含平台前端代码。
