# 对外发布接口文档

> 本文件由控制台“对外发布 > 接口文档”页面实时生成。页面展示内容与下载内容使用同一份文档数据。

## 通用约定

- 推荐鉴权方式：先用长期 API Key 调用 `/openapi/v1/auth/token`，再将返回的短期 `access_token` 放入 `Authorization: Bearer {access_token}`；默认有效期 900 秒。
- 仅 `/openapi/v1/auth/token` 接受长期 API Key；旧 API Key 直接调用只在兼容开关开启时可用，本地开发默认开启，生产默认关闭。
- 流式调用通过 SSE 返回事件；正式调用入口使用 `stream=true`。

## 接入前检查

- 正式调用只读取已发布版本，不会读取正在编辑的版本。
- user_id 是外部主体隔离键，不是控制台登录用户。
- context 为自由透传载荷，平台不解释其内部结构。
- 推荐先用长期 API Key 调用 /openapi/v1/auth/token 换取短期签名 JWT；业务接口统一使用返回的 access_token。
- 临时凭证默认有效 900 秒（15 分钟），可以提前重新换取；长期 API Key 不自动过期，删除或禁用后才失效。
- 旧 API Key 直接调用仅用于兼容：本地开发默认开启，生产部署默认关闭；生产接入不要依赖该方式。
- 目录接口 GET /openapi/v1/agents 仍允许仅传 user_id 的公开查询；使用 catalog 凭证时只返回调用方授权范围内的员工。
- 显式指定无效 release_id 时会被拒绝，不会回退到最新版本。
- 上传文件前先查询目标服务的 attachment-capabilities；返回的 MIME、扩展名、大小和数量限制是本次接入的准入依据。
- 平台根据已发布版本自动选择内置解析器或服务包中的受控解析器，第三方不传 parser_id。
- 需要一次解析供多个 Agent 复用时，使用 credential_type=attachment 的平台解析凭证，并在上传时显式传 parser_service_id。

1. **准备调用凭证**：在“调用授权”中创建调用方应用和长期 API Key，并为调用方配置目标服务的授权范围；然后调用 /auth/token 换取短期凭证。仅拿到 API Key 不代表可以调用任意服务。
2. **选择凭证用途**：查询员工目录使用 credential_type=catalog 且不绑定 service_id；调用服务使用 credential_type=invoke；复用平台解析使用 credential_type=attachment 且不绑定 service_id。
3. **选择稳定调用对象**：优先使用 service_id 调用已发布服务；仅当调用方只维护 AI 员工标识时，才使用 agent_id 快捷入口。不要把编辑中的配置当成正式服务。
4. **为每次调用提供主体标识**：每次请求都传入业务侧稳定的 user_id。它用于隔离外部主体的会话与运行记录，不是控制台登录账号。
5. **先查询附件能力**：上传文件前调用 attachment-capabilities，按返回的 MIME、扩展名、大小和数量限制做前置校验。格式是否支持由已发布服务版本决定。
6. **上传并等待解析**：专属附件调用服务级 attachments 接口；跨 Agent 复用时调用 reusable-attachments 接口并显式选择 parser_service_id，轮询状态直到 ready。
7. **按需启动文档摘要**：拿到 ready 的 attachment_id 后，可独立调用摘要启动接口，再用摘要状态接口查看 total_nodes 与 summarized_nodes；摘要成功后再调用 Agent，摘要失败或关闭时仍可走原有兜底。
8. **按事件序号保存进度**：收到事件后保存最新 sequence_no。连接中断时从该序号之后补发历史事件，再恢复订阅，避免重复展示或遗漏输出。

## 最小成功调用

```bash
# 1. 先用长期 API Key 换取短期 access_token
TOKEN=$(curl -s -X POST "$BASE_URL/openapi/v1/auth/token" \
  -H "Authorization: Bearer {api_key}" \
  -H "Content-Type: application/json" \
  -d '{"credential_type":"invoke","service_ids":["{service_id}"],"requested_scopes":["agent:invoke","run:read"]}' \
  | jq -r '.data.access_token')

# 2. 业务调用只携带短期 access_token
curl -N -X POST "$BASE_URL/openapi/v1/services/{service_id}/invoke" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "请总结这份合同的风险点",
    "user_id": "external_user_001",
    "stream": true
  }'
```

替换 service_id、API Key 与 user_id 后即可测试；示例依赖 jq 读取 access_token，也可以由调用方程序解析 JSON。access_token 过期前重新调用 /auth/token 换取即可。需要传文件时，先查询附件能力并上传，等待 parse_status=ready 后，再把 attachment_id 放入 invoke 的 attachments 数组。首次接入先不要传 capability_ids 或 context；确认基本链路成功后，再按接口详情逐项增加扩展参数。

## 接收流式事件时的处理顺序

1. **建立连接**：收到 connected 后记录 run_id。后续的续流、补发、取消和处理中断都围绕同一个 run_id 进行。
2. **持续追加内容**：对 text.delta 按到达顺序追加正文；reasoning.delta 仅在产品需要展示深度思考且实际收到该事件时展示。
3. **处理中断**：收到 tool.waiting 或 interrupt.waiting 时停止等待新正文，使用事件返回的 interrupt_id 调用 resolve；成功提交后继续订阅原 Run。
4. **识别终态**：message.completed、message.error 和 run.cancelled 都代表本轮结束。结束后停止等待新正文；取消的 Run 不能恢复，应新建一次调用。

## POST /openapi/v1/auth/token

**换取临时调用凭证** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：使用长期 API Key 换取短期签名 JWT；长期 API Key 只出现在换证请求中，不作为业务接口的长期调用凭证返回或透传。

**鉴权方式**：`Authorization: Bearer {api_key}`

**适用场景**：第三方服务启动、凭证即将过期前或需要切换服务绑定范围时调用。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `credential_type` | `string` | 是 | catalog 表示员工目录查询；invoke 表示 Agent 服务调用；attachment 表示平台解析器调用。 |
| `service_ids` | `string[]` | 否 | invoke 必填，可一次绑定多个已授权且已发布的 service_id；catalog 和 attachment 必须为空。 |
| `requested_scopes` | `string[]` | 否 | 可选权限收窄项；catalog 固定为 agent:catalog:read，invoke 支持 agent:invoke 和 run:read，attachment 支持 attachment:parser:read、attachment:upload、attachment:read 和 attachment:control。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `access_token` | `string` | 是 | 短期签名 JWT；后续业务请求放入 Authorization: Bearer。 |
| `token_type` | `string` | 是 | 固定为 Bearer。 |
| `expires_in` | `number` | 是 | 有效秒数，默认 900 秒（15 分钟）。 |
| `scope` | `string[]` | 是 | 实际签发的权限集合。 |
| `service_ids` | `string[]` | 是 | 实际绑定的服务集合；目录凭证为空。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/auth/token" \
  -H "Authorization: Bearer ak_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_type": "invoke",
    "service_ids": ["svc_xxx", "svc_yyy"],
    "requested_scopes": ["agent:invoke", "run:read"]
  }'
```

### 调用规则与限制

- 默认有效期为 900 秒；平台支持提前重新换取新凭证，不需要等旧凭证自然过期。
- invoke 凭证必须传至少一个 service_id，可以一次传多个；每个 service_id 都必须属于该调用方授权范围且已发布。
- catalog 凭证不绑定 service_id，只用于带凭证查询已发布员工目录；目录接口本身仍支持不带凭证查询。
- attachment 凭证只由平台解析 API Key 换取，不绑定 service_id；它与 Agent 调用凭证相互隔离。
- 响应不会返回长期 API Key，也不会把长期 API Key 写入临时 JWT。
- 长期 API Key 默认不自动过期；删除或禁用长期 API Key 后，不能再换取新凭证，已签发的临时凭证也会失效。

## POST /openapi/v1/auth/token/revoke

**撤销临时调用凭证** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：撤销某个长期 API Key 当前已经签发的全部临时凭证；不会删除长期 API Key。

**鉴权方式**：`Authorization: Bearer {access_token}`

**适用场景**：发现凭证泄露、调用方退出、权限变更或需要立即切断当前临时凭证时调用。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `revoked` | `boolean` | 是 | 是否完成撤销。 |
| `revoked_credential_id` | `string` | 是 | 被撤销临时凭证的来源长期 API Key ID。 |
| `revoked_scope` | `string[]` | 是 | 被撤销凭证原有权限范围。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/auth/token/revoke" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 该接口按来源长期 API Key 批量撤销，因此同一长期 API Key 换出的其他临时凭证也会同时失效。
- 撤销不会删除或禁用长期 API Key；如需阻止后续换证，应在调用授权中禁用或删除长期 API Key。
- 正在执行的 Run 不会因凭证在中途过期而被强制中断；后续新请求、重连和事件补读需要重新提供有效凭证。

## POST /openapi/v1/services/{service_id}/invoke

**正式服务流式调用** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：通过已发布的 service_id 调用正式 AI 服务，并以 SSE 实时返回运行事件。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：适合第三方聊天窗口、实时执行观察、深度思考展示、工具等待和中途取消场景。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 service_id**：service_id 必须对应已发布且可调用的正式服务。需要固定历史发布版本时，再显式传入 release_id。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 对外服务标识，来自对外发布抽屉或服务列表。 |
| `input` | `object \| string` | 是 | 调用方输入内容；Agent 服务通常传用户问题或结构化输入。 |
| `message` | `string` | 否 | 用户消息简写；通常等价于 input.content。 |
| `conversation_id` | `string` | 否 | 会话标识；传入后可串联多轮上下文。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |
| `stream` | `boolean` | 是 | 必须传 true；对外文档当前只推荐流式调用口径。 |
| `idempotency_key` | `string` | 否 | 调用幂等键；用于调用方重试时避免重复创建同一业务请求。 |
| `context` | `object` | 否 | 自由结构透传上下文，平台不做结构约束；专项可在内部直接读取。 |
| `release_id` | `string` | 否 | 可选服务发布版本标识；传入后固定使用该版本，不传则使用当前正式版本。 |
| `capability_ids` | `string[] \| null` | 否 | 可选能力白名单（Skill/MCP 能力 ID）。不传或传 null 时沿用 Agent 配置；传 [] 时本次不启用能力；传非空数组时只启用传入且可用的 Agent 已绑定能力。 |
| `attachments` | `string[]` | 否 | 可选附件 ID 列表，最多 4 个；可引用当前服务上传的专属附件，也可引用平台复用解析接口生成且已通过目标 Agent 解析器绑定校验的附件。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `connected` | `SSE event` | 否 | 流连接建立事件，包含 run_id。 |
| `status.update` | `SSE event` | 否 | 运行、治理、委派和子编排状态更新；具体 status 值及来源事件见下方 SSE 事件速览。 |
| `reasoning.delta` | `SSE event` | 否 | 深度思考增量；模型未开启深度思考时不会出现。 |
| `text.delta` | `SSE event` | 否 | 正文增量。 |
| `tool.call.started` | `SSE event` | 否 | 工具或能力开始执行。 |
| `tool.call.allowed` | `SSE event` | 否 | 工具调用已通过权限、护栏和运行时准入。 |
| `tool.call.blocked` | `SSE event` | 否 | 工具调用被权限、护栏或治理策略阻断。 |
| `tool.result` | `SSE event` | 否 | 工具或能力执行结果，包含成功、失败或拒绝状态。 |
| `tool.waiting` | `SSE event` | 否 | 工具调用等待确认或补充处理。 |
| `interrupt.waiting` | `SSE event` | 否 | 运行暂停并等待用户、人工或外部处理。 |
| `interrupt.resolved` | `SSE event` | 否 | 等待事项已处理；不代表本轮运行已完成。 |
| `run.resumed` | `status.update.source_event_type` | 否 | 运行从等待状态恢复；对外折叠到 status.update。 |
| `artifact.ready` | `SSE event` | 否 | Agent 生成的文件产物已就绪，可通过产物下载接口获取。 |
| `card_summary.source` | `SSE event` | 否 | 运行卡片摘要来源已登记或摘要任务待处理。 |
| `card_summary.updated` | `SSE event` | 否 | 运行卡片摘要已更新。 |
| `page_generation.skill.started / page_generation.skill.completed` | `structured SSE event` | 否 | 页面生成技能开始或完成；以结构化 payload 交付页面产物。 |
| `page_output.skeleton / page_output.node.completed` | `structured SSE event` | 否 | 页面骨架建立或页面节点生成完成。 |
| `sandbox.*` | `structured SSE event` | 否 | 沙箱类结构化事件；具体事件名由产物协议定义，客户端应容忍未知事件。 |
| `pipeline.step.aborted` | `SSE event` | 否 | 子编排步骤被取消或中止。 |
| `pipeline.step.http.completed` | `SSE event` | 否 | 子编排中的 HTTP 调用成功。 |
| `pipeline.step.http.failed` | `SSE event` | 否 | 子编排中的 HTTP 调用失败。 |
| `pipeline.step.output.delta` | `SSE event` | 否 | 子编排步骤输出的增量片段。 |
| `pipeline.step.output.completed` | `SSE event` | 否 | 子编排步骤输出已收口。 |
| `followup_suggestions` | `SSE event` | 否 | 本轮回答后的推荐追问。 |
| `message.completed` | `SSE event` | 否 | 助手消息已完成，包含消息标识和引用。 |
| `message.error` | `SSE event` | 否 | 流式处理失败，包含错误码和可展示说明。 |
| `run.cancelled` | `SSE event` | 否 | 运行已取消，后续不再继续。 |

### 调用示例

```bash
curl -N -X POST "$BASE_URL/openapi/v1/services/svc_xxx/invoke" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "请总结这份合同的风险点",
    "conversation_id": "conv_demo_001",
    "user_id": "user_001",
    "stream": true,
    "release_id": "rel_xxx",
    "capability_ids": ["cap_skill_xxx", "cap_mcp_xxx"],
    "context": {
      "page": {
        "id": "page_contract_review"
      }
    }
  }'
