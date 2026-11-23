"""SelectSingle properties and single-option clearing."""
from __future__ import annotations

from typing import Any, Mapping

from ..common import boolean
from ._shared import choice
from ._shared.choice import dependencies, effects, simulate, validate, validate_compound

PROPERTIES = {
    **choice.PROPERTIES,
    "allowClear": boolean(reset=True, has_reset=True),
}


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    return {"exists": False} if prop == "defaultValue" else None
