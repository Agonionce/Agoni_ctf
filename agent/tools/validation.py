"""Central JSON Schema validation for Planner-supplied Tool arguments."""

from __future__ import annotations

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from agent.tools.contracts import ToolError


class ToolArgumentValidator:
    """Validate every ToolCall before policy evaluation or backend execution."""

    @staticmethod
    def check_schema(schema: object) -> None:
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as error:
            raise ValueError(f"invalid Tool input schema: {error.message}") from error

    @staticmethod
    def validate(arguments: object, schema: dict) -> ToolError | None:
        errors = sorted(
            Draft202012Validator(schema).iter_errors(arguments),
            key=lambda item: (
                tuple(str(part) for part in item.absolute_path),
                item.message,
            ),
        )
        if not errors:
            return None
        error = errors[0]
        field_path = "$" + "".join(
            f"[{item}]" if isinstance(item, int) else f".{item}"
            for item in error.absolute_path
        )
        schema_path = "/".join(str(item) for item in error.absolute_schema_path)
        return ToolError(
            code="TOOL_ARGUMENT_SCHEMA_ERROR",
            message=error.message,
            field_path=field_path,
            schema_path=schema_path,
        )
