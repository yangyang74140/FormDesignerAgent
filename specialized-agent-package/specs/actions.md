# 表单动作规范

状态：描述当前编译行为。输出收敛目标见[规范入口](./README.md)。这些是表单动作，不复用页面动作的 payload 或执行器。

## 层次与共同前置条件

模型生成受控 IR：`plan_items[].capability/slots`。`form.field.define` 是字段定义 IR，由编译器生成新增动作；它本身不是宿主执行动作。最终每个动作包含 `actionId`、`action`、`payload`，当前位于 `proposal.result.actions`。

当前生产动作名称以 `form_generation/action_rules/` 注册表为准。`form_generation/actions.py` 是未注册到当前 Pipeline 的旧编译器，不是本规范的运行时来源。

每批必须只有一个 `proposal.*` 状态。只有 ready 结果交付可执行动作。宿主须声明相应动作与动作版本，提供真实组件目录、当前 Schema、目标及 revision；字段生成额外要求单层 Flow 和命名/选项约束。Action 版本协商独立于 FormSchema 版本，不按 FormSchema 版本限制能力。

当前通用动作路径按既有实现从 `supportedActionVersions` 提取非空候选并选择排序最后一项；尚不是逐动作版本交集协商。属性动作路径严格检查对应动作的 `form_property_actions.v1`。本次未改变这些行为，宿主仍需拒绝不能执行的版本。

## 组件动作

下表给出当前消费的 payload 字段。它不是允许模型直接写任意 Schema 的授权；未完整实现的检查在后文列明。

| action | payload 与含义 | 当前校验 |
| --- | --- | --- |
| `form.add_component` | `clientRef`、`componentName`、`props`、`target` | clientRef 格式；九种生成组件范围；宿主组件目录及可写属性；位置 |
| `form.update_component` | `nodeId` 或 `fieldId` 或 `useSelection:true`；非空 `changes` | 目标存在；禁止修改 `name/identifiers`；宿主可写属性 |
| `form.update_component_options` | 目标身份；`options` | 仅 SelectSingle/SelectMulti/CheckboxGroup；宿主 options 可写声明 |
| `form.move_component` | 目标身份；`target` | 节点存在；位置结构 |
| `form.remove_component` | 目标身份 | 节点存在；真实删除、引用检查、事务由宿主执行 |
| `form.convert_component` | 目标身份；`componentName`（当前也读取 `targetComponentName`） | 原节点明确未保存；目标在生成组件及宿主目录中 |

普通更新中的 `changes` 是该动作 payload 内的属性映射，并非另一份并列执行动作数组。新增字段不分配持久化 ID。`clientRef` 以小写字母开头，其后允许小写字母、数字、下划线、连字符；原样保留，不自动更名。

`form.field.define` 路径进一步验证 label、业务 name、唯一 name/clientRef、选项 label/value、数量和新增后的总字段数。它与通用 `form.add_component` 的原始 payload 路径目前校验深度不同，不能把字段定义路径的全部检查写成两条路径都已实现。

字段生成、原始新增和转换均要求目标组件在本轮非空宿主目录中，`supported:false` 的组件不开放。仅读取 capabilities 的 components/componentCatalog/componentCapabilities 目录；规则目录中的兼容组件引用不作为组件授权。生成、原始新增、属性/选项更新要求明确且非空的 `writableProps`（未提供该键时才读取 `editableProps`）；缺失、空列表或格式错误均返回 unsupported，不能从本地默认配置补授权。显式 `writableProps:[]` 不会回退到 `editableProps`。

字段定义严格只接受 client_ref、component_name、label、name、required、placeholder、options；未知槽位不得静默丢弃。组件生命周期动作也只接受上表已定义的 payload 字段；转换不接受未定义的 props 补丁。未声明属性返回具体原因，不靠组件常见用法猜字段。宿主声明某个额外属性不会自动扩展字段定义 IR。

## 身份、位置与顺序