```

### 调用规则与限制

- 正式调用只读取已发布版本，不读取正在编辑的版本。
- 请求会进入 API Key、调用方应用、服务授权、限流、熔断和审计链路。
- user_id 是外部调用的主体隔离键，不是工作空间内部登录用户。
- context 是自由透传载荷，平台不解释其内部结构，只负责带入运行时和子编排。
- release_id 用于固定调用某个已发布版本；后续更新发布不会影响指定版本。不传 release_id 时，默认使用当前正式版本。
- release_id 必须属于当前 service_id 且版本状态可用；版本不存在、跨服务或不可用时请求会被拒绝，不会静默切换到最新版本。
- capability_ids 只影响本次服务 Run，不会修改 Agent 配置；它可以覆盖 Agent 层能力开关，但不能突破 Agent 已绑定范围。
- 能力中心全局关闭的能力即使传入 capability_ids 也会被静默过滤，不报错、不注入、不调用。
- 平台复用附件先通过 attachment 凭证调用 /openapi/v1/attachments/reusable-attachments 创建，再把 ready 的 attachment_id 放入本次 invoke；目标服务仍会校验解析器绑定。
- 当前不再单独提供功能重叠的创建流式运行接口，流式启动统一通过该接口传 stream=true。
- 若服务未发布、Key 无权限或服务被禁用，请求会被拒绝且写入调用日志。

## POST /openapi/v1/agents/{agent_id}/invoke

**Agent 快捷流式调用** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：通过 agent_id 快速调用其绑定的已发布 AI 服务，并以 SSE 实时返回运行事件。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：适合调用方只知道 AI 员工标识，不直接维护 service_id 的场景。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 agent_id**：agent_id 必须关联可调用的已发布服务；该入口仍会执行发布状态、授权、限流和熔断校验。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | `path string` | 是 | AI 员工标识；平台会反查其已发布服务。 |
| `input` | `object \| string` | 是 | 调用方输入内容。 |
| `message` | `string` | 否 | 用户消息简写；通常等价于 input.content。 |
| `conversation_id` | `string` | 否 | 可选会话标识，用于多轮上下文。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |
| `stream` | `boolean` | 是 | 必须传 true；对外文档当前只推荐流式调用口径。 |
| `idempotency_key` | `string` | 否 | 调用幂等键；用于调用方重试时避免重复创建同一业务请求。 |
| `context` | `object` | 否 | 自由结构透传上下文，平台不做结构约束。 |
| `release_id` | `string` | 否 | 可选服务发布版本标识；传入后固定使用该版本，不传则使用当前正式版本。 |
| `attachments` | `string[]` | 否 | 可选附件 ID 列表，最多 4 个；可引用该 Agent 服务的专属附件或平台复用解析后通过绑定校验的附件。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `connected` | `SSE event` | 否 | 流连接建立事件，包含 run_id。 |
| `status.update` | `SSE event` | 否 | 运行、治理、委派和子编排状态更新；具体 status 值及来源事件见下方 SSE 事件速览。 |
| `reasoning.delta` | `SSE event` | 否 | 深度思考增量。 |
| `text.delta` | `SSE event` | 否 | 正文增量。 |
| `tool.call.started` | `SSE event` | 否 | 工具或能力开始执行。 |
| `tool.call.allowed` | `SSE event` | 否 | 工具调用已通过权限、护栏和运行时准入。 |
| `tool.call.blocked` | `SSE event` | 否 | 工具调用被权限、护栏或治理策略阻断。 |
| `tool.result` | `SSE event` | 否 | 工具或能力执行结果，包含成功、失败或拒绝状态。 |
| `tool.waiting` | `SSE event` | 否 | 工具调用等待确认或补充处理。 |
| `interrupt.waiting` | `SSE event` | 否 | 运行暂停并等待用户、人工或外部处理。 |
| `interrupt.resolved` | `SSE event` | 否 | 等待事项已处理；不代表本轮运行已完成。 |
| `run.resumed` | `status.update.source_event_type` | 否 | 运行从等待状态恢复；对外折叠到 status.update。 |
| `artifact.ready` | `SSE event` | 否 | Agent 生成的文件产物已就绪，可通过产物下载接口获取。 |
| `card_summary.source` | `SSE event` | 否 | 运行卡片摘要来源已登记或摘要任务待处理。 |
| `card_summary.updated` | `SSE event` | 否 | 运行卡片摘要已更新。 |
| `page_generation.skill.started / page_generation.skill.completed` | `structured SSE event` | 否 | 页面生成技能开始或完成；以结构化 payload 交付页面产物。 |
| `page_output.skeleton / page_output.node.completed` | `structured SSE event` | 否 | 页面骨架建立或页面节点生成完成。 |
| `sandbox.*` | `structured SSE event` | 否 | 沙箱类结构化事件；具体事件名由产物协议定义，客户端应容忍未知事件。 |
| `pipeline.step.aborted` | `SSE event` | 否 | 子编排步骤被取消或中止。 |
| `pipeline.step.http.completed` | `SSE event` | 否 | 子编排中的 HTTP 调用成功。 |
| `pipeline.step.http.failed` | `SSE event` | 否 | 子编排中的 HTTP 调用失败。 |
| `pipeline.step.output.delta` | `SSE event` | 否 | 子编排步骤输出的增量片段。 |
| `pipeline.step.output.completed` | `SSE event` | 否 | 子编排步骤输出已收口。 |
| `followup_suggestions` | `SSE event` | 否 | 本轮回答后的推荐追问。 |
| `message.completed` | `SSE event` | 否 | 助手消息已完成，包含消息标识和引用。 |
| `message.error` | `SSE event` | 否 | 流式处理失败，包含错误码和可展示说明。 |
| `run.cancelled` | `SSE event` | 否 | 运行已取消，后续不再继续。 |

### 调用示例

```bash
curl -N -X POST "$BASE_URL/openapi/v1/agents/agent_xxx/invoke" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{"input":"帮我生成一份周报","user_id":"user_001","stream":true,"release_id":"rel_xxx","context":{"page":{"id":"weekly_report"}}}'
```

### 调用规则与限制

- 该入口不绕过治理链路，仍会校验 Scope、服务发布状态、限流和熔断。
- 如果 agent_id 没有关联已发布服务，会返回未发布或无权限错误。
- user_id 是外部调用的主体隔离键，不是工作空间内部登录用户。
- context 是自由透传载荷，平台不解释其内部结构，只负责带入运行时和子编排。
- release_id 用于固定调用某个已发布版本；后续更新发布不会影响指定版本。不传 release_id 时，默认使用当前正式版本。
- release_id 必须属于反查到的 service_id 且版本状态可用；无效时请求会被拒绝，不会静默切换到最新版本。
- 平台复用附件必须先通过 attachment 凭证创建并等待 ready；目标 Agent 未绑定对应解析器或版本时，invoke 会拒绝该附件。

## GET /openapi/v1/agents/{agent_id}/chat-config

**查询 Agent 开场白和推荐问题** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：读取已发布 Agent 当前版本的开场白、推荐问题和输入框配置。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：进入第三方聊天页面时调用，用于渲染聊天空状态；不会启动模型、创建 Run 或创建会话。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | `path string` | 是 | 已发布且已授权的 Agent 标识。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | `string` | 是 | 请求的 Agent 标识。 |
| `service_id` | `string` | 是 | 该 Agent 对应的已发布服务标识。 |
| `release_id` | `string` | 是 | 配置来源的当前发布版本。 |
| `profile_id` | `string` | 是 | 发布快照中的 Agent Profile 标识。 |
| `display_name` | `string` | 否 | Agent 展示名称。 |
| `avatar` | `string` | 否 | Agent 头像公共路径。 |
| `opening_message` | `string` | 否 | 开场白。 |
| `suggested_questions` | `string[]` | 否 | 推荐问题列表。 |
| `placeholder` | `string` | 否 | 输入框占位文案。 |
| `empty_state_hint` | `string` | 否 | 空状态提示。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/agents/agent_xxx/chat-config" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 只读取已发布 Release 快照，不读取未发布的编辑草稿；二开 Agent 的包内配置也按发布版本返回。
- 查询接口不会创建 conversation_id、Run 或模型调用。首次真正调用 Agent 时，如果请求未传 conversation_id，调用链才会创建会话并在响应/事件中返回会话标识。
- 后续多轮调用应复用首次调用返回的 conversation_id；传入不存在或无权访问的会话时沿用现有会话校验。
- 当前发布版本更新后，重新查询才会看到新配置；固定 release_id 的调用仍按调用时指定版本执行。

## GET /openapi/v1/services/{service_id}/chat-config

**按服务查询开场白和推荐问题** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：按已发布服务读取当前版本的开场白、推荐问题和输入框配置。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：进入第三方聊天页面时调用；不会启动模型、创建 Run 或创建会话。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 已发布且已授权的 Agent 服务标识。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | `string` | 是 | 该服务发布快照绑定的 Agent 标识。 |
| `service_id` | `string` | 是 | 请求的服务标识。 |
| `release_id` | `string` | 是 | 配置来源的当前发布版本。 |
| `profile_id` | `string` | 是 | 发布快照中的 Agent Profile 标识。 |
| `display_name` | `string` | 否 | Agent 展示名称。 |
| `avatar` | `string` | 否 | Agent 头像公共路径。 |
| `opening_message` | `string` | 否 | 开场白。 |
| `suggested_questions` | `string[]` | 否 | 推荐问题列表。 |
| `placeholder` | `string` | 否 | 输入框占位文案。 |
| `empty_state_hint` | `string` | 否 | 空状态提示。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/services/service_xxx/chat-config" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 只读取该服务已发布 Release 快照，不读取未发布的编辑草稿；二开 Agent 同样适用。
- 查询接口不会创建 conversation_id、Run 或模型调用；首次真正调用服务时才按既有调用链创建会话。
- 该接口与 /openapi/v1/agents/{agent_id}/chat-config 返回同一份发布配置。

## GET /openapi/v1/agents

**查询已发布员工列表** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：公开查询全部已发布 Agent 员工，并取得每个员工对应的 service_id。

**鉴权方式**：`无需凭证即可查询全量；推荐使用 catalog access_token 按授权范围筛选`

**适用场景**：第三方接入初始化或员工选择页加载时调用；拿到 service_id 后再查询附件能力或发起服务调用。

### 调用前确认

1. **无需 Bearer 鉴权**：不传 api_key 时直接返回全部已发布员工；该接口可用于第三方初始化员工选择列表。
2. **按 Key 收窄范围**：推荐先换取 catalog access_token，再通过 Authorization 传入；旧 api_key 查询参数仅在兼容开关开启时可用，无效凭证会被拒绝。
3. **带上 user_id**：user_id 为必填查询主体标识，用于调用日志留痕，不改变返回范围。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `user_id` | `query string` | 是 | 外部查询主体标识，用于调用日志留痕；不改变公开目录的返回范围。 |
| `Authorization` | `header string` | 否 | 可选；传入 catalog 类型 access_token 后，仅返回该调用方已授权的已发布员工。 |
| `api_key` | `query string` | 否 | 兼容字段，可选；仅在旧 API Key 直调开关开启时使用。不传凭证则返回全部已发布员工。 |
| `page` | `query number` | 否 | 可选，页码，从 1 开始，默认 1。 |
| `size` | `query number` | 否 | 可选，每页数量，默认 20，最大 100。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `total` | `number` | 否 | 符合条件的已发布员工总数。 |
| `page` | `number` | 否 | 当前页码。 |
| `size` | `number` | 否 | 当前页数量上限，最大 100。 |
| `has_more` | `boolean` | 否 | 是否还有下一页。 |
| `list[].agent_id` | `string` | 否 | 员工 Agent 标识，可用于 Agent 快捷入口。 |
| `list[].name` | `string` | 否 | 员工展示名称。 |
| `list[].description` | `string` | 否 | 员工描述。 |
| `list[].service_id` | `string` | 是 | 该员工对应的已发布服务标识，后续服务调用和附件操作使用此值。 |
| `list[].release_id` | `string` | 否 | 当前正式发布版本标识。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/agents?user_id=user_001&page=1&size=20" \

# 推荐：先用 credential_type=catalog 换取 access_token，再按授权范围查询：
curl "$BASE_URL/openapi/v1/agents?user_id=user_001&page=1&size=20" \
  -H "Authorization: Bearer {catalog_access_token}"
```

