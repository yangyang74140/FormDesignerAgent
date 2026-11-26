"""Checkpointed clarification using the platform's existing waiting interface."""

from collections.abc import Mapping
from copy import deepcopy

PREPARE_STEP = "form_requirement_preparation"
GUIDANCE_STEP = "form_requirement_confirmation"
GUIDANCE_CONTRACT = "form_requirement_context.v1"


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
    for key in ("question", "choices", "clarificationOptions"):
        proposal.pop(key, None)
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
            text = selected["label"]
    else:
        text = _value(answer, "text") if _value(answer, "kind") == "text" else None
    if not isinstance(text, str) or not text.strip():
        return {"status": "failed", "error_code": "form_guidance_invalid_answer", "abort_run": True}
    data["answer"] = {"question": proposal["question"], "text": text.strip()}
    return {"status": "completed", "output": data}
