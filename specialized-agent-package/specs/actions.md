# 表单动作规范

这是本次实施的单一动作契约。这些是表单动作，不复用页面动作的 payload 或执行器。2026-11-23 用户指定的本地设计器已接入 PC Flow 既有属性处理器的解析、复验和原子应用；不能以 Agent ready 推断其他动作可执行，也不能据此宣称已部署。

## 2026-11-25 PC 双确认与统一变更

本节规定当前唯一可写契约；动作本体语义保持不变。

| 场景 | contractVersion | actionVersion | mode | presentation.kind |
| --- | --- | --- | --- | --- |
| 已协商新建 | form_agent_proposal.v1 | 1.0 | replace_empty_form | shared.form-create-confirm |
| 已协商已有表单变更 | form_change_proposal.v1 | form_change_actions.v1 | append | shared.form-change-confirm |
| 未协商 | unsupported，无可执行动作和确认卡 | — | — | — |

新建只包含 form.add_component；需 capabilities.supportedPresentationKinds 声明新建 kind，且新增动作实际授权 1.0。统一变更需 capabilities.supportedProposalContracts 包含 form_change_proposal.v1、capabilities.supportedPresentationKinds 包含 shared.form-change-confirm、capabilities.supportedActionVersions 包含 form_change_actions.v1（全局字符串、列表或布尔版本表；该键缺省才兼容 context 顶层同名声明，显式空值不回退）。统一版本不借用其他动作的旧版本，但字段动作仍需在宿主动作目录授权。缺少新能力时所有变更路径均返回 unsupported/CHANGE_CONTRACT_UNSUPPORTED；新建缺少 kind 时返回 CREATE_CONTRACT_UNSUPPORTED，缺少 1.0 时返回 ACTION_VERSION_UNSUPPORTED。

`proposal.begin.slots.result_kind=form_changes` 可按原顺序交错字段定义 IR、通用动作注册表全集以及 form.property.change。纯字段 append、纯通用动作、纯属性 change 均要求新能力并输出统一变更。query 和 undo 维持专用路径；form.property.rule/linkage 尚无已约定的新可写协议，返回 PROPERTY_PROTOCOL_UNSUPPORTED，不输出动作。修改协议要求固定 target.schemaId/baseRevision；formId/appId/layoutId 适用时保留。含属性才要求 catalogVersion、节点策略与真实属性处理器。新节点属性仅通过已支持新增 props 表达，属性 change 不接受本批 clientRef。

同一节点多个属性操作复用完整属性候选校验，重复语义属性整批拒绝。删除与修改、转换与修改、原始 update 与属性操作等同节点重叠保守返回 CHANGE_OVERLAP；表单级或无法定位目标的跨字段动作和其他动作同批也保守拒绝。各类动作独立使用仍可通过授权。未指定 target 的字段 IR 可与删除已有节点同批，按动作顺序基于候选列表计算默认追加下标，保留尾部非字段节点及新增顺序。每条这样的新增依赖其前序新增、删除动作。字段 IR 的其他结构混合（包括显式 target 与删除同批，或与原始 add/move/convert 同批）仍返回 CHANGE_POSITION_OVERLAP，可改用明确位置的原始新增动作。不能分别应用两批代替原子提交。

单一 actions、actionId、dependsOn、display、属性 preconditions.before 和 payload 保持原结构。UI 同字段聚合和按需分组仅是投影，不能重排 actions；依赖缺选、复杂位置子集仍按下文规则阻止。编辑后真实宿主必须复验整批最终候选。真实编译样例见 [统一变更](../../doc/form-change-proposal.example.json) 与 [新建](../../doc/form-create-proposal.example.json)，对应输入见同目录 form-change-context.example.json / form-change-ir.example.json。

## 层次与共同前置条件

模型输入保持 `plan_items[].capability/slots`。每批只有一个 `proposal.*` 状态；`form.field.define` 是字段定义 IR，由编译器生成新增动作，本身不是宿主执行动作。最终 output 固定为 `{form_proposal: proposal}`，保留既有 protocol/contractVersion；修改提案的 `mode/actionVersion/actions` 均在 proposal 顶层，不含 result、validation 或重复字段/变更清单。`schemaVersion` 仅是可选画布元数据，不作能力门禁。