### 调用规则与限制

- 不需要 Authorization: Bearer；不传任何凭证时返回全部已启用、已发布且绑定正式版本的 Agent 员工。
- 推荐传 catalog access_token；返回范围收窄为该调用方已授权的服务。无效或已禁用的凭证会被拒绝，不会回退为全量查询。
- user_id 会写入现有 OpenAPI 调用日志；日志会对 api_key 自动脱敏，不保存明文。
- 接口不返回编辑中的员工或未发布服务。

## GET /openapi/v1/services/{service_id}/attachment-capabilities

**查询服务附件能力** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：查询已发布服务当前版本支持的附件类型、大小和数量限制。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：上传文件前先调用，按返回的 MIME、扩展名和大小限制决定是否允许用户选择文件。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 已发布且可调用的服务标识。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |
| `release_id` | `query string` | 否 | 可选；查询指定的已发布版本，不传则查询当前正式版本。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `string` | 否 | 服务标识。 |
| `release_id` | `string` | 否 | 能力来源对应的已发布版本。 |
| `supports_file_upload` | `boolean` | 否 | 该服务是否支持文件上传。 |
| `allowed_document_mime_types` | `string[]` | 否 | 允许上传的文档 MIME 类型。 |
| `allowed_document_extensions` | `string[]` | 否 | 允许上传的文档扩展名。 |
| `max_document_size_bytes` | `number` | 否 | 单个文档的最大字节数。 |
| `max_attachments_per_message` | `number` | 否 | 单次调用最多携带的附件数量。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/services/svc_xxx/attachment-capabilities?user_id=user_001" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 返回的是已发布版本的实际能力，不读取编辑中的 Draft。
- 返回自定义格式只代表该服务已声明并启用对应解析能力，不代表平台所有服务都支持。
- 三方不需要也不能传 parser_id；平台会根据文件识别信息自动选择解析器。

## GET /openapi/v1/agents/{agent_id}/attachment-capabilities

**查询 Agent 附件能力** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：通过 agent_id 查询其已发布服务当前版本支持的附件能力。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：调用方使用 agent_id 而不是 service_id 时，上传附件前查询支持的格式和限制。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | `path string` | 是 | 已关联已发布服务的 Agent 标识。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |
| `release_id` | `query string` | 否 | 可选；指定该 Agent 关联服务的已发布版本。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `string` | 否 | Agent 当前解析到的已发布服务标识。 |
| `release_id` | `string` | 否 | 能力来源对应的已发布版本。 |
| `supports_file_upload` | `boolean` | 否 | 该服务是否支持文件上传。 |
| `allowed_document_mime_types` | `string[]` | 否 | 允许上传的文档 MIME 类型。 |
| `allowed_document_extensions` | `string[]` | 否 | 允许上传的文档扩展名。 |
| `max_document_size_bytes` | `number` | 否 | 单个文档的最大字节数。 |
| `max_attachments_per_message` | `number` | 否 | 单次调用最多携带的附件数量。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/agents/agent_xxx/attachment-capabilities?user_id=user_001" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 该接口只是 service_id 能力查询的只读别名，不能形成第二套能力来源。
- 上传附件仍使用 service_id 服务级上传接口。
- 三方不需要也不能传 parser_id。

## POST /openapi/v1/services/{service_id}/attachments

**上传服务附件** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：把输入文件上传到指定已发布服务，并取得可供 invoke 引用的 attachment_id。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：调用服务前上传文件；上传完成后等待解析状态变为 ready，再在 invoke 中传 attachment_id。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 要处理该文件的已发布服务标识。 |
| `files` | `multipart file[]` | 是 | 重复传入的待解析文件；类型和大小必须符合能力查询结果。兼容旧的单个 file 字段。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |
| `release_id` | `multipart string` | 否 | 可选；固定使用指定的已发布版本。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `data[]` | `object[]` | 否 | 按上传顺序返回每个文件的处理结果。 |
| `data[].status` | `"succeeded" \| "failed"` | 否 | 单文件处理状态。 |
| `data[].attachment_id` | `string` | 否 | 成功项的附件引用 ID，后续传给 invoke。 |
| `data[].service_id` | `string` | 否 | 成功项绑定的服务。 |
| `data[].release_id` | `string` | 否 | 成功项绑定的已发布版本。 |
| `data[].file_name` | `string` | 否 | 原始文件名。 |
| `data[].error` | `object \| null` | 否 | 失败项的低敏错误码和文案。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/services/svc_xxx/attachments" \
  -H "Authorization: Bearer {access_token}" \
  -F "user_id=user_001" \
  -F "release_id=rel_xxx" \
  -F "client_upload_key=file-001" \
  -F "files=@./example.ofd" \
  -F "files=@./appendix.pdf"
