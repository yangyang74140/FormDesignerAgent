"""通用表单生成 Agent：模型只生成受控 Action，代码负责 Schema 规则。"""

from __future__ import annotations

import inspect
from typing import Any

from specialized.builder.sdk import create_external_agent
from .form_generation.actions import (
    FORM_ACTION_CONTRACT,
    FORM_ACTION_PIPELINE,
    FORM_FIELD_BATCH_CONTRACT,
    FORM_OUTPUT_CONTRACT,
    FORM_PIPELINE,
    FORM_SKELETON_CONTRACT,
    action_capabilities,
    compile_form_action,
    compile_form_field_hydration,
    compile_form_skeleton,
    finalize_form_schema,
    hydration_capabilities,
    skeleton_capabilities,
)

FORM_CREATE_INTENT = "create_form"
FORM_MODIFY_INTENT = "modify_form"
FORM_SKELETON_STEP = "form.skeleton.generate"
FORM_HYDRATE_STEP = "form.field.hydrate"
FORM_VALIDATE_STEP = "form.schema.validate"
FORM_ACTION_STEP = "form.action.generate"


def _run_context(step_context: Any) -> dict[str, Any]:
    value = getattr(step_context, "context", None)
    return value if isinstance(value, dict) else {}


def _current_form_schema(step_context: Any) -> dict[str, Any] | None:
    context = _run_context(step_context)
    for key in ("current_form_schema", "current_page_schema", "form_schema"):
        value = context.get(key)
        if isinstance(value, dict) and isinstance(value.get("fields"), list):
            return value
    return None


async def generate_form_skeleton(step_context: Any) -> Any:
    """生成表单骨架并立即发送骨架事件。"""
    result = await step_context.native_capability.generate(
        task=(
            "根据用户需求生成 PC flow 表单骨架 IR。必须先输出 form.create，"
            "再按用户要求的顺序输出 form.skeleton.add_field；只填写字段类型、语义 key 和用途，"
            "不要输出完整 FormSchema、字段 id、props 或 options 内部字段。"
        ),
        input_data={"user_input": step_context.root_inputs},
        allow_plan_items=True,
        max_plan_items=17,
        allowed_capabilities=skeleton_capabilities(),
        forbidden_fields=["schema", "schema_json", "page_schema_json", "children", "id", "componentCategory", "props", "identifiers", "options"],
        compiler=compile_form_skeleton,
        output_type="json",
        output_contract=FORM_SKELETON_CONTRACT,
        prompt_rules=[
            "必须生成表单标题或描述，以及至少一个字段占位符。",
            "字段只能使用 Input、SelectSingle、CheckboxGroup。",
            "field_key 必须稳定、唯一并使用语义化英文或拼音 key。",
            "字段顺序必须与用户描述顺序一致。",
        ],
    )
    if not _completed(result):
        return result
    output = _result_output(result)
    schema = output.get("skeleton_json") if isinstance(output, dict) else None
    if not isinstance(schema, dict):
        return {"status": "failed", "summary": "表单骨架生成失败。", "error_code": "form_skeleton_missing"}
    form_title = output.get("form_title", "") if isinstance(output, dict) else ""
    await _publish_event(
        step_context,
        "page_output.skeleton",
        {
            "block_id": "page_output",
            "title": form_title or "表单生成",
            "status": "generating",
            "skeleton_json": schema,
            "skeleton_source": "external_native_capability",
        },
    )
    return {"status": "completed", "output": {"skeleton_json": schema, "form_title": form_title}, "summary": "表单骨架已生成。"}


