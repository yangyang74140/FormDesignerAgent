"""Canonical editable action drafts shared by field and property proposals."""

from typing import Any


def set_action_draft(
    proposal: dict[str, Any], actions: list[dict[str, Any]], *,
    mode: str, action_version: str, kind: str, title: str,
) -> None:
    if not actions:
        raise ValueError("可执行草稿至少包含一个动作")
    ids = [action["actionId"] for action in actions]
    if any(not isinstance(action_id, str) or not action_id.strip() for action_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("动作 actionId 必须存在且唯一")
    known = set(ids)
    for action in actions:
        action.setdefault("dependsOn", [])
        action.setdefault("display", {"selectedByDefault": True})
        dependencies = action["dependsOn"]
        if (
            not isinstance(dependencies, list)
            or any(not isinstance(item, str) or item not in known or item == action["actionId"] for item in dependencies)
            or len(set(dependencies)) != len(dependencies)
        ):
            raise ValueError("动作依赖必须引用本批其他唯一 actionId")
    visiting, visited = set(), set()
    by_id = {action["actionId"]: action for action in actions}

    def visit(action_id: str) -> None:
        if action_id in visiting:
            raise ValueError("动作依赖不能循环")
        if action_id in visited:
            return
        visiting.add(action_id)
        for dependency in by_id[action_id]["dependsOn"]:
            visit(dependency)
        visiting.remove(action_id)
        visited.add(action_id)

    for action_id in ids:
        visit(action_id)
    proposal.update(
        mode=mode, actionVersion=action_version, actions=actions,
        presentation={"kind": kind, "title": title},
    )
