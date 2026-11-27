# 表单设计器 Agent 业务规范

本目录是本 Agent 的业务契约入口，与运行时代码一起维护。平台 SDK 与事件机制仍以仓库根目录的第三方开发指南和平台接口参考为准。

## 按问题阅读

| 问题 | 规范 | 运行时位置 |
| --- | --- | --- |
| 动作名称、payload、定位、顺序与失败 | [表单动作](./actions.md) | `form_generation/action_rules/` |
| 公共属性、语义值、授权、清空与依赖 | [属性规则](./properties.md) | `form_generation/components/common.py`、`properties.py` |
| 哪些组件支持生成或属性修改 | [组件目录](./components/README.md) | `form_generation/components/` |
| 文本、数字、日期时间、选项的特殊规则 | 组件目录中的各族规范 | `components/definitions/<组件名>.py`；复用处理在 `_shared/` |
| 宿主输入与最终提案外层 | [Agent README](../README.md) | `proposal.py`、`agent_definition.py` |
| 三端展示、确认、应用与保存 | [接入说明](../../doc/ai-chat-property-edit-integration.md) | 消费端与设计器宿主另行实现 |

## 代码结构

```text
form_generation/
├── proposal.py          # 统一编译入口、字段动作编译与顺序
├── properties.py        # 属性提案编排、宿主授权、批次依赖
├── drafts.py            # 单一动作草稿、动作 ID 与依赖结构校验
├── guidance.py          # 场景澄清及字段引导路由
├── field_guidance.py    # 既有非空表单的槽位分组映射、整体复验和回退
├── field_clarification.py # 无表单确认后的部分字段、逐题循环、暂停恢复与编译
├── host.py              # 宿主目录和节点身份读取
├── action_rules/
│   ├── __init__.py      # 动作名称、能力声明与校验分派
│   ├── component.py     # 新增、修改、选项、移动、删除、转换
│   └── extensions.py    # 表单配置、规则、联动和公式
└── components/
    ├── __init__.py      # 组件规则公开入口
    ├── registry.py      # 显式注册，组合公共与组件规则
    ├── common.py        # 公共属性与权限语义
    ├── validation.py    # 共享结构校验与拒绝诊断
    └── definitions/
        ├── __init__.py  # 空包标记，不重复注册
        ├── Input.py
        ├── InputTextArea.py  # 对应 Input.TextArea
        ├── NumberPicker.py
        ├── DatePicker.py
        ├── TimePicker.py
        ├── SelectSingle.py
        ├── SelectMulti.py
        └── _shared/
            ├── __init__.py
            ├── text.py      # 文本默认值、长度限制等共享处理
            ├── temporal.py  # 日期时间默认值、范围等共享处理
            └── choice.py    # 选项身份、默认项等共享处理
```

对外继续使用 `compile_form_proposal()`。内部通过 `action_rules.validate_action()` 校验动作，通过 `components.get_component_rules(componentName)` 获取已组合的规则；`property_names(componentName)` 提供属性集合。注册表返回的规则用于读取快照、操作语义、校验、模拟和依赖处理，宿主授权仍由属性编排层验证。

## PC 双确认补充

2026-11-25 新增能力协商的 PC 双确认：新建 `shared.form-create-confirm`；已有表单字段/属性混合变更 `shared.form-change-confirm`、`form_change_proposal.v1` / `form_change_actions.v1`。新增 `form_changes` IR 路由；`contracts.py` 管协商，`proposal.py` 管有序混合及重叠拒绝。所有可写路径均要求当前新能力，缺失明确拒绝；属性规则与联动暂不支持。详见[动作规范](./actions.md#2026-11-25-pc-双确认与统一变更)。单一 actions 和宿主复验边界保持不变。

## 单一动作输出契约与实施边界

最终 output 为 `{form_proposal: proposal}`。修改提案以顶层 `mode/actionVersion/actions` 为唯一执行草稿；每条动作包含 `actionId/action/payload/dependsOn/display`，普通确认的 `presentation` 仅含注册 `kind/title`。属性变更的原状态在 `preconditions.before`，新值仅在 payload；不输出 result、validation、after 或重复字段/属性清单。查询仍是只读 `component_property_query` 的 items，无动作；撤销使用 `component_property_undo` 专用展示及顶层动作。

ai-chat 按 actionId 勾选并直接编辑唯一草稿，提交 `{proposal: 最终已编辑且已选择的提案}`，宿主独立接收 Apply 幂等键。依赖缺选不能静默代选；字段下标相关子集必须复验，只有整批纯新增、显式 root index 连续且可证明独立的序列可重算位置，其他复杂位置子集拒绝。名称、payload、前置条件与错误语义以[动作规范](./actions.md)和[属性规则](./properties.md)为准。

protocol、动作名称及模型输入 IR 保持不变；contractVersion 按当前新建、变更或专用查询/撤销契约确定；schemaVersion 是可选画布元数据。此次结构调整不增加旧格式解析、迁移、v1/v2 分流或 FormSchema 版本门禁。平台事件和最终 output 通道沿用真实既有机制。

2026-11-23 指定本地设计器已接入 PC Flow 既有属性处理器的新契约；其他能力仍须逐项核验。**规范存在、本地测试通过或 Agent 返回 ready 均不证明宿主已经部署或具备其他执行能力。**区分以下事实：

- **Agent 实现**：以本地编译器和回归测试验证的行为为准。
- **宿主授权**：每轮真实 capabilities、节点策略、处理器与修订信息共同决定能力；本地注册不授予执行能力。
- **三端联调**：ai-chat 同期调整，宿主解析、编辑后复验、原子应用、幂等、撤销和保存仍须按[接入说明](../../doc/ai-chat-property-edit-integration.md)完成并验收。

## 维护规则

新增动作时更新动作规范、动作注册表、对应校验器和编译入口测试。新增组件或属性必须先从宿主真实源码、已核验资料及 capabilities 确认，不能根据组件名或常见控件经验猜测。确认后在 `components/definitions/` 新增同名文件（点号组件名使用无点号文件名并在注册表显式映射），复用公共与已有共享规则、维护具体组件差异，并同时定义类型、适用范围、默认/清空/继承、条件、锁定和复杂处理。只在实际复用时提取 `_shared/`，不为尚未开放属性路径的组件创建空文件。缺少证据时标记待核验；不要只增加属性名称白名单。

业务规范不写入第三方开发指南；根目录 AGENTS.md 维护约束与导航，包 README 维护支持范围，三端接入文档维护接入流程。跨文件引用同一事实时以链接为主，避免维护多份完整属性表。Markdown 用于说明契约，不会在运行时自动注册能力或被模型自动读取。
