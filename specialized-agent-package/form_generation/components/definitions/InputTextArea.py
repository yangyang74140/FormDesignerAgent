"""Input.TextArea properties and shared text behavior."""
from ..common import boolean, number
from ._shared import text
from ._shared.text import clear, matches, normalize_copy, simulate, snapshot, validate

PROPERTIES = {
    **text.PROPERTIES,
    "rows": number(3, 10, default=3, has_default=True),
    "disableAutoHeight": boolean(),
    "showEmptyLines": boolean(),
}
