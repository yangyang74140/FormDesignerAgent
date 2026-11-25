# AI 协作必读

本文件是本仓库的 AI 工作入口。每次开始任务，必须先读本文件，再按任务范围读取相关文档和代码；不要一次性加载全部资料。人工协作者也可据此定位规范。

## 1. 仓库职责与协作边界

本项目要实现和维护的是**表单设计器 Agent**，其源码目录为仓库根目录下的 `specialized-agent-package/`。涉及本 Agent 的功能实现、行为调整和缺陷修复时，以该目录为主要修改范围，并同步维护相关文档、测试和根目录打包工具。

Agent 依据宿主真实上下文生成建议；ai-chat 展示并维护用户确认草稿；设计器宿主校验并应用到画布，保存另行处理。

- 表单设计器 Agent（`specialized-agent-package/`）：负责受控生成、编译、校验和插件打包。
- ai-chat：负责 `shared.table-field-confirm` 等注册组件及用户编辑、勾选、提交。
- 表单设计器宿主：负责实际组件能力、节点身份、修订检查、原子应用、撤销和保存。
- 跨项目修改前，先读取目标项目自己的 `AGENTS.md` 与相关规约；本文件不替代其他项目的约束。

## 2. 根目录文件导航

| 文件 | 用途 | 使用与修改规则 |
| --- | --- | --- |
| `AGENTS.md` | AI 每次必读的协作入口、文档导航和已确认约束 | 本项目自维护；项目级规则发生变化时同步更新，详细业务契约放在项目自己的文档中 |
| `README.md` | 面向开发者的项目简介与资料入口 | 本项目自维护；保持简洁，不复制整份动作或输出契约 |
| `specialized-agent-development-guide.md` | **第三方 Agent 开发文档**：插件三件套、Builder SDK、能力生成、Pipeline、打包发布等平台机制 | **只读参考，不修改**；不要把本项目的表单业务规范写入、追加或改写到这份文档 |
| `external-publish-api-reference.md` | 平台对外调用参考：认证、invoke、SSE、Run、会话、附件等接口和事件 | 接入平台时按需查阅；本项目业务结构调整不能被写成平台已支持的新接口、事件或 SDK 能力 |
| `package_agent.py` | 运行 Agent 测试、校验源码和导入完整性，生成上传 ZIP | 打包工具，不是业务协议规范；需要交付插件时使用 |
| `canvas.json` | 本地表单画布数据样例 | 示例数据，不是规范或能力注册表；不能从示例中的具体业务标识推导通用规则 |
| `aa.json` | 本地生成结果样例，供排查提案结构和重复数据 | 用户样例，不作为正式契约，不擅自覆盖或把其中结构推广为标准 |
| `specialized-agent-package-*.zip` | 按插件版本生成的上传产物 | 从源码打包生成，不直接编辑 ZIP，也不以旧 ZIP 代替当前源码或规范 |

根目录新增其他 JSON、日志或压缩包时，先判断其来源和用途；未经确认，不把临时样例、诊断结果或构建产物当作规范。

## 3. 目录与项目文档导航

