# FormDesignerAgent

AI 协作请先阅读 [AGENTS.md](./AGENTS.md)，其中说明根目录文件用途、文档权威范围、只读第三方资料及当前已确认的设计约束。

表单设计专属 Agent 的能力、宿主接入和当前输出协议见 [包说明](./specialized-agent-package/README.md)，动作、公共属性和组件族规则见 [包内业务规范](./specialized-agent-package/specs/README.md)。子 Agent 最终只输出 `{ form_proposal: proposal }`，通过 `proposal.presentation.kind` 声明现有字段或属性确认组件；ai-chat 本地投影 Props，设计器按原动作契约应用。属性接入细节见 [三端协议说明](./doc/ai-chat-property-edit-integration.md)。