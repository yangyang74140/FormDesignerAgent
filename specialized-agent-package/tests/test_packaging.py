"""Validate the uploaded bytes, not only source files before packaging."""

import asyncio
import importlib
import importlib.abc
import importlib.util
from pathlib import Path
import shutil
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4
import zipfile

from test_form_field_list import assert_action_draft


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "specialized-agent-package"
SPEC = importlib.util.spec_from_file_location("form_agent_packaging", ROOT / "package_agent.py")
PACKAGING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGING)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / f".form-agent-package-test-{uuid4().hex}"
        directory.mkdir()
        self.addCleanup(shutil.rmtree, directory)
        self.archive_path = directory / "agent.zip"

    def write_archive(self, overrides=None, omitted=(), prefix=""):
        files = PACKAGING.source_files(SOURCE)
        contents = {
            path.relative_to(SOURCE).as_posix(): path.read_text(encoding="utf-8").encode("utf-8")
            for path in files
        }
        contents.update(overrides or {})
        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in contents.items():
                if name not in omitted:
                    archive.writestr(prefix + name, content)

    def test_upload_archive_loads_entrypoint_in_two_revision_namespaces(self):
        self.write_archive()
        PACKAGING.validate_archive(self.archive_path)
        sdk = ModuleType("specialized.builder.sdk")
        sdk.create_external_agent = MagicMock()
        builder = sdk.create_external_agent.return_value
        for method in ("use_append_intent", "use_plan", "output_structured", "pipeline_step", "output_pipeline"):
            getattr(builder, method).return_value = builder
        modules = {
            "specialized": ModuleType("specialized"),
            "specialized.builder": ModuleType("specialized.builder"),
            "specialized.builder.sdk": sdk,
        }
        packages = []
        revisions = ("packaging_revision_a", "packaging_revision_b")
        archive_path = self.archive_path

        class ArchiveLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
            def find_spec(self, fullname, path=None, target=None):
                parts = fullname.split(".")
                if len(parts) < 2 or parts[0] not in revisions:
                    return None
                relative = "/".join(parts[1:])
                with zipfile.ZipFile(archive_path) as archive:
                    for member, is_package in ((relative + "/__init__.py", True), (relative + ".py", False)):
                        if member in archive.namelist():
                            spec = importlib.util.spec_from_loader(fullname, self, is_package=is_package)
                            spec.origin = str(archive_path / member)
                            spec.loader_state = member
                            return spec
                return None

            def create_module(self, spec):
                return None

            def exec_module(self, module):
                module.__file__ = module.__spec__.origin
                with zipfile.ZipFile(archive_path) as archive:
                    code = archive.read(module.__spec__.loader_state)
                exec(compile(code, module.__file__, "exec"), module.__dict__)

        with patch.dict(sys.modules, modules), patch.object(sys, "meta_path", [ArchiveLoader(), *sys.meta_path]):
            for name in revisions:
                package = ModuleType(name)
                package.__path__ = [str(self.archive_path)]
                sys.modules[name] = package
                bootstrap = importlib.import_module(f"{name}.bootstrap")
                definition = importlib.import_module(f"{name}.agent_definition")
                compiler = importlib.import_module(f"{name}.form_generation.proposal")
                actions = importlib.import_module(f"{name}.form_generation.action_rules")
                components = importlib.import_module(f"{name}.form_generation.components")
                self.assertIs(compiler.ACTION_KINDS, actions.ACTION_KINDS)
                self.assertIs(compiler.FLOW_COMPONENTS, components.FLOW_COMPONENTS)
                self.assertIs(bootstrap.register_agent, definition.register_agent)
                self.assertIs(definition.compile_form_proposal, compiler.compile_form_proposal)
                self.assertTrue(str(bootstrap.__file__).startswith(str(self.archive_path)))
                context = SimpleNamespace()
                bootstrap.register_specialized_agent(context)
                sdk.create_external_agent.assert_called_with(context)
                from test_form_field_list import blank_context

                async def generate(**kwargs):
                    return SimpleNamespace(**kwargs["compiler"]({"plan_items": [
                        {"capability": "proposal.begin", "slots": {
                            "summary": "生成学号字段。", "result_kind": "form_fields", "mode": "replace_empty_form",
                        }},
                        {"capability": "form.field.define", "slots": {
                            "client_ref": "student_no", "component_name": "Input", "label": "学号", "name": "student_no",
                        }},
                    ]}, None))

                step = SimpleNamespace(inputs="生成学生表", context=blank_context(),
                                       native_capability=SimpleNamespace(generate=generate))
                result = asyncio.run(definition.generate_form_proposal(step))
                self.assertEqual(result["status"], "completed", result)
                proposal = result["output"]["form_proposal"]
                self.assertEqual(set(result["output"]), {"form_proposal"})
                self.assertEqual(proposal["presentation"]["kind"], "shared.table-field-confirm")
                assert_action_draft(self, proposal)
                self.assertEqual(len(proposal["actions"]), 1)
                self.assertEqual(proposal["actions"][0]["payload"]["clientRef"], "student_no")
                self.assertEqual(proposal["actions"][0]["payload"]["props"]["name"], "student_no")
                property_context = {
                    "target": {"schemaId": "form-1", "revision": "rev-1"},
                    "currentSchema": {"fields": [{"id": "reason", "componentName": "Input", "props": {"label": "事由"}}]},
                    "capabilities": {
                        "catalogVersion": "test-catalog",
                        "components": {"Input": {"properties": {"required": {
                            "operations": ["set"], "valueSchema": {"type": "boolean"},
                        }}}},
                        "nodePolicies": {"reason": {"canModify": True, "allowedProperties": ["required"]}},
                    },
                    "supportedActionVersions": {"form.apply_property_change": ["form_property_actions.v1"]},
                }
                property_result = compiler.compile_form_proposal({"plan_items": [
                    {"capability": "proposal.begin", "slots": {"summary": "设置必填", "result_kind": "property_changes"}},
                    {"capability": "form.property.change", "slots": {
                        "node_id": "reason", "property": "required", "operation": "set", "value": True,
                    }},
                ]}, property_context)["output"]["form_proposal"]
                self.assertEqual(property_result["status"], "ready", property_result)
                assert_action_draft(self, property_result, "shared.component-property-checklist", property_actions=True)
                self.assertEqual(len(property_result["actions"]), 1)
                self.assertEqual(property_result["actions"][0]["payload"]["value"], True)
                packages.append(bootstrap)
            self.assertIsNot(packages[0].register_agent, packages[1].register_agent)
            self.assertEqual(builder.register.call_count, 2)

    def test_rejects_binary_python_members_including_bootstrap(self):
        for name in ("bootstrap.py", "agent_definition.py", "form_generation/proposal.py"):
            with self.subTest(name=name):
                for content in (b"%TSD-Header-###%encrypted-source", b"\x00", b"\xff"):
                    with self.subTest(content=content):
                        self.write_archive({name: content})
                        with self.assertRaisesRegex(ValueError, name):
                            PACKAGING.validate_archive(self.archive_path)

    def test_rejects_syntax_errors_in_archive_members(self):
        name = "form_generation/properties.py"
        self.write_archive({name: b"def broken(:\n"})
        with self.assertRaisesRegex(ValueError, name):
            PACKAGING.validate_archive(self.archive_path)

    def test_rejects_extra_parent_directory(self):
        self.write_archive(prefix="specialized-agent-package/")
        with self.assertRaisesRegex(ValueError, "root"):
            PACKAGING.validate_archive(self.archive_path)

    def test_rejects_missing_relative_imports(self):
        for name in (
            "form_generation/proposal.py",
            "form_generation/action_rules/component.py",
            "form_generation/components/__init__.py",
            "form_generation/components/definitions/__init__.py",
            "form_generation/components/definitions/NumberPicker.py",
            "form_generation/components/definitions/_shared/__init__.py",
            "form_generation/components/definitions/_shared/text.py",
            "form_generation/components/definitions/_shared/temporal.py",
            "form_generation/components/definitions/_shared/choice.py",
        ):
            with self.subTest(name=name):
                self.write_archive(omitted=(name,))
                with self.assertRaisesRegex(ValueError, name.removesuffix("/__init__.py").removesuffix(".py")):
                    PACKAGING.validate_archive(self.archive_path)

    def test_source_collection_includes_nested_rules_and_specs_only(self):
        self.write_archive()
        with zipfile.ZipFile(self.archive_path) as archive:
            names = set(archive.namelist())
        self.assertIn("form_generation/action_rules/component.py", names)
        self.assertIn("form_generation/components/__init__.py", names)
        for module in ("Input", "InputTextArea", "NumberPicker", "DatePicker", "TimePicker", "SelectSingle", "SelectMulti"):
            self.assertIn(f"form_generation/components/definitions/{module}.py", names)
        for module in ("text", "temporal", "choice"):
            self.assertIn(f"form_generation/components/definitions/_shared/{module}.py", names)
        self.assertIn("release_config.json", names)
        self.assertIn("specs/actions.md", names)
        self.assertIn("specs/components/temporal.md", names)
        self.assertFalse(any("tests/" in name or "__pycache__/" in name for name in names))


if __name__ == "__main__":
    unittest.main()
