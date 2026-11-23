"""TimePicker properties and shared time-range behavior."""
from ..common import enum, number, string
from ._shared import temporal
from ._shared.temporal import clear, dependencies, effects, simulate, snapshot, validate, validate_compound

PROPERTIES = {
    **temporal.PROPERTIES,
    "placeholder": string(reset="请选择时间", has_reset=True),
    "format": enum(["HH:mm:ss", "HH:mm"], reset="HH:mm:ss", has_reset=True, saved_lock=True),
    "minuteStep": number(1, 59, default=1, has_default=True),
    "secondStep": number(1, 59, default=1, has_default=True),
}
