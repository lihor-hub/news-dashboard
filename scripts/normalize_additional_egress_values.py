#!/usr/bin/env python3
"""Normalize the one operator-controlled Helm values subtree allowed in production."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

_MAX_INPUT_BYTES = 64 * 1024
_MAX_NESTING_DEPTH = 32
_INVALID_MESSAGE = "Invalid additional egress values.\n"


class AdditionalEgressValuesError(ValueError):
    """Raised when input is not the exact additional-egress values structure."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdditionalEgressValuesError
        result[key] = value
    return result


def _reject_nonstandard_constant(_value: str) -> None:
    raise AdditionalEgressValuesError


def _validate_nesting_and_numbers(root: Any) -> None:
    pending = [(root, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > _MAX_NESTING_DEPTH:
            raise AdditionalEgressValuesError
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise AdditionalEgressValuesError


def normalize_additional_egress_values(content: bytes) -> str:
    """Return safe normalized JSON for exactly ``networkPolicy.additionalEgress``."""
    if len(content) > _MAX_INPUT_BYTES:
        raise AdditionalEgressValuesError

    document = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonstandard_constant,
    )
    _validate_nesting_and_numbers(document)

    if not isinstance(document, dict) or set(document) != {"networkPolicy"}:
        raise AdditionalEgressValuesError

    network_policy = document["networkPolicy"]
    if not isinstance(network_policy, dict) or set(network_policy) != {"additionalEgress"}:
        raise AdditionalEgressValuesError

    additional_egress = network_policy["additionalEgress"]
    if not isinstance(additional_egress, list) or not additional_egress:
        raise AdditionalEgressValuesError

    normalized = {"networkPolicy": {"additionalEgress": additional_egress}}
    return json.dumps(normalized, indent=2) + "\n"


def _read_bounded_input(path: str) -> bytes:
    if path == "-":
        content = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    else:
        with Path(path).open("rb") as input_file:
            content = input_file.read(_MAX_INPUT_BYTES + 1)
    if len(content) > _MAX_INPUT_BYTES:
        raise AdditionalEgressValuesError
    return content


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: normalize_additional_egress_values.py INPUT OUTPUT\n")
        return 2

    try:
        content = _read_bounded_input(sys.argv[1])
        normalized = normalize_additional_egress_values(content)
    except (
        json.JSONDecodeError,
        AdditionalEgressValuesError,
        MemoryError,
        OSError,
        RecursionError,
        UnicodeError,
        ValueError,
    ):
        sys.stderr.write(_INVALID_MESSAGE)
        return 2

    try:
        Path(sys.argv[2]).write_text(normalized)
    except (OSError, UnicodeError):
        sys.stderr.write("Unable to write normalized additional egress values.\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
