# 文本族：Input、Input.TextArea

两者组合[公共属性规则](../properties.md)，共享 placeholder、默认值、textLengthLimit/showLimitHint/textMaxLength、快捷复制、链接解析和关联字段语义。

| 属性 | 当前规则 |
| --- | --- |
| defaultValue | `{mode:"undefined"}` 或 `{mode:"custom",value:"字符串"}`；不接受数字代替字符串；公式模式未开放 |
| textLengthLimit | 正数阈值，或关闭语义 `{enabled:false,maxLength?:正数}`；同步 showLimitHint/textMaxLength；关闭可保留历史阈值 |
| textMaxLength | 有限数值且至少 1，依赖 showLimitHint=true；当前没有额外整数限制 |
| enableQuickCopy、enableLinkParser | 布尔；运行态含义由宿主负责 |
| relatedField | 有界结构、专用处理器及远程元数据；节点与表单关联同步由宿主处理 |

Input 专有：allowClear 默认 false；isUnique 需真实服务；uniqueMessage 依赖 isUnique；format/formatMessage/formatValidation 只适用于单行文本。格式枚举为 none、chinese、number、letter、letter_num、phone、tel、postcode、idcard、email；formatMessage 需要实际启用格式校验。formatValidation 成组处理格式和提示，不创建任意 rules 数组。

Input.TextArea 专有：rows 为 3–10 的有限数值，默认 3；disableAutoHeight、showEmptyLines 为布尔。不继承 Input 的 allowClear、唯一性与文本格式校验属性。公共族组合不能意外将单行专有能力开放给多行文本。

默认值 clear 成对设置 defaultValueConfig 为字符串 undefined 并删除静态值；reset 采用宿主声明或内置规则。placeholder 默认均为空字符串。权限与继承行为见公共规则。
