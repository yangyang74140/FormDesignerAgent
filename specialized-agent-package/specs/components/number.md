# 数字族：NumberPicker

组合[公共属性规则](../properties.md)，额外定义数值配置、范围和金额展示。

| 属性 | 当前类型、范围或默认值 |
| --- | --- |
| defaultValue | `{mode:"undefined"}` 或 `{mode:"custom",value:有限数值}`；0 合法；公式未开放 |
| precision | 有限数值 0–10；默认 0；保存后锁定 |
| numberType | numeric/permille/percent；默认 numeric；保存后锁定 |
| step | 有限数值且不小于 0；默认 1 |
| showAmountInUppercase、thousandsSeparator | 布尔 |
| amountInUppercase | inner/outer；默认 outer；依赖 showAmountInUppercase |
| innerAfter | 单位字符串，默认空 |
| numericRange | `{min?:{value:有限数值,message?:字符串},max?:{value:有限数值,message?:字符串}}`；提示最多 200 字；需要宿主 schema/handler；未指定边界关闭并清理；clear/reset 为 `{}` |
| minEnable、maxEnable | 布尔 |
| min、max | 有限数值；分别依赖对应启用开关 |
| minMessage、maxMessage | 字符串；分别依赖对应启用开关 |
| relatedField | 结构化 schema、专用处理器及远程元数据 |

范围按整批最终候选状态验证；开启上下界时必须存在合法数值，最小值不得大于最大值，静态默认值不得超出已启用范围。保存锁要求宿主明确节点 saved/disabledName 状态，缺少状态不能按未保存处理。

数值配置不能统一 clear 为 0；操作是否支持以及 default/clearValue/reset 由具体规则与宿主声明决定。placeholder 默认“请输入数字”。默认值 clear 删除静态内容并成对更新模式。当前范围约束使用 number，没有在本次重构中增加整数限制。