普通修改确认的 presentation 仅为 `{kind,title}`，新建使用 `shared.form-create-confirm`，已有表单变更使用 `shared.form-change-confirm`。只读查询保留 `component_property_query/readOnly/items` 且无 actions；撤销保留 `component_property_undo` 专用展示及顶层动作，不进入普通确认卡。

每条动作必须包含：

| 字段 | 语义 |
| --- | --- |
| `actionId` | 本提案内唯一、稳定的动作标识，也是 UI 勾选标识 |
| `action`、`payload` | 既有受控名称与其载荷；新字段配置和属性目标新值只有这一份 |
| `dependsOn` | 本批其他动作的 actionId 数组，无依赖用 `[]`；无重复、自依赖、环或悬空引用；新节点引用必须依赖在前创建动作 |
| `display` | `selectedByDefault` 为布尔值；可选 `effects` 为解释派生影响的字符串数组，不承载执行指令或另一份新值 |
| `preconditions.before` | 属性变更的原语义状态 `{exists,value?}`；exists=false 不带 value，见[属性规则](./properties.md) |

只有 ready 修改或专用撤销交付执行动作。宿主须声明相应动作、动作版本，提供真实组件目录、当前 Schema、固定目标和 revision；字段生成额外要求单层 Flow、命名和选项约束。新建 actionVersion 固定 1.0；已有表单修改固定 form_change_actions.v1。撤销专用动作仍需 form_property_actions.v1 授权，不借用修改版本。

通用动作名称以 `form_generation/action_rules/` 注册表为准；共享字段与属性语义校验器继续复用。变更只接受 form_change_actions.v1，不协商旧字段动作版本交集。字段动作仍需逐项授权，宿主仍须复验。

## 组件动作

| action | payload 与含义 | 能力与校验边界 |
| --- | --- | --- |
| `form.add_component` | `clientRef`、`componentName`、`props`、`target` | 九种生成组件范围；宿主组件目录、可写属性及位置 |
| `form.update_component` | 目标身份；非空 `changes` | 目标存在；禁止修改 name/identifiers；宿主可写属性 |
| `form.update_component_options` | 目标身份；`options` | 仅 SelectSingle/SelectMulti/CheckboxGroup；宿主 options 可写声明及真实选项身份 |
| `form.move_component` | 目标身份；`target` | 节点存在、位置合法；完整顺序和引用由宿主复验 |
| `form.remove_component` | 目标身份 | 删除已有画布节点；引用检查和事务由宿主执行 |
| `form.convert_component` | 目标身份；`componentName`（既有输入也读取 `targetComponentName`） | 原节点明确未保存；目标组件有授权；属性迁移交给受支持处理器 |

目标身份的既有输入接受 nodeId/fieldId/useSelection；编译器须将选择解析并固定到真实节点，应用不能改绑到当前 selection。读取 containerId 的既有辅助逻辑不表示开放容器操作。`changes` 是既有 update 动作 payload 内的属性映射，不是第二份执行动作数组。

新增不分配持久化 ID。clientRef 以小写字母开头，后续只允许小写字母、数字、下划线或连字符，必须唯一并原样保留；它是新节点身份，不是复选框 ID。字段定义路径进一步校验 label、业务 name、唯一 name/clientRef、选项 label/value、数量和总字段数；通用原始新增路径的既有校验深度不同，不能据此宣称已完成全部语义检查。

字段生成、原始新增和转换要求组件在本轮非空 components/componentCatalog/componentCapabilities 目录中，`supported:false` 不开放；规则目录的兼容组件引用不授予组件能力。生成、原始新增、属性/选项更新要求明确且非空 writableProps；仅未提供该键时才读取 editableProps，显式空列表不回退。新增优先使用组件 create 中的可写目录，未提供 create 时读取组件根目录；属性/选项更新仍读取根目录。缺失、空列表或格式错误均拒绝，不从本地默认配置补授权。

