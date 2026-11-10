"""Hard-coded form action rules and compilers."""

from .actions import (
    FORM_ACTION_CONTRACT,
    FORM_ACTION_PIPELINE,
    FORM_FIELD_BATCH_CONTRACT,
    FORM_OUTPUT_CONTRACT,
    FORM_PIPELINE,
    FORM_SKELETON_CONTRACT,
    compile_form_action,
    compile_form_actions,
    compile_form_field_hydration,
    compile_form_skeleton,
    finalize_form_schema,
)

__all__ = [
    "FORM_ACTION_CONTRACT",
    "FORM_ACTION_PIPELINE",
    "FORM_FIELD_BATCH_CONTRACT",
    "FORM_OUTPUT_CONTRACT",
    "FORM_PIPELINE",
    "FORM_SKELETON_CONTRACT",
    "compile_form_action",
    "compile_form_actions",
    "compile_form_field_hydration",
    "compile_form_skeleton",
    "finalize_form_schema",
]
