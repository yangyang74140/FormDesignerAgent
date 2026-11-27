"""Replayable, single-question collection of partial fields in a creation draft."""

from copy import deepcopy
import hashlib
import json
import re

from .components import FLOW_COMPONENTS, OPTION_COMPONENTS
from .host import CapabilityUnavailable, component_names, writable_props

MAX_ROUNDS = 128
MAX_QUESTIONS = 120
FIELD_KEYS = {"client_ref", "name", "label", "component_name", "required", "placeholder", "options"}
COMPONENT_LABELS = {
    "Input": "单行输入框", "Input.TextArea": "多行输入框", "DatePicker": "日期",
    "TimePicker": "时间", "NumberPicker": "数字", "SelectSingle": "下拉单选",
    "SelectMulti": "下拉多选", "CheckboxGroup": "复选框组", "Switch": "开关",
}
ALIASES = {**{v: k for k, v in COMPONENT_LABELS.items()}, **{k: k for k in FLOW_COMPONENTS},
           "输入框": "Input", "文本框": "Input", "单选": "SelectSingle", "多选": "SelectMulti"}
VAGUE = {"随便", "随便一个框", "普通的", "就普通的", "都行", "不知道", "字段", "一个字段", "生成一个字段", "新增一个字段"}
LATER = {"先这样", "先这样，剩下我后面在设计器改", "剩下我后面在设计器改", "后面我自己改"}
PAUSE = {"暂停", "先把上一个字段放一放", "先把这个字段放一放"}


def requirements_schema():
    return {"type": "object", "additionalProperties": False, "required": ["fields"], "properties": {
        "fields": {"type": "array", "minItems": 1, "maxItems": 20, "items": {
            "type": "object", "additionalProperties": False, "properties": {
                **{k: {"type": "string"} for k in FIELD_KEYS - {"required", "options"}},
                "required": {"type": "boolean"},
                "options": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                    "required": ["label", "value"], "properties": {"label": {"type": "string"}, "value": {"type": "string"}}}},
            },
        }},
        "unsupported_reason": {"type": "string"},
    }}


def validate_fields(fields):
    if not isinstance(fields, list) or not 1 <= len(fields) <= 20:
        raise ValueError("待澄清字段必须为1至20个部分字段对象")
    for field in fields:
        if not isinstance(field, dict) or set(field) - FIELD_KEYS:
            raise ValueError("待澄清字段只能使用已支持的七个字段槽位")
        for key, value in field.items():
            if key == "required":
                valid = type(value) is bool
            elif key == "options":
                valid = isinstance(value, list) and all(
                    isinstance(o, dict) and set(o) == {"label", "value"}
                    and all(isinstance(v, str) and v.strip() for v in o.values()) for o in value)
            else:
                valid = isinstance(value, str) and bool(value.strip())
            if not valid:
                raise ValueError(f"待澄清字段值非法: {key}")


def freeze_requirements(value, proposal_id, fingerprint):
    value = {"fields": [{}]} if value is None else value
    if not isinstance(value, dict) or set(value) - {"fields", "unsupported_reason"}:
        raise ValueError("field_requirements 必须包含部分 fields 和可选 unsupported_reason")
    validate_fields(value.get("fields"))
    reason = value.get("unsupported_reason", "")
    if not isinstance(reason, str):
        raise ValueError("unsupported_reason 必须为文本")
    fields = deepcopy(value["fields"])
    return {"draftId": proposal_id + ":fields", "hostFingerprint": fingerprint,
            "fields": fields, "deferred": [[] for _ in fields], "unsupportedReason": reason,
            "status": "awaiting_confirmation", "isClarifyingField": False, "hasCurrentForm": False,
            "draftFormSchema": {"fields": []}, "round": 0, "queuedRequests": []}


def available_components(host):
    result = []
    for component in FLOW_COMPONENTS:
        if component not in component_names(host.get("capabilities")):
            continue
        try:
            writable = writable_props(component, host.get("capabilities"), creation=True)
        except CapabilityUnavailable:
            continue
        minimum = {"name", "label"} | ({"options"} if component in OPTION_COMPONENTS else set())
        if minimum <= writable:
            result.append(component)
    return result


def _slot(field, deferred, host):
    for key in ("label", "component_name"):
        if key not in field:
            return key
    writable = writable_props(field["component_name"], host.get("capabilities"), creation=True)
    if field["component_name"] in OPTION_COMPONENTS and not field.get("options"):
        return "options"
    for key in ("required", "placeholder"):
        if key == "placeholder" and field["component_name"] == "Switch":
            continue
        if key in writable and key not in field and key not in deferred:
            return key
    return None


