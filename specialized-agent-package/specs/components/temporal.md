# 日期时间族：DatePicker、TimePicker

组合[公共属性规则](../properties.md)，共享格式化默认值、allowClear、关联字段与时间范围。保存后的 format 锁定；缺少明确保存状态时拒绝修改。

| 属性 | DatePicker | TimePicker |
| --- | --- | --- |
| format | YYYY、YYYY-MM、YYYY-MM-DD、YYYY-MM-DD HH、YYYY-MM-DD HH:mm、YYYY-MM-DD HH:mm:ss | HH:mm:ss、HH:mm |
| 默认 format | YYYY-MM-DD | HH:mm:ss |
| defaultValue | undefined/custom/systemDate 模式 | undefined/custom/systemTime 模式 |
| custom 内容 | 与最终 format 严格匹配的日期字符串 | 与最终 format 严格匹配的时间字符串 |
| allowClear | 布尔，默认 true | 布尔，默认 true |
| 专有配置 | disabledDays | minuteStep/secondStep：有限数值 1–59，默认 1 |

默认值使用 `{mode:"custom",value:"..."}`；非 custom 不携带 value。公式模式未开放。按整批最终格式校验，不能因为 IR 顺序不同接受不匹配的默认值。默认值及范围对本批 format 修改建立选择依赖。

## 时间范围

minTimeCondition/maxTimeCondition 需要专用 handler 与有界 schema；clear 为 null。非空值必须 enabled=true，并且 source 分支不能残留其他分支字段：

- fixed：只带 fixedValue，按组件 format 校验；同时启用固定上下界时比较先后。
- field：只带 fieldName；引用真实且唯一的其他同类字段，禁止自引用。
- dynamic/current：TimePicker 只支持当前时间；DatePicker 还需 dynamicAnchor=today/currentWeek/currentMonth/nextMonth/currentQuarter/currentYear。
- dynamic/before 或 after：仅 DatePicker，带 dynamicUnit=day/week/month/quarter/year 和非负 offsetValue。当前说明使用 1/7/30/90/365 天近似偏移，不能宣称完整日历月算法。

## 日期专有联动

disabledDays 使用 `{enabled:boolean,days:["0"到"6"]}` 或 null；days 为允许选择的星期，唯一且启用时非空。YYYY/YYYY-MM 格式不支持星期限制。

仅 DatePicker 的 format 真正改变时更新 placeholder，切到年/月格式同时清除 disabledDays。普通描述修改不触发此联动。TimePicker 不继承日期专有的星期与日期偏移规则。placeholder 默认分别为“年-月-日”和“请选择时间”。
