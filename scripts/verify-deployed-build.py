#!/usr/bin/env python3
"""Reject a healthy-but-stale deployment by checking its public build identity."""

from __future__ import annotations

import json
import re
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def matches_build(body: str, revision: str, version: str) -> bool:
    try:
        build = json.loads(body)
    except (ValueError, TypeError):
        return False
    return (
        isinstance(build, dict)
        and build.get("revision") == revision
        and build.get("version") == version
    )


def verify(base: str, revision: str, version: str, attempts: int = 12) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        message = "Expected a full lowercase commit SHA"
        raise ValueError(message)
    for attempt in range(attempts):
        try:
            request = Request(  # noqa: S310 -- operator-controlled application origin
                f"{base.rstrip('/')}/build-info.json?revision={revision}",
                headers={"Cache-Control": "no-cache"},
            )
            with urlopen(request, timeout=15) as response:  # noqa: S310
                body = response.read(65536).decode("utf-8")
            if matches_build(body, revision, version):
                print(f"Verified public build {revision} ({version})")  # noqa: T201
                return
        except (URLError, TimeoutError, UnicodeError) as exc:
            print(f"Build verification retry: {exc}", file=sys.stderr)  # noqa: T201
        if attempt + 1 < attempts:
            time.sleep(5)
    message = f"Public deployment did not serve expected build {revision} ({version})"
    raise RuntimeError(message)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        message = "Usage: verify-deployed-build.py BASE_URL REVISION VERSION"
        raise SystemExit(message)
    verify(*sys.argv[1:])
