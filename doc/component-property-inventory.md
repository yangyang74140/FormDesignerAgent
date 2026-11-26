# 七类组件属性数据与 Agent 接入边界

整理日期：2026-11-18。范围：当前 ts-ui-ai-form-frontend-refactor 项目中的七类组件及 PC 属性面板。此次仅整理与核验，未修改业务源码、项目 docs、依赖或参考项目。

## 1. 文档范围与阅读说明

本文将属性数据、复杂结构、执行规则、完整 Schema 示例和核验结果合并在一份 Markdown 中，可独立阅读，无需配套 JSON 文件。

- 已从实际源码执行提取七类组件元数据，共 **188 个“组件 + 属性键”条目**；同一个 defaultValue 的自定义/公式 Setter 保留为独立行，共 193 行。它们不是 188 个全局不同属性，也不表示全部已经能由 Agent 正确修改。
- 第 2–5 节：组件标识、截图映射、公共与专有属性，包含中文含义、类型、初始值、枚举、范围和写入条件。
- 第 6–8 节：默认值、选项、日期时间范围、关联字段、清空方式、权限及布局联动。
- 第 9–10 节：当前 Agent 能力缺口与属性逐项勾选协议建议。
- 第 11 节：完整单行文本 FormSchema 示例。
- 第 12 节：十项源码行为核验结果与源码证据入口。

属性表和现状说明以整理时核验的源码为依据；文中标为“建议”“需要接入”的执行和清空规则不能视作宿主已部署。Agent 当前规则及实现分层见包内[属性规范](../specialized-agent-package/specs/properties.md)和[组件目录](../specialized-agent-package/specs/components/README.md)；后续实现进展以这些规范、源码与测试为准，不把本清单的历史缺口描述当作最新状态。声明 writableProps 本身不代表对应能力已实现。

## 2. 组件标识与初始数据

| 用户名称 | componentName | 代码显示名称 | placeholder 初始值 | 默认值初始结构 |
|---|---|---|---|---|
| 单行文本 | `Input` | 单行文本 | `` | `mode="undefined", value=""` |
| 多行文本 | `Input.TextArea` | 多行文本 | `` | `mode="undefined", value=""` |
| 数字 | `NumberPicker` | 数字 | `请输入数字` | `mode="undefined", value=undefined` |
| 日期 | `DatePicker` | 日期 | `年-月-日` | `mode="undefined", value=""` |
| 时间 | `TimePicker` | 时间 | `请选择时间` | `mode="undefined", value=""` |
| 下拉单选 | `SelectSingle` | 下拉单选 | `请选择` | `""` |
| 下拉多选 | `SelectMulti` | 下拉复选 | `请选择` | `[]` |

当前节点模型是 fields[].props（容器子节点使用 children）；不是旧文档中的 CustomFormItem 包 Input 宿主结构。node.title 是组件类型标题快照，业务字段标题使用 props.label；目标定位使用 node.id，不能用标题或数据库字段名代替。

## 3. 截图属性映射（已核实）

| 界面语义 | Schema / 执行语义 | 说明 |
|---|---|---|
| 占位提示 | props.placeholder | 文本；清空为字符串空值 |
| 描述信息 | props.extra | 文本；面板最多 200 字符 |
| 描述平铺 / 问号 | props.extraType = text / icon | 初始 icon；Grid 表单级 extraType 存在时可统一覆盖字段描述方式 |
| 默认值“1” | 依组件设置默认值模式与内容 | 文本为字符串“1”，数字为 number 1，日期/时间必须是对应格式字符串；下拉为真实选项 value |
| 必填 | access.required，通过 applyAccessToggle | 兼容 required 时要保持一致；单独写 required 不足以复用面板联动 |
| 隐藏标题 | props.hideTitle = true | 七类组件只在 Flow 暴露该面板属性 |
| 标题左/右对齐 | props.textAlign = left / right | 字段可独立覆盖；未设置继承表单；不是输入内容对齐 |
| 标题上下 / 左右 | props.labelPosition = top / left | 字段可独立覆盖；未设置继承表单；仅 Flow 面板 |
| 尺寸大 / 默认 / 小 | props.size = large / medium / small | Schema 是 medium，控件内部映射 middle；移动端面板隐藏 size |
| 数据库字段名称 | props.name | 新增时可生成；当前更新动作明确拒绝已有字段改名，不能列为修改能力 |

## 4. 七类组件公共属性

