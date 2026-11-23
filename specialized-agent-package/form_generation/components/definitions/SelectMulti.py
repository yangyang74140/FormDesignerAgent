"""SelectMulti properties and multiple-option clearing."""
from __future__ import annotations

from typing import Any, Mapping

from ..common import PropertyRule, boolean, number, string
from ._shared import choice
from ._shared.choice import dependencies, effects, simulate, validate, validate_compound

PROPERTIES = {
    **choice.PROPERTIES,
    "defaultValue": PropertyRule(unvalidated_operations=("clear", "reset")),
    "selectAll": boolean(),
    "supportReverseSelect": boolean(reset=True, has_reset=True),
    "maxCountEnable": boolean(),
    "maxTagCount": number(1, prerequisite="maxCountEnable"),
    "maxCountMessage": string(prerequisite="maxCountEnable"),
}


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    return {"exists": True, "value": []} if prop == "defaultValue" else None
