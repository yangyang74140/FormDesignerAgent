# 组件目录与扩展方式

生成与属性修改是不同的登记范围。下表仅列出重构前 `proposal.py` 的 FLOW_COMPONENTS 与 `properties.py` 的 COMPONENTS 已登记内容，**不是设计器真实组件全集，也不代表宿主已支持这些操作**。本次只迁移现有定义；没有根据名称推断或增加组件、属性。

七类组件的宿主资料来源是仓库已有属性核验清单；该清单记录的是整理时的核验，宿主当前能力仍以本轮真实 capabilities 和对应源码为准。CheckboxGroup、Switch 在该七类核验范围之外，本次只保留既有生成登记，不补属性规范。

| componentName | Agent 已登记生成 | Agent 已登记属性修改 | 属性定义文件 | 已有规则说明 |
| --- | --- | --- | --- | --- |
| Input | 支持 | 支持 | [Input.py](../../form_generation/components/definitions/Input.py) | [文本](./text.md) |
| Input.TextArea | 支持 | 支持 | [InputTextArea.py](../../form_generation/components/definitions/InputTextArea.py) | [文本](./text.md) |
| NumberPicker | 支持 | 支持 | [NumberPicker.py](../../form_generation/components/definitions/NumberPicker.py) | [数字](./number.md) |
| DatePicker | 支持 | 支持 | [DatePicker.py](../../form_generation/components/definitions/DatePicker.py) | [日期时间](./temporal.md) |
| TimePicker | 支持 | 支持 | [TimePicker.py](../../form_generation/components/definitions/TimePicker.py) | [日期时间](./temporal.md) |
| SelectSingle | 支持 | 支持 | [SelectSingle.py](../../form_generation/components/definitions/SelectSingle.py) | [选项](./choice.md) |
| SelectMulti | 支持 | 支持 | [SelectMulti.py](../../form_generation/components/definitions/SelectMulti.py) | [选项](./choice.md) |
| CheckboxGroup | 支持 | 未开放此属性路径 | 暂无 | [选项](./choice.md) |
| Switch | 支持 | 未开放此属性路径 | 暂无 | 本次不补专有属性；当前字段生成逻辑不输出 placeholder/options |

当前 `form.field.define` 只接收 client_ref、component_name、label、name、required、placeholder、options。属性模块支持 precision 等配置，不代表字段定义 IR 已支持一次性生成所有这些属性。完整字段生成支持单层 Flow；不因属性注册表扩展而自动开放容器或 Grid。

## 如何维护

- `components/common.py` 定义公共语义和可复用类型，例如描述、标题、权限。`components/definitions/` 每个组件一个同名属性文件，专有属性和处理就近维护，例如 DatePicker 可选星期、TimePicker 秒步长。`definitions/_shared/` 只提取多个组件实际共享的定义和处理，例如日期时间默认值与范围。
- 同名属性允许有不同定义：Input 的 format 是文本格式校验，DatePicker 的 format 是日期格式；SelectMulti 的 defaultValue 是数组，NumberPicker 的默认值内容是有限数值。
- 新增组件时在 `definitions/` 新增同名文件并在 `registry.py` 显式注册；`Input.TextArea` 的文件名为 `InputTextArea.py`，注册名仍为 `Input.TextArea`。复用公共与已有共享定义，避免复制整份公共属性；不为未实现的组件创建空定义。只有属性名没有类型、清空和默认值语义的定义不算完成。
- 新增复杂属性时补专用校验与副本预览行为，同时要求宿主真实 handlerId；不要把复杂属性直接 spread 到 props。
- 用编译入口验证用户行为、宿主授权与错误结果；注册表测试验证返回值隔离及具体组件覆盖，不让测试依赖集中私有字典。

现有宿主七类组件的全量属性、默认模板与核验记录见[属性清单](../../../doc/component-property-inventory.md)。该清单是资料来源，其中标为建议或待接入的部分仍需结合宿主实现核实；以下各族规范只说明 Agent 当前语义和限制。