```

### 调用规则与限制

- 平台根据已发布版本的能力声明自动选择内置解析器或服务包中的受控解析器。
- 上传接口不接受 parser_id，不返回完整解析正文。
- 上传成功不等于解析完成；需要查询每个成功项的附件状态。单个文件失败不会回滚同批其他文件。
- 批量上传使用重复的 files 字段；client_upload_key 可重复传入多个值，按文件顺序匹配。

## GET /openapi/v1/services/{service_id}/attachments/{attachment_id}

**查询附件解析状态** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：查询附件是否已经解析完成，以及失败时的稳定错误信息。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：上传后轮询，或在 invoke 前确认附件已 ready。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 附件所属的已发布服务。 |
| `attachment_id` | `path string` | 是 | 上传接口返回的附件 ID。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `string` | 否 | 附件引用 ID。 |
| `release_id` | `string` | 否 | 附件绑定的已发布版本。 |
| `attachment_state` | `string` | 否 | 附件生命周期状态。 |
| `parse_status` | `string` | 否 | pending、processing、ready 或 failed。 |
| `parse_error_code` | `string \| null` | 否 | 解析失败时的稳定错误码。 |
| `page_count` | `number \| null` | 否 | 平台可提供的页数统计。 |
| `extracted_char_count` | `number \| null` | 否 | 平台可提供的提取字符数统计。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/services/svc_xxx/attachments/att_xxx?user_id=user_001" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- ready 后可在 invoke 的 attachments 字段中引用。
- failed 时不能当作无附件继续执行，客户端应展示 parse_error_code 并按业务决定是否重试。
- 状态接口只返回元数据和统计信息，不返回全文。

## POST /openapi/v1/services/{service_id}/attachments/{attachment_id}/summary

**启动服务附件摘要** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：显式启动或继续指定服务附件的文档树摘要任务，返回任务状态和节点进度。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：希望在调用 Agent 前主动准备文档摘要，或继续一个已暂停的摘要任务时调用。

### 调用前确认

1. **确认摘要凭证**：使用 invoke 类型 access_token 或兼容的 API Key，并确保调用方拥有目标 service_id 的权限。
2. **确认附件归属**：attachment_id 必须属于目标 service_id，user_id 必须与上传服务附件时使用的主体标识一致。
3. **显式启动并轮询**：POST 启动接口幂等；结构树未准备好时先等待并重试，status=succeeded 后再调用 Agent。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 附件所属的已发布服务标识。 |
| `attachment_id` | `path string` | 是 | 服务附件上传接口返回的附件 ID。 |
| `user_id` | `query string` | 是 | 上传附件时使用的外部主体隔离键。 |
| `release_id` | `query string` | 否 | 可选；固定校验指定的已发布服务版本。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `string` | 是 | 附件引用 ID。 |
| `artifact_id` | `string` | 是 | 当前解析产物 ID；同一产物共享摘要任务。 |
| `summary_task_id` | `string \| null` | 否 | 摘要任务 ID；尚未创建任务时可能为空。 |
| `summary_enabled` | `boolean` | 是 | 当前附件解析快照是否开启摘要。 |
| `status` | `string` | 是 | 摘要状态：not_started、pending、claimed、retryable、paused、succeeded、failed、disabled 或 unavailable。 |
| `total_nodes` | `number` | 是 | 文档结构树节点总数。 |
| `summarized_nodes` | `number` | 是 | 已经完成摘要的节点数。 |
| `reason_code` | `string` | 否 | 状态原因码；没有原因时为空字符串。 |
| `reusable` | `boolean` | 是 | 摘要结果是否可供后续多个 Agent 或消息复用。 |
| `attempt_count` | `number` | 是 | 摘要任务尝试次数。 |
| `updated_at` | `string` | 是 | 状态最后更新时间，使用 ISO 8601 时间格式。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/services/svc_xxx/attachments/att_xxx/summary?user_id=user_001" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 接口只返回状态和节点计数，不返回摘要正文、Prompt、模型推理、对象存储路径或解析器实现细节。
- 摘要任务属于附件解析产物，不绑定某一条消息；同一 artifact_id 被多个 Agent 或多条消息使用时共享任务和 checkpoint。
- status=succeeded 后，调用方可以把 attachment_id 放入 /openapi/v1/services/{service_id}/invoke 的 attachments；摘要失败、关闭或不可用时，invoke 仍可沿既有附件原文兜底路线执行。
- POST 启动接口幂等；paused 状态需要再次显式 POST 才会继续，GET 只查询，不会隐式启动或恢复任务。
- 摘要尚未完成时不要提前按摘要结果回答；调用方应根据 total_nodes 与 summarized_nodes 展示进度，并在终态停止轮询。
- 服务端会再次校验服务授权、附件归属、解析状态、对象存储和安全状态；客户端不能指定任意 artifact 版本。
- 结构树尚未准备好时返回 pending 和 TREE_STRUCTURE_NOT_READY，表示等待确定性结构树完成，不表示摘要模型失败。

## GET /openapi/v1/services/{service_id}/attachments/{attachment_id}/summary

**查询服务附件摘要状态** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：查询服务附件摘要的状态、原因和节点进度，不会启动或恢复摘要任务。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：启动摘要后轮询，或在断线、页面刷新和多个 Agent 复用时恢复摘要进度。

### 调用前确认

1. **确认摘要凭证**：使用 invoke 类型 access_token 或兼容的 API Key，并确保调用方拥有目标 service_id 的权限。
2. **确认附件归属**：attachment_id 必须属于目标 service_id，user_id 必须与上传服务附件时使用的主体标识一致。
3. **只查询不启动**：GET 只读取状态，不会隐式创建或恢复摘要任务；根据 status 判断是否继续等待。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 附件所属的已发布服务标识。 |
| `attachment_id` | `path string` | 是 | 服务附件上传接口返回的附件 ID。 |
| `user_id` | `query string` | 是 | 上传附件时使用的外部主体隔离键。 |
| `release_id` | `query string` | 否 | 可选；固定校验指定的已发布服务版本。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `string` | 是 | 附件引用 ID。 |
| `artifact_id` | `string` | 是 | 当前解析产物 ID；同一产物共享摘要任务。 |
| `summary_task_id` | `string \| null` | 否 | 摘要任务 ID；尚未创建任务时可能为空。 |
| `summary_enabled` | `boolean` | 是 | 当前附件解析快照是否开启摘要。 |
| `status` | `string` | 是 | 摘要状态：not_started、pending、claimed、retryable、paused、succeeded、failed、disabled 或 unavailable。 |
| `total_nodes` | `number` | 是 | 文档结构树节点总数。 |
| `summarized_nodes` | `number` | 是 | 已经完成摘要的节点数。 |
| `reason_code` | `string` | 否 | 状态原因码；没有原因时为空字符串。 |
| `reusable` | `boolean` | 是 | 摘要结果是否可供后续多个 Agent 或消息复用。 |
| `attempt_count` | `number` | 是 | 摘要任务尝试次数。 |
| `updated_at` | `string` | 是 | 状态最后更新时间，使用 ISO 8601 时间格式。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/services/svc_xxx/attachments/att_xxx/summary?user_id=user_001" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 接口只返回状态和节点计数，不返回摘要正文、Prompt、模型推理、对象存储路径或解析器实现细节。
- 摘要任务属于附件解析产物，不绑定某一条消息；同一 artifact_id 被多个 Agent 或多条消息使用时共享任务和 checkpoint。
- status=succeeded 后，调用方可以把 attachment_id 放入 /openapi/v1/services/{service_id}/invoke 的 attachments；摘要失败、关闭或不可用时，invoke 仍可沿既有附件原文兜底路线执行。
- POST 启动接口幂等；paused 状态需要再次显式 POST 才会继续，GET 只查询，不会隐式启动或恢复任务。
- 摘要尚未完成时不要提前按摘要结果回答；调用方应根据 total_nodes 与 summarized_nodes 展示进度，并在终态停止轮询。

## POST /openapi/v1/services/{service_id}/attachments/{attachment_id}/summary/cancel

**暂停服务附件摘要** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：暂停服务附件的摘要任务并保留已完成节点，后续可以通过启动接口继续。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：用户中断当前摘要、暂时不需要继续消耗模型调用，或需要释放当前摘要执行时调用。

### 调用前确认

1. **确认摘要凭证**：使用 invoke 类型 access_token 或兼容的 API Key，并确保调用方拥有目标 service_id 的权限。
2. **确认附件归属**：attachment_id 必须属于目标 service_id，user_id 必须与上传服务附件时使用的主体标识一致。
3. **暂停并保留进度**：取消只暂停非终态任务并保留 checkpoint；后续需要再次调用 POST 启动接口才会继续。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 附件所属的已发布服务标识。 |
| `attachment_id` | `path string` | 是 | 服务附件上传接口返回的附件 ID。 |
| `user_id` | `query string` | 是 | 上传附件时使用的外部主体隔离键。 |
| `release_id` | `query string` | 否 | 可选；固定校验指定的已发布服务版本。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `string` | 是 | 附件引用 ID。 |
| `artifact_id` | `string` | 是 | 当前解析产物 ID；同一产物共享摘要任务。 |
| `summary_task_id` | `string \| null` | 否 | 摘要任务 ID；尚未创建任务时可能为空。 |
| `summary_enabled` | `boolean` | 是 | 当前附件解析快照是否开启摘要。 |
| `status` | `string` | 是 | 摘要状态：not_started、pending、claimed、retryable、paused、succeeded、failed、disabled 或 unavailable。 |
| `total_nodes` | `number` | 是 | 文档结构树节点总数。 |
| `summarized_nodes` | `number` | 是 | 已经完成摘要的节点数。 |
| `reason_code` | `string` | 否 | 状态原因码；没有原因时为空字符串。 |
| `reusable` | `boolean` | 是 | 摘要结果是否可供后续多个 Agent 或消息复用。 |
| `attempt_count` | `number` | 是 | 摘要任务尝试次数。 |
| `updated_at` | `string` | 是 | 状态最后更新时间，使用 ISO 8601 时间格式。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/services/svc_xxx/attachments/att_xxx/summary/cancel?user_id=user_001" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 接口只返回状态和节点计数，不返回摘要正文、Prompt、模型推理、对象存储路径或解析器实现细节。
- 摘要任务属于附件解析产物，不绑定某一条消息；同一 artifact_id 被多个 Agent 或多条消息使用时共享任务和 checkpoint。
- status=succeeded 后，调用方可以把 attachment_id 放入 /openapi/v1/services/{service_id}/invoke 的 attachments；摘要失败、关闭或不可用时，invoke 仍可沿既有附件原文兜底路线执行。
- POST 启动接口幂等；paused 状态需要再次显式 POST 才会继续，GET 只查询，不会隐式启动或恢复任务。
- 摘要尚未完成时不要提前按摘要结果回答；调用方应根据 total_nodes 与 summarized_nodes 展示进度，并在终态停止轮询。
- 取消接口只暂停非终态任务并保留 checkpoint；succeeded、failed、disabled 和 unavailable 不会被改写。
- 已送达模型供应商的请求不保证能够在供应商侧撤回，但服务端会推进任务 fencing，避免旧任务继续写回。

## GET /openapi/v1/attachments/parser-services/{parser_service_id}/attachment-capabilities

**查询平台解析器能力** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：查询指定平台解析器支持的文件格式和当前执行可用性。

**鉴权方式**：`Authorization: Bearer {attachment_access_token}（使用 attachment 类型凭证换取）`

**适用场景**：上传可复用附件前，确认选择的解析器支持文件格式且服务可执行。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `parser_service_id` | `path string` | 是 | 平台解析器服务标识。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `parser_service_id` | `string` | 否 | 平台解析器服务标识。 |
| `parser_revision_id` | `string` | 否 | 当前发布的解析器版本标识。 |
| `version` | `string` | 否 | 当前发布版本号。 |
| `available` | `boolean` | 否 | 当前是否可以执行解析。 |
| `formats` | `object[]` | 否 | 支持的扩展名和 MIME 类型。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/attachments/parser-services/parser_xxx/attachment-capabilities" \
  -H "Authorization: Bearer {attachment_access_token}"
```

### 调用规则与限制

- 该接口使用 attachment 凭证，不需要 Agent service_id 授权。
- 上传前必须根据 formats 校验扩展名和 MIME；不支持的格式会被接口拒绝。

## POST /openapi/v1/attachments/reusable-attachments

**上传可复用附件** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：指定一个平台解析器解析文件，生成可供多个已绑定该解析器的 Agent 复用的 attachment_id。

**鉴权方式**：`Authorization: Bearer {attachment_access_token}（使用 attachment 类型凭证换取）`

**适用场景**：希望一次解析后被多个 Agent 使用时调用。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `parser_service_id` | `multipart string` | 是 | 指定使用的平台解析器服务标识。 |
| `user_id` | `multipart string` | 是 | 外部主体隔离键；多个 Agent 需要复用时保持一致。 |
| `client_upload_key` | `multipart string` | 否 | 可选幂等键，重试时保持不变。 |
| `files` | `multipart file[]` | 是 | 重复传入的待解析文件，格式必须符合解析器能力；兼容旧的单个 file 字段。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `data[]` | `object[]` | 是 | 按上传顺序返回每个文件的处理结果。 |
| `data[].status` | `"succeeded" \| "failed"` | 否 | 单文件处理状态。 |
| `data[].attachment_id` | `string` | 否 | 成功项后续传入 Agent invoke 的附件引用 ID。 |
| `data[].parser_service_id` | `string` | 否 | 成功项实际使用的平台解析器。 |
| `data[].parser_revision_id` | `string` | 否 | 成功项实际使用的解析器版本。 |
| `data[].parse_status` | `string` | 否 | 成功项初始通常为 pending，完成后为 ready 或 failed。 |
| `data[].error` | `object \| null` | 否 | 失败项的低敏错误码和文案。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/attachments/reusable-attachments" \
  -H "Authorization: Bearer {attachment_access_token}" \
  -F "parser_service_id=parser_xxx" \
  -F "user_id=external_user_001" \
  -F "client_upload_key=file-001" \
  -F "client_upload_key=file-001" \
  -F "files=@./example.pdf" \
  -F "files=@./appendix.docx"
