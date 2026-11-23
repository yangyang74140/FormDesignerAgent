# FormDesignerAgent

AI 协作请先阅读 [AGENTS.md](./AGENTS.md)，其中说明根目录文件用途、文档权威范围、只读第三方资料及当前已确认的设计约束。

表单设计专属 Agent 的能力、宿主输入和单一动作输出契约见 [包说明](./specialized-agent-package/README.md)，动作、公共属性和组件族规则见 [包内业务规范](./specialized-agent-package/specs/README.md)。最终 output 为 `{form_proposal: proposal}`；修改提案使用顶层 `mode/actionVersion/actions`，确认展示仅保留注册组件 `kind/title`。ai-chat 编辑并选择同一份 actions 草稿，提交 `{proposal: 最终提案}`，宿主复验后原子应用，保存另行处理。查询和撤销保留专用展示语义。

**设计器宿主本次未修改，仍须完成新结构解析、草稿复验和应用接入；文档及 Agent 输出不代表宿主已经可执行或已部署。** 接入要求、最小示例与验收边界见 [三端协议说明](./doc/ai-chat-property-edit-integration.md)。不提供旧格式兼容、双格式解析或迁移。