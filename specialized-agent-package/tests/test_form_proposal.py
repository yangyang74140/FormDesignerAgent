"""Regression tests for the capability-aware form-agent.v1 proposal compiler."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("form_proposal", ROOT / "form_generation" / "proposal.py")
proposal = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(proposal)


def host_context(**overrides):
    value = {
        "requestId": "req-test",
        "schemaVersion": "1.0.0",
        "target": {"schemaId": "leave-form", "formId": "form-1", "revision": "rev-10"},
        "currentSchema": {
            "schemaVersion": "1.0.0",
            "fields": [
                {"id": "reason", "componentName": "Input", "props": {"label": "事由", "name": "reason"}, "isSaved": True},
                {"id": "draft-choice", "componentName": "SelectSingle", "props": {"label": "类型", "name": "leave_type"}, "isSaved": False},
                {"id": "section", "componentName": "Tabs", "props": {}, "children": []},
            ],
        },
        "selection": {"nodeId": "reason", "parentId": None},
        "canvas": {"layoutMode": "flow", "device": "pc", "isBlank": False},
        "capabilities": {
            "components": [
                {"componentName": "Input"},
                {"componentName": "SelectSingle"},
                {"componentName": "CheckboxGroup"},
                {"componentName": "Tabs"},
            ],
            "actions": list(proposal.ACTION_KINDS),
            "validators": [{"name": "required"}, {"name": "date_order"}],
            "functions": [{"name": "DATE_DIFF"}],
            "dataSources": [{"id": "employee-directory"}],
        },
        "supportedActionVersions": ["form_actions.v2"],
    }
    value.update(overrides)
    return SimpleNamespace(context=value)


def compile_items(items, context=None):
    return proposal.compile_form_proposal({"plan_items": items}, context or host_context())["output"]["form_proposal"]


class FormProposalCompilerTests(unittest.TestCase):
    def test_ready_actions_use_selection_and_preserve_revision(self):
        result = compile_items([
            {"capability": "proposal.begin", "slots": {"summary": "更新事由并插入备注。", "result_kind": "form_actions"}},
            {"capability": "form.update_component", "slots": {"payload": {"useSelection": True, "changes": {"required": True}}}},
            {"capability": "form.add_component", "slots": {"payload": {
                "clientRef": "leave-note", "componentName": "Input", "props": {"label": "备注"},
                "target": {"kind": "relative", "anchorNodeId": "reason", "position": "after"},
            }}},
            {"capability": "form.set_validation", "slots": {"payload": {
                "fieldId": "reason", "validator": {"name": "required"},
            }}},
        ])
        self.assertEqual(result["protocol"], "form-agent.v1")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["target"]["baseRevision"], "rev-10")
        self.assertEqual(result["result"]["schemaVersion"], "form_actions.v2")
        self.assertEqual(len(result["result"]["actions"]), 3)
        self.assertTrue(result["proposalId"].startswith("proposal-"))

    def test_clarification_has_no_executable_result(self):
        result = compile_items([{"capability": "proposal.needs_clarification", "slots": {
            "summary": "多选转单选会丢失默认值。",
            "question": "转换后保留哪个默认值？",
            "choices": ["事假", "病假", "清除默认值"],
            "code": "LOSSY_CONVERSION_DECISION_REQUIRED",
        }}])
        self.assertEqual(result["status"], "needs_clarification")
        self.assertNotIn("result", result)
        self.assertEqual(result["diagnostics"][0]["code"], "LOSSY_CONVERSION_DECISION_REQUIRED")

    def test_unsupported_and_no_change_are_non_executable(self):
        unsupported = compile_items([{"capability": "proposal.unsupported", "slots": {
            "summary": "缺少历史请假重叠校验器。", "code": "HISTORICAL_OVERLAP_VALIDATOR_UNAVAILABLE",
        }}])
        no_change = compile_items([{"capability": "proposal.no_change", "slots": {"summary": "当前配置已满足要求。"}}])
        self.assertEqual(unsupported["status"], "unsupported")
        self.assertEqual(no_change["status"], "no_change")
        self.assertNotIn("result", unsupported)
        self.assertNotIn("result", no_change)

    def test_single_item_native_capability_root_is_supported(self):
        compiled = proposal.compile_form_proposal(
            {"capability": "proposal.no_change", "slots": {"summary": "无需修改。"}},
            host_context(),
        )["output"]["form_proposal"]
        self.assertEqual(compiled["status"], "no_change")
        self.assertEqual(compiled["summary"], "无需修改。")

    def test_action_must_be_declared_by_host(self):
        context = host_context(capabilities={"components": [{"componentName": "Input"}], "actions": ["form.update_component"]})
        with self.assertRaisesRegex(ValueError, "未声明支持动作"):
            compile_items([
                {"capability": "proposal.begin", "slots": {"summary": "添加字段", "result_kind": "form_actions"}},
                {"capability": "form.add_component", "slots": {"payload": {
                    "clientRef": "note", "componentName": "Input", "target": {"kind": "root"},
                }}},
            ], context)

    def test_actions_require_version_and_capability_catalog(self):
        context = host_context(supportedActionVersions=[])
        with self.assertRaisesRegex(ValueError, "supportedActionVersions"):
            compile_items([
                {"capability": "proposal.begin", "slots": {"summary": "更新字段", "result_kind": "form_actions"}},
                {"capability": "form.update_component", "slots": {"payload": {"fieldId": "reason", "changes": {"required": True}}}},
            ], context)

    def test_conversion_only_accepts_explicitly_unsaved_field(self):
        ready = compile_items([
            {"capability": "proposal.begin", "slots": {"summary": "转换草稿字段", "result_kind": "form_actions"}},
            {"capability": "form.convert_component", "slots": {"payload": {
                "fieldId": "draft-choice", "componentName": "CheckboxGroup",
            }}},
        ])
        self.assertEqual(ready["status"], "ready")
        with self.assertRaisesRegex(ValueError, "未保存"):
            compile_items([
                {"capability": "proposal.begin", "slots": {"summary": "转换已保存字段", "result_kind": "form_actions"}},
                {"capability": "form.convert_component", "slots": {"payload": {
                    "fieldId": "reason", "componentName": "SelectSingle",
                }}},
            ])

    def test_formula_and_rules_reject_dangling_references(self):
        with self.assertRaisesRegex(ValueError, "悬空引用"):
            compile_items([
                {"capability": "proposal.begin", "slots": {"summary": "设置公式", "result_kind": "form_actions"}},
                {"capability": "form.set_formula", "slots": {"payload": {
                    "fieldId": "reason", "formula": {"function": "DATE_DIFF", "fieldRef": "missing-end"},
                }}},
            ])

    def test_formula_rejects_direct_self_reference(self):
        with self.assertRaisesRegex(ValueError, "目标字段自身"):
            compile_items([
                {"capability": "proposal.begin", "slots": {"summary": "设置公式", "result_kind": "form_actions"}},
                {"capability": "form.set_formula", "slots": {"payload": {
                    "fieldId": "reason", "formula": {"function": "DATE_DIFF", "fieldRef": "reason"},
                }}},
            ])

    def test_rules_formulas_and_data_linkage_require_registered_resources(self):
        for action, payload, message in (
            ("form.set_validation", {"fieldId": "reason", "validator": {"name": "unknown-validator"}}, "校验器"),
            ("form.set_formula", {"fieldId": "reason", "formula": {"function": "UNKNOWN"}}, "公式函数"),
            ("form.upsert_linkage", {"fieldId": "reason", "dataSourceId": "missing-source"}, "数据源"),
        ):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, message):
                compile_items([
                    {"capability": "proposal.begin", "slots": {"summary": "配置规则", "result_kind": "form_actions"}},
                    {"capability": action, "slots": {"payload": payload}},
                ])

    def test_mapping_catalogs_are_supported(self):
        context = host_context(capabilities={
            "components": {"Input": {"category": "field"}},
            "actions": {"form.add_component": {"version": "form_actions.v2"}},
        })
        result = compile_items([
            {"capability": "proposal.begin", "slots": {"summary": "添加字段", "result_kind": "form_actions"}},
            {"capability": "form.add_component", "slots": {"payload": {
                "clientRef": "note", "componentName": "Input", "target": {"kind": "root"},
            }}},
        ], context)
        self.assertEqual(result["status"], "ready")

    def test_model_cannot_return_full_schema(self):
        with self.assertRaisesRegex(ValueError, "form_fields 或 form_actions"):
            compile_items([{"capability": "proposal.begin", "slots": {
                "summary": "创建表单", "result_kind": "form_schema",
                "schema": {"fields": [{"id": "name", "componentName": "Input"}]},
            }}])

    def test_revision_conflict_requires_refreshed_context(self):
        context = host_context(executionResult={"status": "conflict"})
        with self.assertRaisesRegex(ValueError, "revision conflict"):
            compile_items([
                {"capability": "proposal.begin", "slots": {"summary": "重发动作", "result_kind": "form_actions"}},
                {"capability": "form.update_component", "slots": {"payload": {"fieldId": "reason", "changes": {"required": True}}}},
            ], context)

    def test_existing_field_name_cannot_be_modified(self):
        with self.assertRaisesRegex(ValueError, "props.name 不可修改"):
            compile_items([
                {"capability": "proposal.begin", "slots": {"summary": "改字段名", "result_kind": "form_actions"}},
                {"capability": "form.update_component", "slots": {"payload": {
                    "fieldId": "reason", "changes": {"name": "other_reason"},
                }}},
            ])

    def test_incremental_changes_respect_writable_props(self):
        context = host_context(capabilities={
            "components": [{"componentName": "Input", "writableProps": ["label"]}],
            "actions": ["form.update_component"],
        })
        with self.assertRaisesRegex(ValueError, "不可写属性"):
            compile_items([
                {"capability": "proposal.begin", "slots": {"summary": "设为必填", "result_kind": "form_actions"}},
                {"capability": "form.update_component", "slots": {"payload": {
                    "fieldId": "reason", "changes": {"required": True},
                }}},
            ], context)

    def test_container_and_grid_targets_are_out_of_scope(self):
        for target in (
            {"kind": "container", "containerId": "section", "slotId": "tab-1", "index": 0},
            {"kind": "grid", "region": {"row": 1, "column": 1}},
        ):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "单层 Flow"):
                compile_items([
                    {"capability": "proposal.begin", "slots": {"summary": "插入字段", "result_kind": "form_actions"}},
                    {"capability": "form.add_component", "slots": {"payload": {
                        "clientRef": "new-field", "componentName": "Input", "target": target,
                    }}},
                ])


if __name__ == "__main__":
    unittest.main()