```

### 调用规则与限制

- attachment 凭证不绑定 Agent；平台只负责解析和生成可复用附件。
- 上传成功不代表解析完成，需对每个成功项轮询状态接口；单个文件失败不会影响同批其他文件。
- 批量上传使用重复的 files 字段；client_upload_key 可重复传入多个值，按文件顺序匹配。
- 目标 Agent 后续仍需具备该解析器绑定，才能在 Agent 调用中使用此 attachment_id。

## GET /openapi/v1/attachments/reusable-attachments/{attachment_id}

**查询可复用附件解析状态** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：查询平台解析器生成的可复用附件状态。

**鉴权方式**：`Authorization: Bearer {attachment_access_token}（使用 attachment 类型凭证换取）`

**适用场景**：上传后轮询，直到 parse_status 为 ready 或 failed。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `path string` | 是 | 上传接口返回的附件 ID。 |
| `user_id` | `query string` | 是 | 上传时使用的外部主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `string` | 否 | 附件引用 ID。 |
| `parse_status` | `string` | 否 | pending、processing、ready 或 failed。 |
| `parse_error_code` | `string \| null` | 否 | 解析失败时的稳定错误码。 |
| `extracted_char_count` | `number \| null` | 否 | 解析得到的字符数统计。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/attachments/reusable-attachments/att_xxx?user_id=external_user_001" \
  -H "Authorization: Bearer {attachment_access_token}"
```

### 调用规则与限制

- 状态接口只返回元数据和统计信息，不返回全文。
- ready 后把 attachment_id 放入 Agent invoke 的 attachments 数组；目标 Agent 仍会校验解析器绑定。

## POST /openapi/v1/reusable-attachments/{attachment_id}/summary

**启动可复用附件摘要** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：显式启动或继续可复用附件的共享文档树摘要任务，供多个 Agent 或消息复用。

**鉴权方式**：`Authorization: Bearer {attachment_access_token}（使用 attachment 类型凭证换取）`

**适用场景**：希望在调用 Agent 前主动准备一次共享摘要，或继续一个已暂停的摘要任务时调用。

### 调用前确认

1. **确认摘要凭证**：使用 attachment 类型 access_token，并确保凭证包含附件解析相关权限。
2. **确认附件归属**：attachment_id 必须属于当前外部主体，user_id 必须与上传可复用附件时完全一致。
3. **显式启动并轮询**：POST 启动接口幂等；结构树未准备好时先等待并重试，status=succeeded 后再调用 Agent。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `path string` | 是 | 可复用附件上传接口返回的附件 ID。 |
| `user_id` | `query string` | 是 | 上传可复用附件时使用的外部主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `string` | 是 | 附件引用 ID。 |
| `artifact_id` | `string` | 是 | 当前解析产物 ID；同一产物共享摘要任务。 |
| `summary_task_id` | `string \| null` | 否 | 摘要任务 ID；尚未创建任务时可能为空。 |
| `summary_enabled` | `boolean` | 是 | 当前附件解析快照是否开启摘要。 |
| `status` | `string` | 是 | 摘要状态：not_started、pending、claimed、retryable、paused、succeeded、failed、disabled 或 unavailable。 |
| `total_nodes` | `number` | 是 | 文档结构树节点总数。 |
| `summarized_nodes` | `number` | 是 | 已经完成摘要的节点数。 |
| `reason_code` | `string` | 否 | 状态原因码；没有原因时为空字符串。 |
| `reusable` | `boolean` | 是 | 摘要结果是否可供后续多个 Agent 或消息复用。 |
| `attempt_count` | `number` | 是 | 摘要任务尝试次数。 |
| `updated_at` | `string` | 是 | 状态最后更新时间，使用 ISO 8601 时间格式。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/reusable-attachments/att_xxx/summary?user_id=external_user_001" \
  -H "Authorization: Bearer {attachment_access_token}"
```

### 调用规则与限制

- 接口只返回状态和节点计数，不返回摘要正文、Prompt、模型推理、对象存储路径或解析器实现细节。
- 摘要任务属于附件解析产物，不绑定某一条消息；同一 artifact_id 被多个 Agent 或多条消息使用时共享任务和 checkpoint。
- status=succeeded 后，调用方可以把 attachment_id 放入 /openapi/v1/services/{service_id}/invoke 的 attachments；摘要失败、关闭或不可用时，invoke 仍可沿既有附件原文兜底路线执行。
- POST 启动接口幂等；paused 状态需要再次显式 POST 才会继续，GET 只查询，不会隐式启动或恢复任务。
- 摘要尚未完成时不要提前按摘要结果回答；调用方应根据 total_nodes 与 summarized_nodes 展示进度，并在终态停止轮询。
- 该接口只要求 attachment API Key 和上传时相同的 user_id，不绑定 Agent 或 service_id。

## GET /openapi/v1/reusable-attachments/{attachment_id}/summary

**查询可复用附件摘要状态** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：查询可复用附件共享摘要的状态、原因和节点进度，不会启动或恢复摘要任务。

**鉴权方式**：`Authorization: Bearer {attachment_access_token}（使用 attachment 类型凭证换取）`

**适用场景**：启动摘要后轮询，或在断线、页面刷新和多个 Agent 复用时恢复共享摘要进度。

### 调用前确认

1. **确认摘要凭证**：使用 attachment 类型 access_token，并确保凭证包含附件解析相关权限。
2. **确认附件归属**：attachment_id 必须属于当前外部主体，user_id 必须与上传可复用附件时完全一致。
3. **只查询不启动**：GET 只读取状态，不会隐式创建或恢复摘要任务；根据 status 判断是否继续等待。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `path string` | 是 | 可复用附件上传接口返回的附件 ID。 |
| `user_id` | `query string` | 是 | 上传可复用附件时使用的外部主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `string` | 是 | 附件引用 ID。 |
| `artifact_id` | `string` | 是 | 当前解析产物 ID；同一产物共享摘要任务。 |
| `summary_task_id` | `string \| null` | 否 | 摘要任务 ID；尚未创建任务时可能为空。 |
| `summary_enabled` | `boolean` | 是 | 当前附件解析快照是否开启摘要。 |
| `status` | `string` | 是 | 摘要状态：not_started、pending、claimed、retryable、paused、succeeded、failed、disabled 或 unavailable。 |
| `total_nodes` | `number` | 是 | 文档结构树节点总数。 |
| `summarized_nodes` | `number` | 是 | 已经完成摘要的节点数。 |
| `reason_code` | `string` | 否 | 状态原因码；没有原因时为空字符串。 |
| `reusable` | `boolean` | 是 | 摘要结果是否可供后续多个 Agent 或消息复用。 |
| `attempt_count` | `number` | 是 | 摘要任务尝试次数。 |
| `updated_at` | `string` | 是 | 状态最后更新时间，使用 ISO 8601 时间格式。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/reusable-attachments/att_xxx/summary?user_id=external_user_001" \
  -H "Authorization: Bearer {attachment_access_token}"
```

### 调用规则与限制

- 接口只返回状态和节点计数，不返回摘要正文、Prompt、模型推理、对象存储路径或解析器实现细节。
- 摘要任务属于附件解析产物，不绑定某一条消息；同一 artifact_id 被多个 Agent 或多条消息使用时共享任务和 checkpoint。
- status=succeeded 后，调用方可以把 attachment_id 放入 /openapi/v1/services/{service_id}/invoke 的 attachments；摘要失败、关闭或不可用时，invoke 仍可沿既有附件原文兜底路线执行。
- POST 启动接口幂等；paused 状态需要再次显式 POST 才会继续，GET 只查询，不会隐式启动或恢复任务。
- 摘要尚未完成时不要提前按摘要结果回答；调用方应根据 total_nodes 与 summarized_nodes 展示进度，并在终态停止轮询。
- 状态查询必须使用上传时相同的 user_id；不返回摘要正文或解析器实现细节。

## POST /openapi/v1/reusable-attachments/{attachment_id}/summary/cancel

**暂停可复用附件摘要** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：暂停可复用附件的共享摘要任务并保留已完成节点，后续可以通过启动接口继续。

**鉴权方式**：`Authorization: Bearer {attachment_access_token}（使用 attachment 类型凭证换取）`

**适用场景**：暂时不需要继续消耗模型调用，或用户中断当前共享摘要时调用。

### 调用前确认

1. **确认摘要凭证**：使用 attachment 类型 access_token，并确保凭证包含附件解析相关权限。
2. **确认附件归属**：attachment_id 必须属于当前外部主体，user_id 必须与上传可复用附件时完全一致。
3. **暂停并保留进度**：取消只暂停非终态任务并保留 checkpoint；后续需要再次调用 POST 启动接口才会继续。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `path string` | 是 | 可复用附件上传接口返回的附件 ID。 |
| `user_id` | `query string` | 是 | 上传可复用附件时使用的外部主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `string` | 是 | 附件引用 ID。 |
| `artifact_id` | `string` | 是 | 当前解析产物 ID；同一产物共享摘要任务。 |
| `summary_task_id` | `string \| null` | 否 | 摘要任务 ID；尚未创建任务时可能为空。 |
| `summary_enabled` | `boolean` | 是 | 当前附件解析快照是否开启摘要。 |
| `status` | `string` | 是 | 摘要状态：not_started、pending、claimed、retryable、paused、succeeded、failed、disabled 或 unavailable。 |
| `total_nodes` | `number` | 是 | 文档结构树节点总数。 |
| `summarized_nodes` | `number` | 是 | 已经完成摘要的节点数。 |
| `reason_code` | `string` | 否 | 状态原因码；没有原因时为空字符串。 |
| `reusable` | `boolean` | 是 | 摘要结果是否可供后续多个 Agent 或消息复用。 |
| `attempt_count` | `number` | 是 | 摘要任务尝试次数。 |
| `updated_at` | `string` | 是 | 状态最后更新时间，使用 ISO 8601 时间格式。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/reusable-attachments/att_xxx/summary/cancel?user_id=external_user_001" \
  -H "Authorization: Bearer {attachment_access_token}"
```

### 调用规则与限制

- 接口只返回状态和节点计数，不返回摘要正文、Prompt、模型推理、对象存储路径或解析器实现细节。
- 摘要任务属于附件解析产物，不绑定某一条消息；同一 artifact_id 被多个 Agent 或多条消息使用时共享任务和 checkpoint。
- status=succeeded 后，调用方可以把 attachment_id 放入 /openapi/v1/services/{service_id}/invoke 的 attachments；摘要失败、关闭或不可用时，invoke 仍可沿既有附件原文兜底路线执行。
- POST 启动接口幂等；paused 状态需要再次显式 POST 才会继续，GET 只查询，不会隐式启动或恢复任务。
- 摘要尚未完成时不要提前按摘要结果回答；调用方应根据 total_nodes 与 summarized_nodes 展示进度，并在终态停止轮询。
- 取消接口只暂停非终态任务并保留 checkpoint；后续必须显式调用启动接口才会继续。

## POST /openapi/v1/attachments/reusable-attachments/{attachment_id}/control

**控制可复用附件解析** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：使用同一个接口暂停、继续或取消指定可复用附件的解析任务。

**鉴权方式**：`Authorization: Bearer {attachment_access_token}（使用 attachment 类型凭证换取）`

**适用场景**：上传后需要主动暂停排队任务、恢复暂停任务，或取消不再需要的解析时调用。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `attachment_id` | `path string` | 是 | 上传接口返回的附件 ID。 |
| `user_id` | `query string` | 是 | 上传时使用的外部主体隔离键。 |
| `action` | `JSON string: "pause" \| "resume" \| "cancel"` | 是 | pause 暂停，resume 继续，cancel 取消解析。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `parse_status` | `string` | 否 | paused、pending、ready、failed 或 cancelled。 |
| `processing_stage` | `string` | 否 | 当前对外可见的处理阶段。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/attachments/reusable-attachments/att_xxx/control?user_id=external_user_001" \
  -H "Authorization: Bearer {attachment_access_token}" \
  -H "Content-Type: application/json" \
  -d '{"action":"pause"}'
```