字段定义仍只接受 client_ref、component_name、label、name、required、placeholder、options；未知槽位不得静默丢弃。组件生命周期动作仅接受已定义 payload，转换不接受未定义 props 补丁。宿主声明额外属性不会自动扩展模型输入 IR。

## 位置、顺序与选择子集

1. 按 actions 数组顺序确定性处理，保留未被取消动作的相对顺序；依赖选择和执行条件由宿主复验。支持的引用键中若引用本批 clientRef，必须指向更早的创建动作并在 dependsOn 包含其 actionId，不允许新节点前向引用或未选中的创建动作。
2. `target={kind:"root",index:非负整数}` 表示执行到该动作时的物理根列表下标，不能越界。原始动作省略 index 表示物理根列表末尾。
3. 字段 IR 默认追加表示最后一个字段之后，category 缺省视为字段；末尾非字段节点保留在后方。编译器必须输出明确 root index，因此该默认行为与原始 root 无 index 的物理末尾追加有区别。
4. 字段 IR 的 target 可用 anchorName、anchorLabel、useSelection 唯一解析真实锚点，再为连续新增生成递增 root index，保持字段原顺序。缺失或歧义须澄清。
5. 原始 `target={kind:"relative",anchorNodeId:"真实ID",position:"before"或"after"}` 仅接受已有真实锚点，不开放 clientRef 锚点。部分组件更新仍依赖现有节点类型；引用检查不会自动授予所有动作以 clientRef 为目标的能力。不支持 Grid、容器和槽位位置。

删除已有字段使用同一 `shared.form-change-confirm` 卡片，`form.remove_component` 动作默认 `display.selectedByDefault=true`；展示名称和类型由消费端从宿主真实快照按固定节点身份读取，不在 payload 增加字段配置副本。纯删除卡主按钮为“删除”，用户可取消勾选，点击前不得修改画布；点击后只提交所选 actions，宿主复验并原子删除，成功后提示未保存并保留撤销。

取消或删除一条建议只修改尚未应用的 actions 草稿；删除已有节点须有 `form.remove_component` 及能力授权。移除创建动作后必须处理依赖和引用，不能留下悬空动作或静默补选创建动作。格式、选项、开关等属性依赖也统一引用 actionId。

勾选子集后必须重新验证顺序与位置。例：两条连续新增的 root index 为 2、3，只选择第二条时不能直接使用旧 3。只有整批都是新增动作、显式 root index 连续且可证明独立、无其他位置/引用影响的序列，才可按保留顺序重算为 2；这属于派生位置修正，不是自动增加用户动作。混有移动、删除、相对锚点或其他复杂位置时拒绝该子集并要求重生成。仅验证下标未越界不够；宿主仍要基于最终草稿复验位置含义。

## 表单配置、规则与公式

| action | 既有 payload | 能力与限制 |
| --- | --- | --- |
| `form.update_form_config` | 非空 `changes` | 现有基础检查仅要求映射非空；具体属性及执行语义由宿主验证 |
| `form.set_validation` | 目标引用；`validator` 或 `validatorName` | 受控引用不得悬空；指定校验器必须在宿主目录注册 |
| `form.upsert_linkage` | 目标引用；`dataSourceId` 或 `dataSource` | 指定数据源必须注册；不得假定服务存在 |
| `form.set_formula` | 目标引用；`formula`，可含 function/functionName | 不允许直接自引用；指定函数必须注册 |

受控引用键为 fieldId、nodeId、fieldRef、clientRef、sourceFieldId、targetFieldId，不按任意字符串猜引用。以上三种扩展动作的既有基础校验并非完整严格 payload schema；缺少资源名称不表示执行器接受该语义。必须由真实支持处理器完成完整候选、引用和规则校验，否则不开放能力。

## 属性与撤销动作

保留 `form.apply_property_change` 和独立 `form.undo_property_transaction` 名称及既有语义，放在顶层 actions。属性 rule/linkage 暂不支持，不生成动作。它们不借通用动作路径绕过属性授权。修改动作的新值只在 payload，原状态只在 preconditions.before，不返回 after。set/copy 带 value；clear/unset/reset 不带 value。专用撤销要求见[属性规则](./properties.md)。