def _question(field, slot, components):
    label = field.get("label", "待新增字段")
    if slot == "label":
        return "这个字段的展示名称是什么？请只填写名称，例如“姓名”。", []
    if slot == "component_name":
        return f'“{label}”使用哪种组件类型？请选择具体类型，“普通的”不会被默认为输入框。', [
            {"id": "component:" + c, "label": COMPONENT_LABELS[c]} for c in components]
    if slot == "options":
        return f'“{label}”有哪些选项？请填写显示名=业务值，每行一项；也可提交 label/value 对象数组。业务值不能猜测。', []
    if slot == "required":
        return f'“{label}”是否必填？', [{"id": "required:yes", "label": "必填"}, {"id": "required:no", "label": "非必填"}]
    return f'“{label}”的占位提示文字是什么？可以选择稍后编辑。', []


def _parse(slot, text, components):
    if text in VAGUE or not text:
        raise ValueError("还不能确定具体值，请填写明确内容或选择候选。")
    if slot == "component_name":
        if text in {"上传", "上传组件", "文件上传", "日期时间", "日期时间选择器", "Upload", "DateTimePicker"}:
            raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", "当前新增字段契约暂不支持该组件：" + text)
        component = ALIASES.get(text)
        if component is None:
            raise ValueError("请选择本题列出的具体组件；未开放的组件不能用输入框替代。")
        if component not in components:
            raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", f"宿主未授权新增组件 {component}。")
        return component
    if slot == "required":
        if text in {"是", "必填", "true"}:
            return True
        if text in {"否", "非必填", "false", "不必填"}:
            return False
        raise ValueError("请明确选择必填或非必填，也可以稍后编辑。")
    if slot == "options":
        if text.startswith("["):
            options = json.loads(text)
        else:
            pairs = [part.strip().split("=", 1) for part in re.split(r"[\n;；]", text) if part.strip()]
            if not pairs or any(len(pair) != 2 for pair in pairs):
                raise ValueError("请同时提供每个选项的显示名称和真实业务值，例如 在职=employee。")
            options = [{"label": label.strip(), "value": value.strip()} for label, value in pairs]
        validate_fields([{"options": options}])
        if not options or len({o["value"] for o in options}) != len(options):
            raise ValueError("选项不能为空且业务值不能重复。")
        return options
    return text


def _value(answer, key):
    return answer.get(key) if isinstance(answer, dict) else getattr(answer, key, None)


def _hold(data, state, summary):
    state = deepcopy(state)
    state["originalRequest"] = deepcopy(data["original_input"])
    result = deepcopy(data)
    result.pop("formCreationConfirmation", None)
    result["proposal"].update(status="needs_clarification", clarificationKind="field_metadata",
                              summary=summary, fieldClarification=deepcopy(state))
    for key in ("question", "choices", "clarificationOptions"):
        result["proposal"].pop(key, None)
    result["proposal"]["diagnostics"] = [{"code": "FIELD_METADATA_PENDING", "message": summary}]
    return {"status": "completed", "output": result}


def resume_requirements(proposal, host):
    from .guidance import FORM_CREATION_KIND, FORM_CREATION_OPTIONS, form_creation_fingerprint, has_no_form

    if (not isinstance(proposal, dict) or proposal.get("status") != "needs_clarification"
            or proposal.get("clarificationKind") != "field_metadata"
            or any(key in proposal for key in ("actions", "presentation", "mode", "actionVersion"))):
        raise ValueError("恢复需要上次未完成的字段澄清提案")
    state = deepcopy(proposal.get("fieldClarification"))
    if (not isinstance(state, dict) or state.get("status") not in {"paused", "incomplete", "collecting"}
            or "originalRequest" not in state
            or state.get("resumeFingerprint") != form_creation_fingerprint({**host, "requestId": ""})
            or not has_no_form(host)):
        raise ValueError("待澄清草稿或宿主快照已失效，不能恢复")
    validate_fields(state["fields"])
    if (not isinstance(state.get("deferred"), list) or len(state["deferred"]) != len(state["fields"])
            or any(not isinstance(keys, list) or any(key not in {"required", "placeholder"} for key in keys)
                   for keys in state["deferred"])):
        raise ValueError("恢复草稿的延后属性记录非法")
    state.update(round=0, status="awaiting_confirmation", isClarifyingField=False,
                 hostFingerprint=form_creation_fingerprint(host))
    result = deepcopy(proposal)
    result["requestId"] = host.get("requestId", "")
    result.update(clarificationKind=FORM_CREATION_KIND, fieldClarification=state,
                  question="是否恢复上次待生成草稿，继续逐题补齐字段信息？",
                  clarificationOptions=deepcopy(FORM_CREATION_OPTIONS),
                  formCreationFingerprint=state["hostFingerprint"])
    return {"status": "completed", "output": {"original_input": deepcopy(state["originalRequest"]),
            "proposal": result, "diagnostics": []}}


