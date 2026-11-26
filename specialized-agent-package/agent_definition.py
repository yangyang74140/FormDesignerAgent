"""单层 Flow 表单 Agent：模型生成受控 IR，Python 编译完整提案。"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import inspect
from typing import Any

from specialized.builder.sdk import create_external_agent
from .form_generation.guidance import (
    PREPARE_STEP, GUIDANCE_STEP, GUIDANCE_CONTRACT, collect_guidance,
)
from .form_generation.proposal import (
    FORM_PROPOSAL_CONTRACT,
    FORM_PROPOSAL_EVENT,
    FORM_PROPOSAL_PIPELINE,
    FORM_PROPOSAL_STEP,
    compile_form_proposal,
    host_context_diagnostic,
    normalize_host_context,
    proposal_capabilities,
)
from .form_generation.contracts import change_enabled

def _step_result(result: Any) -> Any:
    if isinstance(result, Mapping):
        return dict(result)
    # The SDK can return a PipelineStepResult object instead of its dictionary envelope.
    if isinstance(getattr(result, "status", None), str):
        return {
            key: getattr(result, key)
            for key in ("status", "output", "summary", "diagnostics", "error_code", "abort_run", "artifact_ref")
            if hasattr(result, key)
        }
    return result


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
        required_context = ("currentSchema", "capabilities") if property_request or change_enabled(host) else (
            "currentSchema", "capabilities", "supportedActionVersions"
        )
        missing = [key for key in required_context if not host.get(key)]
        if missing and "currentSchema" not in missing:
            return compile_form_proposal({
                "capability": "proposal.unsupported",
                "slots": {
                    "summary": "宿主能力不完整，暂不支持本次操作；缺少：" + "、".join(missing),
                    "code": "HOST_CAPABILITY_REQUIRED",
                },
            }, context)
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
            "abort_run": True,
        }


async def prepare_form_requirement(step_context: Any) -> Any:
    result = await generate_form_proposal(step_context, publish=False)
    if not _completed(result):
        return result
    proposal = result["output"]["form_proposal"]
    if proposal.get("status") == "needs_clarification" and not proposal.get("fieldGuidance") and not proposal.get("clarificationOptions"):
        host = normalize_host_context(step_context)
        missing = [key for key in ("currentSchema", "capabilities", "supportedActionVersions") if not host.get(key)]
        kind = proposal.get("clarificationKind")
        if kind in {None, "field_addition"}:
            if missing:
                return {"status": "failed", "error_code": "form_guidance_host_context_missing",
                        "summary": "宿主上下文或能力缺失：" + "、".join(missing), "abort_run": True}
            result = await generate_form_proposal(step_context, publish=False, user_input={
                "original_request": deepcopy(step_context.inputs),
                "guidance_repair": {
                    "previous_proposal": proposal,
                    "instruction": "仅此一次修复：结合原始请求和真实宿主上下文判定 clarification_kind。字段新增语义未定必须返回完整 field_draft 候选，属性歧义只列对应槽位；属性修改、目标定位、场景需求不得误判为新增字段。能力不足返回 unsupported。不得以普通空选项澄清替代字段引导，也不得把未定需求直接猜成 ready。",
                },
            })
            if not _completed(result):
                return result
            repaired = result["output"]["form_proposal"]
            if (repaired.get("status") not in {"needs_clarification", "unsupported"}
                    or (kind == "field_addition" and repaired.get("status") == "needs_clarification" and not repaired.get("fieldGuidance"))
                    or (repaired.get("status") == "needs_clarification" and not repaired.get("fieldGuidance")
                        and not repaired.get("clarificationOptions") and repaired.get("clarificationKind") in {None, "field_addition"})):
                return {"status": "failed", "error_code": "form_field_guidance_repair_failed",
                        "summary": "字段引导修复未生成有效结构化候选，未生成或应用变更。", "abort_run": True}
    return {
        "status": "completed",
        "output": {"original_input": deepcopy(step_context.inputs),
                   "proposal": result["output"]["form_proposal"],
                   "diagnostics": result.get("diagnostics", [])},
        "diagnostics": result.get("diagnostics", []),
    }


async def generate_confirmed_proposal(step_context: Any) -> Any:
    data = step_context.inputs
    if not isinstance(data, Mapping) or not isinstance(data.get("proposal"), Mapping):
        return {"status": "failed", "error_code": "form_guidance_context_missing", "abort_run": True}
    if "fieldSelection" in data:
        from .form_generation.field_guidance import compile_draft

        draft, selection = data["proposal"].get("fieldGuidance"), data["fieldSelection"]
        if (not isinstance(draft, dict) or not isinstance(selection, dict)
                or selection.get("draftId") != draft.get("draftId")
                or type(selection.get("version")) is not int or not 1 <= selection["version"] <= 4):
            return {"status": "failed", "error_code": "form_field_guidance_stale", "abort_run": True}
        try:
            proposal = compile_draft(draft, selection["fields"], step_context)
        except (ValueError, KeyError, TypeError) as error:
            return {"status": "failed", "error_code": "form_field_guidance_invalid", "summary": str(error), "abort_run": True}
        return await _deliver_proposal(step_context, proposal, data.get("diagnostics", []))
    if "answer" not in data:
        return await _deliver_proposal(step_context, data["proposal"], data.get("diagnostics", []))
    return await generate_form_proposal(step_context, user_input={
        "original_request": data["original_input"], "clarification_answer": data["answer"],
    })


async def generate_form_proposal(step_context: Any, *, publish: bool = True, user_input: Any = None) -> Any:
    """Generate one capability-aware proposal and publish only the final artifact."""
    host_context = normalize_host_context(step_context)
    context_diagnostics = [host_context_diagnostic(step_context, "handler")]

    def compile_with_host_snapshot(ir_payload: Any, context: Any) -> dict[str, Any]:
        trace = host_context_diagnostic(context, "compiler")
        trace["compile_source"] = "handler_snapshot"
        context_diagnostics.append(trace)
        return compile_platform_proposal(ir_payload, host_context)

    result = await step_context.native_capability.generate(
        task=(
            "根据用户请求和宿主快照生成受控 Native Capability IR。"
            "不要直接生成 form-agent.v1 最终提案；Python compiler 会将 IR 编译为最终提案。"
            "无论有一个还是多个项目，根对象都必须且只能是 "
            "{\"plan_items\":[{\"capability\":\"...\",\"slots\":{...}}]}。"
            "禁止直接返回最终提案字段，也禁止使用其他根结构。"
        ),
        input_data={
            "user_input": step_context.inputs if user_input is None else user_input,
            "host_context": deepcopy(host_context),
        },
        allow_plan_items=True,
        max_plan_items=64,
        allowed_capabilities=proposal_capabilities(host_context),
        forbidden_fields=[
            "id", "schema", "form_schema", "javascript", "eval", "sql",
            "dom", "react_state", "local_storage", "primaryKey", "nextValueSeed",
        ],
        compiler=compile_with_host_snapshot,
        output_type="json",
        output_contract=FORM_PROPOSAL_CONTRACT,
        prompt_rules=[
            "只输出严格 JSON，不要输出 Markdown、代码围栏、解释文字或最终 form_proposal。",
            "根对象必须且只能是 {plan_items:[{capability, slots}, ...]}，即使只有一个项目也必须放进 plan_items 数组。",
            "根对象除 plan_items 外不得包含其他字段；不要把 capability、slots、summary、status、fields、actions、presentation、result 或 form_proposal 直接放在根对象。",
            "每个 capability 项目必须同时包含 capability 字符串和 slots 对象，不得省略 slots。",
            "每次必须且只能包含一个 proposal.* 状态项目。",
            "所有 needs_clarification 应提供 clarification_kind：field_addition（已有表单新增字段）、property（修改已有属性）、scenario（场景表单）、target（目标歧义）、other。结合完整语义及宿主上下文判断，不按单个字段关键词分类。添加一个字段属于语义未定，应推荐完整可编译字段而不是空 choices 问名称类型。手机号等明确语义只为真实歧义属性分组，无歧义直接生成；不得猜必填、11位或动态源。",
            "先检查需求是否明确：仅说生成一个审批表单、登记表或管理表单，且没有具体业务用途或明确字段时，必须用 proposal.needs_clarification 引导选择业务场景，不直接猜场景生成字段。",
            "场景引导 slots 使用 summary、question、scenario_options；scenario_options 必须恰好三个互不重复且符合当前语境的具体场景，每项只有 label 和 description。编译器自动添加第四项其他，不同时提供 choices，不生成选项 ID。",
            "例如生成一个审批表单，推荐请假审批表单、采购审批表单、报销审批表单，并说明各自用途；登记、预约等需求必须生成对应语境的推荐，不复用审批菜单。仅推荐表单内容，不承诺审批流程、集成或未授权组件能力。",
            "用户已经说明请假、采购等用途，或给出明确字段清单时直接生成，不重复询问场景；任务是修改属性、移动或删除时不询问表单用途。已有明确要求但能力不足时返回 unsupported，不通过追问或推荐静默省略要求。",
            "收到 original_request 和 clarification_answer 时合并原始需求与当前回答，回答仅补齐或明确纠正对应需求，保留原始约束；不要重复询问已经回答的槽位。回答仍不足或相互冲突时返回 needs_clarification，不猜测剩余关键信息。",
            "已有表单插入字段组合，仅字段槽位有歧义时用 proposal.needs_clarification.slots.field_draft；明确字段要求仍直通，不强制问答。field_draft={prefill:一句话预填,begin:完整proposal.begin槽位,fields:完整form.field.define槽位数组,groups:歧义槽位数组}。begin 必须 result_kind=form_fields、mode=append，保留真实插入位置；其余已明确要求全部保留。",
            "每个歧义组={field:字段0起始下标,slot:类别,reason:真实歧义原因,options:[{label:最终结果短标签,patch:结构化槽位补丁}]}。类别独立：semantics 在语义未定时给出完整 label/name/component_name 以及有依据的 required/placeholder/options；仅称谓歧义可只改 label/name。control 只改 component_name；validation 只改 required；data_source 只改静态 options；properties 只改 placeholder。完整语义候选不能与同字段其他组重复写属性。跨控件残余属性必须通过 patch.unset 显式列出 required/placeholder/options，不能静默清除用户约束；没有用户依据不得清除。不得修改client_ref或增加未知键。基线fields必须可编译，候选只是待确认预填，不表示已接受。",
            "推荐按语境提供3至5个真实可用结果，不足则如实少给或为空；最多20个冻结备选供换一组。label不以选择/设置/配置开头，尽量12至16字且可更短。自定义、保留当前值、重新生成和回退由Agent处理，不生成这些推荐。不根据手机号等名称猜必填、11位、正则或数据源；明确要求不能由这七个字段槽位表达时返回unsupported，不通过引导静默省略。静态options只使用用户或真实宿主提供的label/value；不把动态数据源伪装为静态选项。",
            "目标或属性歧义继续使用 question 和可选 choices；候选只引用真实快照与已支持语义，不为了凑四项虚构目标或能力。宿主上下文缺失不是业务场景缺失，不向用户询问 revision、节点 ID 或能力目录。",
            "宿主 capabilities.supportedProposalContracts 包含 form_change_proposal.v1、supportedPresentationKinds 包含 shared.form-change-confirm 且 capabilities.supportedActionVersions（缺省时读取 context 顶层同名声明）包含 form_change_actions.v1 时，已有表单的混合修改使用 result_kind=form_changes、mode=append；按用户请求顺序交错 form.field.define、既有 form.* 字段动作和 form.property.change。已有表单的纯字段或纯属性修改也编译为统一变更契约；空白新建使用独立的新建契约。",
            "未协商必需的新能力时所有可写路径必须明确 unsupported，不能回退旧卡片或版本、拆批或忽略部分需求。统一变更仅对既有节点使用属性动作；新字段属性只放在已授权的新增 props 中，字段 IR 仍仅支持已声明槽位。查询和撤销维持独立专用路径；属性 rule/linkage 暂无新协议，必须明确 unsupported。",
            "新建完整表单必须使用 plan_items：第一项是 proposal.begin，result_kind=form_fields、mode=replace_empty_form；后续为全部字段各一条 form.field.define。",
            "已有画布只新增字段时，第一项为 proposal.begin，result_kind=form_fields、mode=append；后续仅定义新增的 form.field.define，不重生成已有字段。",
            "append 不指定位置时省略 target，默认在最后一个字段后、尾部非字段组件前追加。混合批次只包含默认追加、删除和互不冲突的属性修改时，用 form_changes 在同一批生成动作，编译器按动作顺序计算位置。用户未指定位置不需要追问。",
            "用户要求修改已有字段的显示名称时更新 label，保留业务字段 name。新增类似「兴趣」的自由填写内容且未指定类型时，可使用宿主已授权的 Input。",
            "在 XX 后/前新增字段时，在 proposal.begin.slots.target 使用 kind=relative、position=after/before，并从 currentSchema 读取 anchorNodeId；也可传原样 anchorLabel 或 anchorName，由编译器唯一匹配。当前字段使用 useSelection=true。",
            "相同锚点的一批新字段按用户描述顺序定义，由编译器计算连续插入下标，不能重复定义已有字段。目标不存在、重名或选择为空时必须澄清，不默认改为末尾追加。",
            "七类组件的属性编辑统一使用 proposal.begin result_kind=property_changes + form.property.change；查询用 property_query + form.property.query；撤销用 property_undo + form.property.undo。属性复制通过 change.operation=copy，不直接复制身份信息。新旧路径不得混用。",
            "每条属性 IR 使用 node_id 或 use_selection=true，也可用 node_label/node_name 唯一定位；property 必须来自宿主 properties 目录。operation=set/clear/unset/reset/copy，set 必须有 value；copy 使用 source_node_id/source_property。",
            "必添/不能为空映射 required；提示文字映射 placeholder；长度上限映射 textLengthLimit，不是 maxLength；标签靠左映射 titleAlign，不是 labelAlign；手机号优先内置 formatValidation。",
            "组件和属性能力缺失时必须明确返回 proposal.unsupported，summary 说明哪项需求暂不支持及缺少的目录、属性或处理器，不得根据常见组件经验猜属性。",
            "用户要求禁用时，不能自行生成 disabled、readOnly、edit=false 或 access，也不能把禁止手工编辑当成禁用。没有明确注册且适用于本操作的禁用语义和写入规则，就说明：暂时还不支持禁用，当前没有已声明的禁用属性及写入规则。",
            "例如生成禁用的姓名字段：姓名应使用 Input；如果禁用能力未声明，返回 unsupported，明确姓名可用 Input 但暂时还不支持禁用。本轮不交付忽略禁用要求的可执行提案；不能声称已完成或静默降级。",
            "form.field.define 仅支持声明的七个槽位；宿主目录提供其他属性也不会自动扩展该 IR。任何用户明确要求但此操作无法表达的属性都要说明暂不支持，不能省略后返回 ready。",
            "属性目录提供值类型、枚举、范围、默认值和操作；开启必填转换 boolean，数字 0 是合法值，文本默认值 1 保留字符串；选项必须保留真实业务 value，不猜序号。",
            "数字上下限优先使用宿主成组 numericRange，value={min:{value:数字,message:提示},max:{value:数字,message:提示}}，省略未指定边界；最多选择数用 selectionLimit 的 {count:整数,message:提示}。不能改成未声明的底层叶子。严格大于0不等于最小值0，宿主未声明严格比较规则时必须澄清或不支持。",
            "textLengthLimit 的 set value 为正整数，清空或重置不携带 value；原状态由编译器写入 action.preconditions.before，新值只在 payload，不输出 after。宿主 resolvedProperties 使用 stored、resolvedValue、source。",
            "大一点、加一个规则等存在多种解释时使用 proposal.needs_clarification；宿主未声明的宽度、规则、联动或撤销使用 unsupported，不生成 JS 字符串表达式。",
            "用户明确请求的属性 selected=true，额外建议 selected=false；一行一个完整语义操作，默认值模式和值、权限联动不拆散；before/after、ID 和文案由编译器生成。",
            "独立校验使用 property_changes + form.property.rule，slots 包含目标、operation=add/replace/remove、rule_type、rule_id，add/replace 带 value；必须来自宿主 ruleCatalog，不把任意正则或 rules 数组当成已注册校验。",
            "条件联动使用 property_changes + form.property.linkage，slots 包含目标、operation=add/replace/remove、linkage_type、linkage_id，add/replace 带目录允许的 AST value；字段和选项值均来自真实快照，不输出字符串表达式。",
            "撤销使用 property_undo + form.property.undo，transaction_id 必须取自 history 的当前可撤销事务；不能用旧属性值构造逆向覆盖。",
            "普通删除、移动、插入等保留 result_kind=form_actions、mode=append 和最小动作；此路径插入动作必须给真实 anchorNodeId。",

            "needs_clarification、unsupported、no_change 没有字段或动作时，也必须使用只含一个项目的 plan_items 数组。",
            "form.field.define 只填写 client_ref、component_name、label、name、required、placeholder、options。",
            "client_ref 在本批及当前画布中唯一，以小写字母开头，其后可用小写字母、数字、下划线或连字符，例如 student_no、student-name；不生成持久化 ID。name 单独遵守宿主 fieldNameRules。",
            "当前任务固定为设计器画布中的表单设计，不询问 Excel、CSV 或文件格式。生成校验失败应保留具体错误，不要求用户重复已明确的字段需求，也不把失败说成已生成或已应用。",
            "首期仅支持 Input、Input.TextArea、DatePicker、TimePicker、NumberPicker、SelectSingle、SelectMulti、CheckboxGroup、Switch。",
            "字段生成支持单层 Flow 画布。Schema 版本仅作元数据，不设白名单，也不要求与当前快照一致；按结构、宿主能力和 Action 契约判断。动作版本只从本批实际动作协商，不借用属性动作版本。空白时 replace_empty_form，非空时必须 append；保留已有 ID、name、props、选项和配置。",
            "同一 context 可同时声明字段生成和属性编辑能力；按用户本轮意图选择 result_kind，不因存在 propertyEditing 就把新建表单归为 property_changes。只使用首期组件与宿主目录的交集。新增属性优先遵循组件 create.writableProps；Switch 未声明 required 时不写入缺省或 false 的 required，明确 true 仍须授权。",
            "属性编辑使用新属性协议；其他现有表单编辑使用 form_actions + append，保留未提及字段、ID、name 和布局。",
            "查询必须读取 resolvedProperties 和真实 Schema，区分本地、继承和默认值；查询输出只读，不产生修改动作。撤销必须引用真实 history 事务，不能生成反向覆盖补丁。",
            "本轮上下文包括 resolvedProperties、history 和 capabilities.nodePolicies；保存锁、设备和布局限制不能绕过。最终动作只在宿主声明支持的协议版本下生成。" ,
            "当前组件绑定发送时 selection.nodeId；无选择且目标依赖当前组件时必须澄清。",
            "首期不生成容器、槽位或 Grid 目标；最终只返回 actions 草稿，presentation 只声明注册 kind 和标题，用户确认后才由宿主应用，不直接替换画布或保存。",
            "字段类型转换只允许明确标记为未保存的新字段；有损转换必须先澄清。",
            "规则和公式只能引用真实字段或本批 clientRef，不得生成 SQL、eval、JavaScript 或未注册函数。",
            "executionResult 为 applied 前只能说已生成提案；applied 也不能声称已保存。conflict 时必须刷新上下文。",
            "不要虚构组件、属性、事件、函数、接口、人员 ID、地区编码或数据库字段。",
        ],
        examples=[
            {
                "input": "创建一份包含姓名和入职日期的员工入职登记表，两项均必填，姓名提示请输入姓名",
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
                "input": "生成一个审批表单",
                "output": {"plan_items": [{
                    "capability": "proposal.needs_clarification",
                    "slots": {
                        "summary": "需要明确审批表单的业务用途。",
                        "question": "你希望生成哪类审批表单？",
                        "scenario_options": [
                            {"label": "请假审批表单", "description": "记录请假类型、起止时间和原因。"},
                            {"label": "采购审批表单", "description": "记录采购物品、数量、预算和用途。"},
                            {"label": "报销审批表单", "description": "记录费用类型、金额和发生日期。"},
                        ],
                    },
                }]},
            },
            {
                "input": "生成一个禁用的姓名字段（宿主没有声明禁用属性和写入规则）",
                "output": {"plan_items": [{
                    "capability": "proposal.unsupported",
                    "slots": {
                        "summary": "姓名字段可使用 Input，但暂时还不支持禁用：当前没有已声明的禁用属性及写入规则。",
                        "code": "UNSUPPORTED_PROPERTY",
                    },
                }]},
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
    context_diagnostics[0]["native_result_type"] = type(result).__name__
    result = _step_result(result)
    native_diagnostics = result.get("diagnostics") if isinstance(result, dict) else None
    diagnostics = [*(native_diagnostics if isinstance(native_diagnostics, list) else []), *context_diagnostics]
    if not _completed(result):
        if isinstance(result, dict):
            if result.get("status") == "failed":
                result["abort_run"] = True
            return {**result, "diagnostics": diagnostics}
        return result
    output = _result_output(result)
    proposal = output.get("form_proposal") if isinstance(output, dict) else None
    if not isinstance(proposal, dict):
        return {
            "status": "failed", "summary": "未得到有效表单提案。",
            "error_code": "form_proposal_missing", "diagnostics": diagnostics, "abort_run": True,
        }
    if not publish:
        return {"status": "completed", "output": {"form_proposal": proposal},
                "summary": proposal.get("summary", ""), "diagnostics": diagnostics}
    return await _deliver_proposal(step_context, proposal, diagnostics)


async def _deliver_proposal(step_context: Any, proposal: Mapping[str, Any], diagnostics: list) -> dict:
    output = {"form_proposal": proposal}
    event_payload = {
        "block_id": "form_proposal",
        "title": "表单设计提案",
        "status": proposal.get("status"),
        "proposal": proposal,
    }
    await _publish_event(step_context, FORM_PROPOSAL_EVENT, event_payload)
    return {
        "status": "completed", "output": output,
        "summary": proposal.get("summary", "表单提案已生成。"), "diagnostics": diagnostics,
    }


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
                "新建时一次性返回包含全部字段的唯一 form.add_component 动作草稿",
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
            key=PREPARE_STEP,
            title="检查表单需求", output_type="json", output_contract=GUIDANCE_CONTRACT,
            handler=prepare_form_requirement, input_from="original_input",
            output_visibility="internal", reasoning_visibility="trace_only", timeout_ms=120000,
        )
        .pipeline_step(
            key=GUIDANCE_STEP,
            title="确认表单需求", output_type="json", output_contract=GUIDANCE_CONTRACT,
            handler=collect_guidance, input_from="previous_step",
            output_visibility="internal", reasoning_visibility="trace_only",
        )
        .pipeline_step(
            key=FORM_PROPOSAL_STEP,
            title="生成表单设计提案",
            running_title="正在检查表单上下文与能力",
            completed_title="表单设计提案已生成",
            failed_title="表单设计提案生成失败",
            output_type="json",
            output_contract=FORM_PROPOSAL_CONTRACT,
            handler=generate_confirmed_proposal,
            input_from="previous_step",
            output_visibility="final_artifact",
            reasoning_visibility="trace_only",
            timeout_ms=120000,
        )
        .output_pipeline(
            key=FORM_PROPOSAL_PIPELINE,
            artifact_kind="form_proposal",
            output_type="json",
            steps=[PREPARE_STEP, GUIDANCE_STEP, FORM_PROPOSAL_STEP],
            final_contract=FORM_PROPOSAL_CONTRACT,
            failure_policy="fail_fast",
        )
        .register()
    )
