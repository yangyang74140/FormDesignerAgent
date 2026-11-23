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
├── proposal.py          # 统一编译入口、字段编译和当前展示投影
├── properties.py        # 属性提案编排、宿主授权、批次依赖
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

## 当前实现与已确认目标

本次分层保持现有编译行为；本目录标为“当前”的载荷均描述现有实现。源码仍生成 `presentation.fields/changes/items` 和 `result.actions`，属性路径仍使用 `form.apply_property_change` 等动作。它们是当前行为，不表示已完成根目录 `AGENTS.md` 第 5 节的输出收敛。

已确认的后续目标包括：统一 `actions`，每条使用 `action/payload`；字段业务配置只保留在动作草稿；presentation 只保留路由和标题等展示信息；用户编辑并选择后提交同一份动作草稿。当前路径与目标的差异应在后续协议调整中统一处理，不因文件重组新增兼容层、版本分流或动作同义词。

规范描述三类事实时必须区分：

- **Agent 已实现**：本地编译器具有对应规则，并有测试覆盖。
- **依赖宿主声明**：每轮真实 capabilities、策略、处理器与修订信息是必要条件；本地注册不授予执行能力。
- **后续目标或宿主待办**：不能以规范存在或 Agent 返回 ready 推断已经部署。

## 维护规则

新增动作时更新动作规范、动作注册表、对应校验器和编译入口测试。新增组件或属性必须先从宿主真实源码、已核验资料及 capabilities 确认，不能根据组件名或常见控件经验猜测。确认后在 `components/definitions/` 新增同名文件（点号组件名使用无点号文件名并在注册表显式映射），复用公共与已有共享规则、维护具体组件差异，并同时定义类型、适用范围、默认/清空/继承、条件、锁定和复杂处理。只在实际复用时提取 `_shared/`，不为尚未开放属性路径的组件创建空文件。缺少证据时标记待核验；不要只增加属性名称白名单。

业务规范不写入第三方开发指南；根目录 AGENTS.md 维护约束与导航，包 README 维护支持范围，三端接入文档维护接入流程。跨文件引用同一事实时以链接为主，避免维护多份完整属性表。Markdown 用于说明契约，不会在运行时自动注册能力或被模型自动读取。