def compile_collected(state, context):
    from .proposal import compile_form_proposal, normalize_host_context
    from .guidance import form_creation_fingerprint

    host = normalize_host_context(context)
    if state.get("hostFingerprint") != form_creation_fingerprint(host):
        raise ValueError("宿主快照已变化，请基于最新画布恢复字段澄清")
    validate_fields(state["fields"])
    if state.get("status") != "complete":
        raise ValueError("字段澄清尚未完成，不能生成提案")
    fields = deepcopy(state["fields"])
    names, refs = {f["name"] for f in fields if "name" in f}, {f["client_ref"] for f in fields if "client_ref" in f}
    for index, field in enumerate(fields):
        if not field.get("label") or not field.get("component_name"):
            raise ValueError("至少确认字段名称与组件类型后才能生成，不能猜测缺失元信息")
        if field["component_name"] in OPTION_COMPONENTS and not field.get("options"):
            raise ValueError("选项组件必须先提供真实选项，不生成空选项字段")
        for key, used in (("name", names), ("client_ref", refs)):
            if key not in field:
                number = index + 1
                while f"field_{number}" in used or f"field_{number}" in host.get("fieldNameRules", {}).get("reserved", []):
                    number += 1
                field[key] = f"field_{number}"
                used.add(field[key])
    result = compile_form_proposal({"plan_items": [
        {"capability": "proposal.begin", "slots": {"summary": "已根据逐题确认的信息生成表单提案。", "request_intent": "field_change",
                                                    "result_kind": "form_fields", "mode": "replace_empty_form"}},
        *[{"capability": "form.field.define", "slots": f} for f in fields],
    ]}, host, form_creation_confirmed=True, preserve_unspecified_properties=True)
    proposal = result["output"]["form_proposal"]
    if proposal["status"] == "ready" and any(state["deferred"]):
        proposal["summary"] += " 部分属性待后续在设计器编辑，未推断其值。"
    if state.get("queuedRequests"):
        proposal["summary"] += " 另有待处理需求（尚未执行）：" + "；".join(state["queuedRequests"])
    return proposal


