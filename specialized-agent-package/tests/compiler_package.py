"""Load compiler tests with the same relative-import semantics as a plugin revision."""

import importlib
from importlib.machinery import ModuleSpec
from pathlib import Path
import sys
from types import ModuleType


_PACKAGE = "form_agent_compiler_tests"


def load_compiler_module(name):
    if _PACKAGE not in sys.modules:
        package = ModuleType(_PACKAGE)
        package.__path__ = [str(Path(__file__).resolve().parents[1] / "form_generation")]
        package.__spec__ = ModuleSpec(_PACKAGE, loader=None, is_package=True)
        package.__spec__.submodule_search_locations = package.__path__
        sys.modules[_PACKAGE] = package
    return importlib.import_module(f"{_PACKAGE}.{name}")
