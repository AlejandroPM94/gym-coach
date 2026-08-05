from typing import Any

from pydantic import ValidationError


class HevyError(Exception):
    """Base error for the Hevy boundary."""


class HevyConfigurationError(HevyError):
    """The local Hevy configuration is incomplete."""


class HevyTimeoutError(HevyError):
    """Hevy did not answer within the configured timeout."""


class HevyTransportError(HevyError):
    """A network-level error prevented communication with Hevy."""


class HevyHTTPError(HevyError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class HevyInvalidResponseError(HevyError):
    """Hevy returned malformed JSON or a response outside the expected contract."""


_EXPECTED_TYPES = {
    "bool": "boolean",
    "bytes": "bytes",
    "date": "date string",
    "datetime": "datetime string",
    "dict": "object",
    "float": "number",
    "int": "integer",
    "list": "array",
    "model": "object",
    "string": "string",
    "url": "URL string",
}


def sanitized_validation_details(error: ValidationError) -> str:
    """Describe validation failures without including input values."""
    details: list[str] = []
    for item in error.errors(include_url=False, include_context=False, include_input=True):
        path = ".".join(str(part) for part in item["loc"]) or "<root>"
        error_type = str(item["type"])
        if error_type == "missing":
            expected = "field present"
            received = "missing"
            issue = "field absent"
        else:
            category = error_type.split("_", maxsplit=1)[0]
            expected = _EXPECTED_TYPES.get(category, "valid value")
            received = _value_type(item.get("input"))
            issue = error_type
        details.append(f"field={path}; expected={expected}; received={received}; issue={issue}")
    return " | ".join(details)


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__
