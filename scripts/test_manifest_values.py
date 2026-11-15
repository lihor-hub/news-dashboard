"""Malformed manifest shapes must fail instead of acquiring unchecked types."""

import pytest

from manifest_values import mapping_at, sequence_at, value_at


def test_nested_manifest_values() -> None:
    document = {"spec": {"containers": [{"name": "app"}]}}
    assert value_at(document, "spec", "containers", 0, "name") == "app"  # noqa: S101
    assert mapping_at(document, "spec", "containers", 0) == {"name": "app"}  # noqa: S101
    assert sequence_at(document, "spec", "containers") == [{"name": "app"}]  # noqa: S101


@pytest.mark.parametrize("value", [None, "scalar", [], {1: "non-string key"}])
def test_mapping_rejects_invalid_shapes(value: object) -> None:
    with pytest.raises(TypeError, match="Expected"):
        mapping_at(value)


@pytest.mark.parametrize("value", [None, "scalar", {}])
def test_sequence_rejects_invalid_shapes(value: object) -> None:
    with pytest.raises(TypeError, match="Expected a list"):
        sequence_at(value)


@pytest.mark.parametrize("path", [("missing",), ("spec", 0), ("items", "name")])
def test_invalid_paths_fail(path: tuple[str | int, ...]) -> None:
    with pytest.raises((KeyError, TypeError)):
        value_at({"spec": {}, "items": []}, *path)
