"""Scenario recommendations and checkpoint-safe native clarification."""

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from compiler_package import load_compiler_module
from test_form_proposal import compile_items

guidance = load_compiler_module("guidance")


def scenario():
    return {"capability": "proposal.needs_clarification", "slots": {
        "summary": "需要明确审批用途。", "question": "你希望生成哪类审批表单？",
        "scenario_options": [
            {"label": "请假审批表单", "description": "记录请假类型、时间和原因。"},
            {"label": "采购审批表单", "description": "记录采购物品、数量和预算。"},
            {"label": "报销审批表单", "description": "记录费用类型、金额和日期。"},
        ],
    }}


class GuidanceTests(unittest.IsolatedAsyncioTestCase):
    def context(self, *answers):
        return SimpleNamespace(
            inputs={"original_input": "生成一个审批表单", "proposal": compile_items([scenario()])},
            clarification=SimpleNamespace(request=AsyncMock(side_effect=list(answers))),
        )

    def test_four_options_are_compiled_without_actions(self):
        proposal = compile_items([scenario()])
        self.assertEqual([o["label"] for o in proposal["clarificationOptions"]],
                         ["请假审批表单", "采购审批表单", "报销审批表单", "其他"])
        self.assertEqual(len({o["id"] for o in proposal["clarificationOptions"]}), 4)
        self.assertNotIn("actions", proposal)
        self.assertNotIn("presentation", proposal)

    def test_invalid_recommendations_fail_closed(self):
        for options in ([], [{"label": "x", "description": "x"}] * 3,
                        [{"label": "其他", "description": "x"}] * 3,
                        [{"label": "x", "description": ""}] * 3):
            item = scenario()
            item["slots"]["scenario_options"] = options
            with self.subTest(options=options), self.assertRaises(ValueError):
                compile_items([item])
        item = scenario()
        item["slots"]["choices"] = ["重复菜单"]
        with self.assertRaises(ValueError):
            compile_items([item])

    async def test_selected_option_preserves_label_and_description(self):
        context = self.context(SimpleNamespace(kind="selected", selected_option_id="scenario-2"))
        before = deepcopy(context.inputs)
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["output"]["answer"]["text"], "采购审批表单：记录采购物品、数量和预算。")
        self.assertEqual(result["output"]["original_input"], "生成一个审批表单")
        self.assertEqual(context.inputs, before)
        call = context.clarification.request.await_args.kwargs
        self.assertEqual(call["key"], "form_requirement")
        self.assertEqual(len(call["options"]), 4)

    async def test_other_collects_text_with_stable_separate_key(self):
        context = self.context({"kind": "selected", "selected_option_id": "other"},
                               {"kind": "text", "text": "合同审批表单"})
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["output"]["answer"]["text"], "合同审批表单")
        self.assertEqual([c.kwargs["key"] for c in context.clarification.request.await_args_list],
                         ["form_requirement", "form_requirement_other"])

    async def test_text_and_cancellation(self):
        context = self.context({"kind": "text", "text": "用车审批表单"})
        self.assertEqual((await guidance.collect_guidance(context))["output"]["answer"]["text"], "用车审批表单")
        for answers in (({"kind": "cancelled"},),
                        ({"kind": "selected", "selected_option_id": "other"}, {"kind": "cancelled"})):
            result = await guidance.collect_guidance(self.context(*answers))
            self.assertEqual(result["output"]["proposal"]["status"], "no_change")
            self.assertNotIn("answer", result["output"])
            self.assertNotIn("clarificationOptions", result["output"]["proposal"])

    async def test_invalid_answer_is_not_generation_authorization(self):
        for answer in ({"kind": "selected", "selected_option_id": "missing"},
                       {"kind": "text", "text": " "}, {"kind": "exhausted"}):
            result = await guidance.collect_guidance(self.context(answer))
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["abort_run"])

    async def test_non_business_results_do_not_prompt(self):
        for status in ("ready", "unsupported", "no_change"):
            context = self.context()
            context.inputs["proposal"] = {"status": status}
            await guidance.collect_guidance(context)
            context.clarification.request.assert_not_awaited()
        context = self.context()
        context.inputs["proposal"]["diagnostics"] = [{"code": "HOST_CONTEXT_REQUIRED"}]
        await guidance.collect_guidance(context)
        context.clarification.request.assert_not_awaited()

    async def test_missing_facade_retains_non_executable_clarification(self):
        context = self.context()
        del context.clarification
        result = await guidance.collect_guidance(context)
        self.assertEqual(result["output"]["proposal"]["status"], "needs_clarification")
        self.assertNotIn("answer", result["output"])

    async def test_reentry_uses_identical_questions_and_options(self):
        context = self.context({"kind": "selected", "selected_option_id": "other"}, {"kind": "text", "text": "用车"},
                               {"kind": "selected", "selected_option_id": "other"}, {"kind": "text", "text": "用车"})
        first = await guidance.collect_guidance(context)
        second = await guidance.collect_guidance(context)
        self.assertEqual(first, second)
        calls = context.clarification.request.await_args_list
        self.assertEqual(calls[:2], calls[2:])