| 路径 | 用途 | 阅读时机 |
| --- | --- | --- |
| `specialized-agent-package/README.md` | 本项目 Agent 的支持范围、宿主输入、当前输出与应用约束 | 修改 Agent 能力、输入输出或接入逻辑前必读；与源码一起维护 |
| `specialized-agent-package/manifest.yaml` | 插件身份、人设、行为边界和委派说明 | 修改 Agent 行为或交付插件时读取；不是第三方 SDK 规范 |
| `specialized-agent-package/bootstrap.py` | 平台要求的插件注册入口 | 排查插件加载、注册或导入时读取 |
| `specialized-agent-package/agent_definition.py` | 本 Agent 的意图、受控能力调用和输出流水线 | 修改生成与编排行为时读取 |
| `specialized-agent-package/specs/README.md` | 包内业务规范入口，区分当前实现与已确认的后续目标 | 修改动作、属性、组件支持范围前必读；按链接读取相关规范 |
| `specialized-agent-package/specs/actions.md` | 表单动作名称、payload、身份、位置、顺序和错误语义 | 动作协议调整前读取；与动作注册表和测试同步维护 |
| `specialized-agent-package/specs/properties.md`、`specialized-agent-package/specs/components/` | 公共属性、组件族与专有属性规则 | 属性或组件扩展前读取；本地定义不替代宿主能力授权 |
| `specialized-agent-package/form_generation/` | 提案编排；`action_rules/` 管动作注册与校验，`components/` 管组件规则，`host.py` 读宿主能力 | 按职责修改；不要把组件规则重新集中到 proposal.py 或 properties.py |
| `specialized-agent-package/form_generation/components/definitions/` | 每个组件的同名属性文件；`InputTextArea.py` 对应 `Input.TextArea`；`_shared/` 放实际复用的族处理 | 组件专有属性与行为放在对应文件；公共文件保留在 components 根层，统一由 registry.py 注册；不为未实现的组件创建空定义 |
| `specialized-agent-package/tests/` | 生成、编译、事件、宿主上下文和上传包的回归测试 | 实施和验证时按改动范围读取、运行 |
| `doc/ai-chat-property-edit-integration.md` | 本项目维护的 Agent、ai-chat、设计器三端接入说明及待办 | 涉及跨端输出、确认、属性修改和应用回执时读取；历史待办不代表功能已部署 |
| `doc/component-property-inventory.md` | 七类组件的属性、类型、默认值、复杂结构和宿主能力核验记录 | 设计属性动作或核对可写配置时读取；“建议”与“已实现”必须区分 |
| `doc/property-context.example.json` | 属性场景的宿主输入示例 | 理解 context 时按需对照，不包含全部通用规则 |
| `doc/property-proposal.example.json` | 属性场景的输出示例 | 对照实际契约使用；示例不是独立规范，也不能替代校验器 |

## 4. 文档权威范围

1. 第三方开发指南约束平台 SDK 的真实用法；平台对外接口参考约束请求和事件。项目代码不能自行扩展这些平台能力。
2. **本项目的动作类型、输出结构和用户确认流程，由本项目自己的业务契约文档维护**，不修改第三方开发指南，不要求协作者从某个 Agent 脚本中自行猜协议。
3. 动作规范需要列明名称、payload、目标身份、位置、顺序、依赖、前置条件和错误语义；代码、示例和测试必须与规范一致。只在提示词里写约束，不代表协议已经被校验。
4. 现有文档与源码可能记录先前实现。用户确认的新设计是本次实施目标；发现冲突时明确指出并同步相关文档、代码和测试，不能宣称尚未完成的设计已经生效。
5. 未经确认，不另创动作同义名或第二套输出结构。页面动作与表单动作分属不同业务，不因操作含义相近就混用 payload 或执行器。
6. 组件种类、属性、类型、默认值及支持范围必须有宿主真实源码、已核验资料或实际 capabilities 作为依据，不根据组件名称或常见控件经验自行猜测。现有 Agent 注册仅代表本地实现范围，不证明宿主支持；缺少依据时标为待核验，不擅自新增或推广。
7. 能力缺失必须明确拒绝并说明原因，不能静默省略用户要求后返回可执行提案。例如姓名字段可使用 Input，但未声明禁用属性及写入规则时，应说明“暂时还不支持禁用”；不得猜 disabled/readOnly、擅自改成 edit=false/access 或用禁止手工编辑替代禁用。

## 5. 已确认的单一动作输出契约

以下为统一实施的业务契约。Agent 与 ai-chat 按共同契约调整；2026-11-23 经用户确认，指定本地设计器已接入 PC Flow 属性草稿的解析、复验、原子应用与回执，不兼容旧结构。**本地接入不代表已经部署，未支持的组件、布局和规则等能力仍须明确拒绝**。

