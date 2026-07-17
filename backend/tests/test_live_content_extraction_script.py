"""Tests for the opt-in live extraction corpus runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from news_dashboard.content_extraction import (
    ExtractionAttempt,
    ExtractionResult,
    assess_extracted_text,
)


def _load_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "check_live_content_extraction.py"
    spec = importlib.util.spec_from_file_location("check_live_content_extraction", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_corpus_module_does_not_run_on_import() -> None:
    with patch("news_dashboard.body_fetch.extract_public_content") as extract:
        _load_script()

    extract.assert_not_called()


def test_run_reports_status_method_quality_and_latency(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    text = "meaningful article word " * 30
    quality = assess_extracted_text(text)
    result = ExtractionResult.success(
        text=text,
        method="selenium",
        quality=quality,
        attempts=(
            ExtractionAttempt(
                method="selenium",
                status="accepted",
                latency_ms=321,
                quality=quality,
            ),
        ),
    )

    with patch.object(module, "extract_public_content", return_value=result):
        exit_code = module.run(["https://example.com/article"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "status=ok" in captured.out
    assert "method=selenium" in captured.out
    assert f"chars={quality.character_count}" in captured.out
    assert "accepted=true" in captured.out
    assert "latency_ms=321" in captured.out
    assert "https://example.com/article" in captured.out
