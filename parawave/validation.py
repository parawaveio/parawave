"""Input and signature validation."""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable

from parawave.errors import ValidationError


def validate_inputs(
    func: Callable,
    data: list,
    broadcast: dict[str, Any],
) -> list[dict]:
    """Validate and merge input data with broadcast kwargs.

    Returns the merged list of dicts ready for execution.
    Raises ValidationError for any issues.
    """
    if not isinstance(data, list):
        raise ValidationError(f"data must be a list of dicts, got {type(data).__name__}")
    if not data:
        raise ValidationError("data must not be empty")

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValidationError(
                f"Each item in data must be a dict, got {type(item).__name__} at index {i}"
            )

    sig = inspect.signature(func)
    params = sig.parameters
    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )
    required_params = {
        name
        for name, p in params.items()
        if p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    valid_params = {
        name
        for name, p in params.items()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }

    merged = []
    for i, item in enumerate(data):
        merged_item = {**broadcast, **item}
        merged.append(merged_item)

        if not has_var_keyword:
            extra = set(merged_item.keys()) - valid_params
            if extra:
                raise ValidationError(
                    f"Item at index {i} has unexpected keys: {extra}. "
                    f"Function accepts: {valid_params}"
                )

        missing = required_params - set(merged_item.keys())
        if missing:
            raise ValidationError(
                f"Item at index {i} is missing required arguments: {missing}"
            )

    return merged


def validate_input_serializability(items: list[dict]) -> None:
    """Validate that all input items are JSON-serializable.

    Raises ValidationError on first non-serializable value found.
    """
    for i, item in enumerate(items):
        try:
            json.dumps(item)
        except (TypeError, ValueError):
            # Find the specific key that failed
            for key, value in item.items():
                try:
                    json.dumps(value)
                except (TypeError, ValueError):
                    raise ValidationError(
                        f"Input at index {i} is not JSON-serializable.\n"
                        f"  Key '{key}' has type '{type(value).__module__}.{type(value).__qualname__}'.\n"
                        f"\n"
                        f"Pass only JSON-serializable values (str, int, float, bool, list, dict, or None)."
                    )
            # Whole item failed but no individual key did (e.g., circular reference)
            raise ValidationError(
                f"Input at index {i} is not JSON-serializable.\n"
                f"\n"
                f"Pass only JSON-serializable values (str, int, float, bool, list, dict, or None)."
            )