| 属性 / 中文含义 | 类型 | 初始值 / 回退 | 枚举 / 限制 | 显示 / 写入条件 |
|---|---|---|---|---|
| `label` / 字段标题 | string | "单行文本" | 最多 50 字符 | 普通字段条件下可配置 |
| `enableCustomTitle` / 自定义标题 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `customTitle` / 自定义标题文字 | string | "" | 最多 50 字符 | enableCustomTitle 为真 |
| `name` / 数据库字段名称 | string | "" | 最多 50 字符 | Agent 修改现有字段禁止 |
| `extra` / 描述信息 | string | "" | 最多 200 字符 | 普通字段条件下可配置 |
| `extraType` / 描述显示方式 | string | "icon" | "text" / "icon" | 普通字段条件下可配置 |
| `required` / 必填 | boolean | access.required：false | 面板未声明范围/枚举 | 写 access.required |
| `requiredMessage` / 必填提示内容 | string | 未声明（不等于 false） | 面板未声明范围/枚举 | required 为真 |
| `edit` / 编辑 | boolean | access.editable：true | 面板未声明范围/枚举 | 写 access.editable |
| `display` / 显示 | boolean | access.visible：true | 面板未声明范围/枚举 | 写 access.visible |
| `disableManualEdit` / 禁止手工编辑 | boolean | access.forbidManualInput：false | 面板未声明范围/枚举 | 写 access.forbidManualInput |
| `hideTitle` / 隐藏标题 | boolean | false | 面板未声明范围/枚举 | 仅 Flow |
| `readOnlyDisplay` / 只读显示 | boolean | false | false / true | 普通字段条件下可配置 |
| `textAlign` / 文字对齐方式 | string | 未写入；继承表单，最终 left | "left" / "right" | 仅 Flow |
| `labelPosition` / 字段标题位置 | string | 未写入；继承表单，最终 left | "top" / "left" | 仅 Flow |
| `size` / 组件尺寸 | string | "medium" | "medium" / "large" / "small" | 普通字段条件下可配置 |

补充：label 的默认值按各组件名称变化；name 的 meta 初始空字符串只用于模板，createNodeFromDef 会自动生成名称。required 的面板值来自 resolveFieldAccess；该函数不会从旧 props.required 兜底。公共默认值里没有 access 对象时，其权威默认值为 visible=true、editable=true、required=false、forbidManualInput=false。

清空/恢复建议（需要执行器实现）：字符串写空字符串；布尔开关关闭并执行相应联动；size 恢复 medium；extraType 恢复 icon；textAlign/labelPosition 移除局部键以恢复继承；标题不能清空；数据库字段名不能经修改提案清空或重命名。数值配置不能统一当成 0；应根据属性恢复默认值或解除条件。

## 5. 各组件专有属性

### 单行文本：`Input`

来源：[input.meta.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/component-metas/basic/input.meta.ts)

| 属性 / 中文含义 | 类型 | 初始值 / 回退 | 枚举 / 限制 | 显示 / 写入条件 |
|---|---|---|---|---|
| `placeholder` / 占位符 | string | "" | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `defaultValueConfig` / 默认值 | string | "undefined" | "undefined" / "custom" / "formula" | 普通字段条件下可配置 |
| `defaultValue` / 默认值内容 | string \| FormulaDefaultValue | "" | 面板未声明范围/枚举 | custom / formula 模式分别使用对应 Setter；须成组写入 |
| `allowClear` / 清除按钮 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `showLimitHint` / 显示计数器 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `textMaxLength` / 计数器与输入长度上限 | number (finite) | 200 | min=1 | showLimitHint 为真 |
| `enableQuickCopy` / 快捷复制 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `enableLinkParser` / 解析超链接 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `relatedField` / 选择关联表单字段 | RelatedFieldValue \| undefined | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `isUnique` / 不允许重复值 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `uniqueMessage` / 重复值提示内容 | string | 未声明（不等于 false） | 面板未声明范围/枚举 | isUnique 为真 |
| `format` / 格式校验 | string | "none" | "none" / "chinese" / "number" / "letter" / "letter_num" / "phone" / "tel" / "postcode" / "idcard" / "email" | 普通字段条件下可配置 |
| `formatMessage` / 格式校验提示内容 | string | 未声明（不等于 false） | 面板未声明范围/枚举 | format ≠ "none" |

### 多行文本：`Input.TextArea`

来源：[input-textarea.meta.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/component-metas/basic/input-textarea.meta.ts)

| 属性 / 中文含义 | 类型 | 初始值 / 回退 | 枚举 / 限制 | 显示 / 写入条件 |
|---|---|---|---|---|
| `placeholder` / 占位符 | string | "" | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `defaultValueConfig` / 默认值 | string | "undefined" | "undefined" / "custom" / "formula" | 普通字段条件下可配置 |
| `defaultValue` / 默认值内容 | string \| FormulaDefaultValue | "" | 面板未声明范围/枚举 | custom / formula 模式分别使用对应 Setter；须成组写入 |
| `rows` / 行数 | number (finite) | 3 | min=3；max=10 | 普通字段条件下可配置 |
| `disableAutoHeight` / 禁止高度自撑 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `showEmptyLines` / 显示空行 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `showLimitHint` / 显示计数器 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `textMaxLength` / 计数器与输入长度上限 | number (finite) | 200 | min=1 | showLimitHint 为真 |
| `enableQuickCopy` / 快捷复制 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `enableLinkParser` / 解析超链接 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `relatedField` / 选择关联表单字段 | RelatedFieldValue \| undefined | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |

### 数字：`NumberPicker`

来源：[number-picker.meta.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/component-metas/basic/number-picker.meta.ts)

