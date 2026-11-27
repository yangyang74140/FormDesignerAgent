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

组件目录约束本轮新增、转换或属性写入，不是完整 `currentSchema` 中全部既有节点的白名单。单层 Flow 中未被修改的既有 `DepartmentSelect` 等节点即使不在目录内或被标为 `supported:false`，也原样保留，不阻止追加已授权的 `Input` 姓名字段；既有节点仍需有非空组件名和唯一非空 ID，字段重名、引用、位置、数量和非空画布禁止覆盖等检查不变。保留既有节点不授予其新增或修改能力；请求操作这些组件时仍按对应动作能力拒绝。用户明确列出字段时只生成所列字段，不按表名补充其他字段。

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

前序内部步骤冻结候选，等待步骤调用平台原生 clarification.request；答案用冻结 ID 查回标签与说明，一并传入后续意图分析，避免选项的语义细节丢失；文本必须非空，未知 ID/答案类型失败关闭。其他入口通过第二个稳定问题收集用途。取消为 no_change，缺少平台澄清接口时保留 needs_clarification；两者均无动作和应用卡。最终编译收到原需求和答案，保留原始约束并按宿主能力重新校验。选择推荐不等于应用确认。恢复检查点及平台事件接入见包 README 与三端接入说明。

### 无表单实例的前置引导

2026-11-27 用户确认：当前宿主以 `currentSchema.fields=[]` 且 `canvas.isBlank=true` 表示无表单实例；不以 formId、选中状态或缺失上下文推断。已有非空 fields 即使 isBlank=true 也不能视为无表单。用户要求新增/删除/修改字段且无表单时，必须先引导，不能因字段明确而自动新建或丢弃字段需求。明确要求生成表单时不重复确认。

无表单时模型状态项目 `proposal.*.slots.request_intent` 必填，枚举 form_creation（生成表单）、field_change（字段操作）、other（查询/解释等）；Native Capability schema 和生产编译回调同时校验。意图由模型语义分类而非关键词判断，此约束不证明模型一定理解了所有自然语言。编译器在字段能力、位置和旧目标解析之前，将 field_change、增量编排或字段/属性歧义转为固定非执行 `needs_clarification`。`request_intent` 只属输入 IR，不复制到最终执行草稿，也不接受模型声明的确认授权。

引导输出 `clarificationKind=form_creation_required`、diagnostics.code=FORM_CREATION_REQUIRED、question 与 clarificationOptions；稳定选项 create-form（生成表单，保留原字段要求）和 cancel（取消，本次需求结束）。`formCreationFingerprint` 绑定规范化宿主快照；没有 actions、mode/actionVersion 或应用 presentation。这沿用真实平台澄清模块，不新增自定义确认卡或平台事件。

等待使用 `clarification.request(key="form_creation_confirmation", options=固定选项, allow_free_text=false, max_rounds=128)`。create-form 展示“先准备空白表单，再添加字段”，仅 selected/create-form 允许准备草稿并进入下面的逐题循环；selected/cancel 或 cancelled 直接 no_change。自由文本、未知选项与 exhausted 失败关闭。无 SDK 时只保留非执行引导。内部检查点的 formCreationConfirmation 绑定 proposalId 与宿主指纹，后续步骤复验，不接受旧快照、旧提案或自行填入的模型确认字段。

### 确认后的逐题字段澄清循环

2026-11-27 用户修订：引导仅为第一道分支；确认后若信息不足必须继续循环。用户另确认当前仓库先实现草稿，不立即创建真实空表。不得更新宿主 hasCurrentForm/currentSchema 或宣称真实创建；草稿 hasCurrentForm=false、draftFormSchema={fields:[]}，isClarifyingField/pendingIndex 只描述非执行需求状态。最终依然交付已有动作草稿及新建确认卡，由宿主应用、撤销与保存。

