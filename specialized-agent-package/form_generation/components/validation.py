"""Shared finite JSON-schema validation and controlled property rejections."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping


class Rejected(Exception):
    def __init__(self, code: str, message: str, clarify: bool = False):
        self.code, self.message, self.clarify = code, message, clarify


def reject(code: str, message: str, clarify: bool = False) -> None:
    raise Rejected(code, message, clarify)


def validate_schema(value: Any, schema: Any) -> None:
    """Validate the deliberately finite supported JSON-schema subset, fail closed."""
    if not isinstance(schema, Mapping) or not schema:
        reject("MISSING_VALUE_SCHEMA", "宿主未声明可验证的值类型。")
    allowed = {"type", "enum", "const", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "pattern", "items", "minItems", "maxItems", "uniqueItems", "properties", "required", "additionalProperties", "oneOf", "anyOf", "description", "title", "default"}
    if set(schema) - allowed:
        reject("UNSUPPORTED_VALUE_SCHEMA", "值 schema 含未支持的验证约束。")
    for union in ("oneOf", "anyOf"):
        if union in schema:
            if not isinstance(schema[union], list) or not schema[union]:
                reject("INVALID_VALUE_SCHEMA", "联合类型声明无效。")
            matches = 0
            for branch in schema[union]:
                try:
                    validate_schema(value, branch)
                    matches += 1
                except Rejected:
                    pass
            if matches == 0 or (union == "oneOf" and matches != 1):
                reject("INVALID_VALUE", "值未匹配注册的联合类型。")
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds] if kinds else []
    types = {"string": type(value) is str, "boolean": type(value) is bool, "number": type(value) in (int, float) and math.isfinite(value), "integer": type(value) in (int, float) and math.isfinite(value) and value == int(value), "object": isinstance(value, dict), "array": isinstance(value, list), "null": value is None}
    if kinds and (any(kind not in types for kind in kinds) or not any(types[kind] for kind in kinds)):
        reject("INVALID_VALUE", "属性值类型不匹配。")
    if not kinds and not any(key in schema for key in ("enum", "const", "oneOf", "anyOf")):
        reject("MISSING_VALUE_SCHEMA", "值 schema 缺少类型。")
    if "enum" in schema and not any(type(value) is type(option) and value == option for option in schema["enum"]):
        reject("INVALID_VALUE", "值不属于注册枚举。")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        reject("INVALID_VALUE", "值不匹配常量。")
    if type(value) in (int, float):
        for key, valid in (("minimum", lambda x: value >= x), ("maximum", lambda x: value <= x), ("exclusiveMinimum", lambda x: value > x), ("exclusiveMaximum", lambda x: value < x)):
            if key in schema and not valid(schema[key]):
                reject("INVALID_VALUE", "数值超出注册范围。")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 100000):
            reject("INVALID_VALUE", "字符串长度超出范围。")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            reject("INVALID_VALUE", "字符串格式不匹配。")
    if isinstance(value, (dict, list)) and "type" not in schema and "properties" not in schema and "items" not in schema and any(key in schema for key in ("oneOf", "anyOf", "enum", "const")):
        return
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1000):
            reject("INVALID_VALUE", "数组长度超出范围。")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            reject("INVALID_VALUE", "数组不能包含重复值。")
        if "items" not in schema:
            reject("MISSING_VALUE_SCHEMA", "数组缺少元素 schema。")
        for item in value:
            validate_schema(item, schema["items"])
    if isinstance(value, dict):
        props = schema.get("properties")
        if not isinstance(props, Mapping) or schema.get("additionalProperties") is not False:
            reject("UNBOUNDED_OBJECT", "复合值必须声明完整字段并禁止额外属性。")
        if set(value) - set(props) or set(schema.get("required", [])) - set(value):
            reject("INVALID_VALUE", "复合值字段缺失或不受支持。")
        for key, child in value.items():
            validate_schema(child, props[key])

