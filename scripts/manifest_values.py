"""Checked access to nested YAML values in rendered-manifest tests."""

from __future__ import annotations


def value_at(value: object, *path: str | int) -> object:
    for key in path:
        if isinstance(key, str):
            if not isinstance(value, dict):
                message = f"Expected a mapping at {key!r}, got {type(value).__name__}"
                raise TypeError(message)
            value = value[key]
        elif isinstance(value, list):
            value = value[key]
        else:
            message = f"Expected a mapping or list at {key!r}, got {type(value).__name__}"
            raise TypeError(message)
    return value


def mapping_at(value: object, *path: str | int) -> dict[str, object]:
    value = value_at(value, *path)
    if not isinstance(value, dict):
        message = f"Expected a mapping at {path!r}, got {type(value).__name__}"
        raise TypeError(message)
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            message = f"Expected a string mapping key, got {key!r}"
            raise TypeError(message)
        result[key] = item
    return result


def sequence_at(value: object, *path: str | int) -> list[object]:
    value = value_at(value, *path)
    if not isinstance(value, list):
        message = f"Expected a list at {path!r}, got {type(value).__name__}"
        raise TypeError(message)
    return value