| 属性 / 中文含义 | 类型 | 初始值 / 回退 | 枚举 / 限制 | 显示 / 写入条件 |
|---|---|---|---|---|
| `placeholder` / 占位提示 | string | "请输入数字" | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `defaultValueConfig` / 默认值 | string | "undefined" | "undefined" / "custom" / "formula" | 普通字段条件下可配置 |
| `defaultValue` / 默认值内容 | number (finite) \| FormulaDefaultValue | undefined | 面板未声明范围/枚举 | custom / formula 模式分别使用对应 Setter；须成组写入 |
| `precision` / 小数位数 | number (finite) | 0 | min=0；max=10 | 保存后锁定 |
| `numberType` / 类型 | string | "numeric" | "numeric" / "permille" / "percent" | 保存后锁定 |
| `showAmountInUppercase` / 金额大写 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `amountInUppercase` / 金额大写显示 | string | "outer" | "inner" / "outer" | showAmountInUppercase 为真 |
| `thousandsSeparator` / 千位分隔符 | boolean | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `step` / 步长 | number (finite) | 1 | min=0 | 普通字段条件下可配置 |
| `innerAfter` / 单位 | string | "" | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `relatedField` / 选择关联表单字段 | RelatedFieldValue \| undefined | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `minEnable` / 最小值 | boolean | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `min` / 最小值阈值 | number (finite) | 未声明（不等于 false） | 面板未声明范围/枚举 | minEnable 为真 |
| `minMessage` / 最小值提示内容 | string | 未声明（不等于 false） | 面板未声明范围/枚举 | minEnable 为真 |
| `maxEnable` / 最大值 | boolean | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `max` / 最大值阈值 | number (finite) | 未声明（不等于 false） | 面板未声明范围/枚举 | maxEnable 为真 |
| `maxMessage` / 最大值提示内容 | string | 未声明（不等于 false） | 面板未声明范围/枚举 | maxEnable 为真 |

### 日期：`DatePicker`

来源：[date-picker.meta.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/component-metas/basic/date-picker.meta.ts)

| 属性 / 中文含义 | 类型 | 初始值 / 回退 | 枚举 / 限制 | 显示 / 写入条件 |
|---|---|---|---|---|
| `placeholder` / 占位提示 | string | "年-月-日" | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `defaultValueConfig` / 默认值 | string | "undefined" | "undefined" / "custom" / "systemDate" / "formula" | 普通字段条件下可配置 |
| `defaultValue` / 默认值内容 | string \| FormulaDefaultValue | "" | 面板未声明范围/枚举 | custom / formula 模式分别使用对应 Setter；须成组写入 |
| `format` / 日期格式 | string | "YYYY-MM-DD" | "YYYY" / "YYYY-MM" / "YYYY-MM-DD" / "YYYY-MM-DD HH" / "YYYY-MM-DD HH:mm" / "YYYY-MM-DD HH:mm:ss" | 保存后锁定 |
| `allowClear` / 清除按钮 | boolean | true | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `relatedField` / 选择关联表单字段 | RelatedFieldValue \| undefined | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `disabledDays` / 可选星期 | { enabled: boolean; days: string[] } \| null | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `minTimeCondition` / 最早时间 | TimeConditionValue \| null | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `maxTimeCondition` / 最晚时间 | TimeConditionValue \| null | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |

### 时间：`TimePicker`

来源：[time-picker.meta.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/component-metas/basic/time-picker.meta.ts)

| 属性 / 中文含义 | 类型 | 初始值 / 回退 | 枚举 / 限制 | 显示 / 写入条件 |
|---|---|---|---|---|
| `placeholder` / 占位提示 | string | "请选择时间" | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `defaultValueConfig` / 默认值 | string | "undefined" | "undefined" / "custom" / "systemTime" / "formula" | 普通字段条件下可配置 |
| `defaultValue` / 默认值内容 | string \| FormulaDefaultValue | "" | 面板未声明范围/枚举 | custom / formula 模式分别使用对应 Setter；须成组写入 |
| `format` / 格式 | string | "HH:mm:ss" | "HH:mm:ss" / "HH:mm" | 保存后锁定 |
| `allowClear` / 清除按钮 | boolean | true | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `minuteStep` / 分钟步长 | number (finite) | 1 | min=1；max=59 | 普通字段条件下可配置 |
| `secondStep` / 秒步长 | number (finite) | 1 | min=1；max=59 | 普通字段条件下可配置 |
| `relatedField` / 选择关联表单字段 | RelatedFieldValue \| undefined | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `minTimeCondition` / 最早时间 | TimeConditionValue \| null | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `maxTimeCondition` / 最晚时间 | TimeConditionValue \| null | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |

### 下拉单选：`SelectSingle`

来源：[select-single.meta.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/component-metas/basic/select-single.meta.ts)

| 属性 / 中文含义 | 类型 | 初始值 / 回退 | 枚举 / 限制 | 显示 / 写入条件 |
|---|---|---|---|---|
| `placeholder` / 占位提示 | string | "请选择" | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `allowClear` / 清除按钮 | boolean | true | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `popupMatchSelectWidth` / 下拉菜单宽度限制 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `showSearch` / 可搜索 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `options` / 选项配置 | CustomComplexOptionValue | {"dataSource":[{"primaryKey":"1","value":"1","label":"选项1","activeKey":false,"color":null,"disabled":false},{"primaryKey":"2","value":"2","label":"选项2","activeKey":false,"color":null,"disabled":false},{"primaryKey":"3","value":"3","label":"选项3","activeKey":false,"color":null,"disabled":false}],"isColor":false,"nextValueSeed":4} | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `relatedField` / 选择关联表单字段 | RelatedFieldValue \| undefined | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |

### 下拉复选：`SelectMulti`

来源：[select-multi.meta.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/component-metas/basic/select-multi.meta.ts)

| 属性 / 中文含义 | 类型 | 初始值 / 回退 | 枚举 / 限制 | 显示 / 写入条件 |
|---|---|---|---|---|
| `placeholder` / 占位提示 | string | "请选择" | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `popupMatchSelectWidth` / 下拉菜单宽度限制 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `selectAll` / 全选功能 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `showSearch` / 可搜索 | boolean | false | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `supportReverseSelect` / 支持反选 | boolean | true | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `options` / 选项配置 | CustomComplexOptionValue | {"dataSource":[{"primaryKey":"1","value":"1","label":"选项1","activeKey":false,"color":null,"disabled":false},{"primaryKey":"2","value":"2","label":"选项2","activeKey":false,"color":null,"disabled":false},{"primaryKey":"3","value":"3","label":"选项3","activeKey":false,"color":null,"disabled":false}],"isColor":false,"nextValueSeed":4} | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `relatedField` / 选择关联表单字段 | RelatedFieldValue \| undefined | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `maxCountEnable` / 最多选择数 | boolean | 未声明（不等于 false） | 面板未声明范围/枚举 | 普通字段条件下可配置 |
| `maxTagCount` / 最多选择数 | number (finite) | 未声明（不等于 false） | min=1 | maxCountEnable 为真 |
| `maxCountMessage` / 超出最多选择数提示内容 | string | 未声明（不等于 false） | 面板未声明范围/枚举 | maxCountEnable 为真 |


这些上下限来自面板配置。当前 Agent 适配器未普遍校验 min/max、长度、有限枚举与跨属性组合；不能把面板限制直接当作 Agent 已强制执行。rows、步长、位数等是否强制整数也应由最终属性协议明确，不把面板未声明的约束伪称现有校验。

专有语义：

- 单行/多行：showLimitHint 开启后才将 textMaxLength 作为运行态输入长度限制，并显示计数器；默认 textMaxLength=200，但开关初始 false。多行不提供格式校验、不重复值和清除按钮面板项。快捷复制/解析超链接主要用于只读展示。
- 单行格式枚举：none（无）、chinese（中文）、number（数字）、letter（字母）、letter_num（字母和数字）、phone（手机号码）、tel（电话号码）、postcode（邮编）、idcard（身份证）、email（邮箱）。isUnique 与 uniqueMessage 是面板配置；真实重复值验证依赖宿主/服务，不能仅凭属性存在宣称后端校验已接通。
- 数字：precision=0、step=1、numberType=numeric。numberType 还有 permille（千分比）、percent（百分比）。运行时显示百分比/千分比分别乘 100/1000，写回除以同一倍率；如要表达 10%，存储值为 0.1。金额大写仅在 numeric 类型生效。min/max 要与 minEnable/maxEnable 成组设置，关闭开关并不等同自动删除原阈值。
- 日期：format 改变会覆盖 placeholder；切到 YYYY 或 YYYY-MM 时还会清 disabledDays=null。保存后 format 锁定。默认值和固定边界按 format 写字符串。
- 时间：面板 format 只有 HH:mm:ss、HH:mm，保存后锁定；minuteStep/secondStep 初始 1、面板范围 1–59。hourStep 初始 1，但没有面板编辑行，不应因为存在于 defaultProps 就自动暴露为 Agent 可修改属性。HH:mm 下 secondStep 不影响实际秒列。
- 下拉单选：有 allowClear（初始 true）；多选没有清除按钮配置，运行时明确忽略历史 allowClear 并强制 false。
- 下拉多选：selectAll=false、supportReverseSelect=true；maxCountEnable + maxTagCount + maxCountMessage 才是最多选择数配置，其中 maxTagCount 在此业务里用于选择数量上限，不可直接解释成 antd 的折叠标签数。

## 6. 默认值不是一个简单属性

### 6.1 文本 / 数字 / 日期 / 时间

| 组件 | 模式枚举 | custom 内容 | 清空规则 |
|---|---|---|---|
| Input / Input.TextArea | undefined / custom / formula | string | mode 字符串设为 undefined，删除/清理 defaultValue |
| NumberPicker | undefined / custom / formula | 有限 number | 同上；0 是合法默认值，不可按空值处理 |
| DatePicker | undefined / custom / systemDate / formula | 按 format 的 string | systemDate 和 undefined 都清静态 defaultValue |
| TimePicker | undefined / custom / systemTime / formula | 按 format 的 string | systemTime 和 undefined 都清静态 defaultValue |

这里的模式 undefined 是字面字符串 **"undefined"**，不等于 JavaScript undefined。面板 helper 清值时写 JS undefined；JSON 序列化会丢失该键，所以 Agent 清空协议应显式支持 unset/reset，不能靠传 undefined，也不能假设所有属性都允许 null。

