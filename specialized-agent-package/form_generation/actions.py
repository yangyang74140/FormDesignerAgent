"""受控表单 IR、FormSchema 编译器和 form_actions.v1 Action 规则。"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

FORM_ACTION_CONTRACT = "form_actions.v1"
FORM_ACTION_PIPELINE = "form_action_generation"
FORM_SKELETON_CONTRACT = "form_skeleton.v1"
FORM_FIELD_BATCH_CONTRACT = "form_field_batch.v1"
FORM_OUTPUT_CONTRACT = "form_output.v1"
FORM_PIPELINE = "form_generation"

COMMON_CHANGE_KEYS = frozenset({"label", "name", "required", "placeholder", "default_value"})
_FORM_PROP_KEYS = {
    "default_value": "defaultValue",
    "text_max_length": "textMaxLength",
    "allow_clear": "allowClear",
    "show_limit_hint": "showLimitHint",
    "enable_quick_copy": "enableQuickCopy",
    "enable_link_parser": "enableLinkParser",
    "show_search": "showSearch",
    "enable_color": "enableColor",
    "support_reverse_select": "supportReverseSelect",
}
COMPONENT_ALIASES = {
    "text": "Input",
    "input": "Input",
    "single_choice": "SelectSingle",
    "select": "SelectSingle",
    "select_single": "SelectSingle",
    "multiple_choice": "CheckboxGroup",
    "checkbox": "CheckboxGroup",
    "checkbox_group": "CheckboxGroup",
}
COMPONENT_TITLES = {
    "Input": "单行文本",
    "SelectSingle": "下拉单选",
    "CheckboxGroup": "复选框",
}
SUPPORTED_COMPONENTS = tuple(COMPONENT_TITLES)
_SHARED_DEFAULTS = {
    "enableCustomTitle": False,
    "customTitle": "",
    "extra": "",
    "extraType": "icon",
    "hideTitle": False,
    "readOnlyDisplay": False,
    "size": "medium",
}
_FORM_CONFIG_KEYS = frozenset({"description", "columns", "labelPosition", "labelWidth", "textAlign", "rowHeight"})


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _bool(value: Any, fallback: bool = False) -> bool:
    return value if isinstance(value, bool) else fallback


def _safe_key(value: Any, fallback: str = "field") -> str:
    key = re.sub(r"[^a-zA-Z0-9_\-]+", "_", _text(value, fallback)).strip("_")
    return key[:50] or fallback


def _normalize_options(value: Any) -> dict[str, Any]:
    """归一化为 FormSchema 的 options 内部结构。"""
    if isinstance(value, Mapping):
        raw = value.get("dataSource") if isinstance(value.get("dataSource"), list) else []
        is_color = _bool(value.get("isColor"), False)
    else:
        raw = value if isinstance(value, list) else []
        is_color = False
    data_source: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        primary_key = _text(item.get("primaryKey"), str(index))
        if primary_key in used_keys:
            primary_key = str(index)
            while primary_key in used_keys:
                primary_key = f"{index}_{len(used_keys) + 1}"
        used_keys.add(primary_key)
        data_source.append(
            {
                "primaryKey": primary_key,
                "value": _text(item.get("value"), str(index)),
                "label": _text(item.get("label"), f"选项{index}"),
                "activeKey": _bool(item.get("activeKey"), False),
                "color": item.get("color") if item.get("color") is not None else None,
                "disabled": _bool(item.get("disabled"), False),
            }
        )
    if not data_source:
        data_source = [
            {
                "primaryKey": "1",
                "value": "1",
                "label": "选项1",
                "activeKey": False,
                "color": None,
                "disabled": False,
            }
        ]
    numeric_keys = [int(item["primaryKey"]) for item in data_source if str(item["primaryKey"]).isdigit()]
    next_seed = max(numeric_keys, default=len(data_source)) + 1
    return {"dataSource": data_source, "isColor": is_color, "nextValueSeed": next_seed}


def _option_values(options: Mapping[str, Any]) -> set[str]:
    """Return the controlled values accepted by a select-like field."""
    data_source = options.get("dataSource")
    return {
        str(item.get("value"))
        for item in data_source
        if isinstance(item, Mapping) and item.get("value") is not None
    } if isinstance(data_source, list) else set()


def _default_field_props(component_name: str, label: str, name: str) -> dict[str, Any]:
    """构造设计器需要的完整默认 props。"""
    shared = deepcopy(_SHARED_DEFAULTS)
    if component_name == "Input":
        props = {
            "label": label,
            "required": False,
            "name": name,
            "placeholder": "",
            "defaultValueConfig": "undefined",
            "defaultValue": "",
            "allowClear": True,
            "showLimitHint": False,
            "textMaxLength": 0,
            "enableQuickCopy": False,
            "enableLinkParser": False,
            "format": "none",
            "isUnique": False,
        }
    elif component_name == "SelectSingle":
        props = {
            "label": label,
            "required": False,
            "name": name,
            "placeholder": "请选择",
            "defaultValue": "",
            "options": _normalize_options([]),
            "showSearch": False,
            "allowClear": True,
            "popupMatchSelectWidth": False,
            "enableColor": False,
        }
    else:
        props = {
            "label": label,
            "required": False,
            "name": name,
            "defaultValue": [],
            "options": _normalize_options([]),
            "direction": "horizontal",
            "supportReverseSelect": True,
        }
    props.update(shared)
    props["identifiers"] = {"name": name}
    return props


def _normalize_component_name(value: Any) -> str:
    raw = _text(value, "Input")
    return COMPONENT_ALIASES.get(raw.lower(), raw)


def _normalize_field_input(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    component_name = _normalize_component_name(raw.get("componentName") or raw.get("type") or raw.get("component_type"))
    if component_name not in SUPPORTED_COMPONENTS:
        raise ValueError(f"不支持的表单组件类型: {component_name}")
    field: dict[str, Any] = {
        "componentName": component_name,
        "label": _text(raw.get("label"), "未命名字段"),
        "name": _safe_key(raw.get("name"), "field"),
        "required": _bool(raw.get("required")),
    }
    for key in ("placeholder", "default_value", "text_max_length", "show_search", "direction"):
        if key in raw:
            field[key] = raw[key]
    if component_name in {"SelectSingle", "CheckboxGroup"} and "options" in raw:
        field["options"] = _normalize_options(raw.get("options"))
    if component_name == "CheckboxGroup" and isinstance(raw.get("default_value"), list):
        field["default_value"] = [str(item) for item in raw["default_value"]]
    return field


def _normalize_changes(changes: Any, component_name: str | None = None) -> dict[str, Any]:
    """按当前字段 componentName 过滤专属属性，防止跨组件污染。"""
    raw = changes if isinstance(changes, Mapping) else {}
    allowed = set(COMMON_CHANGE_KEYS)
    if component_name == "Input":
        allowed.update({"text_max_length", "allow_clear", "show_limit_hint", "enable_quick_copy", "enable_link_parser"})
    elif component_name == "SelectSingle":
        allowed.update({"options", "show_search", "enable_color"})
    elif component_name == "CheckboxGroup":
        allowed.update({"options", "direction", "support_reverse_select"})
    result = {key: deepcopy(raw[key]) for key in allowed if key in raw}
    if "options" in result:
        result["options"] = _normalize_options(result["options"])
    return result


def _normalize_default_value(component_name: str, value: Any, props: Mapping[str, Any]) -> Any:
    """Keep defaults aligned with the values accepted by the field component."""
    if component_name == "Input":
        return value if isinstance(value, str) else ""
    options = props.get("options") if isinstance(props.get("options"), Mapping) else {}
    allowed = _option_values(options)
    if component_name == "SelectSingle":
        candidate = str(value) if value is not None else ""
        return candidate if candidate in allowed else ""
    if component_name == "CheckboxGroup":
        values = value if isinstance(value, list) else []
        return [str(item) for item in values if str(item) in allowed]
    return value


def _action(capability: str, slots: Mapping[str, Any]) -> dict[str, Any]:
    return {"capability": capability, "slots": dict(slots)}


def _build_capabilities() -> list[dict[str, Any]]:
    component_types = {"type": "string", "enum": sorted(COMPONENT_ALIASES)}
    return [
        {
            "capability": "form.create_form",
            "semantics": "初始化 PC flow 表单元数据；修改已有表单时不要使用。",
            "slots_schema": {"type": "object", "properties": {"description": {"type": "string"}, "columns": {"type": "integer", "minimum": 1, "maximum": 4}}},
        },
        {
            "capability": "form.add_component",
            "semantics": "添加一个 PC flow 表单字段；只能使用受支持的组件类型。",
            "slots_schema": {
                "type": "object", "required": ["type", "label", "name"], "properties": {
                    "type": component_types, "label": {"type": "string"}, "name": {"type": "string"}, "required": {"type": "boolean"},
                    "placeholder": {"type": "string"}, "default_value": {}, "options": {"type": "array", "items": {"type": "object"}}, "after_field_id": {"type": "string"},
                },
            },
        },
        {
            "capability": "form.update_component",
            "semantics": "按真实 field_id 修改已有字段的受控业务属性。",
            "slots_schema": {"type": "object", "required": ["field_id", "changes"], "properties": {"field_id": {"type": "string"}, "changes": {"type": "object"}}},
        },
        {
            "capability": "form.update_component_options",
            "semantics": "按真实 field_id 修改已有单选或复选框的选项。",
            "slots_schema": {"type": "object", "required": ["field_id", "options"], "properties": {"field_id": {"type": "string"}, "options": {"type": "array"}}},
        },
        {
            "capability": "form.move_component",
            "semantics": "按真实 field_id 移动字段；after_field_id 为空表示移到最前。",
            "slots_schema": {"type": "object", "required": ["field_id"], "properties": {"field_id": {"type": "string"}, "after_field_id": {"type": "string"}}},
        },
        {
            "capability": "form.remove_component",
            "semantics": "按真实 field_id 删除已有字段。",
            "slots_schema": {"type": "object", "required": ["field_id"], "properties": {"field_id": {"type": "string"}}},
        },
        {
            "capability": "form.update_form_config",
            "semantics": "修改表单级配置；只允许 description、columns、labelPosition、labelWidth、textAlign、rowHeight。",
            "slots_schema": {"type": "object", "properties": {"changes": {"type": "object"}}},
        },
    ]


def action_capabilities() -> list[dict[str, Any]]:
    return _build_capabilities()


def skeleton_capabilities() -> list[dict[str, Any]]:
    """创建阶段的第一阶段 Native Capability。"""
    component_schema = {"type": "string", "enum": list(SUPPORTED_COMPONENTS)}
    return [
        {
            "capability": "form.create",
            "semantics": "创建 PC flow 表单骨架，只填写表单描述和列数。",
            "slots_schema": {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "columns": {"type": "integer"}}},
        },
        {
            "capability": "form.skeleton.add_field",
            "semantics": "在骨架中按顺序声明一个字段占位符。",
            "slots_schema": {"type": "object", "required": ["field_key", "componentName", "purpose"], "properties": {"field_key": {"type": "string"}, "componentName": component_schema, "purpose": {"type": "string"}}},
        },
    ]


def hydration_capabilities() -> list[dict[str, Any]]:
    return [
        {
            "capability": "form.field.configure",
            "semantics": "为一个骨架字段填写业务配置，不改变字段 ID、类型和顺序。",
            "slots_schema": {
                "type": "object", "required": ["field_key", "config"],
                "properties": {"field_key": {"type": "string"}, "config": {"type": "object"}},
            },
        }
    ]


def _compile_actions(ir_payload: Any, step_context: Any) -> tuple[list[dict[str, Any]], str | None]:
    items = ir_payload.get("plan_items") if isinstance(ir_payload, Mapping) else None
    if not isinstance(items, list):
        items = [ir_payload]
    if len(items) != 1 or not isinstance(items[0], Mapping):
        raise ValueError("表单修改一次只能生成一个 Action")
    item = items[0]
    capability = _text(item.get("capability"))
    slots = item.get("slots") if isinstance(item.get("slots"), Mapping) else {}
    schema = _schema_from_context(step_context)
    if not schema:
        raise ValueError("缺少当前 FormSchema，无法编译修改操作")
    fields = _schema_fields(schema)
    by_id = {str(field.get("id")): field for field in fields if field.get("id")}
    actions: list[dict[str, Any]] = []
    if capability == "form.create_form":
        raise ValueError("修改阶段不允许重新创建完整表单")
    if capability == "form.add_component":
        field = _normalize_field_input(slots)
        after_id = _text(slots.get("after_field_id")) or None
        if after_id and after_id not in by_id:
            raise ValueError("新增字段的 after_field_id 不存在")
        actions.append({"action": capability, "payload": {"componentType": field["componentName"], "props": {key: value for key, value in field.items() if key != "componentName"}, "afterFieldId": after_id}})
    elif capability == "form.update_component":
        field_id = _text(slots.get("field_id"))
        field = by_id.get(field_id)
        if field is None:
            raise ValueError("form.update_component 的 field_id 不存在")
        component_name = _text(field.get("componentName"))
        changes = _normalize_changes(slots.get("changes"), component_name)
        if "default_value" in changes:
            current_props = field.get("props") if isinstance(field.get("props"), Mapping) else {}
            effective_props = dict(current_props)
            if "options" in changes:
                effective_props["options"] = changes["options"]
            changes["default_value"] = _normalize_default_value(component_name, changes["default_value"], effective_props)
        if "name" in changes:
            changes["name"] = _safe_key(changes["name"], _safe_key(field.get("id"), "field"))
        if "label" in changes:
            changes["label"] = _text(changes["label"], "未命名字段")
        if not changes:
            raise ValueError("更新组件没有当前类型允许的属性")
        schema_changes = {_FORM_PROP_KEYS.get(key, key): value for key, value in changes.items()}
        actions.append({"action": capability, "payload": {"fieldId": field_id, "changes": schema_changes}})
    elif capability == "form.update_component_options":
        field_id = _text(slots.get("field_id"))
        field = by_id.get(field_id)
        if field is None:
            raise ValueError("form.update_component_options 的 field_id 不存在")
        if _text(field.get("componentName")) not in {"SelectSingle", "CheckboxGroup"}:
            raise ValueError("只有单选或复选框字段支持 options")
        actions.append({"action": capability, "payload": {"fieldId": field_id, "options": _normalize_options(slots.get("options"))}})
    elif capability == "form.move_component":
        field_id = _text(slots.get("field_id"))
        after_id = _text(slots.get("after_field_id")) or None
        if field_id not in by_id or (after_id and (after_id not in by_id or after_id == field_id)):
            raise ValueError("移动字段必须引用当前 Schema 中真实且不同的 field_id")
        actions.append({"action": capability, "payload": {"fieldId": field_id, "afterFieldId": after_id}})
    elif capability == "form.remove_component":
        field_id = _text(slots.get("field_id"))
        if field_id not in by_id:
            raise ValueError("删除字段的 field_id 不存在")
        actions.append({"action": capability, "payload": {"fieldId": field_id}})
    elif capability == "form.update_form_config":
        changes = slots.get("changes") if isinstance(slots.get("changes"), Mapping) else {}
        filtered = {key: deepcopy(changes[key]) for key in _FORM_CONFIG_KEYS if key in changes}
        if not filtered:
            raise ValueError("表单配置没有可修改的属性")
        actions.append({"action": capability, "payload": {"changes": filtered}})
    else:
        raise ValueError(f"不支持的表单修改能力: {capability}")
    return actions, capability


def compile_form_action(ir_payload: Any, step_context: Any) -> dict[str, Any]:
    """把修改阶段单条 IR 编译为 form_actions.v1 语义。"""
    actions, capability = _compile_actions(ir_payload, step_context)
    return {"status": "completed", "output": {"form_action_json": {"schemaVersion": FORM_ACTION_CONTRACT, "actions": actions}, "action_capability": capability}}


def compile_form_actions(ir_payload: Any, step_context: Any) -> dict[str, Any]:
    """兼容旧调用方的 Action 编译入口；创建不再使用它。"""
    actions, _ = _compile_actions(ir_payload, step_context)
    return {"schemaVersion": FORM_ACTION_CONTRACT, "actions": actions}


def _schema_from_context(step_context: Any) -> dict[str, Any]:
    if step_context is None:
        return {}
    for value in (getattr(step_context, "context", None), getattr(step_context, "inputs", None), getattr(step_context, "root_inputs", None)):
        found = _find_schema(value)
        if found:
            return found
    return {}


def _find_schema(value: Any, depth: int = 0) -> dict[str, Any]:
    if depth > 5 or not isinstance(value, Mapping):
        return {}
    for key in ("current_form_schema", "form_schema", "current_page_schema", "page_schema_json", "current_page_json", "page_json"):
        candidate = value.get(key)
        if isinstance(candidate, Mapping) and ("fields" in candidate or "schemaVersion" in candidate):
            return deepcopy(dict(candidate))
    for key in ("context", "specialized_context", "run_context", "input_data", "request", "envelope"):
        found = _find_schema(value.get(key), depth + 1)
        if found:
            return found
    return {}


def _schema_fields(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = schema.get("fields")
    return [dict(field) for field in fields if isinstance(field, Mapping)] if isinstance(fields, list) else []


def _slug(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z_\-]+", "_", _text(value, "field")).strip("_") or "field"


def _unique_id(candidate: str, used: set[str]) -> str:
    base = candidate
    current = base
    index = 2
    while current in used:
        current = f"{base}_{index}"
        index += 1
    used.add(current)
    return current


def _form_root(title: str, description: str, columns: Any) -> dict[str, Any]:
    column_count = columns if isinstance(columns, int) and 1 <= columns <= 4 else 2
    return {
        "schemaVersion": "1.1.0",
        "id": "form_generated",
        "props": {
            "description": description,
            "columns": column_count,
            "labelPosition": "left",
            "labelWidth": 80,
            "textAlign": "left",
            "rowHeight": "16px",
        },
        "layoutMode": "flow",
        "fields": [],
    }


def compile_form_skeleton(ir_payload: Any, step_context: Any = None) -> dict[str, Any]:
    """将创建阶段骨架 IR 编译为稳定的 FormSchema 占位骨架。"""
    items = ir_payload.get("plan_items") if isinstance(ir_payload, Mapping) else None
    if not isinstance(items, list):
        items = [ir_payload]
    title = "未命名表单"
    description = ""
    columns: Any = 2
    fields: list[dict[str, Any]] = []
    used: set[str] = {"form_generated"}
    used_field_keys: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        capability = _text(item.get("capability"))
        slots = item.get("slots") if isinstance(item.get("slots"), Mapping) else {}
        if capability == "form.create":
            title = _text(slots.get("title"), title)
            description = _text(slots.get("description"), description)
            columns = slots.get("columns", columns)
        elif capability == "form.skeleton.add_field":
            component_name = _normalize_component_name(slots.get("componentName"))
            if component_name not in SUPPORTED_COMPONENTS:
                continue
            field_key = _unique_id(
                _safe_key(slots.get("field_key"), f"field_{len(fields) + 1}"),
                used_field_keys,
            )
            field_id = _unique_id(f"fld_{_slug(field_key)}", used)
            label = _text(slots.get("purpose"), field_key)
            fields.append({
                "id": field_id,
                "componentName": component_name,
                "componentCategory": "field",
                "title": COMPONENT_TITLES[component_name],
                "props": _default_field_props(component_name, label, field_key),
            })
    schema = _form_root(title, description, columns)
    schema["fields"] = fields
    return {"status": "completed", "output": {"form_schema": schema, "skeleton_json": schema, "form_title": title}}


def _skeleton_from_input(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    if isinstance(value.get("fields"), list):
        return deepcopy(dict(value))
    output = value.get("output")
    if isinstance(output, Mapping):
        return _skeleton_from_input(output)
    for key in ("form_schema", "skeleton_json"):
        candidate = value.get(key)
        if isinstance(candidate, Mapping):
            return deepcopy(dict(candidate))
    for key in ("context", "input_data", "run_context", "specialized_context"):
        found = _skeleton_from_input(value.get(key))
        if found:
            return found
    return {}


def _field_key(field: Mapping[str, Any]) -> str:
    props = field.get("props") if isinstance(field.get("props"), Mapping) else {}
    return _safe_key(field.get("field_key") or props.get("name"), _slug(field.get("id")))


def _config_to_props(component_name: str, config: Mapping[str, Any], base: Mapping[str, Any]) -> dict[str, Any]:
    """把字段配置 IR 映射到 Schema props，并只保留该组件允许属性。"""
    raw = dict(config)
    raw.setdefault("componentName", component_name)
    raw.setdefault("label", base.get("label", "未命名字段"))
    raw.setdefault("name", base.get("name", "field"))
    raw.setdefault("required", base.get("required", False))
    normalized = _normalize_field_input(raw)
    props = deepcopy(dict(base))
    label = _text(normalized.get("label"), props.get("label", "未命名字段"))
    name = _safe_key(normalized.get("name"), props.get("name", "field"))
    props["label"] = label
    props["name"] = name
    props["required"] = _bool(normalized.get("required"), props.get("required", False))
    props["identifiers"] = {"name": name}
    if "placeholder" in normalized:
        props["placeholder"] = _text(normalized.get("placeholder"))
    if component_name in {"SelectSingle", "CheckboxGroup"}:
        props["options"] = _normalize_options(normalized.get("options", props.get("options")))
    if "default_value" in normalized:
        props["defaultValue"] = _normalize_default_value(component_name, normalized["default_value"], props)
    if component_name == "Input" and "text_max_length" in normalized:
        props["textMaxLength"] = normalized["text_max_length"]
    if component_name == "SelectSingle" and "show_search" in normalized:
        props["showSearch"] = _bool(normalized["show_search"], False)
    if component_name == "CheckboxGroup" and "direction" in normalized:
        props["direction"] = _text(normalized["direction"], "horizontal")
    return props


def compile_form_field_hydration(ir_payload: Any, step_context: Any = None) -> dict[str, Any]:
    """将字段配置 IR 按骨架顺序合并，忽略模型不能控制的身份字段。"""
    skeleton = _skeleton_from_input(getattr(step_context, "inputs", None))
    if not skeleton and step_context is not None:
        skeleton = _skeleton_from_input(getattr(step_context, "root_inputs", None))
    fields = skeleton.get("fields") if isinstance(skeleton.get("fields"), list) else []
    items = ir_payload.get("plan_items") if isinstance(ir_payload, Mapping) else None
    if not isinstance(items, list):
        items = [ir_payload]
    configs: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping) or item.get("capability") != "form.field.configure":
            continue
        slots = item.get("slots") if isinstance(item.get("slots"), Mapping) else {}
        key = _safe_key(slots.get("field_key"), "")
        config = slots.get("config") if isinstance(slots.get("config"), Mapping) else {}
        if key:
            configs[key] = config
    hydrated: list[dict[str, Any]] = []
    for field in fields:
        if not isinstance(field, Mapping):
            continue
        node = deepcopy(dict(field))
        node["componentCategory"] = "field"
        node["props"] = _config_to_props(_text(node.get("componentName"), "Input"), configs.get(_field_key(node), {}), node.get("props", {}))
        node.pop("field_key", None)
        node.pop("purpose", None)
        hydrated.append(node)
    result = deepcopy(skeleton)
    result["fields"] = hydrated
    return {"status": "completed", "output": {"form_schema": result}}


def finalize_form_schema(value: Any) -> dict[str, Any]:
    """保证最终字段节点只包含表单产物所需结构。"""
    source = _skeleton_from_input(value)
    fields = source.get("fields") if isinstance(source.get("fields"), list) else []
    defaults = _form_root("", "", 2)["props"]
    source_props = source.get("props") if isinstance(source.get("props"), Mapping) else {}
    schema = {
        key: deepcopy(source[key])
        for key in ("schemaVersion", "id", "layoutMode")
        if key in source
    }
    schema["schemaVersion"] = "1.1.0"
    schema["id"] = _text(source.get("id"), "form_generated")
    schema["layoutMode"] = "flow"
    schema["props"] = {key: deepcopy(source_props.get(key, default)) for key, default in defaults.items()}
    # 当前支持的三个组件在设计器 meta 中均为 field，分类由代码固定补齐。
    schema["fields"] = [
        {
            **{key: deepcopy(field[key]) for key in ("id", "componentName", "title", "props") if key in field},
            "componentCategory": "field",
        }
        for field in fields if isinstance(field, Mapping) and field.get("id")
    ]
    return schema