无表单字段操作的状态槽位必须包含 `field_requirements`，格式为 `{fields:[部分字段对象],unsupported_reason?:非空支持边界说明}`，最多20个字段。只允许原有七槽位；未知要求必须保存在 unsupported_reason，不能静默丢弃。字段对象可以为空：生成一个字段用 `[{}]`；生成姓名字段用 `[{label:"姓名"}]`；未说明控件、必填或其他属性不能提前写值。Python 冻结为 proposal.fieldClarification，最终步骤使用这些信息收集，不再调用模型补猜。缺少 field_requirements 时生产编译回调明确失败。自然语言的初始提取仍依赖模型，确定性校验不证明所有用户要求都已保留。

依字段原顺序，每次仅问一题，先 label，再 component_name，再该组件属性。组件候选只来自本地九组件与宿主有效新增授权的交集；不预选，不把普通/随便一个框解释为 Input。已明确值不重复问；同槽位的无效或模糊回答在下一稳定 key 继续。名称/占位提示输入文本，类型接受本题选项或明确组件名称，required 接受明确布尔语义。选项组件必须提供真实 label/value（JSON数组或逐行“显示名=业务值”），不猜序号；无业务值继续追问。每个题面只询问当前属性，不把类型、必填、提示一起抛出。

新增七槽位的当前边界不变：可询问宿主授权的 required/placeholder，以及选项组件的静态 options；不能据属性编辑能力推断新字段能配置最大长度、日期时间、数字范围、单位、上传、禁用或动态数据源。明确无法表达的要求整批 unsupported，不静默采用其他组件或丢要求。删除、移动、转换不存在节点不能被解释为创建新字段。组件专有属性待新增协议及真实宿主能力核验后扩展。

固定出口：信息充足则整体编译生成提案；取消则 no_change 并清理 pending；暂停/预算耗尽则非执行 needs_clarification 并保留 pending。用户选“剩下稍后编辑”或明确说“先这样，剩下我后面在设计器改”，只跳过当前及其后可选属性，summary 标注待编辑；缺 label、类型或选项组件真实 options 时只能停止追问并保留草稿，不能违背既有可编译契约猜必需值。新路径编译不补 required=false，保持未指定属性缺省；不改变旧生成路径的默认行为。缺 name/client_ref 时确定性分配 field_N 并经过原有命名规则复验，这不是默认业务元信息。

正在澄清时，新需求不能填入当前槽位；识别到“新增/修改/删除…字段/表单/标题”先问是否完成当前字段。选择继续则暂存新需求、继续原字段；明确“先把上一个字段放一放”或选暂停则保留半成品及 queuedRequests，返回非执行结果。当前实现不自动执行排队的新需求或切换真实表单，消费端需使用最新 context 另发请求。文本控制按明确用语处理，不能声称覆盖任意自然语言的暂停/转题理解。

暂停等非执行输出的 fieldClarification 包含 draftId、hostFingerprint、resumeFingerprint、fields、deferred、pendingIndex（已进入提问时）、round、status、isClarifyingField、hasCurrentForm=false、draftFormSchema、originalRequest 和 queuedRequests。业务下一轮输入 `{resume_field_clarification: 上次完整非执行proposal}` 时不重跑模型；复验部分字段和 deferred，按排除 requestId 的规范化快照核对 resumeFingerprint，允许新 requestId，但能力/画布/revision 变化拒绝。恢复重新原生确认，再按已确认值继续，不自动复用创建授权。

循环题 key 由草稿身份、当前轮次、当前字段与错误/转题状态确定，原生 request 显式 max_rounds=128，最多120题后保留草稿，exhausted 也不生成；可以通过业务恢复继续，不宣称平台支持无限单次 Run。题目依赖前答所以不使用 request_group，不在等待重入调用模型。宿主快照在收集前、每次回答后和最终编译时复验；取消、旧快照、非法选项均不交付部分动作。只在足够信息时结构化编译 `form_fields + replace_empty_form`，至少一个字段；最终提案无 fieldClarification 或第二份字段清单。真实平台等待、恢复与消费端需联调，本地 SDK 替身测试不代表部署。

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
