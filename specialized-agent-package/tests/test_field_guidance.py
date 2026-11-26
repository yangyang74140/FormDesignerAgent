"""Frozen slot answers must reach the registered compiler without an LLM rerun."""

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from compiler_package import load_compiler_module
from test_form_proposal import host_context, compile_items
import test_output_preview

slots = load_compiler_module("field_guidance")
guidance = load_compiler_module("guidance")


def field_ir():
    return {"capability": "proposal.needs_clarification", "slots": {
        "summary": "确认联系人字段", "question": "已预填联系人，可修改有歧义的内容。",
        "field_draft": {
            "prefill": "在事由后插入联系人及备注，联系人称谓和提示可修改。",
            "begin": {"summary": "插入联系人和备注", "mode": "append", "result_kind": "form_fields",
                      "target": {"kind": "relative", "anchorNodeId": "reason", "position": "after"}},
            "fields": [
                {"client_ref": "contact", "name": "contact", "label": "联系人", "component_name": "Input"},
                {"client_ref": "memo", "name": "memo", "label": "备注", "component_name": "Input", "placeholder": "保留原要求"},
            ],
            "groups": [
                {"field": 0, "slot": "semantics", "reason": "联系人称谓有歧义", "options": [
                    {"label": "紧急联系人", "patch": {"label": "紧急联系人"}},
                    {"label": "日常联系人", "patch": {"label": "日常联系人"}},
                ]},
                {"field": 0, "slot": "properties", "reason": "提示文字有歧义", "options": [
                    {"label": "联系人姓名提示", "patch": {"placeholder": "填写联系人姓名"}},
                ]},
            ],
        },
    }}


def choose(questions, suffix="o0"):
    return {"kind": "group", "answers": {q["id"]: {
        "kind": "selected", "selected_option_id": q["id"] + ":" + suffix,
    } for q in questions}}