自定义模式必须原子设置 defaultValueConfig + defaultValue。切换模式要清理不兼容的原值，复用 default-value-helpers.ts 的 applyDefaultValueModeChange / applyCustomTextDefault / applyCustomNumberDefault / applyCustomDateDefault / applyCustomTimeDefault。公式结构为：

~~~json
{
  "defaultValueConfig": "formula",
  "defaultValue": {
    "mode": "formula",
    "formulaName": "公式名称",
    "formulaContent": "表达式",
    "formulaContentShow": "显示表达式"
  }
}
~~~

公式 helper 还兼容历史数组/前缀形式，但 Agent 新写入应使用规范对象；表达式合法性、字段引用与公式服务能力要单独检查。当前通用属性适配器拒绝公式对象，尚未提供完整公式写入能力。

### 6.2 下拉默认值与选项

下拉面板没有独立 defaultValueSetter；通过选项 activeKey 选择默认项。复杂结构：

~~~json
{
  "options": {
    "dataSource": [
      { "primaryKey": "1", "value": "a", "label": "选项A", "activeKey": true, "color": null, "disabled": false },
      { "primaryKey": "2", "value": "b", "label": "选项B", "activeKey": false, "color": null, "disabled": false }
    ],
    "isColor": false,
    "nextValueSeed": 3
  },
  "defaultValue": "a",
  "enableColor": false
}
~~~

单选默认值 string，清空时 setter 派生 undefined；初始 meta 为 ""。多选默认值 string[]，清空为 []。两者都要同步 activeKey；单选最多一个 activeKey=true；默认项须启用。颜色要同步 options.isColor 与 enableColor，不能只改一个字段。primaryKey 与业务 value 是不同标识，不能把标签或列表序号替代业务值。options.relatedParentField 可包含 parentFieldName、parentFieldLabel、parentComponentId、relations[{parentOptionValue,parentOptionLabel,childOptionValues}]。单选选项还支持 associateDirectory；更新时必须保留已存在的关联目录/父子关系等数据。

面板会调用 checkFieldValueUsage 检查删除选项是否被引用。当前 Agent 对已保存字段 options 整体拒绝修改，比面板更严格；不能直接开放删除以规避引用检查。

## 7. 日期/时间范围、关联字段的复合类型

### 7.1 可选星期（DatePicker）

~~~json
{ "disabledDays": { "enabled": true, "days": ["1", "2", "3", "4", "5"] } }
~~~

虽然字段名是 disabledDays，days 表示 **允许选择** 的星期：周日="0"，周一到周六="1"…"6"。关闭为 null。启用时面板默认选中全部七天；当前运行时 days=[] 会回退为不限制，不能解释为所有日期禁用。年/月格式不支持星期配置，格式联动会清空它。

### 7.2 最早/最晚时间

minTimeCondition 和 maxTimeCondition 独立使用 TimeConditionValue | null，关闭写 null：

~~~ts
type TimeConditionValue = {
  enabled: true;
  source: "dynamic" | "fixed" | "field";
  dynamicMode?: "current" | "before" | "after";
  dynamicUnit?: "day" | "week" | "month" | "quarter" | "year";
  dynamicAnchor?: "today" | "currentWeek" | "currentMonth" | "nextMonth" | "currentQuarter" | "currentYear";
  offsetValue?: number;
  fixedValue?: string;
  fieldName?: string;
};
~~~

- fixed：写当前 format 对应字符串；field：写其他同类字段的 name（非标题）；面板排除当前字段自身。
- 日期 dynamic/current：支持当天、当周、当月、下月、当季、当年；before/after 使用 offsetValue（面板 min=0）和 dynamicUnit。
- 当前日期运行时的 before/after 以 day/week/month/quarter/year=1/7/30/90/365 天近似换算，并非自然月/自然年偏移；不要让 Agent 文案承诺另一种语义。
- 时间面板 dynamic 仅提供 current（填写时）；不应因为类型兼容字段包含 before/after 就暴露给 Agent。
- source 切换时要替换不再适用的分支字段，而不是无条件深合并保留旧配置。字段引用存在性、同类限制、上下界关系应由专用验证器检查。

### 7.3 关联表单字段

~~~ts
type RelatedFieldValue = {
  relatedFormId?: string;
  relatedType?: "form" | "document" | "process" | "person" | "department";
  componentName?: string;
  relatedFieldId?: string;
};
~~~

该 Setter 同时更新目标 node.props.relatedField 和表单 props.relatedFields，并依赖来源组件及远程字段元数据。清空也要同步清理两处；不能把其视为普通对象合并。当前 Agent 简单适配器拒绝该对象，应保留为需要专用接入的能力。

## 8. 写入条件与统一执行规则

