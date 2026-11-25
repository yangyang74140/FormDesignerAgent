"""Property compiler regression tests, loaded independently of proposal imports."""
from copy import deepcopy
import unittest

from compiler_package import load_compiler_module
from test_form_field_list import assert_action_draft, assert_non_executable

MODULE = load_compiler_module("properties")
COMPONENT_RULES = load_compiler_module("components")
compile_property_request = MODULE.compile_property_request


def host(component="Input"):
    properties = {prop: {"operations": ["set", "clear", "unset", "reset", "copy", "query"]} for prop in COMPONENT_RULES.property_names(component)}
    return {
        "target": {"schemaId": "form", "revision": "r1"},
        "canvas": {"layoutMode": "flow", "device": "pc"},
        "currentSchema": {"fields": [{"id": "a", "componentName": component, "props": {"label": "说明", "name": "note", "identifiers": {"name": "note"}, "placeholder": "旧", "size": "medium", "defaultValueConfig": "undefined", "access": {"required": False, "visible": False, "editable": False, "forbidManualInput": False}}}], "props": {"textAlign": "right"}},
        "selection": {"nodeId": "a"},
        "capabilities": {"supportedProposalContracts": ["form_change_proposal.v1"], "supportedPresentationKinds": ["shared.form-change-confirm"], "catalogVersion": "properties.v1", "components": {component: {"properties": properties}}},
        "nodePolicies": {"a": {"system": False, "saved": False, "disabledName": False, "writable": True}},
        "supportedActionVersions": {"form_change_actions.v1": True},
    }


def change(prop="placeholder", value="新", operation="set", **extra):
    slots = {"node_id": "a", "property": prop, "operation": operation, **extra}
    if operation == "set":
        slots["value"] = value
    return {"capability": "form.property.change", "slots": slots}


def run(items, context=None, kind="property_changes", base=None):
    return compile_property_request([{"capability": "proposal.begin", "slots": {"result_kind": kind, "summary": "调整属性"}}, *items], context if context is not None else host(), base or {"protocol": "form-agent.v1", "schemaVersion": "1.1.0", "proposalId": "p1"})


