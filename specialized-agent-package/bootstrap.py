"""
@file: bootstrap.py
@description: 外置 Agent 脚手架启动入口

主要功能:
    - 加载相邻 agent_definition.py
    - 暴露平台要求的 register_specialized_agent 入口
    - 委托 SDK 脚手架完成 Bundle 注册

公司：天枢星辰
作者：Codex
创建日期：2026-07-16
"""

from __future__ import annotations

import importlib.util
import hashlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def register_specialized_agent(context: Any) -> None:
    """
    注册外置专属 Agent

    作用：作为 manifest.entrypoint 指向的平台启动入口。
    主要功能：加载同目录 Agent 定义文件，并委托其通过 builder SDK 完成注册。

    Args:
        context: 平台注入的 registry_context
    """
    agent_definition = _load_agent_definition_module()
    agent_definition.register_agent(context)


def _load_agent_definition_module() -> ModuleType:
    """加载同目录下的 agent_definition.py。"""
    module_path = Path(__file__).with_name("agent_definition.py")
    if __package__:
        module_name = f"{__package__}.agent_definition"
    else:
        package_name = "scaffold_external_agent_" + hashlib.sha256(
            str(module_path.parent).encode("utf-8")
        ).hexdigest()[:12]
        package = sys.modules.get(package_name)
        if package is None:
            package = ModuleType(package_name)
            package.__path__ = [str(module_path.parent)]
            sys.modules[package_name] = package
        module_name = f"{package_name}.agent_definition"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载外置 Agent 脚手架 agent_definition.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