## 引导确认（非执行产物）

`proposal.needs_clarification` 的 IR 保留 summary/question/choices/code，增加可选 `scenario_options`：恰好三个只含非空 label/description 的具体场景，标签不能重复或包含“其他”，不能同时提供非空 choices。编译器追加第四项“其他”，输出 proposal.clarificationOptions，每项为稳定 id/label/description；场景项 ID 为 scenario-1 至 scenario-3，其他为 other。此列表只有询问语义，不是动作草稿或宿主执行能力声明。普通定位/属性澄清仍可只含 question/choices，不为凑四项捏造目标。

前序内部步骤冻结候选，等待步骤调用平台原生 clarification.request；答案用冻结 ID 查回标签，文本必须非空，未知 ID/答案类型失败关闭。其他入口通过第二个稳定问题收集用途。取消为 no_change，缺少平台澄清接口时保留 needs_clarification；两者均无动作和应用卡。最终编译收到原需求和答案，保留原始约束并按宿主能力重新校验。选择推荐不等于应用确认。恢复检查点及平台事件接入见包 README 与三端接入说明。

### 字段槽位草稿

字段级歧义使用 `proposal.needs_clarification.slots.field_draft`，不能混入 scenario_options 或 choices。这只是非执行引导状态的扩展；`form.field.define` 的七个槽位、最终 actions 与动作名称均不变。结构示例：

```json
{
  "prefill": "在事由后插入联系人，称谓可修改。",
  "begin": {
    "summary": "新增联系人", "result_kind": "form_fields", "mode": "append",
    "target": {"kind": "relative", "anchorNodeId": "reason", "position": "after"}
  },
  "fields": [{"client_ref": "contact", "component_name": "Input", "label": "联系人", "name": "contact"}],
  "groups": [{
    "field": 0, "slot": "semantics", "reason": "联系人称谓尚不明确",
    "options": [
      {"label": "紧急联系人", "patch": {"label": "紧急联系人"}},
      {"label": "日常联系人", "patch": {"label": "日常联系人"}}
    ]
  }]
}
```

begin 仅支持 form_fields/append，保留完整位置约束；fields 是完整待插入组合，不含旧字段。预填组合及每个推荐单独替换后的组合都必须可编译；本轮全部回答合并后再次整体校验，名称冲突、类型不兼容、未知属性、能力缺失等都阻止整批，不删除其他要求“修复”。基线只是候选预填，所有歧义组必须收到有效回答才能生成提案。原文语义与候选业务真实性由模型规则约束，编译器确定性校验结构、能力、身份、引用和最终候选；不能声称已证明自然语言需求完整性。

每组只对应一个字段下标与一个槽位类别，同字段同类别不得重复：

| slot | patch 允许键 | 当前边界 |
| --- | --- | --- |
| semantics | label、name；完整候选另含 component_name 及有依据的 required、placeholder、options | 语义未定推荐完整字段；仅称谓歧义可单改名称。client_ref、数量与位置固定 |
| control | component_name；可选 unset | 宿主可用组件与本地支持交集，不能隐式删除不兼容选项 |
| validation | required | 仅布尔值；不自动推导长度、正则等校验 |
| data_source | options | 有依据的静态 label/value 数组；不绑定动态来源 |
| properties | placeholder | 非空提示文字；其他字段属性暂不支持 |

完整语义补丁一旦设置控件或属性，必须同时包含 label/name/component_name；如 `{"label":"手机号","name":"phone","component_name":"Input"}`，不凭名称推断必填、11位或动态来源。semantics/control 的可选 `unset` 数组显式列出要移除的 required/placeholder/options；其他属性组只能清除自己的键。禁止删除身份、同时设置并删除或重复键。省略属性表示保留，跨控件不自动清理；清理须有用户约束依据，并由用户确认及整体编译复验。完整语义候选与同字段其他分组不可重叠写属性，自定义合并也检查重叠，避免后组覆盖前组。候选属性的自然语言依据仍由模型判断，结构校验不能证明其业务真实性。