### 调用规则与限制

- 该操作只允许上传者控制自己的可复用附件，并要求 attachment:control 权限。
- 暂停不会删除原始附件；继续会重新进入解析队列；取消后该解析任务不可继续。
- 任务已经完成或失败时不会被重新改写，最终状态以状态查询返回为准。

## GET /openapi/v1/runs/{run_id}/stream

**订阅已有运行事件流** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：订阅已有正式 Run 的实时事件，常用于确认中断后继续接收输出。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：适合已拿到 run_id，且需要继续监听该 Run 后续事件的场景。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `path string` | 是 | 正式运行标识。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `connected` | `SSE event` | 否 | 订阅建立，返回当前 run_id。 |
| `tool.waiting` | `SSE event` | 否 | 工具或技能需要确认，payload 中包含 tool_call_id 或 interrupt_id。 |
| `interrupt.waiting` | `SSE event` | 否 | 运行进入等待中断态，payload 中包含 interrupt_id、type 与 actions。 |
| `interrupt.resolved` | `SSE event` | 否 | 中断已处理并恢复，payload 中包含 action 与结果摘要。 |
| `run.resumed` | `SSE event` | 否 | Run 已从中断恢复，后续事件继续输出。 |
| `tool.result` | `SSE event` | 否 | 工具或技能执行结果。 |
| `followup_suggestions` | `SSE event` | 否 | 后置追问建议。 |
| `run.cancelled` | `SSE event` | 否 | 运行已取消，终态，不再继续恢复。 |

### 调用示例

```bash
const stream = new EventSource(
  "$BASE_URL/openapi/v1/runs/run_xxx/stream?user_id=user_001"
);
```

### 调用规则与限制

- 确认、拒绝、取消都不在该接口里提交；该接口只负责输出事件。
- 如果 Run 已取消，客户端应把本轮展示为已结束，可保留已输出内容。
- user_id 是外部调用的主体隔离键，不是工作空间内部登录用户。

## GET /openapi/v1/runs/{run_id}/events?after_sequence_no={sequence_no}

**按序号恢复事件** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：从持久化事件表补发指定序号之后的历史事件。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：适合页面刷新、网络断开或 SDK 需要可靠补偿时使用。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `path string` | 是 | 正式运行标识。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |
| `after_sequence_no` | `query number` | 否 | 客户端最后已处理的事件序号；后端从下一条开始补发。 |
| `last_event_sequence` | `query number` | 否 | 兼容旧字段；同时传入时以 after_sequence_no 为准。 |
| `limit` | `query number` | 否 | 本次最多返回的事件数，默认 100。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `string` | 否 | 运行标识。 |
| `status` | `string` | 否 | 运行主状态。 |
| `display_status` | `string` | 否 | 展示用状态。 |
| `detail` | `object` | 否 | 运行详情。 |
| `events` | `array` | 否 | 按序号补发的事件列表；每项通常包含 sequence_no、event_type 和 payload。 |
| `total` | `number` | 否 | 事件总数。 |
| `has_more` | `boolean` | 否 | 是否还有更多历史事件。 |
| `last_sequence_no` | `number` | 否 | 本次返回的最后事件序号。 |
| `after_sequence_no` | `number` | 否 | 本次请求采用的起始序号。 |

### 调用示例

```bash
GET /openapi/v1/runs/run_xxx/events?after_sequence_no=128&user_id=user_001
```

### 调用规则与限制

- 恢复语义必须以 sequence_no 为准，不应混用内存缓冲游标。
- 该接口只做一次性历史补发，不保持 SSE 长连接。
- 补发完成后如需继续实时监听，请订阅已有运行事件流。

## GET /openapi/v1/services/{service_id}/conversations

**查询历史会话** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：查询当前调用应用、指定服务和当前外部用户的历史会话。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：展示历史会话列表，用户选择后再查询该会话的消息。

### 调用前确认

1. **确认调用凭证**：使用 invoke 类型凭证并包含 run:read；服务绑定与平台当前授权都必须有效。
2. **确认用户与查询对象**：传入与发送消息一致的 user_id 或 external_subject_id 及身份维度；会话列表使用 service_id，消息记录使用 conversation_id。
3. **处理分页和空结果**：page 默认 1、size 默认 20 且不超过 100；消息按最早到最新分页。无匹配列表为空，不可访问的会话返回统一 404。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 发布中心的服务 ID，不是员工 ID。 |
| `user_id` | `query string` | 否 | 与发送消息时相同的外部用户 ID；与 external_subject_id 至少传一个非空值。 |
| `external_subject_id` | `query string` | 否 | 外部用户标识；和 user_id 同传时，去首尾空格并忽略大小写后必须一致。 |
| `external_tenant_id` | `query string` | 否 | 调用时使用的外部租户标识；使用过此字段时，查询也必须传相同值。 |
| `external_org_id` | `query string` | 否 | 调用时使用的外部组织标识，必须保持一致。 |
| `external_department_id` | `query string` | 否 | 调用时使用的外部部门标识，必须保持一致。 |
| `page` | `query integer` | 否 | 页码，默认 1，最小 1。 |
| `size` | `query integer` | 否 | 每页数量，默认 20，范围 1～100。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `items` | `array` | 否 | 会话列表，按 updated_at 倒序，同时间按 conversation_id 倒序。 |
| `items[].conversation_id` | `string` | 否 | 会话 ID，用于查询消息和续聊。 |
| `items[].service_id` | `string` | 否 | 会话所属服务 ID。 |
| `items[].title` | `string` | 否 | 会话标题，历史数据可能为空。 |
| `items[].status` | `string` | 否 | active 或 archived；已删除会话不返回。 |
| `items[].created_at / updated_at` | `string` | 否 | 北京时间 ISO 8601 时间，包含 +08:00 时区。 |
| `total` | `integer` | 否 | 当前归属过滤后的会话总数。 |
| `page / size` | `integer` | 否 | 当前页码和每页数量；超出末页时 items 为空，total 保留。 |

### 调用示例

```bash
curl -G "$BASE_URL/openapi/v1/services/svc_xxx/conversations" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  --data-urlencode "user_id=user_001" \
  --data-urlencode "page=1" --data-urlencode "size=20"
```

### 调用规则与限制

- 使用 credential_type=invoke 的临时凭证，scope 需要 run:read，service_ids 必须包含会话所属服务；平台当前服务授权仍须有效。旧 API Key 直调受现有兼容开关控制。
- 第三方服务端先认证最终用户，再传递其身份声明。应用调用凭证只认证应用，不代表已认证最终用户，不要让浏览器任意替换 user_id。
- 用户标识和租户、组织、部门必须与发送消息时一致；不支持不传用户查全应用历史。参数无效返回 422，认证失败沿用现有 401/403。
- 历史归属优先核验可信主体和运行记录。无可信主体的旧数据仅允许同应用、同服务、原始 user_id 精确匹配且无租户等维度的兼容查询；归属不明或混合用户的会话不返回。
- 按租户、组织或部门查询需要调用时已保存可信主体信息；未保存这些维度的旧记录不能推断归属，带维度查询不会返回。
- 接口只读，不补写或修复历史归属；返回统一信封，下面列出的是 data 内字段。
- 无匹配会话返回空列表；服务不存在或无权访问返回 404 RESOURCE_NOT_FOUND_OR_FORBIDDEN。新消息会更新会话顺序，翻页过程中列表可能移动。

## GET /openapi/v1/conversations/{conversation_id}/messages

**查询会话聊天记录** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：分页读取指定会话中用户和员工的聊天消息。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：打开历史会话、刷新聊天页面或回看之前的消息。

### 调用前确认

1. **确认调用凭证**：使用 invoke 类型凭证并包含 run:read；服务绑定与平台当前授权都必须有效。
2. **确认用户与查询对象**：传入与发送消息一致的 user_id 或 external_subject_id 及身份维度；会话列表使用 service_id，消息记录使用 conversation_id。
3. **处理分页和空结果**：page 默认 1、size 默认 20 且不超过 100；消息按最早到最新分页。无匹配列表为空，不可访问的会话返回统一 404。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `conversation_id` | `path string` | 是 | 会话 ID，来自 invoke 响应或历史会话列表。 |
| `user_id` | `query string` | 否 | 与发送消息时相同的外部用户 ID；与 external_subject_id 至少传一个非空值。 |
| `external_subject_id` | `query string` | 否 | 外部用户标识；和 user_id 同传时，去首尾空格并忽略大小写后必须一致。 |
| `external_tenant_id` | `query string` | 否 | 调用时使用的外部租户标识；使用过此字段时，查询也必须传相同值。 |
| `external_org_id` | `query string` | 否 | 调用时使用的外部组织标识，必须保持一致。 |
| `external_department_id` | `query string` | 否 | 调用时使用的外部部门标识，必须保持一致。 |
| `page` | `query integer` | 否 | 页码，默认 1，最小 1。 |
| `size` | `query integer` | 否 | 每页数量，默认 20，范围 1～100。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `items` | `array` | 否 | 消息列表，按 sequence 正序、message_id 正序；默认第一页为最早消息。 |
| `items[].message_id / run_id` | `string` | 否 | 消息 ID 和对应运行 ID；旧消息 run_id 可能为空。 |
| `items[].role` | `string` | 否 | 仅 user 或 assistant。 |
| `items[].content_type / content` | `string` | 否 | 消息格式和展示正文。 |
| `items[].status / sequence` | `string / integer` | 否 | 消息状态和排序序号。 |
| `items[].created_at` | `string` | 否 | 北京时间 ISO 8601 时间，包含 +08:00 时区。 |
| `items[].content_parts` | `array` | 否 | 持久化文本/附件片段，按 sort_order 排列；旧消息可能为空，使用 content 展示。 |
| `items[].content_parts[].attachment` | `object \| null` | 否 | 同消息、未删除附件的 attachment_id、message_id、file_name、mime_type、size_bytes；不可用时为 null，不包含下载链接。 |
| `total` | `integer` | 否 | 过滤后的消息总数；不含 system/tool 和 retried 消息。 |
| `page / size` | `integer` | 否 | 当前页码和每页数量。 |

### 调用示例

```bash
curl -G "$BASE_URL/openapi/v1/conversations/conv_xxx/messages" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  --data-urlencode "user_id=user_001" \
  --data-urlencode "page=1" --data-urlencode "size=20"
```

