# 属性规则与宿主授权

本规范保留七类组件已定义的属性语义，并统一使用顶层 actions 草稿。修改确认的 presentation 仅含 `shared.component-property-checklist` 的 kind/title；没有属性 items、after 或第二份目标新值。**设计器宿主本次未修改，仍须接入最终草稿复验与执行。** 本地组件定义只代表 Agent 理解和校验范围，宿主每轮声明才决定实际能力；未核验的组件或属性不自行补充。

## 规则的组织方式

组件规则按公共定义、实际复用的族定义和具体组件定义组合。每个组件在 `form_generation/components/definitions/` 下有同名属性文件，例如 `NumberPicker.py`；`Input.TextArea` 映射为 `InputTextArea.py`。运行时注册表提供单个组件的完整属性定义；编译器无需维护一份汇总七类组件的巨型属性字典。值校验、默认值和清空、预览联动应使用同一条规则链。

通用编排保留在 `form_generation/properties.py`：定位节点、宿主目录与策略、提案状态、动作生成、复制来源、批次依赖及最终候选校验。组件专有规则和处理放在对应组件文件，文本、日期时间、选项实际共享的处理放在 `definitions/_shared/`。公共属性 `common.py`、结构化 schema 校验 `validation.py` 和统一注册 `registry.py` 保留在 `components/` 根层。

## 公共语义

| 语义 | 类型或存储映射 | 特殊约束 |
| --- | --- | --- |
| label、enableCustomTitle、customTitle | 标题、标题开关、自定义标题 | 标题不得为空；label/customTitle 最多 50 字符；customTitle 依赖开关 |
| description、descriptionDisplay | extra、extraType | 描述最多 200 字符；展示方式 text/icon |
| required、edit、display、disableManualEdit | access.required/editable/visible/forbidManualInput | 通过权限联动；不是任意设置四个独立布尔值 |
| requiredMessage | 必填提示字符串 | 依赖 required |
| titleHidden、titleAlign、titlePosition | hideTitle、textAlign、labelPosition | 仅明确 Flow；对齐 left/right；位置 top/left；对齐与位置可删除局部覆盖恢复继承 |
| size、readOnlyDisplay | 尺寸 small/medium/large、只读显示布尔 | 当前要求明确 PC/desktop 设备信息 |
| placeholder | 字符串 | 默认值由具体组件确定 |
| defaultValue | 组件决定的语义类型 | 文本、数字、日期时间与选项不能统一用同一种值结构 |

公共语义当前只对七种属性组件成立，不表示九种生成组件均支持属性修改。实际可写范围还必须与宿主属性目录和节点策略一致。name、identifiers、id 及任意点路径、数组路径、原型键不允许作为可修改属性。

## 宿主目录与策略

宿主提供 `capabilities.catalogVersion` 和 `components.<componentName>.properties`。每个语义定义可声明 operations、valueSchema、handlerId、default、clearValue、reset、conditions、布局和设备限制；supported=false 明确关闭。

节点策略须明确读写授权。现代策略使用 canRead、canModify、allowedProperties；受保存锁保护的属性还需明确 saved/disabledName。已保存数字的 precision/numberType、日期时间 format、选项配置不开放修改。宿主额外的 lockedProperties/readOnlyProperties 继续生效。

最终支持范围是本地已实现规则、宿主目录、节点授权、布局设备、保存状态及处理器可用性的共同约束。组件级和属性级 supported=false 均拒绝。缺失声明不能自动从本地默认值补成可执行能力。复合属性必须有有界结构定义和真实处理器；关联字段需要远程元数据，唯一性约束需要真实服务。

“禁用”没有已注册语义及写入规则时，必须说明“暂时还不支持禁用”，不能猜 disabled/readOnly 或擅自映射 edit=false、access、disableManualEdit。edit、display、disableManualEdit 只用于对应已确认的权限语义，并继续要求本轮属性目录与节点授权。无法表达的用户要求不能静默省略；含不支持项的修改批次不交付任何动作。拒绝原因同时出现在 summary 与 diagnostics.message，避免摘要仍显示请求已完成。

## IR 与统一动作

输入 IR 不变：`proposal.begin.slots.result_kind` 使用 property_changes、property_query 或 property_undo。目标为 node_id、use_selection，或可唯一匹配的 node_label/node_name；编译后的动作绑定真实 nodeId，不能在应用时跟随新的 selection。

| IR | 关键 slots | 输出 |
| --- | --- | --- |
| `form.property.change` | property、operation；set 带 value；copy 带 source_node_id/source_property | `form.apply_property_change` |
| `form.property.query` | property | 只读查询，无 actions，不要求写动作版本 |
| `form.property.rule` | operation=add/replace/remove、rule_type、rule_id、value | `form.apply_property_rule` |
| `form.property.linkage` | operation=add/replace/remove、linkage_type、linkage_id、value | `form.apply_property_linkage` |
| `form.property.undo` | transaction_id | `form.undo_property_transaction`；只允许真实当前可撤销事务 |

