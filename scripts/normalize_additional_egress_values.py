#!/usr/bin/env python3
"""Normalize the one operator-controlled Helm values subtree allowed in production."""

from __future__ import annotations

import sys
from collections.abc import Hashable
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken

_MAPPING_TAG = "tag:yaml.org,2002:map"
_MERGE_TAG = "tag:yaml.org,2002:merge"


class AdditionalEgressValuesError(ValueError):
    """Raised when input is not the exact additional-egress values structure."""


class _StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate and merge keys."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        if not isinstance(node, MappingNode):
            raise ConstructorError(None, None, "expected a mapping node", node.start_mark)

        keys: set[Hashable] = set()
        for key_node, _ in node.value:
            if key_node.tag == _MERGE_TAG:
                raise AdditionalEgressValuesError
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, Hashable) or key in keys:
                raise AdditionalEgressValuesError
            keys.add(key)

        return super().construct_mapping(node, deep=deep)


_StrictSafeLoader.add_constructor(_MAPPING_TAG, _StrictSafeLoader.construct_mapping)


class _NoAliasSafeDumper(yaml.SafeDumper):
    """Emit a self-contained document without aliases."""

    def ignore_aliases(self, _data: Any) -> bool:
        return True


def _load_documents(content: str) -> list[Any]:
    if any(
        isinstance(token, (AliasToken, AnchorToken))
        for token in yaml.scan(content, Loader=yaml.SafeLoader)
    ):
        raise AdditionalEgressValuesError
    return list(yaml.load_all(content, Loader=_StrictSafeLoader))


def normalize_additional_egress_values(content: str) -> str:
    """Return safe normalized YAML for exactly ``networkPolicy.additionalEgress``."""
    try:
        documents = _load_documents(content)
    except (AdditionalEgressValuesError, yaml.YAMLError) as exc:
        raise AdditionalEgressValuesError from exc

    if len(documents) != 1:
        raise AdditionalEgressValuesError

    document = documents[0]
    if not isinstance(document, dict) or set(document) != {"networkPolicy"}:
        raise AdditionalEgressValuesError

    network_policy = document["networkPolicy"]
    if not isinstance(network_policy, dict) or set(network_policy) != {"additionalEgress"}:
        raise AdditionalEgressValuesError

    additional_egress = network_policy["additionalEgress"]
    if not isinstance(additional_egress, list) or not additional_egress:
        raise AdditionalEgressValuesError

    normalized = {"networkPolicy": {"additionalEgress": additional_egress}}
    return yaml.dump(
        normalized,
        Dumper=_NoAliasSafeDumper,
        default_flow_style=False,
        sort_keys=False,
    )


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text()


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: normalize_additional_egress_values.py INPUT OUTPUT\n")
        return 2

    try:
        content = _read_input(sys.argv[1])
        normalized = normalize_additional_egress_values(content)
    except (AdditionalEgressValuesError, OSError, UnicodeError):
        sys.stderr.write("Invalid additional egress values structure.\n")
        return 2

    try:
        Path(sys.argv[2]).write_text(normalized)
    except (OSError, UnicodeError):
        sys.stderr.write("Unable to write normalized additional egress values.\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