async def hydrate_form_fields(step_context: Any) -> Any:
    """批量生成字段配置，再逐个发布字段完成事件。"""
    state = _unwrap_output(step_context.inputs)
    skeleton = state.get("skeleton_json") if isinstance(state, dict) else None
    fields = skeleton.get("fields") if isinstance(skeleton, dict) else None
    if not isinstance(skeleton, dict) or not isinstance(fields, list) or not fields:
        return {"status": "failed", "summary": "表单骨架没有字段。", "error_code": "form_fields_missing"}
    result = await step_context.native_capability.generate(
        task=(
            "根据表单骨架一次性为所有字段生成 form.field.configure。"
            "每个 plan_items 只配置一个 field_key；只填写 label、name、required、placeholder、default_value、options 等业务属性，"
            "不要改变字段 id、类型、顺序或输出完整 Schema。"
        ),
        input_data={
            "user_input": step_context.root_inputs,
            "skeleton_json": skeleton,
            "fields": [
                {
                    "field_key": (field.get("field_key") or (field.get("props") or {}).get("name", "")),
                    "componentName": field.get("componentName"),
                    "purpose": (field.get("purpose") or (field.get("props") or {}).get("label", "")),
                }
                for field in fields if isinstance(field, dict)
            ],
        },
        allow_plan_items=True,
        max_plan_items=max(len(fields), 1),
        allowed_capabilities=hydration_capabilities(),
        forbidden_fields=["schema", "schema_json", "page_schema_json", "children", "id", "componentName", "componentCategory", "identifiers", "primaryKey", "nextValueSeed"],
        compiler=compile_form_field_hydration,
        output_type="json",
        output_contract=FORM_FIELD_BATCH_CONTRACT,
        prompt_rules=[
            "必须为骨架中的每个 field_key 返回一条配置。",
            "没有用户提供的真实业务数据时，选项使用空泛但合理的默认选项，不编造业务事实。",
            "字段身份、默认属性内部结构由编译器补齐。",
        ],
    )
    if not _completed(result):
        return result
    hydrated = _result_output(result)
    hydrated_schema = hydrated.get("form_schema") if isinstance(hydrated, dict) else None
    if not isinstance(hydrated_schema, dict):
        return {"status": "failed", "summary": "表单字段生成结果无效。", "error_code": "form_hydration_missing"}
    completed_fields = hydrated_schema.get("fields") if isinstance(hydrated_schema.get("fields"), list) else []
    total = len(completed_fields)
    for index, field in enumerate(completed_fields, start=1):
        await _publish_event(
            step_context,
            "page_output.node.completed",
            {
                "block_id": "page_output",
                "title": "组件生成",
                "status": "generating",
                "node_id": str(field.get("id") or ""),
                "component_name": str(field.get("componentName") or ""),
                "component_index": index,
                "component_total": total,
                "node": field,
            },
        )
    return {"status": "completed", "output": {"skeleton_json": skeleton, "form_schema": hydrated_schema}, "summary": f"已生成 {total} 个表单字段。"}


async def finalize_form_output(step_context: Any) -> Any:
    """校验、裁剪并发送最终表单产物。"""
    state = _unwrap_output(step_context.inputs)
    schema = finalize_form_schema(state.get("form_schema") if isinstance(state, dict) else {})
    fields = schema.get("fields") if isinstance(schema.get("fields"), list) else []
    if not fields:
        return {"status": "failed", "summary": "最终表单没有有效字段。", "error_code": "form_schema_empty"}
    artifact = {"status": "completed", "output_kind": "form_schema_json", "form_schema_json": schema, "validation": {"status": "passed", "renderable": True, "error_count": 0, "field_count": len(fields)}, "summary": f"表单结构已完成，共 {len(fields)} 个字段。"}
    await _publish_event(
        step_context,
        "page_output.completed",
        {
            "block_id": "page_output",
            "title": "表单生成",
            "status": "completed",
            "output_kind": "form_schema_json",
            "form_schema_json": schema,
            "validation": artifact["validation"],
        },
    )
    return {"status": "completed", "output": artifact, "summary": artifact["summary"]}


async def generate_form_action(step_context: Any) -> Any:
    """根据当前表单 Schema 生成一个增量 Action。"""
    result = await build_form_actions(step_context)
    if not _completed(result):
        return result
    output = _result_output(result)
    action = output.get("form_action_json") if isinstance(output, dict) else None
    if not isinstance(action, dict):
        return {"status": "failed", "summary": "未得到有效表单 Action。", "error_code": "form_action_missing"}
    artifact = {"status": "completed", "output_kind": "form_action_json", "form_action_json": action, "validation": {"status": "passed", "renderable": True, "error_count": 0}, "summary": "表单修改操作已生成。"}
    await _publish_event(step_context, "form_output.completed", {"block_id": "form_output", "title": "修改表单", "status": "completed", "output_kind": "form_action_json", "form_action_json": action, "validation": artifact["validation"]})
    return {"status": "completed", "output": artifact, "summary": artifact["summary"]}


async def build_form_actions(step_context: Any) -> Any:
    """让模型理解自然语言并返回单个受控表单 Action。"""
    current_schema = _current_form_schema(step_context)
    if not current_schema:
        return {"status": "needs_user_input", "summary": "修改表单需要当前 FormSchema。", "error_code": "modify_form_requires_current_schema"}
    return await step_context.native_capability.generate(
        task="根据用户需求和当前 FormSchema 生成一个表单修改 IR，只输出一个 plan_items。",
        input_data={"user_input": step_context.root_inputs, "current_form_schema": current_schema},
        allow_plan_items=True,
        max_plan_items=1,
        allowed_capabilities=action_capabilities(),
        forbidden_fields=["schema", "schema_json", "page_schema_json", "children", "componentName", "componentCategory", "id", "identifiers", "primaryKey", "nextValueSeed"],
        compiler=compile_form_action,
        output_type="json",
        output_contract=FORM_ACTION_CONTRACT,
        prompt_rules=[
            "只输出一个严格 JSON IR，不要输出完整 FormSchema。",
            "修改、移动、删除必须使用当前 Schema 中真实存在的 field_id。",
            "未被用户指向的字段不得修改。",
        ],
    )