- 最终 output 固定为 `{form_proposal: proposal}`；保留既有 `protocol/contractVersion`，`schemaVersion` 只作可选画布元数据。修改提案的 `mode/actionVersion/actions` 均位于 proposal 顶层，不再输出 `result`、`validation` 或重复字段/变更清单。
- 每条动作为 `{actionId, action, payload, dependsOn, display}`；`dependsOn` 是 actionId 数组，`display.selectedByDefault` 为布尔值。属性变更另有 `preconditions.before={exists,value?}`；原状态只保留在此处，新值只保留在 payload。可选 `display.effects` 仅解释派生影响，不复制目标新值或执行指令。
- 普通修改确认的 presentation 仅含 `kind/title`：字段使用 `shared.table-field-confirm`，属性使用 `shared.component-property-checklist`。只读 `component_property_query` 保留 `readOnly/items` 且不含动作；`component_property_undo` 保留专用撤销展示，动作仍在顶层，不转普通确认卡。
- 保留现有表单动作名称和语义，包括组件生命周期动作及 `form.apply_property_change/rule/linkage`、`form.undo_property_transaction`；不另造同义名，不混用页面动作。模型输入 IR 不因输出调整而变化。
- `set/copy` 的新值位于 payload.value；`clear/unset/reset` 不带 value，具体语义由已支持的组件规则与宿主处理器决定。不能附加 after 或第二份目标新值。
- ai-chat 编辑唯一 actions 草稿，以 actionId 勾选，提交 `{proposal: 最终已编辑且已选择的提案}`；Apply 幂等键经宿主独立通道传递。不提交选择 ID 数组、edits 或另一份原始载荷；clientRef 仅是新节点身份，不是复选框 ID。
- 动作顺序确定，dependsOn 引用本批其他动作且不得成环；引用本批新节点时必须依赖在前创建动作。用户缺选依赖时明确阻止，不静默代选。下标相关子集须重新验证；仅可对整批纯新增、显式 root index 连续且可证明独立的序列重算位置；其他复杂位置或无法保证语义的子集拒绝应用。
- 字段编译器输出明确 root index，保留插入顺序。原始动作省略 root index 表示物理根列表末尾；字段 IR 默认追加则是最后一个字段之后、末尾非字段之前，两者不能混同。
- 删除未应用建议只移除草稿动作，并复验引用与顺序；删除已有画布节点须使用受支持的 `form.remove_component`。类型转换和完整候选校验交给已支持处理器，缺少能力明确拒绝。
- 生成时校验不授权用户编辑后的草稿。宿主仍须复验固定目标、revision、能力、before、依赖、引用、顺序与最终候选状态，原子应用并执行独立 Apply 幂等、撤销和保存分离。
- 尚未正式使用，不兼容旧输出、不维护双格式解析或迁移，不因这次结构调整新增 v1/v2 分流或 FormSchema 版本门禁；真实平台事件名和最终 output 通道保持不变。

### 2026-11-25 PC 双确认补充契约

本节优先于上文普通确认 kind 和“不新增版本”的历史描述。已协商的新建使用 `form_agent_proposal.v1` / `1.0`、`replace_empty_form`、`shared.form-create-confirm`，仅纯新增。已有表单变更使用 `form_change_proposal.v1` / `form_change_actions.v1`、`append`、`shared.form-change-confirm`，actions 仍是唯一草稿，不改变动作 payload、before、dependsOn 或 display。

统一变更需同时声明 `capabilities.supportedProposalContracts` 包含新契约、`capabilities.supportedPresentationKinds` 包含新 kind、`capabilities.supportedActionVersions` 包含新动作版本（该键缺省才回退 context 顶层同名声明，显式空值不回退）；新建 kind 单独通过 supportedPresentationKinds 协商，新增动作仍需 1.0 授权。无新能力时保留原有纯路径及旧注册组件；这不恢复旧 result 嵌套结构兼容。混合能力缺失时明确 unsupported。查询、撤销及属性 rule/linkage 保留专用路径。

新 IR `result_kind=form_changes` 支持既有字段动作及 `form.property.change`，保留动作相对顺序。统一变更要求 schemaId/baseRevision，formId 适用时保留，含属性才要求 catalogVersion；属性仅定位既有节点，新节点属性在已授权新增 props 中表达。同字段聚合和分组仅是 UI 投影，不复制执行清单或重排动作。不能证明安全的重叠整批拒绝，规则与样例见包内动作规范和三端接入说明。

## 6. 按任务阅读与验证

- 平台或 SDK 接入：本文件 → 第三方开发指南对应章节 → 平台接口参考对应接口。
- 表单动作或输出设计：本文件 → Agent 包 README → 包内 specs/actions.md → 相关三端接入文档 → 编译器与消费端对应实现；先锁定共同契约，再同步实施。
- 属性能力：本文件 → 包内 specs/properties.md 与对应组件族规范 → 组件属性清单 → 属性接入说明及示例 → 属性编译和宿主实现。
- 插件交付：核对源码与文档后，运行 `python3 -B package_agent.py`；它会先运行现有 Python 测试，再校验并打包。仅验证测试可使用 `python3 -B -m unittest discover -s specialized-agent-package/tests -q`。
- 文档导航调整无需运行业务测试，但应检查文件路径、链接及第三方文件未被修改。

保留用户已有未提交改动；没有明确要求，不提交、不推送、不切分支、不自动覆盖样例文件。
