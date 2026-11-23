# 选项族：SelectSingle、SelectMulti、CheckboxGroup

SelectSingle、SelectMulti 支持[公共属性规则](../properties.md)及选项语义。CheckboxGroup 当前仅支持字段生成和通用选项动作，不开放七组件属性编译路径。

## 生成与修改的选项形态

字段定义 IR 使用 `options:[{label:"显示名",value:"真实业务值"}]`，要求非空、value 唯一并遵守宿主数量限制。生成器不分配已有选项的持久化身份。

属性修改使用宿主真实 options 复合结构，包括 dataSource、isColor 等。每个选项必须保留 primaryKey、value、disabled、activeKey；primaryKey 与 value 各自唯一。既有选项的业务 value、目录和父子关联不得改变。当前属性编译器拒绝删除既有选项，因为完整引用检查尚需宿主能力，不把 handlerId 存在视为删除已安全。

通用 `form.update_component_options` 当前只检查组件类型与 options 可写性；不能据此声称它已有上述属性路径的全部结构、保存锁与引用校验。

## 具体组件差异

| 属性 | SelectSingle | SelectMulti |
| --- | --- | --- |
| defaultValue | 单个真实选项 value 字符串 | 唯一 value 字符串数组 |
| clear 默认值 | 删除局部 defaultValue，并清空 activeKey | defaultValue=[]，清空 activeKey |
| 默认项 | 至多一个，且明确 disabled=false | 多个，均须明确启用 |
| allowClear | 支持，默认 true | 不在当前专有属性目录 |
| popupMatchSelectWidth、showSearch | 布尔 | 布尔 |
| selectAll、supportReverseSelect | 不支持 | 布尔；反选默认 true |
| maxCountEnable/maxTagCount/maxCountMessage | 不支持 | 开关、至少 1 的有限数值、字符串；后两项依赖开关 |
| selectionLimit | 不支持 | `{count:1–1000整数,message?:最多200字字符串}`；需要宿主 schema/handler；clear/reset 为 null，关闭并清理数量和提示 |

设置默认值同步 dataSource[].activeKey；更新选项同步默认值与颜色开关。SelectMulti 最终默认项数量不得超过已启用的选择数量限制。原始 label 不能替代 value。复制默认值仍需检查目标真实选项存在且启用。

relatedField 需要专用处理器和远程元数据。options 修改需要明确保存锁状态；已保存字段不开放该属性路径。placeholder 默认“请选择”。
