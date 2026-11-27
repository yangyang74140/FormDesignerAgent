"""Coexisting field-generation and property capabilities must stay isolated."""
from copy import deepcopy
import unittest
from test_form_field_list import assert_action_draft, blank_context, compile_fields
from test_form_proposal import compile_items, host_context
import test_property_integration


FIELD = {"client_ref": "application-note", "component_name": "Input", "label": "申请说明", "name": "application_note"}


def mixed_context(version="1.1.0"):
    value = deepcopy(blank_context())
    value["schemaVersion"] = version
    value["currentSchema"]["schemaVersion"] = version
    value["capabilities"]["components"]["Switch"] = {
        "componentLabel": "开关", "writableProps": ["label", "name"],
        "create": {"writableProps": ["label", "name"]},
    }
    value["capabilities"]["propertyCatalog"] = {"components": {
        "Switch": {"properties": {"required": {"valueSchema": {"type": "boolean"}}}},
    }}
    value["supportedActionVersions"]["form.apply_property_change"] = ["form_property_actions.v1"]
    return value


class ActionVersionCompatibilityTests(unittest.TestCase):
    def test_generation_preserves_both_schema_versions_with_property_capabilities(self):
        for version in ("1.0.0", "1.1.0"):
            with self.subTest(version=version):
                context = mixed_context(version)
                before = deepcopy(context)
                result = compile_fields([FIELD], context)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["schemaVersion"], version)
                assert_action_draft(self, result)
                self.assertEqual(result["actionVersion"], "1.0")
                self.assertEqual(context, before)

    def test_append_to_existing_schema_keeps_ids_and_uses_change_version(self):
        context = mixed_context()
        existing = {"id": "saved-note", "componentName": "Input", "props": {"label": "姓名", "name": "employee_name", "custom": "preserve"}}
        context["currentSchema"]["fields"] = [existing]
        context["canvas"]["isBlank"] = False
        result = compile_items([
            {"capability": "proposal.begin", "slots": {"summary": "追加说明", "result_kind": "form_fields", "mode": "append"}},
            {"capability": "form.field.define", "slots": FIELD},
        ], context)
        assert_action_draft(self, result)
        self.assertEqual(result["actionVersion"], "form_change_actions.v1")
        self.assertEqual(context["currentSchema"]["fields"], [existing])
        self.assertEqual(len(result["actions"]), 1)
        payload = result["actions"][0]["payload"]
        self.assertEqual(payload["target"], {"kind": "root", "index": 1})
        self.assertNotIn("id", payload)

    def test_switch_omits_unwritable_false_required_without_overriding_catalog(self):
        for required in ({}, {"required": False}):
            field = {**FIELD, "component_name": "Switch", **required}
            result = compile_fields([field], mixed_context())
            assert_action_draft(self, result)
            props = result["actions"][0]["payload"]["props"]
            self.assertEqual(props, {"label": "申请说明", "name": "application_note"})
        result = compile_fields([{**FIELD, "component_name": "Switch", "required": True}], mixed_context())
        self.assertEqual(result["status"], "unsupported", result)
        self.assertIn("不可写属性: required", result["summary"])

    def test_explicit_create_catalog_wins_over_legacy_writable_props(self):
        context = mixed_context()
        context["capabilities"]["components"]["Input"]["create"] = {"writableProps": ["label", "name", "required"]}
        result = compile_fields([{**FIELD, "placeholder": "不允许"}], context)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertIn("不可写属性: placeholder", result["summary"])
        context["capabilities"]["components"]["Input"]["create"] = {"writableProps": []}
        result = compile_fields([FIELD], context)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertEqual(result["diagnostics"][0]["code"], "MISSING_WRITABLE_PROPS")

    def test_direct_add_also_checks_creation_catalog(self):
        context = mixed_context()
        context["canvas"]["isBlank"] = False
        result = compile_items([
            {"capability": "proposal.begin", "slots": {"result_kind": "form_actions"}},
            {"capability": "form.add_component", "slots": {"payload": {"clientRef": "new-switch", "componentName": "Switch", "props": {"required": True}, "target": {"kind": "root"}}}},
        ], context)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertIn("不可写属性: required", result["summary"])

    def test_missing_or_unimplemented_add_version_cannot_borrow_property_version(self):
        for versions in (None, [], ["9.0"], ["form_property_actions.v1"]):
            context = mixed_context()
            context["capabilities"]["supportedActionVersions"] = {"form.add_component": versions}
            with self.subTest(versions=versions):
                result = compile_fields([FIELD], context)
                self.assertEqual(result["status"], "unsupported", result)
                self.assertEqual(result["diagnostics"][0]["code"], "ACTION_VERSION_UNSUPPORTED")
                self.assertIn("form.add_component", result["summary"])

    def test_legacy_field_versions_do_not_authorize_changes_or_creation(self):
        for versions in (["1.0"], ["form_actions.v1"], ["form_actions.v2"], {"1.0": True}):
            context = mixed_context()
            context["capabilities"].pop("supportedActionVersions")
            context["supportedActionVersions"] = versions
            context["canvas"]["isBlank"] = False
            result = compile_items([
                {"capability": "proposal.begin", "slots": {"result_kind": "form_actions"}},
                {"capability": "form.remove_component", "slots": {"payload": {"nodeId": "saved-note"}}},
            ], context)
            self.assertEqual(result["status"], "unsupported", result)
            self.assertNotIn("actions", result)
            if versions != ["1.0"] and versions != {"1.0": True}:
                context["canvas"]["isBlank"] = True
                result = compile_fields([FIELD], context)
                self.assertEqual(result["status"], "unsupported", result)
                self.assertNotIn("actions", result)

    def test_property_actions_use_change_version_on_both_schemas(self):
        helper = test_property_integration.PropertyIntegrationTests()
        for version in ("1.0.0", "1.1.0"):
            context = helper.context()
            context["schemaVersion"] = version
            context["currentSchema"]["schemaVersion"] = version
            context["supportedActionVersions"]["form.add_component"] = ["1.0"]
            result = compile_items(helper.ir()["plan_items"], context)
            self.assertEqual(result["status"], "ready", result)
            self.assertEqual(result["schemaVersion"], version)
            assert_action_draft(self, result, "shared.form-change-confirm", property_actions=True)
            self.assertEqual(result["actionVersion"], "form_change_actions.v1")
