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

from typing import Any

from .agent_definition import register_agent


def register_specialized_agent(context: Any) -> None:
    """
    注册外置专属 Agent

    作用：作为 manifest.entrypoint 指向的平台启动入口。
    主要功能：加载同目录 Agent 定义文件，并委托其通过 builder SDK 完成注册。

    Args:
        context: 平台注入的 registry_context
    """
    register_agent(context)