def _unwrap_output(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("output"), dict):
        return value["output"]
    return value if isinstance(value, dict) else {}


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



def register_agent(context: Any) -> None:
    builder = create_external_agent(context)
    create_intent = builder.intent(
        key=FORM_CREATE_INTENT,
        name="创建表单",
        description="根据自然语言创建 PC flow 表单，并逐步输出字段。",
        examples=["生成一个学生信息表，包含姓名、性别和兴趣"],
        negative_examples=["把性别字段改成必填", "解释一下什么是表单设计器"],
        planner_hint=builder.planner_hint(
            needs_capability=False, candidate_capabilities=[], plan_template_key="standard_generation",
            success_criteria=["先输出表单骨架", "再逐个发送字段完成事件", "最终输出可消费的 FormSchema"], risk_level="normal",
        ),
        output_policy=FORM_PIPELINE,
    )
    modify_intent = builder.intent(
        key=FORM_MODIFY_INTENT,
        name="修改表单",
        description="根据自然语言使用真实 fieldId 增量修改当前 PC flow 表单。",
        examples=["把性别字段改成必填", "删除兴趣字段，在姓名后面添加手机号"],
        negative_examples=["生成一个新表单", "把这段文字翻译成英文"],
        planner_hint=builder.planner_hint(
            needs_capability=False, candidate_capabilities=[], plan_template_key="standard_generation",
            success_criteria=["只输出一个表单 Action", "只修改用户指向的真实字段"], risk_level="normal",
        ),
        output_policy=FORM_ACTION_PIPELINE,
    )
    form_family = builder.intent_family(
        key="form_generation", name="表单生成与编辑",
        description="识别 PC flow 表单的创建和增量编辑任务。",
        fallback_intent=FORM_CREATE_INTENT,
        boundary="只处理 PC flow 表单的创建和增量编辑；不处理发布、保存、Grid、移动端或未接入组件。",
        trigger_keywords=["生成表单", "创建表单", "添加字段", "删除字段", "移动字段", "修改字段", "表单"],
        out_of_scope=["移动端表单", "Grid 布局专项", "发布表单", "保存表单", "未接入的组件"],
        intents=[create_intent, modify_intent],
    )
    (
        builder
        .use_append_intent(families=[form_family])
        .use_plan(plan_template_key="standard_generation", strategy="intent_family", enabled=True)
        .output_structured(kind="form_output", schema=FORM_OUTPUT_CONTRACT, schema_version="1")
        .pipeline_step(key=FORM_SKELETON_STEP, title="生成表单骨架", running_title="正在生成表单骨架", completed_title="表单骨架已生成", failed_title="表单骨架生成失败", output_type="json", output_contract=FORM_SKELETON_CONTRACT, handler=generate_form_skeleton, input_from="original_input", output_visibility="preview", reasoning_visibility="visible", timeout_ms=120000)
        .pipeline_step(key=FORM_HYDRATE_STEP, title="生成表单字段", running_title="正在生成表单字段", completed_title="表单字段已生成", failed_title="表单字段生成失败", output_type="json", output_contract=FORM_FIELD_BATCH_CONTRACT, handler=hydrate_form_fields, input_from=f"step:{FORM_SKELETON_STEP}", output_visibility="preview", reasoning_visibility="visible", timeout_ms=120000)
        .pipeline_step(key=FORM_VALIDATE_STEP, title="校验表单结构", running_title="正在校验表单结构", completed_title="表单结构已校验", failed_title="表单结构校验失败", output_type="json", output_contract=FORM_OUTPUT_CONTRACT, handler=finalize_form_output, input_from=f"step:{FORM_HYDRATE_STEP}", output_visibility="final_artifact", reasoning_visibility="visible", timeout_ms=120000)
        .pipeline_step(key=FORM_ACTION_STEP, title="生成表单修改操作", output_type="json", output_contract=FORM_ACTION_CONTRACT, handler=generate_form_action, input_from="original_input", output_visibility="final_artifact", reasoning_visibility="trace_only", timeout_ms=120000)
        .output_pipeline(key=FORM_PIPELINE, artifact_kind="form_output", output_type="json", steps=[FORM_SKELETON_STEP, FORM_HYDRATE_STEP, FORM_VALIDATE_STEP], final_contract=FORM_OUTPUT_CONTRACT, failure_policy="fail_fast")
        .output_pipeline(key=FORM_ACTION_PIPELINE, artifact_kind="form_output", output_type="json", steps=[FORM_ACTION_STEP], final_contract=FORM_ACTION_CONTRACT, failure_policy="fail_fast")
        .register()
    )