前置步骤使用 `clarification_kind`（field_addition/property/scenario/target/other，输出为 clarificationKind）区分字段新增、属性修改、场景、定位及其他澄清，不用关键词路由。字段草稿隐含 field_addition。普通澄清缺分类，或已确认 field_addition 却缺 field_draft 时，检查宿主 currentSchema/capabilities/supportedActionVersions；缺失以 form_guidance_host_context_missing 明确失败。上下文齐备则仅调用一次相同 Native Capability 生成器，带原请求与修复要求重新分类并生成结构化候选；修复不能把未定需求猜成 ready/no_change。仍缺结构化字段草稿或分类则 form_field_guidance_repair_failed，模型/编译失败保留原失败，不进入空 options 等待。已明确属性/目标澄清、场景三个加其他、ready 需求维持原路径。修复只在有检查点的前置步骤执行；等待和选择后编译都不调用模型。

每组最多20个冻结候选，每轮显示最多5个推荐；不足3个如实展示，自定义不算推荐。label 非空、不重复、至多16字且不能以选择/设置/配置开头。相同补丁不重复推荐。开放槽位总有显式“自定义”入口；直接自由文本或自定义补充题只接收当前槽位 JSON 对象，禁止跨组改键，未知键拒绝。全组收集后才合并，不逐槽位问答；选了自定义的组也统一补充。

编译器输出非 ready 的 `proposal.fieldGuidance`，包含上述草稿、由内容及宿主快照计算的 draftId、version=1 和 hostFingerprint。平台检查点保存完整候选 patch，不向 SDK options 添加 payload/slot_key。每题及选项 ID 带 draftId、当前版本及组序号，推荐选项映射回冻结 patch；任何未知、旧版 ID 或缺失分组失败关闭。等待步骤产物 fieldSelection 只在内部保存最终字段值与身份版本，最终步骤复验当前宿主指纹并直接结构化编译，不产生第二份最终字段清单。

复核操作独立于槽位推荐：confirm 生成提案；back 恢复本轮回答前的字段和确认状态；regenerate 在冻结池中移动5项并保留已确认值，不能调用模型重新解释答案。每次重新展示版本递增，最多四次；原生所有请求显式 max_rounds=16，最多12次请求，保留自由文本可答空间。请求 key 确定性生成，重入从相同前置检查点重放；不使用全局会话状态、随机 key 或自行创建 Run。失败码 form_field_guidance_invalid，最终内部身份错误为 form_field_guidance_stale。缺少原生分组接口保持非执行状态，取消不保留 fieldGuidance。选择推荐不是 Apply 授权。

## 错误与应用

组件、属性、动作或动作版本能力缺失时整批 `unsupported`，summary 与 diagnostics.message 说明原因，无执行动作或可应用确认卡。典型码：MISSING_COMPONENT_CATALOG、UNSUPPORTED_COMPONENT、MISSING_WRITABLE_PROPS、UNSUPPORTED_PROPERTY、ACTION_UNSUPPORTED、ACTION_VERSION_UNSUPPORTED。不得交付忽略不支持要求的部分 ready 提案。例如未声明禁用语义时说明“暂时还不支持禁用”，不猜 disabled/readOnly/edit=false/access 或以禁止手工编辑替代；用户明确要求且授权的权限操作仍使用既有语义。

非法 payload、引用或值由生产 handler 转为 `form_proposal_validation_failed` 并中止 Run；锚点缺失/歧义为 needs_clarification。其他属性诊断见属性规范。非 ready 状态不携带执行动作。

生成校验只针对生成时快照；用户可编辑 payload，因此宿主必须再次校验最终草稿的目标、revision、能力/动作版本、before、依赖、引用、确定性顺序、位置与最终候选。类型转换的默认值、迁移、有损决定以及删除引用完整性须由支持处理器验证，不能用 UI 投影伪造。全部成功才原子应用，以独立 Apply 幂等键防重放，形成真实撤销事务；应用只更新画布，保存另行完成。完整请求和回执边界见[三端接入说明](../../doc/ai-chat-property-edit-integration.md)。