- 现有目标优先读取 payload 的 `fieldId/nodeId/containerId`；否则 `useSelection:true` 从本轮 selection 读取真实 nodeId。字段动作的正式目标仍是字段节点；读取 containerId 不表示支持容器操作。
- 动作按数组顺序处理。新增成功后将 clientRef 加入本批已知引用，后面的规则/公式可通过受控引用键使用；不接受前向引用。当前部分组件更新仍依赖宿主现有节点类型，不能把 clientRef 宣称为所有动作通用目标。
- `target={kind:"root",index:非负整数}` 表示根层位置；index 可省略。生成及展示投影按当前列表计算插入位置，不同动作的顺序会改变后续下标。
- `target={kind:"relative",anchorNodeId:"真实ID",position:"before"或"after"}` 引用真实锚点；当前原始动作的 relative target 不接受新 clientRef 锚点。
- 字段定义 IR 的 `proposal.begin.slots.target` 还可使用 anchorName、anchorLabel、useSelection，由编译器唯一解析；多字段插入按递增下标生成，保证原顺序。默认追加到最后一个字段之后。
- 不支持 Grid、容器、槽位位置。根层下标的最终合法性、修订冲突、引用完整性由宿主再次验证。

当前没有统一的动作级 `dependsOn` 协议；属性卡的 change 依赖见[属性规则](./properties.md)。任意勾选动作子集、新字段删除后的依赖重算、动作级互斥及 clientRef 全生命周期仍需与消费端锁定，不能由各端各自发明规则。

## 表单配置、规则与公式

| action | 当前读取字段 | 当前校验与限制 |
| --- | --- | --- |
| `form.update_form_config` | 非空 `changes` | 仅检查映射非空；具体属性和执行语义由宿主验证 |
| `form.set_validation` | 目标引用；`validator` 或 `validatorName` | 受控引用不得悬空；指定校验器时必须在宿主目录注册 |
| `form.upsert_linkage` | 目标引用；`dataSourceId` 或 `dataSource` | 受控引用不得悬空；指定数据源时必须注册 |
| `form.set_formula` | 目标引用；`formula`，其中可声明 `function/functionName` | 不允许直接引用自身；引用不得悬空；指定函数时必须注册 |

当前识别的引用键为 fieldId、nodeId、fieldRef、clientRef、sourceFieldId、targetFieldId；不以任意字符串猜引用。上述三种扩展动作尚没有完整严格的 payload schema，资源名称未提供时也不代表执行器已经接受该语义。宿主未实现对应能力时不开放。

## 当前属性动作

属性编译路径另生成 `form.apply_property_change`、`form.apply_property_rule`、`form.apply_property_linkage`、`form.undo_property_transaction`；其名称与载荷保持现状，见[属性规则](./properties.md)。它们不在通用动作注册表中，也不能借通用路径绕过属性授权与语义校验。未来统一动作集合时需共同决策，不在这次模块拆分中另造名称。

## 错误、预览与应用

组件、属性、动作或动作版本能力缺失时，编译器返回 `unsupported`，summary 和 diagnostics.message 明确说明原因，不包含 result 或可应用 presentation；典型诊断码为 MISSING_COMPONENT_CATALOG、UNSUPPORTED_COMPONENT、MISSING_WRITABLE_PROPS、UNSUPPORTED_PROPERTY、ACTION_UNSUPPORTED、ACTION_VERSION_UNSUPPORTED。一批动作中任一项缺少能力时整批拒绝，不交付先前已经编译的动作。handler 按既有最终事件返回此非执行提案。

例如“生成一个禁用的姓名字段”：姓名可用 Input，但未声明禁用语义及写入规则时应说明“暂时还不支持禁用”，本轮不交付忽略禁用要求的 ready 提案。不能自行猜 disabled、readOnly、edit=false、access 或用禁止手工编辑替代禁用。用户明确要求且宿主已授权的编辑权限操作仍走既有属性语义。

其余非法 payload、节点引用或字段值继续抛 ValueError，由生产 handler 转为 `form_proposal_validation_failed` 并中止 Run。字段追加的锚点缺失或歧义返回 `needs_clarification` 且无 result。属性错误采用明确诊断码，见属性规范。

当前展示快照由动作在副本上投影；转换的属性迁移与默认值由宿主决定，含转换时不推测完整快照。投影不证明宿主已执行。应用前宿主必须检查固定目标、revision、真实能力及最终候选状态，以原子提交与独立 Apply 幂等键执行；应用仅更新画布，保存另行完成。转换有损决策、删除引用和完整批次冲突不能靠展示快照替代。
