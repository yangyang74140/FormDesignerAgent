"""Checkpointed clarification using the platform's existing waiting interface."""

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json

PREPARE_STEP = "form_requirement_preparation"
GUIDANCE_STEP = "form_requirement_confirmation"
GUIDANCE_CONTRACT = "form_requirement_context.v1"
FORM_CREATION_KIND = "form_creation_required"
FORM_CREATION_OPTIONS = [
    {"id": "create-form", "label": "先准备空白表单，再添加字段", "description": "进入待生成草稿；字段信息不全时逐题澄清，完成后交由宿主确认应用。"},
    {"id": "cancel", "label": "取消", "description": "结束本次需求，不生成表单或字段变更。"},
]


def has_no_form(context):
    schema, canvas = context.get("currentSchema", {}), context.get("canvas", {})
    return schema.get("fields") == [] and canvas.get("isBlank") is True


def form_creation_fingerprint(context):
    return hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def require_form_creation(proposal, context, requirements=None):
    from .field_clarification import freeze_requirements

    result = deepcopy(proposal)
    result.update(
        status="needs_clarification", clarificationKind=FORM_CREATION_KIND,
        summary="当前没有表单实例，需要先确认是否根据本次字段需求生成表单。",
        question="当前还没有表单。是否先生成包含本次字段需求的表单？",
        clarificationOptions=deepcopy(FORM_CREATION_OPTIONS),
        formCreationFingerprint=form_creation_fingerprint(context),
        diagnostics=[{"code": "FORM_CREATION_REQUIRED", "message": "尚未确认生成表单，未生成或应用字段变更。"}],
    )
    result["fieldClarification"] = freeze_requirements(
        requirements, result["proposalId"], result["formCreationFingerprint"])
    result["fieldClarification"]["resumeFingerprint"] = form_creation_fingerprint({**context, "requestId": ""})
    return result


def scenario_options(value):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("场景引导必须提供三个具体推荐项，其他入口由编译器添加")
    options = []
    labels = set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, Mapping) or set(item) != {"label", "description"}:
            raise ValueError("场景推荐项只允许 label 和 description")
        label, description = item["label"], item["description"]
        if not isinstance(label, str) or not label.strip() or not isinstance(description, str) or not description.strip():
            raise ValueError("场景推荐标题与说明必须为非空文本")
        label = label.strip()
        if label in labels or "其他" in label:
            raise ValueError("场景推荐项不得重复或占用其他入口")
        labels.add(label)
        options.append({"id": f"scenario-{index}", "label": label, "description": description.strip()})
    return options + [{"id": "other", "label": "其他", "description": "补充你需要的具体场景或用途。"}]


def _value(answer, key):
    return answer.get(key) if isinstance(answer, Mapping) else getattr(answer, key, None)


def _cancelled(data):
    result = deepcopy(data)
    proposal = result["proposal"]
    for key in ("question", "choices", "clarificationOptions", "formCreationFingerprint", "fieldClarification"):
        proposal.pop(key, None)
    result.pop("formCreationConfirmation", None)
    result.pop("answer", None)
    proposal.update(status="no_change", summary="已取消本次引导，未生成或应用变更。", diagnostics=[])
    return {"status": "completed", "output": result}


async def collect_guidance(context):
    data = deepcopy(context.inputs)
    if not isinstance(data, dict) or not isinstance(data.get("proposal"), dict):
        return {"status": "failed", "error_code": "form_guidance_context_missing", "abort_run": True}
    proposal = data["proposal"]
    if proposal.get("status") == "needs_clarification" and "fieldGuidance" in proposal:
        from .field_guidance import collect_field_guidance
        return await collect_field_guidance(context, data)
    if proposal.get("status") != "needs_clarification":
        return {"status": "completed", "output": data}
    # Integration failures need a fresh host request, not a business answer.
    if any(item.get("code") == "HOST_CONTEXT_REQUIRED" for item in proposal.get("diagnostics", [])):
        return {"status": "completed", "output": data}
    request = getattr(getattr(context, "clarification", None), "request", None)
    if not callable(request):
        return {"status": "completed", "output": data}
    if proposal.get("clarificationKind") == FORM_CREATION_KIND:
        answer = await request(
            key="form_creation_confirmation", question=proposal["question"],
            options=deepcopy(FORM_CREATION_OPTIONS), allow_free_text=False, max_rounds=128,
        )
        if _value(answer, "kind") == "cancelled" or (
                _value(answer, "kind") == "selected" and _value(answer, "selected_option_id") == "cancel"):
            return _cancelled(data)
        if _value(answer, "kind") != "selected" or _value(answer, "selected_option_id") != "create-form":
            return {"status": "failed", "error_code": "form_creation_invalid_answer", "abort_run": True}
        data["formCreationConfirmation"] = {
            "proposalId": proposal["proposalId"], "hostFingerprint": proposal["formCreationFingerprint"],
        }
        return {"status": "completed", "output": data}
    options = proposal.get("clarificationOptions") or [
        {"id": f"choice-{index}", "label": label}
        for index, label in enumerate(proposal.get("choices", []), 1)
    ]
    answer = await request(
        key="form_requirement", question=proposal["question"],
        options=options or None, allow_free_text=True, max_rounds=3,
    )
    if _value(answer, "kind") == "cancelled":
        return _cancelled(data)
    if _value(answer, "kind") == "selected":
        selected = next((item for item in options if item["id"] == _value(answer, "selected_option_id")), None)
        if selected is None:
            return {"status": "failed", "error_code": "form_guidance_invalid_option", "abort_run": True}
        if selected["id"] == "other":
            answer = await request(
                key="form_requirement_other", question="请描述你需要的具体场景或用途。",
                options=None, allow_free_text=True, max_rounds=3,
            )
            if _value(answer, "kind") == "cancelled":
                return _cancelled(data)
            text = _value(answer, "text") if _value(answer, "kind") == "text" else None
        else:
            description = selected.get("description")
            text = f'{selected["label"]}：{description}' if description else selected["label"]
    else:
        text = _value(answer, "text") if _value(answer, "kind") == "text" else None
    if not isinstance(text, str) or not text.strip():
        return {"status": "failed", "error_code": "form_guidance_invalid_answer", "abort_run": True}
    data["answer"] = {"question": proposal["question"], "text": text.strip()}
    return {"status": "completed", "output": data}
