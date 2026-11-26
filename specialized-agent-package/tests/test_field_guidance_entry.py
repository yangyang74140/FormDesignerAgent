"""Exercise actual preparation, native compiler callback and waiting handlers."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import test_field_guidance as fixtures
from test_field_guidance import field_ir, slots
from test_form_proposal import compile_items


def plain(kind=None):
    item = {"capability": "proposal.needs_clarification", "slots": {
        "summary": "需要字段信息", "question": "请说明要添加的字段名称和类型", "choices": []}}
    if kind:
        item["slots"]["clarification_kind"] = kind
    return item


def complete_candidate():
    item = field_ir()
    draft = item["slots"]["field_draft"]
    draft["fields"] = draft["fields"][:1]
    draft["groups"] = [{"field": 0, "slot": "semantics", "reason": "字段语义尚未确定", "options": [
        {"label": label, "patch": {"label": label, "name": name, "component_name": "Input"}}
        for label, name in (("联系人", "contact"), ("备注", "memo"), ("手机号", "phone"))]}]
    return item


class FieldEntryTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.RegisteredFieldGuidanceTests.setUpClass.__func__(cls)

    def context(self, items):
        context = fixtures.FieldGuidanceTests().context()
        context.inputs = "添加一个字段"
        responses = iter(items)
        async def generate(**kw):
            return kw["compiler"]({"plan_items": [next(responses)]}, None)
        context.native_capability = SimpleNamespace(generate=AsyncMock(side_effect=generate))
        context.event_publisher = AsyncMock()
        return context

    async def test_empty_clarification_repaired_before_wait_and_direct_compilation(self):
        context = self.context([plain(), complete_candidate()])
        prepared = await self.agent.prepare_form_requirement(context)
        self.assertEqual(prepared["status"], "completed", prepared)
        self.assertEqual(context.native_capability.generate.await_count, 2)
        context.inputs = prepared["output"]
        first = await self.agent.collect_guidance(context)
        replay = await self.agent.collect_guidance(context)
        self.assertEqual(first, replay)
        questions = context.clarification.request_group.await_args.kwargs["questions"]
        self.assertEqual(len(questions[0]["options"]), 4)
        self.assertNotEqual(context.clarification.request.await_args.kwargs["key"], "form_requirement")
        context.inputs = first["output"]
        result = await self.agent.generate_confirmed_proposal(context)
        self.assertEqual(result["output"]["form_proposal"]["status"], "ready")
        props = result["output"]["form_proposal"]["actions"][0]["payload"]["props"]
        self.assertEqual(props["label"], "联系人")
        self.assertEqual(context.native_capability.generate.await_count, 2)

    async def test_repair_is_bounded_and_cannot_guess_ready(self):
        for second in (plain(), plain("field_addition"), {"capability": "proposal.no_change", "slots": {"summary": "完成"}}):
            context = self.context([plain("field_addition"), second])
            result = await self.agent.prepare_form_requirement(context)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(context.native_capability.generate.await_count, 2)
            context.clarification.request.assert_not_awaited()

    async def test_missing_context_reports_without_repair(self):
        for key in ("currentSchema", "capabilities", "supportedActionVersions"):
            context = self.context([plain()])
            context.context.pop(key)
            result = await self.agent.prepare_form_requirement(context)
            self.assertEqual(result["error_code"], "form_guidance_host_context_missing")
            context.native_capability.generate.assert_awaited_once()

    async def test_property_and_scenario_not_routed_to_fields(self):
        from test_guidance import scenario
        for item in (plain("property"), plain("target"), scenario()):
            context = self.context([item])
            result = await self.agent.prepare_form_requirement(context)
            self.assertEqual(result["status"], "completed")
            self.assertNotIn("fieldGuidance", result["output"]["proposal"])
            context.native_capability.generate.assert_awaited_once()

    async def test_unclassified_property_repair_preserves_request(self):
        context = self.context([plain(), plain("property")])
        context.inputs = "给手机号字段添加一个校验规则"
        result = await self.agent.prepare_form_requirement(context)
        self.assertEqual(result["output"]["proposal"]["clarificationKind"], "property")
        repair_input = context.native_capability.generate.await_args.kwargs["input_data"]["user_input"]
        self.assertEqual(repair_input["original_request"], context.inputs)
        self.assertNotIn("fieldGuidance", result["output"]["proposal"])

    async def test_invalid_repair_is_compiler_failure_without_another_attempt(self):
        item = complete_candidate()
        item["slots"]["field_draft"]["groups"][0]["options"][0]["patch"]["component_name"] = "Unknown"
        context = self.context([plain("field_addition"), item])
        result = await self.agent.prepare_form_requirement(context)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(context.native_capability.generate.await_count, 2)
        context.clarification.request_group.assert_not_awaited()

    async def test_explicit_field_direct(self):
        context = self.context([])
        context.inputs = "添加手机号文本字段"
        async def generate(**kw):
            draft = complete_candidate()["slots"]["field_draft"]
            return kw["compiler"]({"plan_items": [
                {"capability": "proposal.begin", "slots": draft["begin"]},
                {"capability": "form.field.define", "slots": dict(draft["fields"][0], label="手机号", name="phone")},
            ]}, None)
        context.native_capability.generate.side_effect = generate
        result = await self.agent.prepare_form_requirement(context)
        self.assertEqual(result["output"]["proposal"]["status"], "ready")
        context.native_capability.generate.assert_awaited_once()

    def test_full_semantics_switch_requires_explicit_residual_cleanup(self):
        item = complete_candidate()
        draft = item["slots"]["field_draft"]
        draft["fields"][0].update(component_name="SelectSingle", options=[{"label": "员工", "value": "employee"}])
        with self.assertRaisesRegex(ValueError, "非选项组件"):
            compile_items([item])
        for option in draft["groups"][0]["options"]:
            option["patch"]["unset"] = ["options"]
        proposal = compile_items([item])
        frozen = proposal["fieldGuidance"]
        field = slots._patch(frozen["fields"], frozen["groups"][0], frozen["groups"][0]["options"][0]["patch"])[0]
        self.assertNotIn("options", field)
        self.assertEqual(field["component_name"], "Input")
        for invalid in (["client_ref"], ["options", "options"], [123]):
            broken = deepcopy(item)
            broken["slots"]["field_draft"]["groups"][0]["options"][0]["patch"]["unset"] = invalid
            with self.assertRaises(ValueError):
                compile_items([broken])

    def test_complete_semantics_cannot_overlap_property_group(self):
        item = complete_candidate()
        draft = item["slots"]["field_draft"]
        draft["groups"][0]["options"][0]["patch"]["placeholder"] = "姓名"
        draft["groups"].append({"field": 0, "slot": "properties", "reason": "提示待定", "options": []})
        with self.assertRaisesRegex(ValueError, "同时修改"):
            compile_items([item])