class FieldGuidanceTests(unittest.IsolatedAsyncioTestCase):
    def context(self, ir=None):
        return SimpleNamespace(
            context=host_context().context,
            inputs={"original_input": "插入联系人和备注", "proposal": compile_items([ir or field_ir()])},
            clarification=SimpleNamespace(
                request_group=AsyncMock(side_effect=lambda **kw: choose(kw["questions"])),
                request=AsyncMock(side_effect=lambda **kw: {"kind": "selected", "selected_option_id": kw["options"][0]["id"]}),
            ),
        )

    async def test_frozen_group_replay_and_direct_compile(self):
        context = self.context()
        before = deepcopy(context.inputs)
        first = await guidance.collect_guidance(context)
        second = await guidance.collect_guidance(context)
        self.assertEqual(first, second)
        self.assertEqual(context.inputs, before)
        self.assertEqual(context.clarification.request_group.await_args_list[0], context.clarification.request_group.await_args_list[1])
        selected = first["output"]["fieldSelection"]
        result = slots.compile_draft(before["proposal"]["fieldGuidance"], selected["fields"], context)
        self.assertEqual([a["payload"]["target"]["index"] for a in result["actions"]], [1, 2])
        self.assertEqual(result["actions"][0]["payload"]["props"]["label"], "紧急联系人")
        self.assertEqual(result["actions"][1]["payload"]["props"]["placeholder"], "保留原要求")
        self.assertNotIn("fieldGuidance", result)
        self.assertEqual(set(result["presentation"]), {"kind", "title"})
        questions = context.clarification.request_group.await_args.kwargs["questions"]
        self.assertEqual([len(q["options"]) for q in questions], [3, 2])
        self.assertTrue(all(q["options"][-1]["label"] == "自定义" for q in questions))
        self.assertTrue(all(set(o) == {"id", "label"} for q in questions for o in q["options"]))

    async def test_custom_values_are_json_not_natural_language(self):
        context = self.context()
        async def answer(**kw):
            if kw["key"].endswith(":custom"):
                return {"kind": "group", "answers": {q["id"]: {"kind": "text", "text": '{"label":"家属联系人"}'} for q in kw["questions"]}}
            result = choose(kw["questions"])
            question = kw["questions"][0]
            result["answers"][question["id"]]["selected_option_id"] = question["id"] + ":custom"
            return result
        context.clarification.request_group.side_effect = answer
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["output"]["fieldSelection"]["fields"][0]["label"], "家属联系人")
        self.assertEqual(context.clarification.request_group.await_count, 2)

    async def test_regeneration_preserves_confirmed_and_back_restores_previous(self):
        context = self.context()
        controls = iter(("regenerate", "back", "confirm"))
        context.clarification.request.side_effect = lambda **kw: {"kind": "selected", "selected_option_id": kw["key"].removesuffix(":review") + ":" + next(controls)}
        snapshots = []
        async def answer(**kw):
            snapshots.append(deepcopy(kw["questions"]))
            return choose(kw["questions"], "o0" if len(snapshots) == 1 else "keep")
        context.clarification.request_group.side_effect = answer
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["output"]["fieldSelection"]["version"], 3)
        self.assertEqual(result["output"]["fieldSelection"]["fields"][0]["label"], "紧急联系人")
        self.assertIn("紧急联系人", snapshots[1][0]["question"])
        self.assertNotEqual(snapshots[0][0]["id"], snapshots[1][0]["id"])
        self.assertTrue(any(o["label"] == "保留当前值" for o in snapshots[2][0]["options"]))

    async def test_stale_option_partial_group_and_plain_text_fail_closed(self):
        for mode in ("stale", "missing", "text"):
            context = self.context()
            def answer(**kw):
                result = choose(kw["questions"])
                question_id = kw["questions"][0]["id"]
                if mode == "missing":
                    result["answers"].pop(question_id)
                elif mode == "stale":
                    result["answers"][question_id]["selected_option_id"] = "old:v1:g0:o0"
                else:
                    result["answers"][question_id] = {"kind": "text", "text": "改为手机号并校验11位"}
                return result
            context.clarification.request_group.side_effect = answer
            with self.subTest(mode=mode):
                self.assertEqual((await guidance.collect_guidance(context))["status"], "failed")
                context.clarification.request.assert_not_awaited()

    async def test_changed_host_cancel_and_missing_group_support(self):
        context = self.context()
        context.context["target"]["revision"] = "new"
        self.assertEqual((await guidance.collect_guidance(context))["status"], "failed")
        context.clarification.request_group.assert_not_awaited()
        context = self.context()
        context.clarification.request_group.side_effect = None
        context.clarification.request_group.return_value = {"kind": "cancelled"}
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["output"]["proposal"]["status"], "no_change")
        self.assertNotIn("fieldGuidance", result["output"]["proposal"])
        context = self.context()
        del context.clarification.request_group
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["output"]["proposal"]["status"], "needs_clarification")
        context.clarification.request.assert_not_awaited()

    def test_recommendations_reject_unknown_capability_and_mixed_slots(self):
        for patch in ({"disabled": True}, {"required": True}, {"label": "事由", "name": "reason"}):
            ir = field_ir()
            ir["slots"]["field_draft"]["groups"][0]["options"][0]["patch"] = patch
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                compile_items([ir])
        ir = field_ir()
        ir["slots"]["field_draft"]["groups"][0] = {"field": 0, "slot": "control", "reason": "类型待确认", "options": [{"label": "不支持的组件", "patch": {"component_name": "Unknown"}}]}
        with self.assertRaises(ValueError):
            compile_items([ir])

    async def test_control_validation_and_static_source_are_independent(self):
        ir = field_ir()
        draft = ir["slots"]["field_draft"]
        draft["fields"][0].update(component_name="SelectSingle", options=[{"label": "员工", "value": "employee"}])
        draft["groups"] = [
            {"field": 0, "slot": "control", "reason": "单选或多选待确认", "options": [{"label": "复选框组", "patch": {"component_name": "CheckboxGroup"}}]},
            {"field": 0, "slot": "validation", "reason": "是否必填待确认", "options": [{"label": "允许不填", "patch": {"required": False}}]},
            {"field": 0, "slot": "data_source", "reason": "静态选项待确认", "options": [{"label": "员工选项", "patch": {"options": [{"label": "员工", "value": "employee"}]}}]},
        ]
        context = self.context(ir)
        result = await guidance.collect_guidance(context)
        fields = result["output"]["fieldSelection"]["fields"]
        self.assertEqual(fields[0]["component_name"], "CheckboxGroup")
        self.assertIs(fields[0]["required"], False)
        self.assertEqual(fields[0]["options"][0]["value"], "employee")
        self.assertNotIn("required", fields[1])
        questions = context.clarification.request_group.await_args.kwargs["questions"]
        self.assertEqual(len(questions), 3)
        for invalid in ({"dataSource": "employee-directory"}, {"textLengthLimit": 11}):
            draft["groups"][2]["options"][0]["patch"] = invalid
            with self.assertRaises(ValueError):
                compile_items([ir])

    async def test_empty_real_candidates_still_offer_custom(self):
        ir = field_ir()
        ir["slots"]["field_draft"]["groups"] = [
            {"field": 0, "slot": "properties", "reason": "提示尚不明确", "options": []},
        ]
        context = self.context(ir)
        async def answer(**kw):
            questions = kw["questions"]
            self.assertEqual(len(questions[0]["options"]), 1)
            self.assertEqual(questions[0]["options"][0]["label"], "自定义")
            return {"kind": "group", "answers": {questions[0]["id"]: {"kind": "text", "text": '{"placeholder":"请填写联系人"}'}}}
        context.clarification.request_group.side_effect = answer
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["output"]["fieldSelection"]["fields"][0]["placeholder"], "请填写联系人")

    def test_labels_and_incompatible_options_are_rejected(self):
        for label in ("选择紧急联系人", "设置联系人", "配置联系人", "过长" * 9, " 其他称谓"):
            ir = field_ir()
            ir["slots"]["field_draft"]["groups"][0]["options"][0]["label"] = label
            with self.subTest(label=label), self.assertRaises(ValueError):
                compile_items([ir])
        ir = field_ir()
        ir["slots"]["field_draft"]["groups"] = [{"field": 0, "slot": "data_source", "reason": "来源歧义", "options": [{"label": "空选项", "patch": {"options": []}}]}]
        with self.assertRaisesRegex(ValueError, "非选项组件"):
            compile_items([ir])

    async def test_combined_changes_cannot_silently_drop_requirements(self):
        ir = field_ir()
        ir["slots"]["field_draft"]["groups"] = [
            {"field": 0, "slot": "semantics", "reason": "名称待确认", "options": [{"label": "联系人代号", "patch": {"name": "duplicate"}}]},
            {"field": 1, "slot": "semantics", "reason": "名称待确认", "options": [{"label": "备注代号", "patch": {"name": "duplicate"}}]},
        ]
        context = self.context(ir)
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("output", result)
        context.clarification.request.assert_not_awaited()


class RegisteredFieldGuidanceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        test_output_preview.OutputPreviewTests.setUpClass.__func__(cls)

    async def test_registered_pipeline_freeze_answer_compile_no_second_generation(self):
        builder = MagicMock()
        for method in ("use_append_intent", "use_plan", "output_structured", "pipeline_step", "output_pipeline"):
            getattr(builder, method).return_value = builder
        with patch.object(self.agent, "create_external_agent", return_value=builder):
            self.agent.register_agent(SimpleNamespace())
        steps = [call.kwargs["handler"] for call in builder.pipeline_step.call_args_list]
        context = FieldGuidanceTests().context()
        context.inputs = "在事由后加联系人和备注，称谓和提示尚未确定"
        async def generate(**kw):
            return kw["compiler"]({"plan_items": [field_ir()]}, None)
        context.native_capability = SimpleNamespace(generate=AsyncMock(side_effect=generate))
        context.event_publisher = AsyncMock()
        for handler in steps:
            result = await handler(context)
            self.assertEqual(result["status"], "completed", result)
            context.inputs = result["output"]
        context.native_capability.generate.assert_awaited_once()
        context.event_publisher.assert_awaited_once()
        self.assertEqual(set(context.inputs), {"form_proposal"})
        self.assertEqual(context.inputs["form_proposal"]["status"], "ready")
        self.assertEqual(len(context.inputs["form_proposal"]["actions"]), 2)
