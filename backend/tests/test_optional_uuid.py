"""Exercise the UUID API consumed by the pinned Crawl4AI/LiteLLM path."""

import copy
import json
import pickle
import re
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest


@pytest.fixture
def native_uuid() -> Any:
    return pytest.importorskip("fastuuid")


def test_litellm_uuid4_callers(native_uuid: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    helper = pytest.importorskip("litellm._uuid")
    assert helper.uuid is native_uuid
    for generate in (helper.uuid4, helper.uuid.uuid4):
        values = [generate() for _ in range(256)]
        assert all(isinstance(value, native_uuid.UUID) for value in values)
        serialized = json.loads(json.dumps([str(value) for value in values]))
        assert len(set(serialized)) == len(values)
        for text in serialized:
            assert re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", text
            )
            parsed = uuid.UUID(text)
            assert parsed.version == 4
            assert parsed.variant == uuid.RFC_4122


@pytest.mark.parametrize("version", [1, 3, 4, 5, 6, 7])
def test_native_uuid_representation_and_binding_comparisons(native_uuid: Any, version: int) -> None:
    reference = uuid.UUID("12345678-1234-1234-9234-123456789abc", version=version)
    value = native_uuid.UUID(str(reference))
    assert str(value) == str(reference)
    assert repr(value) == repr(reference)
    for name in ("int", "bytes", "bytes_le", "hex", "urn", "fields", "time", "version", "variant"):
        assert getattr(value, name) == getattr(reference, name)
    assert value == native_uuid.UUID(bytes=reference.bytes)
    assert value == native_uuid.UUID(bytes_le=reference.bytes_le)
    assert value == native_uuid.UUID(int=reference.int)
    assert value == native_uuid.UUID(fields=reference.fields)
    assert copy.copy(value) == value
    assert copy.deepcopy(value) == value
    assert pickle.loads(pickle.dumps(value)) == value  # noqa: S301 - trusted test value
    assert value != native_uuid.UUID(int=0)
    assert value > native_uuid.UUID(int=0)
    assert value >= native_uuid.UUID(str(reference))
    assert native_uuid.UUID(int=0) < value
    assert value <= native_uuid.UUID(str(reference))


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({}, TypeError, "one of the hex"),
        ({"hex": "invalid"}, ValueError, "badly formed"),
        ({"bytes": b"short"}, ValueError, "16-char"),
        ({"bytes_le": b"short"}, ValueError, "16-char"),
        ({"fields": (1, 2)}, ValueError, "6-tuple"),
        (
            {"hex": "12345678-1234-1234-9234-123456789abc", "version": 9},
            ValueError,
            "illegal version",
        ),
    ],
)
def test_native_uuid_preserves_errors(
    native_uuid: Any, kwargs: dict[str, Any], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        native_uuid.UUID(**kwargs)


def test_native_uuid4_threads_do_not_repeat(native_uuid: Any) -> None:
    with ThreadPoolExecutor(max_workers=4) as executor:
        values = list(executor.map(lambda _: str(native_uuid.uuid4()), range(4096)))
    assert len(set(values)) == len(values)
    assert all(uuid.UUID(value).version == 4 for value in values)


def test_optional_import_remains_lazy() -> None:
    code = """
import sys
from news_dashboard.body_fetch import _crawl4ai_extract_body
assert "crawl4ai" not in sys.modules
assert "fastuuid" not in sys.modules
assert _crawl4ai_extract_body("https://example.com/article") == ("", "error")
assert "crawl4ai" not in sys.modules
assert "fastuuid" not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603 - fixed regression code