1. 组件/系统限制：确认 node.id 存在且组件类型匹配；当前 AI 拒绝系统字段及容器更新，不应绕过。
2. 布局/设备：上述布局三项 hideTitle/textAlign/labelPosition 在七类组件的 Grid 面板隐藏；移动端还有 size/readOnlyDisplay 等过滤。现有 Agent getPropertyFields 未传布局，因此暂未执行相同过滤。
3. 保存锁：saved=true 或 disabledName=true 时，数字 precision/numberType、日期/时间 format 禁改；已有字段 name 的任何真正改名始终被当前提案转换器拒绝。
4. 条件显隐：requiredMessage、计数器长度、自定义/公式默认值、金额大写位置、min/max、最多选择数等应基于最终候选状态验证，允许一个原子补丁中先启用模式再写依赖值。
5. access 联动：显示关闭会关闭其余三个状态；编辑关闭会清必填/禁止手工编辑；开启必填或禁止手工编辑会开启显示+编辑。不能只 spread required。
6. 数值、字符串长度、枚举、日期字符串和范围关系需要执行期验证；属性名白名单不能替代值校验。
7. 嵌套结构分别处理：access 用 applyAccessToggle；默认值用 paired helper；options 用保留身份/引用的选项执行器；日期范围按 source 规范化；relatedField 做跨节点/表单同步。没有一种通用深合并能覆盖全部语义。
8. 日期联动应只由真正触发的格式变更执行；普通描述修改不应意外覆盖自定义 placeholder。整批修改最后一次性写 store，形成一个撤销帧。

### 8.1 清空与恢复规则对照

以下区分面板现有行为与建议的 Agent 操作；建议尚未实现，不能直接作为当前动作载荷发送。

| 属性或组合 | 清空 / 恢复语义 | 需要保留的联动或限制 |
|---|---|---|
| placeholder、extra、customTitle、各提示文案 | 写入空字符串 `""` | customTitle 清空不等于关闭 enableCustomTitle；提示文案为空时运行时可能使用默认提示 |
| label | 不允许把必填标题清空 | 修改业务标题使用 props.label，不能改 node.title 代替 |
| name | 现有字段禁止清空或改名 | 新增字段由新增动作生成合法且唯一的名称 |
| enableCustomTitle | 关闭写 false | 关闭后隐藏自定义标题输入；是否删除历史文字需显式定义，不默认丢弃 |
| required、edit、display、disableManualEdit | 转为对应 access 键，调用 applyAccessToggle(false) | display/edit 关闭会派生关闭其他权限；不能只改普通 props |
| hideTitle | 取消隐藏写 false | 七类组件的该配置面板仅在 Flow 展示 |
| readOnlyDisplay | 恢复“显示输入框”写 false | 它是只读展示形式，不等于解除字段只读权限 |
| size | 恢复默认写 `"medium"` | 不能把控件内部的 `"middle"` 写入 Schema |
| extraType | 恢复初始值写 `"icon"` | Grid 的表单级设置可能覆盖字段配置 |
| textAlign、labelPosition | 删除字段局部键，恢复继承 | 写 `"left"` 是显式覆盖，不等于恢复继承 |
| 文本/数字/日期/时间默认值 | 写模式字符串 `"undefined"`，同时清理 defaultValue | 复用默认值 helper；不能只把内容写空或写 null |
| systemDate、systemTime 模式 | 写对应模式，同时清理静态 defaultValue | 动态默认值由运行时生成，不固化当前时间 |
| 下拉单选默认值 | 取消所有 activeKey，setter 派生 defaultValue=undefined | 初始 meta 的空字符串与 setter 的清空结果应按语义兼容 |
| 下拉多选默认值 | 取消所有 activeKey，defaultValue=[] | 保留选项身份和业务 value |
| showLimitHint | 关闭写 false | 运行时停止计数和相应输入长度限制；不要求删除 textMaxLength |
| textMaxLength、rows、step、precision、分钟/秒步长 | 恢复各自 meta 默认值，或按业务定义解除配置 | 不统一写 0/null；precision 保存后不可改 |
| Input.format | 取消格式校验写 `"none"` | 是否清理 formatMessage 需明确；不把历史值残留误判为启用 |
| DatePicker / TimePicker.format | 恢复组件初始格式也属于格式修改 | 保存锁仍适用；日期格式改变还会修改占位提示及星期配置 |
| minEnable、maxEnable、maxCountEnable | 关闭对应开关 | 停用阈值校验，不等于自动删除原阈值/提示文案 |
| disabledDays | 写 null | 不使用 days=[] 表达“所有日期禁用” |
| minTimeCondition、maxTimeCondition | 写 null | 切换 source 时按新分支重新规范化对象 |
| options | 按业务动作增删改选项，不能通用清空覆盖 | 检查引用、默认项、稳定身份、关联目录和父子关系；当前已保存字段不开放 AI 修改 |
| options.isColor 与 enableColor | 同步关闭为 false | 不必因此删除选项已有 color，避免丢失配置 |
| relatedField | 清除字段绑定并同步清理表单 relatedFields | 需要跨字段/表单的一致性更新 |

其他布尔功能（如 allowClear、showSearch、selectAll、supportReverseSelect、enableQuickCopy、enableLinkParser、showAmountInUppercase 等）写 false 表示关闭，不一定等于恢复其初始默认值。例如 SelectSingle.allowClear 初始 true、SelectMulti.supportReverseSelect 初始 true；“恢复默认”和“关闭功能”应使用不同语义。

## 9. 当前 Agent 链路已存在与缺口

