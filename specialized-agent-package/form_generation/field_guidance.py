"""Frozen field-slot drafts transported by the documented clarification facade."""

from copy import deepcopy
import hashlib
import json

SLOT_KEYS = {
    "semantics": {"label", "name", "component_name", "required", "placeholder", "options"},
    "control": {"component_name"},
    "validation": {"required"},
    "data_source": {"options"},
    "properties": {"placeholder"},
}
SLOT_LABELS = dict(zip(SLOT_KEYS, ("字段语义", "控件类型", "校验", "数据来源", "字段属性")))


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def _value(answer, key):
    return answer.get(key) if isinstance(answer, dict) else getattr(answer, key, None)


def _patch(fields, group, patch):
    slot = group["slot"]
    if not isinstance(patch, dict) or not patch or set(patch) - SLOT_KEYS[slot] - {"unset"}:
        raise ValueError("自定义值必须是当前槽位的非空 JSON 对象，不支持的要求不能省略")
    unset = patch.get("unset", [])
    removable = {"required", "placeholder", "options"} if slot in {"semantics", "control"} else SLOT_KEYS[slot]
    if (not isinstance(unset, list) or any(not isinstance(k, str) for k in unset)
            or len(set(unset)) != len(unset) or set(unset) - removable or set(unset) & set(patch)):
        raise ValueError("unset 必须显式列出当前槽位可清除的属性，且不能同时设置")
    values = {k: v for k, v in patch.items() if k != "unset"}
    if not values and not unset:
        raise ValueError("补丁不能为空")
    if slot == "semantics":
        if not set(values) & {"label", "name"}:
            raise ValueError("语义候选必须包含字段名称")
        if (set(values) - {"label", "name"} or unset) and not {"label", "name", "component_name"} <= set(values):
            raise ValueError("完整语义候选必须同时给出 label/name/component_name")
    for key, value in values.items():
        if key == "required":
            valid = type(value) is bool
        elif key == "options":
            valid = isinstance(value, list) and all(
                isinstance(item, dict) and set(item) == {"label", "value"}
                and all(isinstance(item[k], str) and item[k].strip() for k in item)
                for item in value
            )
        else:
            valid = isinstance(value, str) and bool(value.strip())
        if not valid:
            raise ValueError(f"槽位值类型或内容不合法: {key}")
    result = deepcopy(fields)
    for key in unset:
        result[group["field"]].pop(key, None)
    result[group["field"]].update(deepcopy(values))
    return result


def _validate_fields(fields):
    if not isinstance(fields, list) or not fields or not all(isinstance(field, dict) for field in fields):
        raise ValueError("字段草稿必须为非空对象数组")
    for field in fields:
        required = {"client_ref", "component_name", "label", "name"}
        if not required <= set(field) or set(field) - required - {"required", "placeholder", "options"}:
            raise ValueError("字段草稿只能包含既有七个字段槽位，明确要求无法表达时必须拒绝")
        if any(not isinstance(field[k], str) or not field[k].strip() for k in required):
            raise ValueError("字段身份、名称、标签及类型必须是非空文本")
        for slot, keys in SLOT_KEYS.items():
            patch = {k: v for k, v in field.items() if k in keys}
            if patch:
                _patch([field], {"field": 0, "slot": slot}, patch)
        if "options" in field:
            from .components import OPTION_COMPONENTS
            if field["component_name"] not in OPTION_COMPONENTS:
                raise ValueError("非选项组件不能携带或丢弃 options")


def compile_draft(draft, fields, host):
    from .proposal import compile_form_proposal, normalize_host_context

    if draft["hostFingerprint"] != _digest(normalize_host_context(host)):
        raise ValueError("宿主快照已变化，请基于最新画布重新生成字段引导")
    _validate_fields(fields)
    result = compile_form_proposal({"plan_items": [
        {"capability": "proposal.begin", "slots": deepcopy(draft["begin"])},
        *({"capability": "form.field.define", "slots": deepcopy(field)} for field in fields),
    ]}, host)
    proposal = result.get("output", {}).get("form_proposal", {})
    if proposal.get("status") != "ready":
        raise ValueError(proposal.get("summary") or result.get("summary") or "字段组合不能编译")
    return proposal


