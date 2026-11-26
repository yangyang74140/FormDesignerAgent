"""Contract tests for the designer's grouped properties and stored snapshots."""
from copy import deepcopy
import unittest
from test_properties import COMPONENT_RULES, host, change, run
from test_form_field_list import assert_action_draft


class HostPropertyCompatibilityTests(unittest.TestCase):
    def applied(self, context, result):
        self.assertEqual(result["status"], "ready", result)
        assert_action_draft(self, result, "shared.form-change-confirm", property_actions=True)
        node = deepcopy(context["currentSchema"]["fields"][0])
        rules = COMPONENT_RULES.get_component_rules(node["componentName"])
        for action in result["actions"]:
            payload = action["payload"]
            prop, operation = payload["property"], payload["operation"]
            definition = context["capabilities"]["components"][node["componentName"]]["properties"][prop]
            after = {"exists": True, "value": deepcopy(payload["value"])} if operation in ("set", "copy") else rules.after(node, prop, operation, {}, definition)
            rules.simulate(node, prop, after)
        return node

    def compound(self, component, prop, schema, default=None):
        context = host(component)
        context["capabilities"]["components"][component]["properties"][prop].update(
            handlerId=prop + ".v1", valueSchema=schema, default=default)
        return context

    def test_before_uses_validated_host_stored_state(self):
        context = host()
        stored = {"exists": True, "value": {"enabled": False, "maxLength": 200}}
        context["resolvedProperties"] = {"a": {"textLengthLimit": {
            "stored": stored, "resolvedValue": stored["value"], "source": "default"}}}
        result = run([change("textLengthLimit", 20)], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["actions"][0]["preconditions"]["before"], stored)
        applied = self.applied(context, result)
        self.assertEqual(COMPONENT_RULES.get_component_rules("Input").snapshot(applied, "textLengthLimit"), {
            "exists": True, "value": {"enabled": True, "maxLength": 20}})
        self.assertEqual(result["actions"][0]["payload"]["value"], 20)
        context["resolvedProperties"]["a"]["textLengthLimit"]["stored"] = {"exists": False, "value": None}
        self.assertEqual(run([change("textLengthLimit", 20)], context)["status"], "unsupported")

    def test_length_clear_and_reset_are_not_set_schema_values(self):
        context = host()
        context["currentSchema"]["fields"][0]["props"].update(showLimitHint=True, textMaxLength=50)
        context["capabilities"]["components"]["Input"]["properties"]["textLengthLimit"].update(
            valueSchema={"type": "integer", "minimum": 1}, default={"enabled": False, "maxLength": 200})
        for operation, maximum in (("clear", 50), ("reset", 200)):
            result = run([change("textLengthLimit", operation=operation)], context)
            self.assertEqual(result["status"], "ready", result)
            props = self.applied(context, result)["props"]
            self.assertFalse(props["showLimitHint"])
            self.assertEqual(props["textMaxLength"], maximum)
            self.assertNotIn("value", result["actions"][0]["payload"])

    def test_numeric_range_group_and_validation(self):
        bound = {"type": "object", "properties": {"value": {"type": "number"}, "message": {"type": "string", "maxLength": 200}}, "required": ["value"], "additionalProperties": False}
        schema = {"type": "object", "properties": {"min": bound, "max": bound}, "additionalProperties": False}
        context = self.compound("NumberPicker", "numericRange", schema, {})
        value = {"min": {"value": 0}, "max": {"value": 100, "message": "最多100"}}
        result = run([change("numericRange", value)], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["actions"][0]["payload"]["value"], value)
        applied = self.applied(context, result)
        self.assertEqual(COMPONENT_RULES.get_component_rules("NumberPicker").snapshot(applied, "numericRange")["value"], value)
        for operation in ("clear", "reset"):
            context["currentSchema"]["fields"][0]["props"].update(minEnable=True, min=1)
            result = run([change("numericRange", operation=operation)], context)
            self.assertEqual(result["status"], "ready", result)
            applied = self.applied(context, result)
            self.assertEqual(COMPONENT_RULES.get_component_rules("NumberPicker").snapshot(applied, "numericRange")["value"], {})
            self.assertNotIn("value", result["actions"][0]["payload"])
        self.assertEqual(run([change("numericRange", {"min": {"value": 2}, "max": {"value": 1}})], context)["status"], "unsupported")

    def test_selection_limit_group_and_clear(self):
        schema = {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 1000}, "message": {"type": "string", "maxLength": 200}}, "required": ["count"], "additionalProperties": False}
        context = self.compound("SelectMulti", "selectionLimit", schema)
        result = run([change("selectionLimit", {"count": 3})], context)
        self.assertEqual(result["status"], "ready", result)
        context["currentSchema"]["fields"][0]["props"].update(maxCountEnable=True, maxTagCount=3)
        for operation in ("clear", "reset"):
            result = run([change("selectionLimit", operation=operation)], context)
            self.assertEqual(result["status"], "ready", result)
            applied = self.applied(context, result)
            self.assertFalse(applied["props"]["maxCountEnable"])
            self.assertNotIn("maxTagCount", applied["props"])
            self.assertNotIn("value", result["actions"][0]["payload"])
        self.assertEqual(run([change("selectionLimit", {"count": 0})], context)["status"], "unsupported")

    def test_final_candidate_rejects_incompatible_defaults(self):
        text = host()
        result = run([change("textLengthLimit", 2), change("defaultValue", {"mode": "custom", "value": "too long"})], text)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertNotIn("result", result)
        self.assertEqual(result["diagnostics"][0]["code"], "INVALID_DEFAULT_RANGE")
        date = self.compound("DatePicker", "minTimeCondition", {
            "type": "object", "properties": {"enabled": {"const": True}, "source": {"const": "fixed"}, "fixedValue": {"type": "string"}},
            "required": ["enabled", "source", "fixedValue"], "additionalProperties": False})
        date["currentSchema"]["fields"][0]["props"]["format"] = "YYYY-MM-DD"
        result = run([change("minTimeCondition", {"enabled": True, "source": "fixed", "fixedValue": "2026-12-01"}), change("defaultValue", {"mode": "custom", "value": "2026-01-01"})], date)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertNotIn("result", result)
        self.assertEqual(result["diagnostics"][0]["code"], "INVALID_DEFAULT_RANGE")

    def test_numeric_and_selection_defaults_respect_final_limits(self):
        bound = {"type": "object", "properties": {"value": {"type": "number"}}, "required": ["value"], "additionalProperties": False}
        number = self.compound("NumberPicker", "numericRange", {"type": "object", "properties": {"min": bound, "max": bound}, "additionalProperties": False}, {})
        number["currentSchema"]["fields"][0]["props"].update(defaultValueConfig="custom", defaultValue=20)
        result = run([change("numericRange", {"max": {"value": 10}})], number)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertEqual(result["diagnostics"][0]["code"], "INVALID_DEFAULT_RANGE")
        selection = self.compound("SelectMulti", "selectionLimit", {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1}}, "required": ["count"], "additionalProperties": False})
        selection["currentSchema"]["fields"][0]["props"]["defaultValue"] = ["a", "b"]
        result = run([change("selectionLimit", {"count": 1})], selection)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertEqual(result["diagnostics"][0]["code"], "INVALID_DEFAULT_RANGE")

    def test_time_current_anchor_matches_panel(self):
        value = {"enabled": True, "source": "dynamic", "dynamicMode": "current", "dynamicAnchor": "today"}
        schema = {"type": "object", "properties": {"enabled": {"const": True}, "source": {"const": "dynamic"}, "dynamicMode": {"const": "current"}, "dynamicAnchor": {"const": "today"}}, "required": list(value), "additionalProperties": False}
        context = self.compound("TimePicker", "minTimeCondition", schema)
        result = run([change("minTimeCondition", value)], context)
        self.assertEqual(result["status"], "ready", result)
        for operation in ("clear", "reset"):
            context["currentSchema"]["fields"][0]["props"]["minTimeCondition"] = deepcopy(value)
            self.assertEqual(run([change("minTimeCondition", operation=operation)], context)["status"], "ready")
