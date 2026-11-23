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
        property_request = any(
            isinstance(item, dict) and isinstance(item.get("slots"), dict)
            and str(item["slots"].get("result_kind", "")).startswith("property_")
            for item in items
        )
        required_context = ("currentSchema", "capabilities") if property_request else (
            "currentSchema", "capabilities", "supportedActionVersions"
        )
        missing = [key for key in required_context if not host.get(key)]
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
            "已有画布只新增字段时，第一项为 proposal.begin，result_kind=form_fields、mode=append；后续仅定义新增的 form.field.define，不重生成已有字段。",
            "append 默认插入 currentSchema.fields 中最后一个 componentCategory=field（缺省视为 field）的组件之后；不指定位置时省略 target。",
            "在 XX 后/前新增字段时，在 proposal.begin.slots.target 使用 kind=relative、position=after/before，并从 currentSchema 读取 anchorNodeId；也可传原样 anchorLabel 或 anchorName，由编译器唯一匹配。当前字段使用 useSelection=true。",
            "相同锚点的一批新字段按用户描述顺序定义，由编译器计算连续插入下标，不能重复定义已有字段。目标不存在、重名或选择为空时必须澄清，不默认改为末尾追加。",
            "七类组件的属性编辑统一使用 proposal.begin result_kind=property_changes + form.property.change；查询用 property_query + form.property.query；撤销用 property_undo + form.property.undo。属性复制通过 change.operation=copy，不直接复制身份信息。新旧路径不得混用。",
            "每条属性 IR 使用 node_id 或 use_selection=true，也可用 node_label/node_name 唯一定位；property 必须来自宿主 properties 目录。operation=set/clear/unset/reset/copy，set 必须有 value；copy 使用 source_node_id/source_property。",
            "必添/不能为空映射 required；提示文字映射 placeholder；长度上限映射 textLengthLimit，不是 maxLength；标签靠左映射 titleAlign，不是 labelAlign；手机号优先内置 formatValidation。禁用按权限语义处理，不能虚构 disabled。",
            "属性目录提供值类型、枚举、范围、默认值和操作；开启必填转换 boolean，数字 0 是合法值，文本默认值 1 保留字符串；选项必须保留真实业务 value，不猜序号。",
            "数字上下限优先使用宿主成组 numericRange，value={min:{value:数字,message:提示},max:{value:数字,message:提示}}，省略未指定边界；最多选择数用 selectionLimit 的 {count:整数,message:提示}。不能改成未声明的底层叶子。严格大于0不等于最小值0，宿主未声明严格比较规则时必须澄清或不支持。",
            "textLengthLimit 的 set value 为正整数，清空或重置不携带 value；卡片 before/after 为宿主语义配置快照，由编译器计算，不自行生成。宿主 resolvedProperties 使用 stored、resolvedValue、source。",
            "大一点、加一个规则等存在多种解释时使用 proposal.needs_clarification；宿主未声明的宽度、规则、联动或撤销使用 unsupported，不生成 JS 字符串表达式。",
            "用户明确请求的属性 selected=true，额外建议 selected=false；一行一个完整语义操作，默认值模式和值、权限联动不拆散；before/after、ID 和文案由编译器生成。",
            "独立校验使用 property_changes + form.property.rule，slots 包含目标、operation=add/replace/remove、rule_type、rule_id，add/replace 带 value；必须来自宿主 ruleCatalog，不把任意正则或 rules 数组当成已注册校验。",
            "条件联动使用 property_changes + form.property.linkage，slots 包含目标、operation=add/replace/remove、linkage_type、linkage_id，add/replace 带目录允许的 AST value；字段和选项值均来自真实快照，不输出字符串表达式。",
            "撤销使用 property_undo + form.property.undo，transaction_id 必须取自 history 的当前可撤销事务；不能用旧属性值构造逆向覆盖。",
            "普通删除、移动、插入等保留 result_kind=form_actions、mode=append 和最小动作；此路径插入动作必须给真实 anchorNodeId。",

            "needs_clarification、unsupported、no_change 没有字段或动作时，也必须使用只含一个项目的 plan_items 数组。",
            "form.field.define 只填写 client_ref、component_name、label、name、required、placeholder、options。",
            "首期仅支持 Input、Input.TextArea、DatePicker、TimePicker、NumberPicker、SelectSingle、SelectMulti、CheckboxGroup、Switch。",
            "字段生成支持 Schema 1.0.0 和 1.1.0 的单层 Flow 画布，1.1.0 仍支持原有新增、追加及增量动作。原样保留画布 schemaVersion；动作版本由编译器按本批实际动作协商，不从其他能力借用协议，不将属性动作版本用于新增字段。空白时 replace_empty_form，非空时必须 append；保留已有 ID、name、props、选项和配置。",
            "同一 context 可同时声明字段生成和属性编辑能力；按用户本轮意图选择 result_kind，不因存在 propertyEditing 就把新建表单归为 property_changes。只使用首期组件与宿主目录的交集，不使用目录里其他尚不支持的组件。新增属性优先遵循组件 create.writableProps；Switch 未声明 required 时不要设置必填，不能虚构宿主写入能力。",
            "属性编辑使用新属性协议；其他现有表单编辑使用 form_actions + append，保留未提及字段、ID、name 和布局。",
            "查询必须读取 resolvedProperties 和真实 Schema，区分本地、继承和默认值；查询输出只读，不产生修改动作。撤销必须引用真实 history 事务，不能生成反向覆盖补丁。",
            "本轮上下文包括 resolvedProperties、history 和 capabilities.nodePolicies；保存锁、设备和布局限制不能绕过。最终动作只在宿主声明支持的协议版本下生成。" ,
            "当前组件绑定发送时 selection.nodeId；无选择且目标依赖当前组件时必须澄清。",
            "首期不生成容器、槽位或 Grid 目标；不把 presentation.fields 全量展示快照当作替换画布或保存的数据。",
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
                                "result_kind": "property_changes",
                                "mode": "append",
                            },
                        },
                        {
                            "capability": "form.property.change",
                            "slots": {
                                "use_selection": True,
                                "property": "required",
                                "operation": "set",
                                "value": True,
                                "selected": True,
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
            {
                "input": "在学号后新增监护人字段（currentSchema 中存在唯一标签为学号的字段）",
                "output": {
                    "plan_items": [
                        {
                            "capability": "proposal.begin",
                            "slots": {
                                "summary": "在学号后新增监护人字段。",
                                "result_kind": "form_fields",
                                "mode": "append",
                                "target": {"kind": "relative", "anchorLabel": "学号", "position": "after"},
                            },
                        },
                        {
                            "capability": "form.field.define",
                            "slots": {
                                "client_ref": "guardian",
                                "component_name": "Input",
                                "label": "监护人",
                                "name": "guardian",
                            },
                        },
                    ]
                },
            },
            {
                "input": "这个组件现在是不是必填？",
                "output": {"plan_items": [
                    {"capability": "proposal.begin", "slots": {
                        "summary": "查询当前组件的必填状态。", "result_kind": "property_query"
                    }},
                    {"capability": "form.property.query", "slots": {
                        "use_selection": True, "property": "required"
                    }},
                ]},
            },
            {
                "input": "把它改成大一点（没有说明宽度、字号或组件尺寸）",
                "output": {"plan_items": [
                    {"capability": "proposal.needs_clarification", "slots": {
                        "summary": "需要确认调整对象。",
                        "question": "你希望调整组件尺寸、输入框宽度，还是字体大小？",
                        "choices": ["组件尺寸", "输入框宽度", "字体大小"],
                        "code": "AMBIGUOUS_PROPERTY"
                    }},
                ]},
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
        description="识别属性修改/查询/复制/清空/重置/规则/撤销意图，生成七组件属性勾选提案或单层 Flow 表单字段及增量动作。",
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