### 调用规则与限制

- 使用 credential_type=invoke 的临时凭证，scope 需要 run:read，service_ids 必须包含会话所属服务；平台当前服务授权仍须有效。旧 API Key 直调受现有兼容开关控制。
- 第三方服务端先认证最终用户，再传递其身份声明。应用调用凭证只认证应用，不代表已认证最终用户，不要让浏览器任意替换 user_id。
- 用户标识和租户、组织、部门必须与发送消息时一致；不支持不传用户查全应用历史。参数无效返回 422，认证失败沿用现有 401/403。
- 历史归属优先核验可信主体和运行记录。无可信主体的旧数据仅允许同应用、同服务、原始 user_id 精确匹配且无租户等维度的兼容查询；归属不明或混合用户的会话不返回。
- 按租户、组织或部门查询需要调用时已保存可信主体信息；未保存这些维度的旧记录不能推断归属，带维度查询不会返回。
- 接口只读，不补写或修复历史归属；返回统一信封，下面列出的是 data 内字段。
- 即使已知 conversation_id，也要传当前用户身份；后端会重新校验调用应用、服务授权及会话归属。不存在、已删除或无权访问统一返回 404 RESOURCE_NOT_FOUND_OR_FORBIDDEN。
- 不返回系统提示词、工具消息、内部思考、工具参数、原始运行事件或存储路径；本接口用于聊天回放，实时进度仍使用 Run stream/events。
- 正在生成的 assistant 消息可能尚未完成，status 和 content 以本次查询时的数据库状态为准。

## GET /openapi/v1/runs/{run_id}

**查询正式运行状态** · 规划中

**接口状态**：规划中

**接入提示**：当前接口用于提前规划客户端兼容结构，尚不能作为生产接入前提。请使用已可用的事件流和补发接口完成现阶段能力。

**用途**：查询正式 Run 的当前状态、最后事件序号和待处理中断，适合页面刷新后恢复展示。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：适合需要轮询运行状态、恢复详情页展示或检查待处理中断的场景。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `path string` | 是 | 正式运行标识。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `string` | 否 | 运行标识。 |
| `run_status` | `string` | 否 | 运行主状态。 |
| `orchestration_status` | `string` | 否 | 编排子状态。 |
| `last_sequence_no` | `number` | 否 | 最后事件序号。 |
| `pending_interrupts` | `array` | 否 | 待处理中断列表。 |

### 调用示例

```bash
GET /openapi/v1/runs/run_xxx?user_id=user_001
```

### 调用规则与限制

- 该接口只查询运行事实，不负责补发事件流。
- 需要继续接收事件时，请使用 stream；需要补历史事件时，请使用 events。
- user_id 是外部调用的主体隔离键，不是工作空间内部登录用户。

## POST /openapi/v1/runs/{run_id}/cancel

**取消正式运行** · 待外部联调

**接口状态**：待外部联调

**接入提示**：当前接口仍在外部联调或能力完善阶段。可以据此预留客户端分支，但上线前必须以实际联调结果为准，不能将其作为唯一生产路径。

**用途**：终止当前正式 Run，进入 cancelled 终态。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：适合调用方主动停止生成、用户离开页面或业务判断不再需要继续输出的场景。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `path string` | 是 | 要取消的正式运行标识。 |
| `reason` | `string` | 否 | 取消原因；不传时默认 user_cancelled。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `string` | 否 | 被取消的运行标识。 |
| `status` | `cancelled` | 否 | 取消后的终态。 |
| `reason` | `string` | 否 | 取消原因。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/runs/run_xxx/cancel" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "reason":"user_cancelled",
    "user_id":"user_001"
  }'
```

### 调用规则与限制

- 取消不是暂停，不支持继续恢复。
- 已输出内容应保留，后续不会再输出正文增量、后置追问或完成事件。
- 客户端收到 run.cancelled 后应展示为本轮输出结束。
- user_id 是外部调用的主体隔离键，不是工作空间内部登录用户。
- 该接口当前不单独提供 idempotency_key，重复取消请以服务端最新 Run 状态为准。

## POST /openapi/v1/runs/{run_id}/interrupts/{interrupt_id}/resolve

**处理中断并恢复运行** · 部分可用

**接口状态**：部分可用

**接入提示**：当前接口仍在外部联调或能力完善阶段。可以据此预留客户端分支，但上线前必须以实际联调结果为准，不能将其作为唯一生产路径。

**用途**：提交工具授权、用户澄清、人工审核、重试决策等中断处理结果。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：适合收到 tool.waiting 或 interrupt.waiting 后，调用方需要提交同意、拒绝或补充输入的场景。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `path string` | 是 | 等待处理的运行标识。 |
| `interrupt_id` | `path string` | 是 | 中断标识，由等待事件返回。 |
| `action` | `string` | 是 | 处理动作，例如 approve、reject、answer、retry、cancel、continue。 |
| `payload` | `object` | 否 | 动作附加参数，例如用户补充答案、拒绝原因或确认信息。 |
| `idempotency_key` | `string` | 否 | 幂等键，防止重复提交同一个处理结果。 |
| `user_id` | `string` | 是 | 外部人维度主键，标准口径下的主体隔离键。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `interrupt_id` | `string` | 否 | 已处理的中断标识。 |
| `run_id` | `string` | 否 | 所属运行标识。 |
| `status` | `string` | 否 | 提交结果，例如 resolved、cancelled。 |
| `action` | `string` | 否 | 最终处理动作，例如 approve、reject、answer、retry、cancel、continue。 |
| `idempotent_replay` | `boolean` | 否 | 是否命中幂等重放。 |

### 调用示例

```bash
curl -X POST "$BASE_URL/openapi/v1/runs/run_xxx/interrupts/int_xxx/resolve" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "approve",
    "payload": {"reason": "允许本次工具调用"},
    "idempotency_key": "approve-run_xxx-int_xxx",
    "user_id": "user_001"
  }'
```

### 调用规则与限制

- resolve 只提交决策，不在同一个响应里继续吐 SSE。
- 后续事件继续从 run stream 或 events 接口读取。
- 旧 tool-calls confirm 接口已废弃，不应作为新 SDK 入口。
- user_id 是外部调用的主体隔离键，不是工作空间内部登录用户。

## GET /openapi/v1/services/{service_id}/artifacts/{artifact_id}

**查询生成文件产物** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：查询 Agent 生成文件的元数据和生成状态，不返回文件正文或内部存储路径。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：收到聊天或运行事件中的 artifact_id 后，查询文件是否已经 ready。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 已发布服务标识。 |
| `artifact_id` | `path string` | 是 | 生成文件产物标识。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `artifact_id` | `string` | 是 | 文件产物标识。 |
| `filename` | `string` | 是 | 归一化后的文件名。 |
| `status` | `generating \| ready \| failed \| expired` | 是 | 产物状态。 |
| `size_bytes` | `number` | 否 | 文件大小。 |
| `created_at` | `string` | 否 | 创建时间。 |
| `ready_at` | `string \| null` | 否 | 就绪时间。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/services/svc_xxx/artifacts/art_xxx" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 文件生成仍由 Agent ToolLoop 发起，接口只查询已经产生的产物。
- 产物必须属于当前 service 和当前 API Key 主体；未就绪、失败和过期不会被伪装成成功。

## GET /openapi/v1/services/{service_id}/artifacts/{artifact_id}/content

**下载生成文件** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：下载已生成完成的文件本体。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：产物状态为 ready 后下载文件；也可以使用短时 URL 交给浏览器或下游系统。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 已发布服务标识。 |
| `artifact_id` | `path string` | 是 | 生成文件产物标识。 |
| `download_token` | `query string` | 否 | 由 /url 接口签发的短时下载令牌，可替代 API Key。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `body` | `binary` | 是 | 文件二进制内容，Content-Type 和文件名来自产物元数据。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/services/svc_xxx/artifacts/art_xxx/content" \
  -H "Authorization: Bearer {access_token}" \
  -o report.docx
```

### 调用规则与限制

- 只有 ready 状态可以下载；expired、failed、generating 分别返回对应错误码。
- 响应不暴露 storage_key、宿主机路径或永久公开地址。

## GET /openapi/v1/services/{service_id}/artifacts/{artifact_id}/url

**获取生成文件短时下载地址** · 已可用

**接口状态**：已可用

**接入提示**：当前接口可作为正式接入入口。调用前仍需确认服务已发布、调用方已获得授权，并在客户端处理流式终态与异常响应。

**用途**：签发绑定当前服务和产物的短时下载地址。

**鉴权方式**：`Authorization: Bearer {access_token}（先通过 /openapi/v1/auth/token 换取）`

**适用场景**：需要把文件交给浏览器、消息卡片或下游系统下载时使用。

### 调用前确认

1. **权限已配置**：请求携带有效 API Key，且调用方已获目标服务的授权范围。服务未发布、已禁用或无权限时不能通过重试绕过。
2. **确认 run_id**：run_id 必须来自同一调用主体已建立的正式运行。不要混用其他用户、服务或历史运行的标识。
3. **带上 user_id**：user_id 是外部主体隔离键。客户端应使用稳定、可追溯的业务用户标识，而不是随机生成或控制台账户标识。
4. **准备客户端状态**：流式入口需保存 run_id 与 sequence_no；可能进入等待状态的场景还需保存 interrupt_id，并在终态后停止追加或继续恢复。

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `service_id` | `path string` | 是 | 已发布服务标识。 |
| `artifact_id` | `path string` | 是 | 生成文件产物标识。 |

### 响应字段 / 事件字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `download_url` | `string` | 是 | 默认 5 分钟有效的下载地址。 |
| `expires_in` | `number` | 是 | 剩余有效秒数。 |
| `expires_at` | `string` | 是 | 过期时间。 |

### 调用示例

```bash
curl "$BASE_URL/openapi/v1/services/svc_xxx/artifacts/art_xxx/url" \
  -H "Authorization: Bearer {access_token}"
```

### 调用规则与限制

- 短时地址只绑定当前 service_id 和 artifact_id，不能跨服务复用。
- 文件过期或产物无权访问时不会签发地址。

## SSE 事件速览