async def collect_field_metadata(context, data):
    from .proposal import normalize_host_context
    from .guidance import _cancelled, form_creation_fingerprint

    state = deepcopy(data["proposal"]["fieldClarification"])
    host = normalize_host_context(context)
    try:
        if state["hostFingerprint"] != form_creation_fingerprint(host):
            raise ValueError("宿主快照已变化，请重新发起字段需求")
        validate_fields(state["fields"])
        if state["unsupportedReason"]:
            state.update(status="unsupported", isClarifyingField=False)
            result = _hold(data, state, state["unsupportedReason"])
            result["output"]["proposal"].update(status="unsupported", diagnostics=[{
                "code": "UNSUPPORTED_FIELD_REQUIREMENT", "message": state["unsupportedReason"]}])
            return result
        components = available_components(host)
        if not components:
            raise CapabilityUnavailable("MISSING_COMPONENT_CATALOG", "没有同时具备新增属性授权的可用组件，无法继续字段澄清。")
        for field in state["fields"]:
            if "component_name" in field and field["component_name"] not in components:
                raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", "所需组件当前不能新增：" + field["component_name"])
        request = getattr(getattr(context, "clarification", None), "request", None)
        state.update(status="collecting", isClarifyingField=True)
        error, switching = "", None
        for turn in range(MAX_QUESTIONS + 1):
            index = next((i for i, f in enumerate(state["fields"]) if _slot(f, state["deferred"][i], host)), None)
            if index is None:
                state.update(status="complete", isClarifyingField=False)
                proposal = compile_collected(state, context)
                result = deepcopy(data)
                result["proposal"] = proposal
                result.pop("formCreationConfirmation", None)
                return {"status": "completed", "output": result}
            if turn == MAX_QUESTIONS:
                break
            state["pendingIndex"] = index
            field = state["fields"][index]
            slot = _slot(field, state["deferred"][index], host)
            question, options = _question(field, slot, components)
            options += [{"id": "later", "label": "剩下稍后编辑"}, {"id": "pause", "label": "暂停当前字段"}, {"id": "cancel", "label": "取消本次需求"}]
            if switching is not None:
                question, options = "还在收集上一个字段的信息，是否先完成这个字段？", [
                    {"id": "continue", "label": "先完成当前字段"}, {"id": "pause", "label": "暂停并保留新需求"}, {"id": "cancel", "label": "取消本次需求"}]
            state["round"] += 1
            state["question"], state["options"] = question, deepcopy(options)
            if not callable(request):
                return _hold(data, state, "字段信息尚未补齐，当前环境缺少原生澄清入口。")
            key = state["draftId"] + ":" + hashlib.sha256(json.dumps(
                [state["round"], index, slot, field, switching, error], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
            answer = await request(key=key, question=(error + "\n" if error else "") + question,
                                   options=options, allow_free_text=switching is None, max_rounds=MAX_ROUNDS)
            if form_creation_fingerprint(normalize_host_context(context)) != state["hostFingerprint"]:
                raise ValueError("回答期间宿主快照已变化，不能继续生成")
            kind, selected = _value(answer, "kind"), _value(answer, "selected_option_id")
            if kind == "cancelled" or (kind == "selected" and selected == "cancel"):
                result = _cancelled(data)
                result["output"]["proposal"].pop("fieldClarification", None)
                return result
            if kind == "exhausted":
                state.update(status="paused", isClarifyingField=False)
                return _hold(data, state, "平台澄清轮次已耗尽，已保留待补齐字段；未生成或应用变更。")
            if kind == "selected" and selected not in {o["id"] for o in options}:
                raise ValueError("选项不属于当前字段问题，不能使用旧问题答案")
            text = _value(answer, "text") if kind == "text" else ""
            if not isinstance(text, str):
                raise ValueError("字段回答必须是文本或本题选项")
            text = text.strip().rstrip("。")
            if (selected == "pause" or text in PAUSE
                    or re.match(r"^先把(上一个|这个)字段放一放[，,]", text)):
                state.update(status="paused", isClarifyingField=False)
                if re.match(r"^先把(上一个|这个)字段放一放[，,]", text):
                    state["queuedRequests"].append(re.split("[，,]", text, maxsplit=1)[1])
                return _hold(data, state, "已暂停并保留当前字段草稿；尚未创建表单或写入字段，新需求须携带最新上下文处理。")
            if switching is not None:
                if kind != "selected" or selected != "continue":
                    raise ValueError("请先决定是否完成当前字段")
                switching, error = None, ""
                continue
            if kind == "text" and re.match(r"^(新增|添加|再加|修改|更改|删除|调整).*(字段|表单|标题)", text):
                state["queuedRequests"].append(text)
                switching, error = text, ""
                continue
            if selected == "later" or text in LATER:
                if slot in {"label", "component_name", "options"}:
                    state.update(status="incomplete", isClarifyingField=False)
                    return _hold(data, state, "已停止追问并保留草稿；缺少名称、具体组件类型或真实选项时不能安全生成字段，请补齐后继续。")
                for remaining in range(index, len(state["fields"])):
                    state["deferred"][remaining] = sorted(set(state["deferred"][remaining]) | {"required", "placeholder"})
                if any(_slot(f, state["deferred"][i], host) in {"label", "component_name", "options"}
                       for i, f in enumerate(state["fields"])):
                    state.update(status="incomplete", isClarifyingField=False)
                    return _hold(data, state, "已停止追问并保留草稿；其他待新增字段仍缺少必需信息，不能猜测生成。")
                error = ""
                continue
            if kind == "selected":
                text = selected.removeprefix("component:") if selected.startswith("component:") else {
                    "required:yes": "true", "required:no": "false"}.get(selected, "")
            elif kind != "text":
                raise ValueError("字段回答类型不合法")
            try:
                value = _parse(slot, text, components)
                candidate = deepcopy(field)
                candidate[slot] = value
                validate_fields([candidate])
                if slot == "options":
                    from .proposal import _normalize_options
                    _normalize_options(value, host)
                state["fields"][index] = candidate
                error = ""
            except CapabilityUnavailable:
                raise
            except (ValueError, TypeError) as exc:
                error = str(exc)
        state.update(status="paused", isClarifyingField=False)
        return _hold(data, state, "已保留字段草稿，达到本轮安全轮次预算；未生成或应用变更，请继续补齐。")
    except CapabilityUnavailable as exc:
        state.update(status="unsupported", isClarifyingField=False)
        result = _hold(data, state, str(exc))
        result["output"]["proposal"].update(status="unsupported", diagnostics=[{"code": exc.code, "message": str(exc)}])
        return result
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "failed", "error_code": "field_metadata_invalid", "summary": str(exc), "abort_run": True}