| 项目 | 当前事实 | 接入前需要处理 |
|---|---|---|
| 能力上下文 | blank-canvas-context.json 给所有组件同一组 label/name/required/placeholder/options | 七类组件逐项提供语义属性定义，区分新增与修改；非选项组件不能声明 options；修改能力不能声明 name |
| 简单属性 | 实际 adaptComponentProps 按 defaultProps + propertyFields 建允许集合，有基本类型/部分枚举校验 | 与上下文能力声明保持一致，校验范围、长度和写入条件 |
| 模式默认值 | 未复用默认值 helper | 成对写模式和值，并定义清空操作；模式枚举由 helper 提供 |
| 数字默认值 | defaultProps.defaultValue=undefined，适配器用 typeof expected，导致 number 1 被拒绝 | 按组件语义校验 number，而不是按默认值 typeof 推断 |
| 权限 | required 同步了 access.required，但没有 applyAccessToggle；display/edit/disableManualEdit 被当普通属性 | 复用面板 access 映射和联动 |
| 日期联动 | 适配器 changedKey=null，执行全部联动 | 仅格式变化触发相应值联动，避免改 extra 也重置 placeholder |
| 下拉默认值 | 写 defaultValue 不同步 activeKey；options 适配保留旧 activeKey | 由一套执行器同时维护默认值与选项状态 |
| 下拉复杂数据 | convertOptions 只输出有限字段，未保留 relatedParentField / associateDirectory 等 | 复杂适配保留已有数据并进行引用检查 |
| 清空 | 简单值路径不接受 null/undefined | 明确 set/unset/reset，按属性语义执行 |
| revision/目标 | target 必须带 baseRevision，但 convertFormProposal 中目标和版本比较的 if 被注释 | 恢复/完成实际校验；不能把现状描述为已有完整并发保护 |
| 幂等/事务/撤销 | controller 有 proposalId+fingerprint 幂等、事务副本、单次 store 提交、unsaved 回执 | 属性修改复用现有事务入口；联动和复合对象仍需补齐 |
| 保存 | Agent 应用回执 unsaved=true | 应用不等于已持久化到服务；保存链路及保存后回读需要在实施时验证 |
| 逐属性勾选 | 当前 selectedClientRefs 仅允许纯新增；非新增必须整批执行，edits 仅允许改新增列表标题 | 截图的逐属性勾选需要新契约，不能复用新增勾选语义 |

## 10. 属性动作草稿契约

2026-11-23 的输出调整统一使用顶层 `actions`，以 `actionId` 作为勾选和依赖标识。属性修改保留 `form.apply_property_change` 的语义处理，`payload` 保存 nodeId、componentName、property、operation 及适用的新值，`preconditions.before` 保存修改前状态。默认值模式与内容、选项默认项、access 联动属于一项完整语义操作，不能拆成会产生无效组合的任意叶子键。

子 Agent 仅输出 `{ form_proposal: proposal }`，新建使用 `shared.form-create-confirm`，已有表单变更使用 `shared.form-change-confirm`；确认卡的 presentation 只含 kind 和 title，不复制 fields/changes/items 或 result.actions。用户编辑并选择后提交唯一最终动作草稿，不附旧载荷及 edits，也不维护旧输出双格式解析。“换一换”需要最新快照和 revision。宿主必须重新检查目标、版本、before、能力、依赖、锁定及最终候选状态，再原子应用；本次不修改设计器宿主，其接入仍需同步完成。第 9 节记录原核验时的宿主事实，不表示缺口已修复。完整契约见[三端接入说明](./ai-chat-property-edit-integration.md)。

现有更新动作载荷示例（只展示已有动作外形，不表示缺口已经修复）：

~~~json
{
  "actionId": "action_update_placeholder",
  "action": "form.update_component",
  "payload": {
    "fieldId": "fld_input_example",
    "changes": { "placeholder": "请输入申请说明" }
  }
}
~~~

## 11. 完整单行文本 Schema 示例

下面是当前模型的完整示例，不是线上用户数据。它展示标题、数据库标识、描述、默认值、权限与布局的组合。字段布局为 top，表单布局为 left，用以说明字段可覆盖表单配置。required 同步用于兼容，access 仍为权威状态。

~~~json
{
  "schemaVersion": "1.1.0",
  "id": "form_property_example",
  "props": {
    "description": "",
    "columns": 2,
    "labelPosition": "left",
    "labelWidth": 80,
    "textAlign": "left",
    "rowHeight": "16px"
  },
  "layoutMode": "flow",
  "fields": [
    {
      "id": "fld_input_example",
      "componentName": "Input",
      "componentCategory": "field",
      "title": "单行文本",
      "props": {
        "label": "申请说明",
        "required": true,
        "placeholder": "请输入申请说明",
        "defaultValueConfig": "custom",
        "defaultValue": "1",
        "allowClear": false,
        "showLimitHint": false,
        "textMaxLength": 200,
        "enableQuickCopy": false,
        "enableLinkParser": false,
        "format": "none",
        "isUnique": false,
        "enableCustomTitle": false,
        "customTitle": "",
        "name": "application_note",
        "extra": "请填写申请原因",
        "extraType": "text",
        "hideTitle": false,
        "readOnlyDisplay": false,
        "size": "large",
        "identifiers": {
          "name": "application_note"
        },
        "access": {
          "visible": true,
          "editable": true,
          "required": true,
          "forbidManualInput": false
        },
        "textAlign": "left",
        "labelPosition": "top"
      }
    }
  ]
}
~~~

