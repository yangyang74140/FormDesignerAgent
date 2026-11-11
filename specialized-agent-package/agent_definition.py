"""单层 Flow 表单 Agent：模型生成受控 IR，Python 编译完整提案。"""

from __future__ import annotations

import inspect
from typing import Any

from specialized.builder.sdk import create_external_agent
from .form_generation.proposal import (
    FORM_PROPOSAL_CONTRACT,
    FORM_PROPOSAL_EVENT,
    FORM_PROPOSAL_PIPELINE,
    FORM_PROPOSAL_STEP,
    compile_form_proposal,
    normalize_host_context,
    proposal_capabilities,
)

def _completed(result: Any) -> bool:
    return isinstance(result, dict) and str(result.get("status") or "") == "completed"


def _result_output(result: Any) -> Any:
    return result.get("output") if isinstance(result, dict) else getattr(result, "output", None)


async def _publish_event(step_context: Any, event_type: str, payload: dict[str, Any]) -> None:
    publisher = getattr(step_context, "event_publisher", None)
    if callable(publisher):
        result = publisher(event_type, payload)
        if inspect.isawaitable(result):
            await result
        return
    emitter = getattr(step_context, "emit", None)
    if callable(emitter):
        result = emitter(event_type, payload)
        if inspect.isawaitable(result):
            await result


def compile_platform_proposal(ir_payload: Any, context: Any) -> dict[str, Any]:
    """Accept the documented callback signature and retain validation diagnostics."""
    host = normalize_host_context(context)
    items = ir_payload.get("plan_items", [ir_payload]) if isinstance(ir_payload, dict) else []
    if isinstance(items, list) and any(
        isinstance(item, dict) and item.get("capability") == "proposal.begin" for item in items
    ):
        missing = [
            key for key in ("currentSchema", "capabilities", "supportedActionVersions")
            if not host.get(key)
        ]
        if missing:
            return compile_form_proposal({
                "capability": "proposal.needs_clarification",
                "slots": {
                    "summary": "宿主上下文不完整，暂未生成可执行提案。",
                    "question": "请由表单设计器在请求顶层 context 中提供：" + "、".join(missing),
                    "code": "HOST_CONTEXT_REQUIRED",
                },
            }, context)
    try:
        return compile_form_proposal(ir_payload, context)
    except ValueError as error:
        return {
            "status": "failed",
            "error_code": "form_proposal_validation_failed",
            "summary": f"表单提案校验未通过：{error}",
        }


async def generate_form_proposal(step_context: Any) -> Any:
    """Generate one capability-aware proposal and publish only the final artifact."""
    host_context = normalize_host_context(step_context)
    result = await step_context.native_capability.generate(
        task=(
            "根据用户请求和宿主快照生成受控 Native Capability IR。"
            "不要直接生成 form-agent.v1 最终提案；Python compiler 会将 IR 编译为最终提案。"
            "无论有一个还是多个项目，根对象都必须且只能是 "
            "{\"plan_items\":[{\"capability\":\"...\",\"slots\":{...}}]}。"
            "禁止直接返回最终提案字段，也禁止使用其他根结构。"
        ),
        input_data={
            "user_input": step_context.inputs,
            "host_context": host_context,
        },
        allow_plan_items=True,
        max_plan_items=64,
        allowed_capabilities=proposal_capabilities(),
        forbidden_fields=[
            "id", "schema", "form_schema", "javascript", "eval", "sql",
            "dom", "react_state", "local_storage", "primaryKey", "nextValueSeed",
        ],
        compiler=compile_platform_proposal,
        output_type="json",
        output_contract=FORM_PROPOSAL_CONTRACT,
        prompt_rules=[
            "只输出严格 JSON，不要输出 Markdown、代码围栏、解释文字或最终 form_proposal。",
            "根对象必须且只能是 {plan_items:[{capability, slots}, ...]}，即使只有一个项目也必须放进 plan_items 数组。",
            "根对象除 plan_items 外不得包含其他字段；不要把 capability、slots、summary、status、fields、actions、presentation、result 或 form_proposal 直接放在根对象。",
            "每个 capability 项目必须同时包含 capability 字符串和 slots 对象，不得省略 slots。",
            "每次必须且只能包含一个 proposal.* 状态项目。",
            "新建完整表单必须使用 plan_items：第一项是 proposal.begin，result_kind=form_fields、mode=replace_empty_form；后续为全部字段各一条 form.field.define。",
            "增量修改必须使用 plan_items：第一项是 proposal.begin，result_kind=form_actions、mode=append；后续为最小动作项目。",
            "needs_clarification、unsupported、no_change 没有字段或动作时，也必须使用只含一个项目的 plan_items 数组。",
            "form.field.define 只填写 client_ref、component_name、label、name、required、placeholder、options。",
            "首期仅支持 Input、Input.TextArea、DatePicker、TimePicker、NumberPicker、SelectSingle、SelectMulti、CheckboxGroup、Switch。",
            "完整生成仅用于 Schema 1.0.0 的空白单层 Flow 画布；否则澄清或 unsupported。",
            "修改现有表单使用 form_actions + append，优先最小增量动作并保留未提及字段、ID、name 和布局。",
            "当前组件绑定发送时 selection.nodeId；无选择且目标依赖当前组件时必须澄清。",
            "前后插入必须给出真实 anchorNodeId 和 before/after；首期不生成容器、槽位或 Grid 目标。",
            "字段类型转换只允许明确标记为未保存的新字段；有损转换必须先澄清。",
            "规则和公式只能引用真实字段或本批 clientRef，不得生成 SQL、eval、JavaScript 或未注册函数。",
            "executionResult 为 applied 前只能说已生成提案；applied 也不能声称已保存。conflict 时必须刷新上下文。",
            "不要虚构组件、属性、事件、函数、接口、人员 ID、地区编码或数据库字段。",
        ],
        examples=[
            {
                "input": "创建一份包含姓名和入职日期的员工入职登记表",
                "output": {
                    "plan_items": [
                        {
                            "capability": "proposal.begin",
                            "slots": {
                                "title": "员工入职登记表",
                                "summary": "创建包含姓名和入职日期的员工入职登记表。",
                                "result_kind": "form_fields",
                                "mode": "replace_empty_form",
                            },
                        },
                        {
                            "capability": "form.field.define",
                            "slots": {
                                "client_ref": "employee-name",
                                "component_name": "Input",
                                "label": "姓名",
                                "name": "employee_name",
                                "required": True,
                                "placeholder": "请输入姓名",
                            },
                        },
                        {
                            "capability": "form.field.define",
                            "slots": {
                                "client_ref": "hire-date",
                                "component_name": "DatePicker",
                                "label": "入职日期",
                                "name": "hire_date",
                                "required": True,
                            },
                        },
                    ]
                },
            },
            {
                "input": "把当前字段设为必填",
                "output": {
                    "plan_items": [
                        {
                            "capability": "proposal.begin",
                            "slots": {
                                "summary": "将当前字段设为必填。",
                                "result_kind": "form_actions",
                                "mode": "append",
                            },
                        },
                        {
                            "capability": "form.update_component",
                            "slots": {
                                "payload": {
                                    "useSelection": True,
                                    "changes": {"required": True},
                                }
                            },
                        },
                    ]
                },
            },
            {
                "input": "在当前字段后插入字段，但没有当前选中字段",
                "output": {
                    "plan_items": [
                        {
                            "capability": "proposal.needs_clarification",
                            "slots": {
                                "summary": "缺少插入位置所需的当前字段。",
                                "question": "请先选择一个字段，或说明新字段应插入到哪个字段之后。",
                                "code": "ANCHOR_FIELD_REQUIRED",
                            },
                        }
                    ]
                },
            },
        ],
    )
    if not _completed(result):
        return result
    output = _result_output(result)
    proposal = output.get("form_proposal") if isinstance(output, dict) else None
    if not isinstance(proposal, dict):
        return {"status": "failed", "summary": "未得到有效表单提案。", "error_code": "form_proposal_missing"}
    await _publish_event(
        step_context,
        FORM_PROPOSAL_EVENT,
        {
            "block_id": "form_proposal",
            "title": "表单设计提案",
            "status": proposal.get("status"),
            "proposal": proposal,
        },
    )
    return {"status": "completed", "output": {"form_proposal": proposal}, "summary": proposal.get("summary", "表单提案已生成。")}