修改提案保留 `protocol=form-agent.v1`、`contractVersion=form_property_proposal.v1`，顶层为 `mode=append`、`actionVersion=form_property_actions.v1` 和 actions。每条动作都有唯一 actionId、action、payload、dependsOn 数组及 display.selectedByDefault；属性变更、规则和联动动作还需 `preconditions.before={exists,value?}`。原状态优先读取 resolvedProperties[nodeId][property].stored，要求仅含 exists/value、exists 为布尔且与 value 是否存在一致，并为有限 JSON；没有 stored 时由组件规则读取本地快照。exists=false 不带 value；显式 false/null/0/空字符串不能被当作不存在，继承有效值不能冒充本地存储状态。规则/联动的 before 对应被修改配置的原语义值；不存在的配置用 exists=false。

修改 payload 包含 nodeId、componentName、property、operation。set 的新值只在 payload.value；copy 固定 sourceNodeId/sourceProperty 和既有来源读取快照，复制值只在 payload.value；sourceSnapshot 是来源前置状态，不另造展示用目标新值副本。clear/unset/reset 不携带 value。before 是并发前置状态，不是重复新值；不得另加 after 或展示用目标新值。可选 display.effects 仅用字符串解释派生影响，例如“同时开启显示和编辑”，不作为写入指令。

规则/联动沿用既有 payload 语义，要求注册目录、结构化 schema、兼容组件、真实引用与处理器；联动使用有界 AST，不执行模型生成的 JS 字符串。查询保留 `contractVersion=form_property_query.v1`、`presentation.kind=component_property_query`、readOnly=true 及 items，不含动作。撤销保留 component_property_undo 专用展示，transactionId/canUndo 用于真实事务状态，执行动作位于顶层 actions；不得投影为普通属性勾选卡。

## 设置、清空、删除、重置与复制

- set：使用该组件的语义类型校验，有限数字不接受 NaN/Infinity，不将 0 当成缺失。
- clear：清空内容或关闭配置。字符串可为空；日期范围可为 null；默认值按各组件处理。不能统一写 null、0 或 false。
- unset：删除明确允许的局部覆盖；标题、权限及复合语义不能用任意删键代替 helper。
- reset：恢复明确的默认值或继承；优先使用宿主声明的默认值，再采用已实现的组件规则；没有重置语义时拒绝。
- copy：读取生成时的真实来源及有效值，校验来源权限和目标类型；语义不同需要宿主声明兼容组，不能复制身份或猜引用迁移。

权限联动：开启 required 或 disableManualEdit 同时开启显示与编辑；关闭显示会关闭编辑、必填和禁止手工编辑；关闭编辑会关闭后两项。兼容 required 同步到 access.required。

## 批次、依赖与失败

每批先在副本上模拟，再按最终候选状态校验值、条件与联动。默认值依赖本批格式或选项变更；提示内容依赖对应开关。`dependsOn` 统一引用本批其他动作 actionId，无重复、自依赖、环或悬空引用；默认勾选或用户最终选择缺少依赖时明确阻止，不静默代选。同节点同语义重复、互斥设置及派生影响冲突均拒绝。权限及复合语义的底层效果封装在同一个处理器内，不能拆成独立叶子动作供勾选。

ai-chat 直接编辑 payload 并按 actionId 选择同一 actions 草稿，提交 `{proposal: 最终已编辑且已选择的提案}`。不得将改动只写进卡片文案后仍提交原始动作，也不另传选择 ID 列表或 edits。编辑不改变原 before；已交付的 ai-chat 属性接口直接调用 `bridge.apply({proposal, applyRequestId})`，无 register 步骤，回执使用 appliedActionIds。前端支持真实 context 的 formDraftCapabilities；applyRequestId 独立于 proposal，宿主须以它关联最终请求指纹，相关宿主实现本次未修改。

| 情况 | 状态或典型错误码 |
| --- | --- |
| 目标为空、重名、需要补值或选择依赖不满足 | needs_clarification；TARGET_REQUIRED/VALUE_REQUIRED/SELECTION_DEPENDENCY 等 |
| 目录、策略、动作版本或处理器缺失 | unsupported；MISSING_PROPERTY_CATALOG/MISSING_NODE_POLICY/ACTION_VERSION_UNSUPPORTED/MISSING_COMPOUND_HANDLER |
| 属性、类型、保存锁或组合非法 | unsupported；UNSUPPORTED_PROPERTY/SAVED_PROPERTY_LOCKED/PROPERTY_CONFLICT/SEMANTIC_CONFLICT 等 |
| 存储状态及候选状态均无变化 | no_change |

非 ready 修改结果没有执行动作或可应用确认卡。生成校验不授权编辑后的草稿：宿主须复验固定目标、revision、目录与能力、动作版本、before、复制来源、依赖、引用和顺序，在副本运行真实处理器并验证最终候选，全部通过才原子提交。回执和撤销必须反映实际事务；应用仅更新画布，保存另行完成。具体请求和验收见[三端接入说明](../../doc/ai-chat-property-edit-integration.md)。

具体组件属性、类型和复杂结构见[组件目录](./components/README.md)；完整宿主属性核验依据见[属性清单](../../doc/component-property-inventory.md)，其中标为建议的行为不能视作已部署。