def freeze_draft(value, host):
    from .proposal import normalize_host_context

    if not isinstance(value, dict) or set(value) != {"prefill", "begin", "fields", "groups"}:
        raise ValueError("字段引导必须包含 prefill/begin/fields/groups")
    if not isinstance(value["prefill"], str) or not value["prefill"].strip():
        raise ValueError("字段引导需要一句话预填")
    begin = value["begin"]
    if (not isinstance(begin, dict) or begin.get("mode") != "append"
            or begin.get("result_kind") != "form_fields"
            or set(begin) - {"mode", "result_kind", "summary", "title", "target"}):
        raise ValueError("字段引导仅支持已有表单 form_fields + append")
    normalized = normalize_host_context(host)
    if not normalized.get("currentSchema", {}).get("fields"):
        raise ValueError("字段引导需要已有表单")
    fields, groups = value["fields"], value["groups"]
    if not isinstance(fields, list) or not fields or not all(isinstance(f, dict) for f in fields):
        raise ValueError("字段草稿不能为空")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 20:
        raise ValueError("仅为歧义槽位提供分组，最多20组")
    draft = deepcopy(value)
    draft.update(hostFingerprint=_digest(normalized), version=1)
    draft["draftId"] = "field-" + _digest(draft)
    compile_draft(draft, fields, host)
    seen = set()
    claimed = {}
    for group in groups:
        if (not isinstance(group, dict) or set(group) != {"field", "slot", "reason", "options"}
                or type(group["field"]) is not int or not 0 <= group["field"] < len(fields)
                or not isinstance(group["slot"], str) or group["slot"] not in SLOT_KEYS or not isinstance(group["reason"], str)
                or not group["reason"].strip()):
            raise ValueError("槽位组需要有效字段下标、槽位类别及歧义原因")
        identity = (group["field"], group["slot"])
        if identity in seen:
            raise ValueError("同一字段同一槽位不得重复分组")
        seen.add(identity)
        options = group["options"]
        if not isinstance(options, list) or len(options) > 20:
            raise ValueError("候选必须为数组，最多20项；不足时不虚构")
        labels, patches = set(), set()
        writes = set() if group["slot"] == "semantics" else set(SLOT_KEYS[group["slot"]])
        for option in options:
            if not isinstance(option, dict) or set(option) != {"label", "patch"}:
                raise ValueError("推荐项必须有 label 和结构化 patch")
            label = option["label"]
            if (not isinstance(label, str) or not label.strip() or label != label.strip() or len(label) > 16
                    or label.startswith(("选择", "设置", "配置")) or label in labels
                    or label in {"自定义", "保留当前值"}):
                raise ValueError("推荐标签应为16字以内的最终结果且不得重复")
            fingerprint = _digest(option["patch"])
            if fingerprint in patches:
                raise ValueError("推荐值不得重复")
            labels.add(label)
            patches.add(fingerprint)
            compile_draft(draft, _patch(fields, group, option["patch"]), host)
            writes.update(set(option["patch"]) - {"unset"})
            writes.update(option["patch"].get("unset", []))
        if writes & claimed.get(group["field"], set()):
            raise ValueError("完整语义候选与属性分组不能同时修改同一槽位")
        claimed.setdefault(group["field"], set()).update(writes)
    return draft


def _questions(draft, fields, confirmed, version, offset):
    questions, mappings = [], {}
    prefix = f'{draft["draftId"]}:v{version}'
    for index, group in enumerate(draft["groups"]):
        question_id = f"{prefix}:g{index}"
        candidates = group["options"]
        rotated = candidates[offset % len(candidates):] + candidates[:offset % len(candidates)] if candidates else []
        options, mapping = [], {}
        for number, candidate in enumerate(rotated[:5]):
            option_id = f"{question_id}:o{number}"
            options.append({"id": option_id, "label": candidate["label"]})
            mapping[option_id] = candidate["patch"]
        if index in confirmed:
            option_id = f"{question_id}:keep"
            options.append({"id": option_id, "label": "保留当前值"})
            keys = SLOT_KEYS[group["slot"]]
            if group["slot"] == "semantics":
                keys = {"label", "name"} | {k for option in candidates for k in option["patch"] if k != "unset"}
            mapping[option_id] = {k: v for k, v in fields[group["field"]].items() if k in keys}
        options.append({"id": f"{question_id}:custom", "label": "自定义"})
        mapping[f"{question_id}:custom"] = None
        questions.append({"id": question_id, "question": (
            f'{draft["prefill"]}\n可改点：{fields[group["field"]]["label"]} · {SLOT_LABELS[group["slot"]]}。'
            f'{group["reason"]} 当前值：' + json.dumps(
                {k: v for k, v in fields[group["field"]].items() if k in SLOT_KEYS[group["slot"]]}, ensure_ascii=False)
            + "。自定义可直接填写此槽位 JSON 对象。"),
            "options": options, "allow_free_text": True})
        mappings[question_id] = (index, group, mapping)
    return questions, mappings


