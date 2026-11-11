import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from form_generation import FLOW_COMPONENTS, compile_form_proposal


COMPONENT_CATALOG = {
    component: {
        "componentLabel": component,
        "writableProps": ["label", "name", "required", "placeholder", "options"],
    }
    for component in FLOW_COMPONENTS
}


def blank_context():
    return {
        "requestId": "req-onboarding",
        "schemaVersion": "1.0.0",
        "target": {"schemaId": "employee-onboarding", "formId": "form-new", "revision": "rev-0"},
        "currentSchema": {"schemaVersion": "1.0.0", "fields": []},
        "selection": {},
        "canvas": {"layoutMode": "flow", "isBlank": True},
        "capabilities": {
            "components": COMPONENT_CATALOG,
            "fieldNameRules": {"pattern": "^[a-z][a-z0-9_]*$", "maxLength": 50, "reserved": ["id"]},
            "optionRules": {"maxOptions": 20},
        },
        "supportedActionVersions": {
            "form.add_component": ["1.0"],
            "form.update_component": ["1.0"],
            "form.update_component_options": ["1.0"],
            "form.move_component": ["1.0"],
            "form.remove_component": ["1.0"],
            "form.convert_component": ["1.0"],
            "form.update_field_rules": ["1.0"],
            "form.update_form_rules": ["1.0"],
            "form.upsert_formula": ["1.0"],
        },
    }


def compile_fields(fields, context=None):
    items = [{
        "capability": "proposal.begin",
        "slots": {
            "summary": "生成员工入职登记表",
            "result_kind": "form_fields",
            "mode": "replace_empty_form",
            "scope": "form",
        },
    }]
    items.extend({"capability": "form.field.define", "slots": field} for field in fields)
    compiled = compile_form_proposal({"plan_items": items}, SimpleNamespace(context=context or blank_context()))
    return compiled["output"]["form_proposal"]


class FormFieldListTests(unittest.TestCase):
    def test_complete_field_list_and_actions_share_one_source(self):
        fields = [
            {
                "client_ref": f"field-{index}",
                "component_name": component,
                "label": f"字段 {index}",
                "name": f"field_{index}",
                "required": index == 1,
                "placeholder": "请输入" if component in {"Input", "Input.TextArea"} else "",
                "options": [
                    {"label": "选项 A", "value": "a"},
                    {"label": "选项 B", "value": "b"},
                ] if component in {"SelectSingle", "SelectMulti", "CheckboxGroup"} else [],
            }
            for index, component in enumerate(FLOW_COMPONENTS, start=1)
        ]

        result = compile_fields(fields)

        self.assertEqual(result["contractVersion"], "form_agent_proposal.v1")
        self.assertEqual(result["presentation"]["contractVersion"], "form_field_list.v1")
        self.assertEqual(result["schemaVersion"], "1.0.0")
        self.assertEqual(result["requestId"], "req-onboarding")
        self.assertEqual(result["presentation"]["kind"], "form_field_list")
        self.assertEqual(result["result"]["mode"], "replace_empty_form")
        self.assertEqual(len(result["presentation"]["fields"]), 9)
        self.assertEqual(len(result["result"]["actions"]), 9)
        for index, (field, action) in enumerate(
            zip(result["presentation"]["fields"], result["result"]["actions"])
        ):
            payload = action["payload"]
            self.assertNotIn("id", field)
            self.assertNotIn("id", payload)
            self.assertEqual(payload["clientRef"], field["clientRef"])
            self.assertEqual(payload["componentName"], field["componentName"])
            self.assertEqual(payload["props"], field["props"])
            self.assertEqual(payload["target"], {"kind": "root", "index": index})

    def test_full_generation_requires_blank_flow_schema_1_0(self):
        field = {"client_ref": "name", "component_name": "Input", "label": "姓名", "name": "name"}
        for mutation, message in (
            ({"canvas": {"layoutMode": "grid", "isBlank": True}}, "flow"),
            ({"canvas": {"layoutMode": "flow", "isBlank": False}}, "空白"),
            ({"schemaVersion": "1.1.0"}, "Schema 1.0.0"),
        ):
            context = blank_context()
            context.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, message):
                compile_fields([field], context)

    def test_field_name_client_ref_and_option_rules_are_enforced(self):
        base = {"client_ref": "choice", "component_name": "SelectSingle", "label": "类型", "name": "type"}
        invalid_cases = (
            ({**base, "client_ref": "bad ref", "options": [{"label": "A", "value": "a"}]}, "clientRef"),
            ({**base, "name": "Type", "options": [{"label": "A", "value": "a"}]}, "不符合规则"),
            ({**base, "name": "id", "options": [{"label": "A", "value": "a"}]}, "保留名"),
            ({**base, "options": []}, "至少一个 option"),
            ({**base, "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "a"}]}, "value 重复"),
        )
        for field, message in invalid_cases:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                compile_fields([field])

    def test_duplicate_names_and_client_refs_are_rejected(self):
        first = {"client_ref": "field-one", "component_name": "Input", "label": "姓名", "name": "name"}
        with self.assertRaisesRegex(ValueError, "重复 clientRef"):
            compile_fields([first, {**first, "name": "other"}])
        with self.assertRaisesRegex(ValueError, "字段 name 重复"):
            compile_fields([first, {**first, "client_ref": "field-two"}])

    def test_non_option_component_rejects_options(self):
        with self.assertRaisesRegex(ValueError, "不支持 options"):
            compile_fields([{
                "client_ref": "name", "component_name": "Input", "label": "姓名", "name": "name",
                "options": [{"label": "A", "value": "a"}],
            }])


if __name__ == "__main__":
    unittest.main()