def register_agent(context: Any) -> None:
    builder = create_external_agent(context)
    design_intent = builder.intent(
        key="design_form",
        name="设计与修改表单",
        description="生成单层 Flow 表单字段列表，或按宿主快照生成可执行的增量修改提案。",
        examples=[
            "创建一份员工入职登记表",
            "把当前字段改为必填，并在它后面插入备注字段",
            "将这个未保存的单选字段转换为多选",
        ],
        negative_examples=["直接保存表单", "修改已提交的业务记录", "绕过权限调用后端接口"],
        planner_hint=builder.planner_hint(
            needs_capability=False,
            candidate_capabilities=[],
            plan_template_key="standard_generation",
            success_criteria=[
                "读取 requestId、schemaVersion、target、currentSchema、selection、canvas、capabilities 和动作版本",
                "新建时一次性返回完整字段列表和同源 form.add_component 动作",
                "所有字段名、选项、组件和动作通过 Python 编译器校验",
                "修改现有表单使用最小增量动作并保留无关配置",
            ],
            risk_level="normal",
        ),
        output_policy=FORM_PROPOSAL_PIPELINE,
    )
    form_family = builder.intent_family(
        key="form_design",
        name="表单设计",
        description="识别单层 Flow 表单创建、字段编辑、插入、删除、移动、未保存字段转换和宿主已声明规则任务。",
        fallback_intent="design_form",
        boundary="只生成和解释表单设计提案；设计器负责应用、撤销、预览和保存，业务后端负责最终数据约束。",
        trigger_keywords=["表单", "字段", "组件", "入职登记表", "插入", "删除", "修改", "转换"],
        out_of_scope=["容器嵌套或 Grid", "直接操作 DOM 或 React 状态", "直接保存表单", "修改业务记录", "任意 SQL 或 JavaScript 执行"],
        intents=[design_intent],
    )
    (
        builder
        .use_append_intent(families=[form_family])
        .use_plan(plan_template_key="standard_generation", strategy="intent_family", enabled=True)
        .output_structured(kind="form_proposal", schema=FORM_PROPOSAL_CONTRACT, schema_version="1")
        .pipeline_step(
            key=FORM_PROPOSAL_STEP,
            title="生成表单设计提案",
            running_title="正在检查表单上下文与能力",
            completed_title="表单设计提案已生成",
            failed_title="表单设计提案生成失败",
            output_type="json",
            output_contract=FORM_PROPOSAL_CONTRACT,
            handler=generate_form_proposal,
            input_from="original_input",
            output_visibility="final_artifact",
            reasoning_visibility="trace_only",
            timeout_ms=120000,
        )
        .output_pipeline(
            key=FORM_PROPOSAL_PIPELINE,
            artifact_kind="form_proposal",
            output_type="json",
            steps=[FORM_PROPOSAL_STEP],
            final_contract=FORM_PROPOSAL_CONTRACT,
            failure_policy="fail_fast",
        )
        .register()
    )