## 12. 核验与证据入口

### 12.1 十项源码行为核验

此前已直接执行当前源码的元数据组合、默认值 helper、属性适配器、日期联动和 access 解析，以下十项观察均由断言确认。这里的“确认”表示复现当前行为，不表示功能已满足接入要求。

| 序号 | 输入或场景 | 已确认的当前结果 | 对 Agent 接入的影响 |
|---|---|---|---|
| 1 | NumberPicker 设置 `defaultValueConfig="custom"`、`defaultValue=1` | 当前通用适配器拒绝，报复杂默认值需要专用适配器 | 必须按数字语义校验，不能按初始值 undefined 推断类型 |
| 2 | Input.TextArea 设置 `rows=99` | 当前适配器接受，未执行面板 max=10 | 属性协议须补充范围校验 |
| 3 | Input 设置未知 `defaultValueConfig` 模式 | 当前适配器接受未知字符串 | 模式枚举须从默认值 helper 提供并在执行时检查 |
| 4 | Input 设置 `display=false` | 只写普通属性，`access.visible` 仍为 true | 应映射到 access.visible 并调用权限联动 |
| 5 | 原 access.visible/editable 均为 false，设置 `required=true` | access.required 变为 true，但 visible/editable 仍为 false | 与面板行为不同；须复用 applyAccessToggle |
| 6 | SelectSingle 设置 `defaultValue="2"` | defaultValue 改变，但选项 activeKey 没有同步 | 默认值与选项默认项应成组更新 |
| 7 | DatePicker 已有自定义 placeholder，仅修改 extra | 全量联动将 placeholder 重置为当前日期格式提示 | 应只在实际格式变更时执行格式派生更新 |
| 8 | 已保存 NumberPicker 修改 precision | 当前适配器拒绝 | 保留已保存字段的受保护属性限制 |
| 9 | 默认值模式切换为“无” | helper 写入字符串 `defaultValueConfig="undefined"` 和 JS `defaultValue=undefined` | JSON 协议须显式表达清值，不能依赖 undefined 序列化 |
| 10 | 调用文本自定义默认值 helper，输入字符串“1” | 同时写入 `defaultValueConfig="custom"`、`defaultValue="1"` | Agent 应复用成组写入语义 |

另已执行 validateSchema 对第 11 节完整示例做结构校验，并核验七类元数据来源与本报告全部源码链接存在。结构校验不替代逐属性业务校验。此次未修改项目代码，因此未运行全量 typecheck/build；未验证远程保存回读、真实公式服务、唯一性接口或浏览器交互，也未声称这些能力已接通。

本节记录整理时取得的核验结果；后续源码变化后，应重新执行相关核验再据此判断支持状态。

### 12.2 源码证据入口

| 证据 | 入口 |
|---|---|
| 公共属性、默认值、校验字段 | [sharedProperties.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/property-panel/sharedProperties.ts) |
| 面板保存锁、条件过滤与更新入口 | [PropertyPanel.tsx](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/property-panel/PropertyPanel.tsx) |
| 属性分组和布局可见性 | [propertyFields.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/registry/propertyFields.ts) / [gridLayoutPropertyRules.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/property-panel/gridLayoutPropertyRules.ts) |
| 默认值成组写入 | [default-value-helpers.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/setters/default-value-helpers.ts) |
| 权限解析与联动 | [access.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-schema/src/access.ts) |
| 字段布局继承、尺寸映射 | [fieldLayout.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-renderer/src/fieldLayout.ts) |
| 复杂选项编辑与默认项派生 | [custom-complex-option-setter.tsx](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/setters/custom-complex-option-setter.tsx) |
| 日期星期与边界 Setter | [custom-date-check-group-setter.tsx](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/setters/custom-date-check-group-setter.tsx) / [custom-time-condition-setter.tsx](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/setters/custom-time-condition-setter.tsx) |
| 关联字段双向维护 | [custom-related-fields-setter.tsx](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/configs/setters/custom-related-fields-setter.tsx) |
| 数字比例语义 | [number-picker-display.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-renderer/src/fields/shared/number-picker-display.ts) |
| 数字/多选等运行时校验 | [validators.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-renderer/src/validators.ts) |
| 能力声明 | [blank-canvas-context.json](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/left-panel/ai/blank-canvas-context.json) / [AgentChatPanel.tsx](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/left-panel/ai/AgentChatPanel.tsx) |
| Agent 属性适配与限制 | [component-prop-adapters.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/left-panel/ai/component-prop-adapters.ts) |
| 提案解析、修改执行、被注释的目标/版本检查 | [form-proposal-adapter.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/left-panel/ai/form-proposal-adapter.ts) |
| 宿主幂等与原子提交 | [use-form-proposal.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/left-panel/ai/use-form-proposal.ts) |
| 当前提案类型 | [form-proposal-types.ts](/Users/demo_user/Desktop/work/form-refactor/ts-ui-ai-form-frontend-refactor/packages/form-designer/src/modules/left-panel/ai/form-proposal-types.ts) |

既有 docs/input-default-value-chain.md 描述了旧宿主结构，不能替代这次以当前 meta 与 setter 为依据的清单。没有改动该文档。
