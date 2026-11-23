"""Generation component catalog and the seven supported intrinsic property rules."""
from .registry import PROPERTY_COMPONENTS, get_component_rules, property_names

FLOW_COMPONENTS = (
    "Input",
    "Input.TextArea",
    "DatePicker",
    "TimePicker",
    "NumberPicker",
    "SelectSingle",
    "SelectMulti",
    "CheckboxGroup",
    "Switch",
)
OPTION_COMPONENTS = frozenset({"SelectSingle", "SelectMulti", "CheckboxGroup"})
COMPONENT_LABELS = {
    "Input": "单行文本",
    "Input.TextArea": "多行文本",
    "DatePicker": "日期",
    "TimePicker": "时间",
    "NumberPicker": "数字",
    "SelectSingle": "下拉单选",
    "SelectMulti": "下拉多选",
    "CheckboxGroup": "复选框组",
    "Switch": "开关",
}

__all__ = [
    "FLOW_COMPONENTS", "OPTION_COMPONENTS", "COMPONENT_LABELS", "PROPERTY_COMPONENTS",
    "get_component_rules", "property_names",
]