| 事件 | 类型 | 说明 |
| --- | --- | --- |
| `connected` | `event` | SSE 建连成功，包含 run_id。 |
| `status.update` | `event` | 统一状态事件。payload 含 title、summary、tone、status、source_event_type；运行、治理、护栏、委派和子编排状态都由此承载，status 值见下方状态表。 |
| `reasoning.delta` | `event` | 深度思考增量；模型开启深度思考时才出现。 |
| `text.delta` | `event` | 正文增量，客户端应按顺序追加展示。 |
| `tool.call.started` | `event` | 工具或能力开始执行；携带工具标识、名称和参数。 |
| `tool.call.allowed` | `event` | 工具调用已通过权限、护栏和运行时准入。 |
| `tool.call.blocked` | `event` | 工具调用被权限、护栏或治理策略阻断。 |
| `tool.result` | `event` | 工具或能力执行结果；由 tool.call.completed / tool.call.failed 适配而来，status 区分完成、失败或用户拒绝。 |
| `tool.waiting` | `event` | 工具或技能等待确认，需要调用 resolve。 |
| `interrupt.waiting` | `event` | 运行进入等待中断态，需要调用 resolve。 |
| `interrupt.resolved` | `event` | 等待事项已处理；后续是否恢复以恢复事件和状态为准。 |
| `run.resumed` | `status.update.source_event_type` | Run 从等待状态恢复；对外折叠到 status.update。 |
| `artifact.ready` | `event` | Agent 生成的文件产物已就绪，可通过产物下载接口获取。 |
| `card_summary.source` | `event` | 运行卡片摘要来源已登记或摘要任务待处理。 |
| `card_summary.updated` | `event` | 运行卡片摘要已更新。 |
| `page_generation.skill.started / page_generation.skill.completed` | `structured event` | 页面生成技能开始或完成；以结构化 payload 交付页面产物。 |
| `page_output.skeleton / page_output.node.completed` | `structured event` | 页面骨架建立或页面节点生成完成。 |
| `sandbox.*` | `structured event` | 沙箱类结构化事件；具体事件名由产物协议定义，客户端应容忍未知事件。 |
| `pipeline.started` | `status.update.source_event_type` | 子编排开始；状态通过 status.update 推送，不是独立 SSE event。 |
| `pipeline.resumed` | `status.update.source_event_type` | 等待处理后子编排恢复；状态通过 status.update 推送。 |
| `pipeline.step.started` | `status.update.source_event_type` | 子编排步骤开始；状态通过 status.update 推送。 |
| `pipeline.step.resumed` | `status.update.source_event_type` | 子编排步骤恢复；状态通过 status.update 推送。 |
| `pipeline.step.completed` | `status.update.source_event_type` | 子编排步骤完成；状态通过 status.update 推送。 |
| `pipeline.step.failed` | `status.update.source_event_type` | 子编排步骤失败；状态通过 status.update 推送。 |
| `pipeline.completed` | `status.update.source_event_type` | 子编排完成，不代表父 Run 已完成；状态通过 status.update 推送。 |
| `pipeline.failed` | `status.update.source_event_type` | 子编排失败；父 Run 可能继续、降级或结束，状态通过 status.update 推送。 |
| `pipeline.step.aborted` | `event` | 子编排步骤被取消或中止。 |
| `pipeline.step.http.completed` | `event` | 子编排中的 HTTP 调用成功。 |
| `pipeline.step.http.failed` | `event` | 子编排中的 HTTP 调用失败。 |
| `tool.transport.updated` | `status.update.source_event_type` | 原生工具调用切换或回退状态；状态通过 status.update 推送。 |
| `model.recovery` | `status.update.source_event_type` | 模型调用恢复或降级状态；状态通过 status.update 推送。 |
| `control_decision.degraded` | `status.update.source_event_type` | 意图识别或任务规划使用规则降级；状态通过 status.update 推送。 |
| `run.status_changed` | `status.update.source_event_type` | Run 或编排状态变化；状态通过 status.update 推送。 |
| `run.completed / run.failed / run.timeout` | `status.update.source_event_type` | Run 成功、失败或超时终态；通过 status.update 推送。 |
| `run.governance_waiting` | `status.update.source_event_type` | Run 因治理或等待条件暂停；客户端等待用户、人工或外部动作。 |
| `run.governance_retry_scheduled / run.governance_retry_ready / run.governance_retry_exhausted` | `status.update.source_event_type` | 治理重试已安排、就绪或耗尽；状态通过 status.update 推送。 |
| `run.governance_reflect_started / run.governance_reflect_exhausted` | `status.update.source_event_type` | 自动调整策略开始或次数耗尽；状态通过 status.update 推送。 |
| `run.governance_escalated` | `status.update.source_event_type` | 自动处理升级为人工确认；状态通过 status.update 推送。 |
| `run.transition_rejected / run.late_result_discarded / run.failure_archived` | `status.update.source_event_type` | 状态迁移拒绝、迟到结果丢弃或失败归档等运行治理事实；状态通过 status.update 推送。 |
| `guardrail.decision` | `event / status.update.source_event_type` | 护栏决策事件；可映射为状态卡，审批类裁决可能保留为原事件。 |
| `intent.created / intent.recognized / intent.low_confidence` | `status.update.source_event_type` | 用户目标创建、意图识别或低置信度处理状态。 |
| `plan.generating / plan.created / plan_step.created / plan_step.mapped` | `status.update.source_event_type` | 计划生成、计划建立和步骤拆解或映射状态。 |
| `reasoning.summary.completed / run.card_summary_source_registered` | `card_summary.source.source_event_type` | 面向用户的思考摘要来源已登记；摘要通过 card_summary.source 推送。 |
| `card_summary.projection.updated / run.card_summary_updated` | `card_summary.source / card_summary.updated.source_event_type` | 运行卡片摘要投影或最终摘要更新；分别通过 card_summary.source 或 card_summary.updated 推送。 |
| `divergence.detected / divergence.replanned` | `status.update.source_event_type` | 检测到执行偏离或完成计划调整。 |
| `intent_family.classified / intent_family.fallback / intent_family.schema_loaded` | `status.update.source_event_type` | 意图族分类、降级或规则加载状态。 |
| `slot.filled / slot.missing` | `status.update.source_event_type` | 执行所需信息已补齐或仍有缺失。 |
| `clarification.requested / clarification.fulfilled / clarification.exhausted / clarification.late_input_discarded` | `status.update.source_event_type` | 澄清请求、信息补齐、轮次耗尽或迟到输入处理状态。 |
| `plan_template.recommended / plan_template.adoption_recorded` | `status.update.source_event_type` | 计划模板推荐或采纳记录状态。 |
| `run.empty_final_output` | `event` | 运行未生成可展示的最终正文；通常还会收到 message.error 或失败状态。 |
| `pipeline.step.output.delta` | `event` | 子编排步骤输出增量；客户端按顺序拼接 payload.delta 或 payload.content。 |
| `pipeline.step.output.completed` | `event` | 子编排步骤输出已完整收口，可结束该步骤的增量展示。 |
| `collaboration.plan.frozen` | `status.update.source_event_type` | 委派计划已冻结；状态通过 status.update 推送。 |
| `collaboration.arrangement.updated` | `status.update.source_event_type` | 委派安排或结果投影更新；状态通过 status.update 推送。 |
| `collaboration.worker.started` | `status.update.source_event_type` | 委派智能体开始执行；状态通过 status.update 推送。 |
| `collaboration.worker.progress` | `status.update.source_event_type` | 委派智能体进度或等待状态更新；状态通过 status.update 推送。 |
| `collaboration.worker.completed` | `status.update.source_event_type` | 委派智能体结束；状态通过 status.update 推送，不代表父 Run 完成。 |
| `collaboration.batch.stopped` | `status.update.source_event_type` | 未完成的委派批次已停止；状态通过 status.update 推送。 |
| `collaboration.merge.completed` | `status.update.source_event_type` | 委派结果已汇总；父 Run 仍可能继续执行。 |
| `followup_suggestions` | `event` | 后置追问建议，通常在正文完成后出现。 |
| `message.completed` | `event` | 助手消息已完成，包含 message_id 和 citations；它表示消息交付完成。 |
| `message.error` | `event` | 流式处理失败，包含错误码和可展示说明。 |
| `run.cancelled` | `event` | 取消终态，不再恢复。 |

## status.update 状态值

| 状态值 | 类型 | 说明 |
| --- | --- | --- |
| `running` | `payload.status` | 正在执行；也用于委派 Worker 和子编排步骤进行中。 |
| `completed` | `payload.status` | 对应消息、步骤或委派结果已完成，不单独代表父 Run 完成。 |
| `failed` | `payload.status` | 对应运行、步骤、委派任务或护栏处理失败。 |
| `cancelled` | `payload.status` | 运行或委派任务已取消。 |
| `timeout` | `payload.status` | 运行或委派任务已超时。 |
| `waiting_model` | `payload.status` | 等待模型响应。 |
| `waiting_tool_result` | `payload.status` | 等待工具返回结果。 |
| `waiting_user_input` | `payload.status` | 暂停并等待用户补充信息。 |
| `waiting_human` | `payload.status` | 暂停并等待人工确认或处理。 |
| `retrying` | `payload.status` | 等待或正在执行受控重试。 |
| `resuming` | `payload.status` | 正在从等待或治理暂停状态恢复。 |
| `reflecting` | `payload.status` | 系统正在调整执行策略。 |
| `degraded` | `payload.status` | 模型或护栏进入降级处理。 |
| `clear` | `payload.status` | 护栏检查通过或无额外动作。 |
| `warning` | `payload.status` | 护栏产生提醒或需要关注的处理结果。 |
| `remediated` | `payload.status` | 护栏已执行改写、过滤或脱敏处理。 |
| `blocked` | `payload.status` | 护栏已阻止当前内容或动作。 |
| `requires_action` | `payload.status` | 委派任务等待确认或补充动作；处理后可继续原 Run。 |
| `pipeline_started` | `payload.status` | 子编排开始。 |
| `pipeline_resumed` | `payload.status` | 等待处理后子编排整体恢复。 |
| `intent_created` | `payload.status` | 本轮用户目标已记录。 |
| `intent_recognized` | `payload.status` | 本轮意图识别已完成。 |
| `intent_low_confidence` | `payload.status` | 意图置信度较低，运行进入保守处理。 |
| `plan_generating` | `payload.status` | 正在生成执行计划。 |
| `plan_created` | `payload.status` | 执行计划已生成。 |
| `plan_step_created` | `payload.status` | 计划步骤已拆解。 |
| `plan_step_mapped` | `payload.status` | 当前执行步骤已映射到计划。 |
| `reasoning_summary_completed` | `payload.status` | 可展示的思考摘要已完成。 |
| `divergence_detected` | `payload.status` | 检测到执行偏离；实际值也可能使用 none、uncertain、diverged、confirmed、replanned 或 resolved。 |
| `none / uncertain / diverged / confirmed / replanned / resolved` | `payload.status` | divergence.detected 事件携带的偏离判断状态。 |
| `divergence_replanned` | `payload.status` | 已按偏离情况重新调整执行计划。 |
| `intent_family_classified` | `payload.status` | 意图族分类已完成。 |
| `intent_family_fallback` | `payload.status` | 意图族识别降级至兜底路径。 |
| `intent_family_schema_loaded` | `payload.status` | 意图族规则已加载。 |
| `slot_filled` | `payload.status` | 执行所需信息已补齐。 |
| `slot_missing` | `payload.status` | 执行仍缺少必要信息。 |
| `clarification_requested` | `payload.status` | 已向用户请求澄清。 |
| `clarification_fulfilled` | `payload.status` | 澄清信息已收到并回填。 |
| `clarification_exhausted` | `payload.status` | 可用澄清轮次已耗尽。 |
| `clarification_late_input_discarded` | `payload.status` | 运行进入终态后收到的迟到澄清输入已忽略。 |
| `plan_template_recommended` | `payload.status` | 已推荐计划模板。 |
| `plan_template_adoption_recorded` | `payload.status` | 已记录计划模板采纳结果。 |
| `transition_rejected` | `payload.status` | 非法或过期的运行状态迁移已拒绝。 |
| `late_result_discarded` | `payload.status` | 终态或失去执行权后的迟到结果已丢弃。 |
| `failure_archived` | `payload.status` | 运行失败诊断信息已归档。 |