async def collect_field_guidance(context, data):
    draft = data["proposal"]["fieldGuidance"]
    facade = getattr(context, "clarification", None)
    if not callable(getattr(facade, "request_group", None)) or not callable(getattr(facade, "request", None)):
        return {"status": "completed", "output": data}
    try:
        compile_draft(draft, draft["fields"], context)
        fields, confirmed, history = deepcopy(draft["fields"]), set(), []
        offset = 0
        for version in range(1, 5):
            questions, mappings = _questions(draft, fields, confirmed, version, offset)
            prefix = f'{draft["draftId"]}:v{version}'
            answer = await facade.request_group(key=prefix, questions=questions, max_rounds=16)
            if _value(answer, "kind") == "cancelled":
                return _cancel(data)
            answers = _value(answer, "answers")
            if _value(answer, "kind") != "group" or not isinstance(answers, dict) or set(answers) != set(mappings):
                raise ValueError("字段回答必须匹配冻结草稿身份、版本及完整分组")
            pending, custom = {}, []
            for question_id, (index, group, mapping) in mappings.items():
                item = answers[question_id]
                kind = _value(item, "kind")
                if kind == "text":
                    pending[index] = json.loads(_value(item, "text"))
                elif kind == "selected" and _value(item, "selected_option_id") in mapping:
                    patch = mapping[_value(item, "selected_option_id")]
                    if patch is None:
                        custom.append({"id": question_id, "question": f'{SLOT_LABELS[group["slot"]]}自定义 JSON，支持键：' + ", ".join(sorted(SLOT_KEYS[group["slot"]])), "allow_free_text": True})
                    else:
                        pending[index] = patch
                else:
                    raise ValueError("候选不属于当前草稿版本，或回答类型不合法")
            if custom:
                custom_answer = await facade.request_group(key=prefix + ":custom", questions=custom, max_rounds=16)
                if _value(custom_answer, "kind") == "cancelled":
                    return _cancel(data)
                values = _value(custom_answer, "answers")
                if _value(custom_answer, "kind") != "group" or not isinstance(values, dict) or set(values) != {q["id"] for q in custom}:
                    raise ValueError("自定义回答必须包含全部待补充槽位")
                for question_id, item in values.items():
                    if _value(item, "kind") != "text":
                        raise ValueError("自定义值必须为结构化 JSON 文本")
                    pending[mappings[question_id][0]] = json.loads(_value(item, "text"))
            candidate = deepcopy(fields)
            writes = {}
            for index, patch in pending.items():
                group = draft["groups"][index]
                candidate = _patch(candidate, group, patch)
                keys = (set(patch) - {"unset"}) | set(patch.get("unset", []))
                if keys & writes.get(group["field"], set()):
                    raise ValueError("同一字段的分组回答存在重叠修改，不能覆盖用户约束")
                writes.setdefault(group["field"], set()).update(keys)
            compile_draft(draft, candidate, context)
            history.append((deepcopy(fields), set(confirmed)))
            fields, confirmed = candidate, confirmed | set(pending)
            control = await facade.request(
                key=prefix + ":review", question="字段组合已整体复验，仅生成待确认提案。" + json.dumps(fields, ensure_ascii=False),
                options=[{"id": prefix + ":confirm", "label": "生成提案"},
                         {"id": prefix + ":back", "label": "回退上次修改"},
                         {"id": prefix + ":regenerate", "label": "重新生成推荐"}],
                allow_free_text=False, max_rounds=16,
            )
            if _value(control, "kind") == "cancelled":
                return _cancel(data)
            selected = _value(control, "selected_option_id")
            if _value(control, "kind") != "selected":
                raise ValueError("请使用独立操作入口")
            if selected == prefix + ":confirm":
                data["fieldSelection"] = {"draftId": draft["draftId"], "version": version, "fields": fields}
                return {"status": "completed", "output": data}
            if selected == prefix + ":back":
                fields, confirmed = history.pop()
            elif selected == prefix + ":regenerate":
                offset += 5
            else:
                raise ValueError("操作不属于当前草稿版本")
        raise ValueError("已达到字段引导修改次数限制，请重新发起需求；未生成或应用变更")
    except (ValueError, TypeError, KeyError) as error:
        return {"status": "failed", "error_code": "form_field_guidance_invalid", "summary": str(error), "abort_run": True}


def _cancel(data):
    from .guidance import _cancelled
    result = _cancelled(data)
    result["output"]["proposal"].pop("fieldGuidance", None)
    return result