class PropertyTests(unittest.TestCase):
    def rejected(self, result, code=None, status="unsupported"):
        self.assertEqual(result["status"], status, result)
        assert_non_executable(self, result)
        if code:
            self.assertEqual(result["diagnostics"][0]["code"], code, result)

    def property_action(self, result, index=0):
        self.assertEqual(result["status"], "ready", result)
        assert_action_draft(self, result, "shared.form-change-confirm", property_actions=True)
        return result["actions"][index]

    def apply_property_action(self, context, action):
        payload = action["payload"]
        node = deepcopy(next(node for node in context["currentSchema"]["fields"] if node["id"] == payload["nodeId"]))
        rules = COMPONENT_RULES.get_component_rules(node["componentName"])
        prop, operation = payload["property"], payload["operation"]
        self.assertEqual(action["preconditions"]["before"], rules.snapshot(node, prop))
        if operation in {"set", "copy"}:
            after = {"exists": True, "value": deepcopy(payload["value"])}
        else:
            self.assertNotIn("value", payload)
            definition = context["capabilities"]["components"][node["componentName"]]["properties"][prop]
            after = rules.after(node, prop, operation, {}, definition)
        effects = rules.simulate(node, prop, after)
        self.assertEqual(effects, action["display"]["effects"])
        return node

    def test_stable_detached_checklist_and_mapping(self):
        context = host()
        before = deepcopy(context)
        items = [change("extra", "描述", selected=False)]
        first = run(items, context)
        self.assertEqual(first, run(items, context))
        self.assertEqual(context, before)
        action = self.property_action(first)
        self.assertEqual(action["payload"]["property"], "description")
        self.assertFalse(action["display"]["selectedByDefault"])
        self.assertEqual(action["preconditions"]["before"], {"exists": False})
        self.assertEqual(action["payload"]["value"], "描述")
        applied = self.apply_property_action(context, action)
        self.assertEqual(applied["props"]["extra"], "描述")
        action["payload"]["value"] = "mutated"
        self.assertEqual(context, before)
        self.assertEqual(run(items, context)["actions"][0]["payload"]["value"], "描述")

    def test_required_alias_access_effect(self):
        for alias in ("required", "必添", "requried"):
            result = run([change(alias, True)])
            self.assertEqual(result["status"], "ready", result)
            action = self.property_action(result)
            self.assertEqual(action["preconditions"]["before"], {"exists": True, "value": False})
            self.assertIn("显示和编辑", action["display"]["effects"][0])
            self.assertNotIn("access", action["payload"])
            applied = self.apply_property_action(host(), action)
            self.assertTrue(all(applied["props"]["access"][key] for key in ("visible", "editable", "required")))

    def test_all_seven_components_support_common_semantics(self):
        for component in sorted(MODULE.COMPONENTS):
            with self.subTest(component=component):
                result = run([change()], host(component))
                action = self.property_action(result)
                self.assertEqual(action["payload"]["componentName"], component)

    def test_finite_types_and_intrinsic_ranges(self):
        for value in (True, "5", float("nan"), float("inf"), 11, 2):
            self.rejected(run([change("rows", value)], host("Input.TextArea")))
        self.assertEqual(run([change("rows", 5)], host("Input.TextArea"))["status"], "ready")
        self.rejected(run([change("description", "x" * 201)]), "INVALID_VALUE")
        self.rejected(run([change("label", "")]), "INVALID_VALUE")
        self.rejected(run([change("size", "middle")]), "INVALID_VALUE")
        self.rejected(run([change("required", 1)]), "INVALID_VALUE")

    def test_saved_locks_and_missing_policies(self):
        for component, prop, value in (("NumberPicker", "precision", 2), ("DatePicker", "format", "YYYY"), ("TimePicker", "format", "HH:mm")):
            for flag in ("saved", "disabledName"):
                context = host(component)
                context["nodePolicies"]["a"][flag] = True
                self.rejected(run([change(prop, value)], context), "SAVED_PROPERTY_LOCKED")
        context = host()
        del context["nodePolicies"]
        self.rejected(run([change()], context), "MISSING_NODE_POLICY")
        for key in ("system", "writable", "saved", "disabledName"):
            context = host()
            del context["nodePolicies"]["a"][key]
            self.rejected(run([change()], context), "MISSING_NODE_POLICY")
        context = host()
        context["nodePolicies"]["a"]["system"] = True
        self.rejected(run([change()], context), "NODE_READ_ONLY")

    def test_layout_device_restrictions(self):
        context = host()
        context["canvas"]["layoutMode"] = "grid"
        self.rejected(run([change("textAlign", "left")], context), "LAYOUT_RESTRICTED")
        context = host()
        context["canvas"]["device"] = "mobile"
        self.rejected(run([change("size", "large")], context), "DEVICE_RESTRICTED")

    def test_default_zero_and_paired_clear(self):
        context = host("NumberPicker")
        result = run([change("defaultValue", {"mode": "custom", "value": 0})], context)
        self.assertEqual(result["status"], "ready", result)
        action = self.property_action(result)
        self.assertEqual(action["payload"]["value"], {"mode": "custom", "value": 0})
        self.assertIn("成对", action["display"]["effects"][0])
        applied = self.apply_property_action(context, action)
        self.assertEqual(applied["props"]["defaultValue"], 0)
        self.assertEqual(applied["props"]["defaultValueConfig"], "custom")
        context["currentSchema"]["fields"][0]["props"].update(defaultValueConfig="custom", defaultValue=4)
        cleared = run([change("defaultValue", operation="clear")], context)
        action = self.property_action(cleared)
        self.assertEqual(action["preconditions"]["before"], {"exists": True, "value": {"mode": "custom", "value": 4}})
        self.assertEqual(action["payload"]["operation"], "clear")
        applied = self.apply_property_action(context, action)
        self.assertEqual(applied["props"]["defaultValueConfig"], "undefined")
        self.assertNotIn("defaultValue", applied["props"])
        for value in ({"mode": "custom", "value": "0"}, {"mode": "custom", "value": True}, {"mode": "formula", "value": "1+1"}):
            self.rejected(run([change("defaultValue", value)], context))

    def test_date_format_and_default_validation(self):
        context = host("DatePicker")
        context["currentSchema"]["fields"][0]["props"]["format"] = "YYYY-MM-DD"
        self.rejected(run([change("defaultValue", {"mode": "custom", "value": "2026-02-30"})], context), "INVALID_DATE")
        result = run([change("defaultValue", {"mode": "custom", "value": "2026-11-18"})], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(self.property_action(run([change("description", "说明")], context))["display"]["effects"], [])
        self.assertIn("日期格式", self.property_action(run([change("format", "YYYY")], context))["display"]["effects"][0])

    def test_select_defaults_real_values_and_copy_incompatibility(self):
        context = host("SelectSingle")
        context["currentSchema"]["fields"][0]["props"]["options"] = {"dataSource": [{"primaryKey": "1", "value": "business", "label": "名称", "disabled": False}]}
        result = run([change("defaultValue", "business")], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertIn("activeKey", self.property_action(result)["display"]["effects"][0])
        for value in ("名称", "1", "missing"):
            self.rejected(run([change("defaultValue", value)], context), "INVALID_DEFAULT_OPTION")
        source = deepcopy(host("NumberPicker")["currentSchema"]["fields"][0])
        source["id"] = "b"
        source["props"].update(defaultValueConfig="custom", defaultValue=0)
        context = host()
        context["capabilities"]["components"].update(host("NumberPicker")["capabilities"]["components"])
        context["currentSchema"]["fields"].append(source)
        context["nodePolicies"]["b"] = deepcopy(context["nodePolicies"]["a"])
        self.rejected(run([change("defaultValue", operation="copy", source_node_id="b")], context), "INVALID_VALUE")

    def test_copy_resolved_source_snapshot(self):
        context = host()
        source = deepcopy(context["currentSchema"]["fields"][0])
        source["id"] = "b"
        source["props"].pop("placeholder")
        context["currentSchema"]["fields"].append(source)
        context["nodePolicies"]["b"] = deepcopy(context["nodePolicies"]["a"])
        context["resolvedProperties"] = {"b": {"placeholder": {"source": "default", "resolvedValue": "有效提示"}}}
        result = run([change(operation="copy", source_node_id="b")], context)
        self.assertEqual(result["status"], "ready", result)
        action = self.property_action(result)
        self.assertEqual(action["payload"]["value"], "有效提示")
        self.assertEqual(action["payload"]["sourceNodeId"], "b")
        self.assertEqual(action["payload"]["sourceProperty"], "placeholder")
        self.assertEqual(action["payload"]["sourceSnapshot"]["stored"], {"exists": False})
        self.assertEqual(self.apply_property_action(context, action)["props"]["placeholder"], "有效提示")

    def test_queries_without_action_version_and_inheritance(self):
        context = host()
        del context["supportedActionVersions"]
        query = {"capability": "form.property.query", "slots": {"use_selection": True, "property": "titleAlign"}}
        result = run([query], context, "property_query")
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["contractVersion"], "form_property_query.v1")
        row = result["presentation"]["items"][0]
        self.assertEqual((row["source"], row["resolvedValue"], row["stored"]), ("inherited", "right", {"exists": False}))
        self.assertTrue(result["presentation"]["readOnly"])
        for key in ("actions", "mode", "actionVersion", "result", "validation"):
            self.assertNotIn(key, result)
        context["resolvedProperties"] = {"a": {"titleAlign": {"source": "inherited", "resolvedValue": "left"}}}
        self.assertEqual(run([query], context, "property_query")["presentation"]["items"][0]["resolvedValue"], "left")

    def test_empty_or_ambiguous_selection_clarifies(self):
        item = change()
        item["slots"].pop("node_id")
        item["slots"]["use_selection"] = True
        context = host()
        context["selection"] = {}
        self.rejected(run([item], context), "TARGET_REQUIRED", "needs_clarification")
        context = host()
        duplicate = deepcopy(context["currentSchema"]["fields"][0])
        duplicate["id"] = "b"
        context["currentSchema"]["fields"].append(duplicate)
        item["slots"] = {"node_label": "说明", "property": "placeholder", "operation": "set", "value": "新"}
        self.rejected(run([item], context), "TARGET_REQUIRED", "needs_clarification")

    def test_action_versions_catalogs_and_operations_fail_closed(self):
        for versions in (None, ["1.0"], ["form_property_actions.v2"]):
            context = host()
            context["supportedActionVersions"] = versions
            self.rejected(run([change()], context), "CHANGE_CONTRACT_UNSUPPORTED")
        context = host()
        del context["capabilities"]["catalogVersion"]
        self.rejected(run([change()], context), "MISSING_CATALOG_VERSION")
        context = host()
        context["capabilities"]["components"]["Input"]["properties"]["placeholder"]["operations"] = ["query"]
        self.rejected(run([change()], context), "OPERATION_UNSUPPORTED")

    def test_reset_missing_vs_local_and_clear_different_from_default(self):
        context = host()
        unchanged = run([change("titleAlign", operation="reset")], context)
        self.assertEqual(unchanged["status"], "no_change")
        assert_non_executable(self, unchanged)
        context["currentSchema"]["fields"][0]["props"]["textAlign"] = "right"
        action = self.property_action(run([change("titleAlign", operation="unset")], context))
        self.assertEqual(action["preconditions"]["before"], {"exists": True, "value": "right"})
        self.assertEqual(action["payload"]["operation"], "unset")
        self.assertNotIn("textAlign", self.apply_property_action(context, action)["props"])
        context = host("SelectSingle")
        for operation, expected in (("clear", False), ("reset", True)):
            with self.subTest(operation=operation):
                action = self.property_action(run([change("allowClear", operation=operation)], context))
                self.assertEqual(action["payload"]["operation"], operation)
                self.assertEqual(self.apply_property_action(context, action)["props"]["allowClear"], expected)
        self.rejected(run([change("label", operation="clear")]), "TITLE_REQUIRED")
        self.rejected(run([change("step", operation="clear")], host("NumberPicker")), "CLEAR_UNSUPPORTED")

    def test_conflicts_and_final_candidate_conditions(self):
        self.rejected(run([change(), change(value="另一值")]), "PROPERTY_CONFLICT")
        self.rejected(run([change("required", True), change("display", False)]), "SEMANTIC_CONFLICT")
        self.rejected(run([change("requiredMessage", "必填")]), "PROPERTY_CONDITION_UNMET", "needs_clarification")
        result = run([change("requiredMessage", "必填"), change("required", True)])
        self.assertEqual(result["status"], "ready", result)
        self.property_action(result)
        actions = result["actions"]
        self.assertEqual(actions[0]["dependsOn"], [actions[1]["actionId"]])
        self.rejected(run([change("requiredMessage", "必填"), change("required", True, selected=False)]), "SELECTION_DEPENDENCY", "needs_clarification")

    def test_identity_prototype_rules_and_unknown_compounds(self):
        for prop in ("name", "identifiers", "__proto__", "constructor", "props.name", "width", "rules", "defaultValueConfig"):
            self.rejected(run([change(prop, "bad")]))
        context = host()
        context["capabilities"]["components"]["Input"]["properties"]["relatedField"].update(valueSchema={"type": "object", "properties": {}, "additionalProperties": False})
        self.rejected(run([change("relatedField", {})], context), "MISSING_COMPOUND_HANDLER")
        result = run([{"capability": "form.property.rule", "slots": {"node_id": "a", "operation": "add", "rule_id": "r", "rule_type": "regex", "value": "script"}}])
        self.rejected(result, "PROPERTY_PROTOCOL_UNSUPPORTED")

    def test_registered_bounded_rule_and_remove(self):
        context = host()
        context["capabilities"]["ruleCatalog"] = {"length": {"handlerId": "length.v1", "components": ["Input"], "operations": ["add", "replace", "remove"], "valueSchema": {"type": "object", "properties": {"max": {"type": "integer", "minimum": 1, "maximum": 200}}, "required": ["max"], "additionalProperties": False}}}
        context["supportedActionVersions"]["form.apply_property_rule"] = [MODULE.PROPERTY_ACTION_VERSION]
        context["rules"] = {"a": []}
        item = {"capability": "form.property.rule", "slots": {"node_id": "a", "operation": "add", "rule_type": "length", "rule_id": "r1", "value": {"max": 10}}}
        original = deepcopy(context)
        self.rejected(run([item], context), "PROPERTY_PROTOCOL_UNSUPPORTED")
        context["rules"]["a"] = [{"id": "r1", "type": "length", "value": {"max": 10}}]
        item["slots"].update(operation="remove")
        item["slots"].pop("value")
        self.rejected(run([item], context), "PROPERTY_PROTOCOL_UNSUPPORTED")
        self.assertEqual(original["rules"], {"a": []})

    def test_linkage_rejected_even_with_registered_legacy_authorization(self):
        context = host()
        context["capabilities"]["linkageCatalog"] = {"visible": {"handlerId": "visible.v1", "components": ["Input"], "operations": ["add"]}}
        context["supportedActionVersions"]["form.apply_property_linkage"] = [MODULE.PROPERTY_ACTION_VERSION]
        item = {"capability": "form.property.linkage", "slots": {"node_id": "a", "operation": "add", "linkage_type": "visible", "linkage_id": "l1", "value": {"op": "eq", "nodeId": "a", "value": "yes"}}}
        self.rejected(run([item], context), "PROPERTY_PROTOCOL_UNSUPPORTED")

    def test_undo_current_history_only_and_no_inverse_patch(self):
        context = host()
        context["history"] = {"current": {"canUndo": True, "transactionId": "tx1", "revision": "r1"}}
        item = {"capability": "form.property.undo", "slots": {"transaction_id": "tx1"}}
        self.rejected(run([item], context, "property_undo"), "ACTION_VERSION_UNSUPPORTED")
        context["supportedActionVersions"]["form.undo_property_transaction"] = [MODULE.PROPERTY_ACTION_VERSION]
        result = run([item], context, "property_undo")
        self.assertEqual(result["actions"][0]["payload"], {"transactionId": "tx1", "revision": "r1"})
        context["history"]["current"]["revision"] = "old"
        self.rejected(run([item], context, "property_undo"), "UNDO_UNAVAILABLE")

    def test_malformed_metadata_and_ir_never_escape(self):
        for context in ({}, {"selection": []}, None, []):
            self.rejected(run([change()], context if context is not None else {}))
        for items in (None, [None], [{"capability": "form.property.change", "slots": []}]):
            result = compile_property_request(items, host(), {})
            self.rejected(result)
        context = host()
        context["capabilities"]["components"] = []
        self.rejected(run([change()], context))

    def test_documented_capability_policy_shape_and_read_denial(self):
        context = host()
        context.pop("nodePolicies")
        context["capabilities"]["nodePolicies"] = {"a": {"canRead": True, "canModify": True, "allowedProperties": ["placeholder"]}}
        self.assertEqual(run([change()], context)["status"], "ready")
        self.rejected(run([change("description", "文案")], context), "PROPERTY_READ_ONLY")
        query = {"capability": "form.property.query", "slots": {"node_id": "a", "property": "placeholder"}}
        context["capabilities"]["nodePolicies"]["a"]["canRead"] = False
        self.rejected(run([query], context, "property_query"), "QUERY_UNSUPPORTED")

    def test_final_date_format_is_validated_independent_of_ir_order(self):
        context = host("DatePicker")
        context["currentSchema"]["fields"][0]["props"]["format"] = "YYYY-MM-DD"
        default = change("defaultValue", {"mode": "custom", "value": "2026-11"})
        fmt = change("format", "YYYY-MM")
        for items in ([default, fmt], [fmt, default]):
            self.assertEqual(run(items, context)["status"], "ready")

    def test_numeric_range_and_conditional_format_message(self):
        context = host("NumberPicker")
        self.rejected(run([change("minEnable", True), change("min", 10), change("maxEnable", True), change("max", 5)], context), "INVALID_RANGE")
        self.assertEqual(run([change("min", 0), change("minEnable", True)], context)["status"], "ready")
        self.rejected(run([change("formatMessage", "提示")]), "PROPERTY_CONDITION_UNMET", "needs_clarification")

    def test_registered_weekday_structure_and_semantics(self):
        context = host("DatePicker")
        context["currentSchema"]["fields"][0]["props"]["format"] = "YYYY-MM-DD"
        definition = context["capabilities"]["components"]["DatePicker"]["properties"]["disabledDays"]
        definition.update(handlerId="weekdays.v1", valueSchema={"type": ["object", "null"], "properties": {"enabled": {"type": "boolean"}, "days": {"type": "array", "items": {"type": "string"}}}, "required": ["enabled", "days"], "additionalProperties": False}, clearValue=None)
        self.assertEqual(run([change("disabledDays", {"enabled": True, "days": ["1", "2"]})], context)["status"], "ready")
        self.rejected(run([change("disabledDays", {"enabled": True, "days": []})], context), "INVALID_WEEKDAYS")
        self.assertEqual(run([change("disabledDays", operation="clear")], context)["status"], "ready")

    def test_text_limit_copy_reset_and_default_cleanup(self):
        context = host()
        props = context["currentSchema"]["fields"][0]["props"]
        props.update(showLimitHint=True, textMaxLength=20)
        source = deepcopy(context["currentSchema"]["fields"][0])
        source["id"] = "b"
        source["props"]["textMaxLength"] = 30
        context["currentSchema"]["fields"].append(source)
        context["nodePolicies"]["b"] = deepcopy(context["nodePolicies"]["a"])
        result = run([change("textLengthLimit", operation="copy", source_node_id="b")], context)
        self.assertEqual(result["status"], "ready", result)
        action = self.property_action(result)
        self.assertEqual(action["payload"]["value"], 30)
        self.assertEqual(action["payload"]["sourceSnapshot"]["stored"]["value"], {"enabled": True, "maxLength": 30})
        self.assertEqual(self.apply_property_action(context, action)["props"]["textMaxLength"], 30)
        reset = run([change("textLengthLimit", operation="reset")], context)
        action = self.property_action(reset)
        self.assertEqual(action["payload"]["operation"], "reset")
        applied = self.apply_property_action(context, action)
        self.assertFalse(applied["props"]["showLimitHint"])
        self.assertEqual(applied["props"]["textMaxLength"], 200)
        props["defaultValue"] = "stale"
        cleared = self.property_action(run([change("defaultValue", operation="clear")], context))
        self.assertNotIn("defaultValue", self.apply_property_action(context, cleared)["props"])

    def test_ir_extraneous_slots_and_unimplemented_json_schema(self):
        self.rejected(run([change(path=["props", "placeholder"])]), "INVALID_IR")
        context = host()
        context["capabilities"]["components"]["Input"]["properties"]["placeholder"]["valueSchema"] = {"type": "string", "not": {"const": "x"}}
        self.rejected(run([change()], context), "UNSUPPORTED_VALUE_SCHEMA")

    def test_component_registry_separates_generation_and_property_support(self):
        self.assertEqual(COMPONENT_RULES.FLOW_COMPONENTS, ("Input", "Input.TextArea", "DatePicker", "TimePicker", "NumberPicker", "SelectSingle", "SelectMulti", "CheckboxGroup", "Switch"))
        self.assertEqual(COMPONENT_RULES.OPTION_COMPONENTS, {"SelectSingle", "SelectMulti", "CheckboxGroup"})
        self.assertEqual(set(COMPONENT_RULES.COMPONENT_LABELS), set(COMPONENT_RULES.FLOW_COMPONENTS))
        self.assertEqual(COMPONENT_RULES.PROPERTY_COMPONENTS, MODULE.COMPONENTS)
        for component in ("CheckboxGroup", "Switch"):
            with self.subTest(component=component):
                with self.assertRaises(KeyError):
                    COMPONENT_RULES.property_names(component)
                context = host()
                context["currentSchema"]["fields"][0]["componentName"] = component
                self.rejected(run([change()], context), "UNSUPPORTED_COMPONENT")

    def test_composed_family_rules_keep_specific_overrides_and_detach_metadata(self):
        rules = COMPONENT_RULES.get_component_rules("Input")
        self.assertIn("textLengthLimit", COMPONENT_RULES.property_names("Input.TextArea"))
        self.assertNotIn("formatValidation", COMPONENT_RULES.property_names("Input.TextArea"))
        self.assertNotIn("allowClear", COMPONENT_RULES.property_names("SelectMulti"))
        self.assertNotIn("disabledDays", COMPONENT_RULES.property_names("TimePicker"))
        self.assertNotIn("minuteStep", COMPONENT_RULES.property_names("DatePicker"))
        input_format = rules.intrinsic_schema("format")
        date_format = COMPONENT_RULES.get_component_rules("DatePicker").intrinsic_schema("format")
        time_format = COMPONENT_RULES.get_component_rules("TimePicker").intrinsic_schema("format")
        self.assertIn("email", input_format["enum"])
        self.assertNotIn("email", date_format["enum"])
        self.assertIn("YYYY", date_format["enum"])
        self.assertNotIn("YYYY", time_format["enum"])
        input_format["enum"].clear()
        rules.properties["size"].schema["enum"].clear()
        rules.properties.clear()
        self.assertIn("email", COMPONENT_RULES.get_component_rules("Input").intrinsic_schema("format")["enum"])
        for component in ("Input", "Input.TextArea"):
            self.assertEqual(COMPONENT_RULES.get_component_rules(component).intrinsic_schema("size")["enum"], ["small", "medium", "large"])

    def test_temporal_range_branches_and_final_format_dependencies(self):
        context = host("TimePicker")
        context["currentSchema"]["fields"][0]["props"]["format"] = "HH:mm:ss"
        condition_schema = {"type": ["object", "null"], "properties": {
            "enabled": {"type": "boolean"}, "source": {"type": "string"},
            "fixedValue": {"type": "string"}, "dynamicMode": {"type": "string"},
            "dynamicUnit": {"type": "string"}, "offsetValue": {"type": "number"},
        }, "required": ["enabled", "source"], "additionalProperties": False}
        for prop in ("minTimeCondition", "maxTimeCondition"):
            context["capabilities"]["components"]["TimePicker"]["properties"][prop].update(handlerId="time-range", valueSchema=condition_schema)
        current = {"enabled": True, "source": "dynamic", "dynamicMode": "current"}
        self.assertEqual(run([change("minTimeCondition", current)], context)["status"], "ready")
        offset = {**current, "dynamicMode": "after", "dynamicUnit": "day", "offsetValue": 1}
        self.rejected(run([change("minTimeCondition", offset)], context), "INVALID_TIME_CONDITION")
        lower = {"enabled": True, "source": "fixed", "fixedValue": "12:00:00"}
        upper = {**lower, "fixedValue": "11:00:00"}
        self.rejected(run([change("minTimeCondition", lower), change("maxTimeCondition", upper)], context), "INVALID_RANGE")
        date = host("DatePicker")
        date["currentSchema"]["fields"][0]["props"]["format"] = "YYYY-MM-DD"
        default = change("defaultValue", {"mode": "custom", "value": "2026-11"})
        self.rejected(run([default, change("format", "YYYY-MM", selected=False)], date), "SELECTION_DEPENDENCY", "needs_clarification")

    def test_choice_option_identity_and_relations_survive_family_helpers(self):
        context = host("SelectSingle")
        option = {"primaryKey": "pk", "value": "business", "label": "名称", "activeKey": False, "disabled": False}
        context["currentSchema"]["fields"][0]["props"]["options"] = {"dataSource": [option], "relatedParentField": {"parentFieldName": "parent"}}
        option_schema = {"type": "object", "properties": {
            "primaryKey": {"type": "string"}, "value": {"type": "string"},
            "label": {"type": "string"}, "activeKey": {"type": "boolean"}, "disabled": {"type": "boolean"},
        }, "required": ["primaryKey", "value", "activeKey", "disabled"], "additionalProperties": False}
        options_schema = {"type": "object", "properties": {
            "dataSource": {"type": "array", "items": option_schema}, "isColor": {"type": "boolean"},
            "relatedParentField": {"type": "object", "properties": {"parentFieldName": {"type": "string"}}, "required": ["parentFieldName"], "additionalProperties": False},
        }, "required": ["dataSource"], "additionalProperties": False}
        context["capabilities"]["components"]["SelectSingle"]["properties"]["options"].update(handlerId="options", valueSchema=options_schema)
        value = {"dataSource": [{**option, "activeKey": True}], "isColor": True, "relatedParentField": {"parentFieldName": "parent"}}
        before = deepcopy(context)
        result = run([change("options", value), change("defaultValue", "business")], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(context, before)
        self.property_action(result)
        actions = result["actions"]
        self.assertEqual(actions[1]["dependsOn"], [actions[0]["actionId"]])
        self.assertIn("颜色", actions[0]["display"]["effects"][0])
        self.assertEqual(actions[0]["payload"]["value"], value)
        removed = {**value, "dataSource": []}
        self.rejected(run([change("options", removed)], context), "OPTION_REFERENCE_CHECK_REQUIRED")
        renamed = deepcopy(value)
        renamed["dataSource"][0]["value"] = "new-business"
        self.rejected(run([change("options", renamed)], context), "OPTION_IDENTITY_CHANGED")
        lost_relation = {"dataSource": value["dataSource"]}
        self.rejected(run([change("options", lost_relation)], context), "OPTION_RELATION_CHANGED")

    def test_native_capability_schema_fresh_and_complete(self):
        definitions = MODULE.property_capabilities()
        self.assertEqual(len(definitions), 3)
        schema = definitions[0]["slots_schema"]
        self.assertEqual(schema["properties"]["selected"]["default"], True)
        self.assertEqual(schema["properties"]["operation"]["enum"], ["set", "clear", "unset", "reset", "copy"])
        definitions[0]["slots_schema"]["properties"].clear()
        self.assertIn("property", MODULE.property_capabilities()[0]["slots_schema"]["properties"])


if __name__ == "__main__":
    unittest.main()
