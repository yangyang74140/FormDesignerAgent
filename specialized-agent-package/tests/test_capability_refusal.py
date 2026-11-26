"""Missing host capabilities must never produce guessed component properties."""

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from test_form_field_list import assert_non_executable, blank_context, compile_fields
from test_form_proposal import compile_items, host_context
from test_properties import change, host as property_host, run as compile_properties
import test_output_preview


class CapabilityRefusalTests(unittest.TestCase):
    def refused(self, proposal, reason):
        self.assertEqual(proposal["status"], "unsupported", proposal)
        assert_non_executable(self, proposal)
        self.assertIn(reason, proposal["summary"])
        self.assertIn(reason, proposal["diagnostics"][0]["message"])

    def action_items(self, action, payload):
        return [
            {"capability": "proposal.begin", "slots": {"summary": "验证组件能力", "result_kind": "form_actions"}},
            {"capability": action, "slots": {"payload": payload}},
        ]

    def test_add_and_convert_require_a_nonempty_host_component_catalog(self):
        for catalog in (None, [], {}):
            for action, payload in (
                ("form.add_component", {"clientRef": "person-name", "componentName": "Input", "props": {"label": "姓名"}, "target": {"kind": "root"}}),
                ("form.convert_component", {"fieldId": "draft-choice", "componentName": "Input"}),
            ):
                context = host_context()
                if catalog is None:
                    context.context["capabilities"].pop("components")
                else:
                    context.context["capabilities"]["components"] = catalog
                with self.subTest(catalog=catalog, action=action):
                    self.refused(compile_items(self.action_items(action, payload), context), "组件目录")

    def test_explicitly_unsupported_components_cannot_be_added_or_converted(self):
        for action, payload in (
            ("form.add_component", {"clientRef": "person-name", "componentName": "Input", "props": {"label": "姓名"}, "target": {"kind": "root"}}),
            ("form.convert_component", {"fieldId": "draft-choice", "componentName": "Input"}),
        ):
            context = host_context()
            context.context["capabilities"]["components"] = {"Input": {"supported": False, "writableProps": ["label"]}}
            with self.subTest(action=action):
                self.refused(compile_items(self.action_items(action, payload), context), "不支持组件")
        context = blank_context()
        context["capabilities"] = deepcopy(context["capabilities"])
        context["capabilities"]["components"]["Input"]["supported"] = False
        self.refused(compile_fields([self.field()], context), "不支持组件")

    def field(self, **extra):
        return {"client_ref": "person-name", "component_name": "Input", "label": "姓名", "name": "person_name", **extra}

    def test_components_outside_the_host_or_local_catalog_are_refused(self):
        for component in ("Switch", "InventedWidget"):
            context = host_context()
            context.context["capabilities"]["components"] = {"Input": {"writableProps": ["label"]}, "InventedWidget": {"writableProps": ["label"]}}
            for action, payload in (
                ("form.add_component", {"clientRef": "probe", "componentName": component, "props": {"label": "测试"}, "target": {"kind": "root"}}),
                ("form.convert_component", {"fieldId": "draft-choice", "componentName": component}),
            ):
                with self.subTest(component=component, action=action):
                    self.refused(compile_items(self.action_items(action, payload), context), "组件")

    def test_field_definition_cannot_silently_drop_unknown_properties(self):
        for extra in ({"disabled": True}, {"props": {"disabled": True}}, {"width": 200}):
            with self.subTest(extra=extra):
                self.refused(compile_fields([self.field(**extra)]), "不支持")

    def test_raw_writes_require_an_explicit_nonempty_property_allowlist(self):
        for metadata in ({}, {"writableProps": []}, {"writableProps": "label"}, {"writableProps": [], "editableProps": ["label"]}):
            context = host_context()
            context.context["capabilities"]["components"] = {"Input": metadata}
            actions = (
                ("form.add_component", {"clientRef": "person-name", "componentName": "Input", "props": {"label": "姓名", "disabled": True}, "target": {"kind": "root"}}),
                ("form.update_component", {"fieldId": "reason", "changes": {"disabled": True}}),
            )
            for action, payload in actions:
                with self.subTest(metadata=metadata, action=action):
                    self.refused(compile_items(self.action_items(action, payload), context), "可写属性")
            generation_context = blank_context()
            generation_context["capabilities"]["components"] = {"Input": metadata}
            with self.subTest(metadata=metadata, action="form.field.define"):
                self.refused(compile_fields([self.field()], generation_context), "可写属性")

    def test_declared_properties_work_but_disabled_is_not_inferred(self):
        context = host_context()
        context.context["capabilities"]["components"] = {"Input": {"writableProps": ["label", "name"]}}
        original = deepcopy(context.context)
        payload = {"clientRef": "person-name", "componentName": "Input", "props": {"label": "姓名", "name": "person_name"}, "target": {"kind": "root"}}
        result = compile_items(self.action_items("form.add_component", payload), context)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["actions"][0]["payload"]["props"], payload["props"])
        payload["props"]["disabled"] = True
        self.refused(compile_items(self.action_items("form.add_component", payload), context), "禁用")
        self.assertEqual(context.context, original)

    def test_undeclared_properties_cannot_hide_in_action_payload(self):
        for action, payload in (
            ("form.add_component", {"clientRef": "person-name", "componentName": "Input", "target": {"kind": "root"}, "disabled": True}),
            ("form.convert_component", {"fieldId": "draft-choice", "componentName": "Input", "props": {"disabled": True}}),
        ):
            with self.subTest(action=action):
                self.refused(compile_items(self.action_items(action, payload)), "不支持")

    def test_semantic_disabled_is_refused_without_inventing_an_edit_operation(self):
        result = compile_properties([change("disabled", True)])
        self.assertEqual(result["status"], "unsupported", result)
        assert_non_executable(self, result)
        self.assertIn("暂时还不支持禁用", result["summary"])
        self.assertIn("disabled", result["diagnostics"][0]["message"])

    def test_missing_property_catalog_still_explains_disabled_is_unsupported(self):
        context = host_context()
        context.context["capabilities"]["components"] = {"Input": {}}
        items = self.action_items("form.update_component", {"fieldId": "reason", "changes": {"disabled": True}})
        self.refused(compile_items(items, context), "暂时还不支持禁用")

    def test_mixed_batch_refusal_keeps_no_partial_actions_or_snapshot_changes(self):
        context = host_context()
        original = deepcopy(context.context)
        items = self.action_items("form.update_component", {"fieldId": "reason", "changes": {"label": "姓名"}})
        items.append({"capability": "form.update_component", "slots": {"payload": {"fieldId": "reason", "changes": {"disabled": True}}}})
        self.refused(compile_items(items, context), "暂时还不支持禁用")
        self.assertEqual(context.context, original)
        self.refused(compile_properties([change("placeholder", "姓名"), change("disabled", True)]), "禁用")

    def test_editable_props_fallback_requires_an_absent_writable_props_key(self):
        context = host_context()
        context.context["capabilities"]["components"] = {"Input": {"editableProps": ["label"]}}
        result = compile_items(self.action_items("form.update_component", {"fieldId": "reason", "changes": {"label": "姓名"}}), context)
        self.assertEqual(result["status"], "ready", result)

    def test_explicit_authorized_edit_permission_remains_supported(self):
        context = property_host()
        context["currentSchema"]["fields"][0]["props"]["access"]["editable"] = True
        result = compile_properties([change("edit", False)], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["actions"][0]["payload"]["property"], "edit")

    def test_option_updates_require_a_writable_property_catalog(self):
        context = host_context()
        context.context["capabilities"]["components"] = {"SelectSingle": {}}
        items = self.action_items("form.update_component_options", {"fieldId": "draft-choice", "options": [{"label": "A", "value": "a"}]})
        self.refused(compile_items(items, context), "可写属性")

    def test_rule_component_references_do_not_authorize_components(self):
        context = host_context()
        context.context["capabilities"].pop("components")
        context.context["capabilities"]["ruleCatalog"] = {"required": {"components": ["Input"]}}
        items = self.action_items("form.add_component", {"clientRef": "person-name", "componentName": "Input", "props": {}, "target": {"kind": "root"}})
        self.refused(compile_items(items, context), "组件目录")

    def test_component_supported_false_applies_to_semantic_properties(self):
        context = property_host()
        context["capabilities"]["components"]["Input"]["supported"] = False
        result = compile_properties([change("placeholder", "请输入姓名")], context)
        self.assertEqual(result["status"], "unsupported", result)
        assert_non_executable(self, result)


class CapabilityRefusalBoundaryTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        test_output_preview.OutputPreviewTests.setUpClass.__func__(cls)

    async def test_missing_capability_returns_an_explanatory_unsupported_event(self):
        scenarios = []
        context = blank_context()
        context["capabilities"]["components"] = {"Input": {"writableProps": ["label", "name", "required"]}}
        for extra, reason in (({"disabled": True}, "暂时还不支持禁用"), ({"width": 200}, "width")):
            scenarios.append((deepcopy(context), [
                {"capability": "proposal.begin", "slots": {"summary": "生成禁用的姓名字段", "result_kind": "form_fields"}},
                {"capability": "form.field.define", "slots": {"client_ref": "person-name", "component_name": "Input", "label": "姓名", "name": "person_name", **extra}},
            ], reason))
        action_context = blank_context()
        action_context["capabilities"].pop("components")
        action_context["capabilities"]["actions"] = ["form.add_component"]
        scenarios.append((action_context, [
            {"capability": "proposal.begin", "slots": {"summary": "生成姓名", "result_kind": "form_actions"}},
            {"capability": "form.add_component", "slots": {"payload": {"clientRef": "person-name", "componentName": "Input", "target": {"kind": "root"}}}},
        ], "组件目录"))
        for key in ("capabilities", "supportedActionVersions"):
            missing_context = deepcopy(context)
            missing_context.pop(key)
            if key == "supportedActionVersions":
                missing_context["capabilities"].pop(key)
            scenarios.append((missing_context, scenarios[0][1], key))
        for host, items, reason in scenarios:
            with self.subTest(reason=reason):
                step = SimpleNamespace(inputs="生成禁用的姓名字段", context=host, event_publisher=AsyncMock())

                async def generate(**kwargs):
                    return kwargs["compiler"]({"plan_items": items}, None)

                step.native_capability = SimpleNamespace(generate=generate)
                result = await self.agent.generate_form_proposal(step)
                self.assertEqual(result["status"], "completed", result)
                proposal = result["output"]["form_proposal"]
                self.assertEqual(proposal["status"], "unsupported", result)
                self.assertIn(reason, proposal["summary"])
                assert_non_executable(self, proposal)
                step.event_publisher.assert_awaited_once()
                self.assertEqual(step.event_publisher.await_args.args[1]["proposal"], proposal)

    async def test_generator_is_given_only_the_host_component_intersection(self):
        host = blank_context()
        host["capabilities"] = {"components": {"Input": {"writableProps": ["label", "name", "required"]}, "Switch": {"supported": False}, "InventedWidget": {}}}
        step = SimpleNamespace(inputs="生成姓名字段", context=host)

        async def generate(**kwargs):
            field = next(item for item in kwargs["allowed_capabilities"] if item["capability"] == "form.field.define")
            self.assertEqual(field["slots_schema"]["properties"]["component_name"]["enum"], ["Input"])
            return kwargs["compiler"]({"plan_items": [{"capability": "proposal.no_change", "slots": {"summary": "测试"}}]}, None)

        step.native_capability = SimpleNamespace(generate=generate)
        await self.agent.generate_form_proposal(step)

    async def test_missing_host_components_are_not_exposed_as_field_candidates(self):
        host = blank_context()
        host["capabilities"] = {"actions": ["form.add_component"]}
        step = SimpleNamespace(inputs="生成姓名", context=host)

        async def generate(**kwargs):
            self.assertNotIn("form.field.define", [item["capability"] for item in kwargs["allowed_capabilities"]])
            return kwargs["compiler"]({"plan_items": [{"capability": "proposal.unsupported", "slots": {"summary": "缺少组件目录", "code": "MISSING_COMPONENT_CATALOG"}}]}, None)

        step.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(step)
        self.assertEqual(result["output"]["form_proposal"]["status"], "unsupported")
        assert_non_executable(self, result["output"]["form_proposal"])
