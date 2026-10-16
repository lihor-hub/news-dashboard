# Python 3.15 compatibility report — 2026-10-16

**Keep the supported Python 3.14 runtime. Python 3.15 cutover is not validated.**
This report versions the compatibility evidence for maintainers delivering
[the migration umbrella #1340](https://github.com/lihor-hub/news-dashboard/issues/1340).
The report does not raise the advertised minimum. The core and optional dependency refreshes below
record targeted dependency changes and additional validation workflows; current
runtime declarations, existing CI gates and containers remain on Python 3.14.
[CPython 3.15.0 is stable, released October 9, 2026](https://www.python.org/downloads/release/python-3150/);
the earlier prerelease assumption no longer applies to this assessment.

## Provenance and evidence boundaries

Both audits inspected repository commit
[`d708d05c5c43dfa6cd8720bfe15545400eab5546`](https://github.com/lihor-hub/news-dashboard/commit/d708d05c5c43dfa6cd8720bfe15545400eab5546).
The first used isolated manifests, environments and a source snapshot; the second
inventoried source and ran network-free standard-library probes. The
[persisted audit evidence and planning rechecks](https://github.com/lihor-hub/news-dashboard/issues/1340#issuecomment-6221077889)
are the public provenance, including the original 61-component matrix. Results
below are those observations on **2026-10-16**, except for the explicitly dated
delivery refresh. Neither set establishes the outstanding migration gates.

The detailed local `python315-audit/audit-report.json` has SHA-256
`af7abeb1c155efe1e92dae0c1d615f39adc2950d3b84aba5802bd456a5439a7a`.
Its local location is recorded in the evidence comment; it is a provenance
pointer, not a required public download. This sanitized report omits local user
paths, environments, caches, credentials and raw logs.

The original audit's executed interpreter evidence is limited to **macOS 27.0.1
arm64, standard-GIL CPython 3.15.0 final**, uv python-build-standalone build of
October 14, 2026.
The isolated tool was [uv 0.13.1](https://github.com/astral-sh/uv/releases/tag/0.13.1);
host uv 0.11.24 could not provision final 3.15. That provisioning failure does
not establish Python unavailability. Source-build tools were rustc/cargo 1.96.1.
The delivery refresh adds bounded Linux interpreter probes. No free-threaded
compatibility or new application platform support is claimed.

Evidence levels must remain separate:

| Level | What the audit established | What it does not establish |
|---|---|---|
| Resolution | Original `uv lock --python 3.15.0 --locked` resolved 244 packages, exit 0 | Successful download, build or install |
| Published artifacts | Compatible wheel tags and Linux image indexes exist for some components | Successful install or execution on those platforms |
| Install | Candidate runtime/dev installed 193 packages; `uv pip check` passed | All-extras installation, production pip installation or functional correctness |
| Import | Candidate app and FastMCP Client imported; OpenAPI generated 190 paths | Working database, SMTP relay or browser extraction |
| Functional checks | Ten offline native/API checks passed in v2; 58 focused tests passed in v3 | Full backend, Linux/Windows execution, container, CI/security or deployment validation |

## Delivery refresh — 2026-10-16

The documentation branch was rebased onto
[`ecb6016aaef9bc7f54131ad54449123e1d73d9ff`](https://github.com/lihor-hub/news-dashboard/commit/ecb6016aaef9bc7f54131ad54449123e1d73d9ff).
This refresh validates report delivery on supported **CPython 3.14.6, macOS arm64**;
it does not rerun the original 3.15 candidate suite or change the historical
61-component matrix. Node was 26.7.0, npm 11.19.0 and host uv 0.11.24.

The initial report PR's
[Dependency Review failure](https://github.com/lihor-hub/news-dashboard/actions/runs/38941852878/job/117111185336)
identified source-map-js 1.2.1 (high) and smol-toml 1.8.0 (moderate).
[Separate security PR #1536](https://github.com/lihor-hub/news-dashboard/pull/1536)
merged fixes, including root versions 1.2.2 and 1.9.1. The inherited all-files
Ruff ISC004 failure in `scripts/check_live_content_extraction.py` was fixed by
[PR #1545](https://github.com/lihor-hub/news-dashboard/pull/1545).
Both commits are in this refresh's base. These are resolved report-delivery
blockers; they were not Python 3.15 incompatibilities. No security policy or
Ruff target was weakened.

Fresh commands below exited **0**:

| Check | Bounded result |
|---|---|
| `scripts/bootstrap-worktree.sh`; `uv sync --frozen --all-extras --dry-run`; `uv pip check` | Supported 3.14 environment ready, no sync changes proposed, 236 installed packages consistent; not a fresh 3.15 installation |
| `npm ci`; `make lint`; `make typecheck` | Current lock installed; lint, mypy, ty, pyrefly and frontend typecheck passed |
| `source .env && export PGOPTIONS='-c max_parallel_workers_per_gather=0' && make test` | **3,597 backend/script tests passed, 2 skipped, 24 warnings, 88% coverage**; **1,081 frontend tests passed in 102 files**, plus **2 security regressions** |
| `make build`; `pre-commit run --all-files` | Production frontend build, bundle/CSP checks and every all-files hook passed, including formerly failing Ruff |
| `npx --yes audit-ci@^7 --config .audit-ci.jsonc`; `npm audit --json` | Root policy passed; zero root vulnerabilities |
| `cd website && npx --yes audit-ci@^7 --critical` | Existing website critical threshold passed; noncritical findings remain visible, not a zero-vulnerability claim |

Both DB URL destinations were checked before tests, followed by authenticated
read-only queries: `news_dashboard` on `localhost:55432/news_dashboard_test`,
PostgreSQL 16.14, recovery false, parallel query workers disabled. The existing
`nd-test-pg` was healthy. No database/container reset or native-5432 connection
was used. The two skips are the serial-only performance benchmark under xdist
and unsupported Chrome BiDi interception.

The original Podman/browser prerequisites have also been qualified. A fresh
offline `AsyncWebCrawler` extraction of `raw:` HTML with `CacheMode.BYPASS`
passed on **3.14.6 with crawl4ai 0.9.4**. This does not establish 3.15 all-extras
or browser compatibility. Fresh PyPI metadata still lists fastuuid 0.14.0 with
no cp315/abi3 wheels and the same crawl4ai 0.9.5 dependency chain described below.

Fresh digest-pinned official-image probes exited 0, asserting CPython 3.15.0,
standard GIL and the expected architecture before printing interpreter details:

| Platform | Platform manifest digest | Executed interpreter |
|---|---|---|
| linux/arm64 | `sha256:f97898458240000890f4d60cc53c24550fc141f4215e8ee881701e5f8a3ff8a7` | Linux aarch64, GCC 12.2.0, `Py_GIL_DISABLED=0` |
| linux/amd64 | `sha256:c1035719031463035de2f9b5ee86b0ab18842ddee18556ee89999f4b38a3c559` | Linux x86_64 under QEMU, GCC 12.2.0, `Py_GIL_DISABLED=0` |

The exact probe commands were:

```sh
podman run --rm --platform linux/arm64 \
  docker.io/library/python@sha256:f97898458240000890f4d60cc53c24550fc141f4215e8ee881701e5f8a3ff8a7 \
  python -c 'import platform,sys,sysconfig; assert platform.machine() == "aarch64"; assert sys.version_info[:3] == (3,15,0); assert not sysconfig.get_config_var("Py_GIL_DISABLED"); print(platform.system(),platform.machine(),sys.version,sysconfig.get_config_var("Py_GIL_DISABLED"))'
podman run --rm --platform linux/amd64 \
  docker.io/library/python@sha256:c1035719031463035de2f9b5ee86b0ab18842ddee18556ee89999f4b38a3c559 \
  python -c 'import platform,sys,sysconfig; assert platform.machine() == "x86_64"; assert sys.version_info[:3] == (3,15,0); assert not sysconfig.get_config_var("Py_GIL_DISABLED"); print(platform.system(),platform.machine(),sys.version,sysconfig.get_config_var("Py_GIL_DISABLED"))'
```

An initial mutable-tag
probe with `--pull=never --platform linux/arm64` exited 0 but warned of a cached
amd64 image and printed x86_64; it is **not** an arm64 pass. Digest pinning and
architecture assertions corrected that probe. Neither successful interpreter
probe installed application dependencies or tested image health, MCP, the
devcontainer lifecycle, attestations, security scans or deployment.

Current-head PR checks remain a separate delivery gate; inspect
[PR #1532](https://github.com/lihor-hub/news-dashboard/pull/1532) for their live
results. Documentation path filtering may skip full CI suites; the local full
suite above is separate evidence. No merge, production deployment or 3.15
cutover is implied by this refresh.

## Core dependency preparation — #1528, 2026-10-16

This refresh starts at `28e0437aa99c26e02244c55cdd469a97df945c84`
and keeps `requires-python >=3.14`, all checker targets (including Ruff py313),
existing CI runtime declarations, Dockerfile and devcontainer unchanged.
The report's historical matrix below remains the original audit, not a fresh
certification of every package or platform.

Fresh [PyPI metadata](https://pypi.org/pypi/ormsgpack/json) selects the same five
candidates in the table below: ormsgpack 1.13.0, jiter 0.17.0, tiktoken 0.14.0,
pydantic 2.14.1 and beartype 0.23.1. The targeted lock command updates those
packages, pydantic-core to 2.50.1, typing-inspection to 0.4.4 and removes the
3.15-only typing-extensions 4.15.0 selection in favor of existing 4.16.0.
No other package version changes. No transitive package becomes a direct
requirement: the app uses no newly introduced APIs, and the production install
probe also checks current unconstrained resolution separately.

Fresh failures were reproduced before validation: installing the original
runtime/dev export on stable macOS arm64 3.15 fails building ormsgpack 1.12.2
because PyO3 0.27.2 supports at most 3.14. An isolated import of original
beartype 0.22.9 fails on removed `typing.no_type_check_decorator`. No PyO3
compatibility override is used.

The preparation adds 28 network-free email cases using the **real**
`smtplib.SMTP.send_message` with only transport operations stubbed. They cover
ASCII envelopes with Unicode display names, internationalized domains, sender
and recipient local parts, advertised/absent SMTPUTF8, all three configured TLS
modes, Unicode MIME bodies, safe `smtp_error`, allowed unsubscribe headers,
ignored Bcc injection and rejected CRLF headers. These establish the existing
negotiation behavior on both interpreters. Replacing negotiated sending with
direct serialization makes all 24 transport cases fail; restoring the code
passes all 49 email tests on each interpreter. No production SMTP defect was
reproduced and no runtime email code or header policy changes.

On macOS 27.0.1 arm64, standard-GIL CPython 3.14.6 and stable 3.15.0 (uv
python-build-standalone, October 14), the exact lock installs with these commands:

```sh
uv sync --frozen --all-extras
uv pip check
uv export --frozen --extra dev --no-emit-project > .delivery-evidence/runtime-dev.txt
# PY315 is the installed stable 3.15.0 interpreter described above.
uv venv --python "$PY315" .delivery-evidence/py315
uv pip sync --python .delivery-evidence/py315/bin/python .delivery-evidence/runtime-dev.txt
uv pip check --python .delivery-evidence/py315/bin/python
uv pip install --python .delivery-evidence/py315/bin/python --no-deps -e .
source .env
export PGOPTIONS='-c max_parallel_workers_per_gather=0'
.delivery-evidence/py315/bin/python -m pytest backend/tests/test_email.py backend/tests/test_digest.py \
  backend/tests/test_briefing_email_deliveries.py backend/tests/test_database_config.py \
  backend/tests/test_prompt_catalog.py backend/tests/test_url_safety.py -n 0 -q
.delivery-evidence/py315/bin/python -m pytest --cov --cov-report=term-missing
```

Fresh supported-runtime gates (`make lint`, all three Python checkers and
frontend typecheck via `make typecheck`, `make build`, all-files pre-commit)
pass. `source .env && export PGOPTIONS='-c max_parallel_workers_per_gather=0'
&& make test` passes **3,634 backend tests, 2 skips, 88% coverage**, **1,081
frontend tests** and both npm security regressions. The first 3.14 run had one
duplicate-user-key failure in `test_submit_quiz_not_found`; a full sequential
rerun passed. The failed run is retained in local delivery evidence and is not
counted as passing.

The supported 3.14 all-extras environment has **236 consistent packages**;
3.15 runtime/dev has **193 dependencies plus the editable project (194 installed)**,
explicitly excluding crawl4ai. Native imports,
FastMCP Client, app import, **190 OpenAPI paths**, Unicode MessagePack/JSON,
Pydantic validation and offline tiktoken round trips pass on both.
The focused 3.15 selection passes **167 tests**; full runtime/dev passes
**3,634 tests, 2 skips, 88% coverage**. The skips remain the xdist timing
benchmark and unavailable Chrome BiDi interception. Dedicated `nd-test-pg`
destinations were verified for both URLs at localhost:55432 as `news_dashboard`;
parallel query workers were disabled. No native 5432 connection or database
reset was performed.

Linux 3.15 attempts used the exact runtime export as pip constraints and the
same digest-pinned images recorded above. Bare arm64 slim fails because GCC
is absent. Adding GCC and Rust builds news-dashboard, pyyaml, uuid-utils,
MarkupSafe, orjson, http-ece, httptools, uvloop, xxhash, zstandard, aiohttp and
regex, then fails cffi on missing `ffi.h`. The amd64 QEMU attempt fails when
rustc receives SIGSEGV during uuid-utils metadata preparation. These are failed
install attempts, not passes or proven package incompatibilities.
The opt-in `Python core compatibility` workflow (manual dispatch, or a PR
labeled `python-core-compatibility`) runs on **native**
`ubuntu-24.04` amd64 and `ubuntu-24.04-arm` with GCC, Rust and libffi headers.
It checks both 3.14 and 3.15, separately installing through production `pip
install .` with exact exported runtime constraints and without constraints,
checking consistency, native/app/FastMCP imports and offline functional probes.
Artifacts preserve constraints, installed versions and logs. It does not
publish images or certify the slim-image runtime, optional extras or deployment.

[Native run 38962978516](https://github.com/lihor-hub/news-dashboard/actions/runs/38962978516)
completed successfully on head `71b52b74d04f91366c52d60cebf117fb9df7551c`.
All **eight** production pip installs exited 0: exact scoped lock constraints and
unconstrained `pip install .` on each architecture/interpreter pair below.
Every install passed `pip check`, native/app/FastMCP imports, 190 OpenAPI paths
and Unicode MessagePack, JSON, Pydantic and offline tokenizer probes.

| Native runner | Interpreters | Build tools | Frozen and unlocked installs |
|---|---|---|---|
| Ubuntu 24.04 amd64, glibc 2.39 | CPython 3.14.8, 3.15.0 | GCC 13.3.0, rustc/cargo 1.99.0, libffi headers | Passed |
| Ubuntu 24.04 arm64, glibc 2.39 | CPython 3.14.8, 3.15.0 | GCC 13.3.0, rustc/cargo 1.99.0, libffi headers | Passed |

Both install modes selected the eight scoped candidate versions described above.
Unconstrained resolution also selects newer unrelated dependencies; the artifacts
retain every installed version, and those broader changes are **not** copied
into `uv.lock`. Full backend suite evidence above uses the scoped lock.
The first-head required CI and Dependency Review also passed in
[run 38962978019](https://github.com/lihor-hub/news-dashboard/actions/runs/38962978019).
Inspect [PR #1547](https://github.com/lihor-hub/news-dashboard/pull/1547) for
current-head checks and review; no merge or production deployment is claimed.

The fresh runtime/dev CVE audit command is:

```sh
uvx --python 3.14 pip-audit --disable-pip --no-deps -r .delivery-evidence/runtime-dev.txt -f json
```

It reports **two unchanged findings**, rather than a zero-vulnerability pass:
[langgraph-sdk 0.4.2 authorization filtering (GHSA-fvww-7h3r-vfhp)](https://github.com/advisories/GHSA-fvww-7h3r-vfhp)
and [multidict 6.7.1 memory leak (GHSA-54p9-h82j-f925)](https://github.com/advisories/GHSA-54p9-h82j-f925).
Their fixes are separately tracked by existing
[PR #1539](https://github.com/lihor-hub/news-dashboard/pull/1539) (0.4.4) and
[PR #1540](https://github.com/lihor-hub/news-dashboard/pull/1540) (6.9.1).
No audit allowlist or security gate is changed by this Python preparation.

Fresh fastuuid 0.14.0 source installation still rejects Python 3.15 via
PyO3 0.26.0. Its current metadata still has no cp315/abi3 wheel; **3.15 all-extras
remains blocked under #1530**. This core preparation is independently deployable
on 3.14, and does not advertise full 3.15 support.

## Optional dependency preparation — #1530, 2026-10-17

This refresh starts at `00652956fddff923ea76fe76668783f009269885` and keeps
the Python >=3.14 minimum, Ruff py313, product behavior and existing CI gates.
The historical all-extras failure above remains evidence for the old lock.
A fresh stable macOS arm64 3.15.0 source install reproduced fastuuid 0.14.0's
PyO3 0.26 rejection before the fix.

Fresh metadata for [Crawl4AI 0.9.5](https://pypi.org/pypi/crawl4ai/0.9.5/json)
still pins unclecode-litellm 1.81.13. Its only fastuuid import is in
`litellm._uuid`; main, router and utils call `uuid.uuid4()` and serialize with
`str()`. Upstream [LiteLLM 1.105.1](https://pypi.org/pypi/litellm/1.105.1/json)
also depends on fastuuid. No released standard-library-backed replacement path
was available. The owning LLM package is much larger than fastuuid's source.

The authorized alternative is an identified **fastuuid 0.14.0+nd.1 native source
patch**, under its original BSD 3-Clause license. It uses supported **PyO3
0.30.1**, not a compatibility flag. The binding migration replaces six removed
`downcast` calls with `cast` and explicitly preserves clone-based comparisons;
UUID algorithms, OS-backed randomness, representations and errors are unchanged.
See [source, readable patch, ownership and rebuild instructions](../vendor/fastuuid/README.md).
The manifest activates this source patch only on **Python >=3.15**, retaining
published fastuuid 0.14.0 wheels on 3.14 to avoid a new Rust prerequisite there.
It references the source archive at immutable commit
`310a24220f4c24e098da9a44a75dfcbc7c8419c9`, with SHA-256
`c025db54352c78802b919cc93504321f94f58974c4bebedf4ac7e323bc0d5c22`.
Hatch's documented direct-reference metadata option permits ordinary pip to
consume that same artifact. No resolver override, fabricated distribution,
omitted dependency or source-build compatibility override is involved.

The lock retains fastuuid 0.14.0 below 3.15 and adds its identified local variant
for 3.15+. The only other version changes are **SciPy 1.18.0 → 1.18.1**, **Shapely 2.1.2 →
2.2.0**, and adds **Hypothesis 6.170.1** for upstream property tests. The optional
extra declares the scientific compatibility floors. Crawl4AI remains 0.9.4 and
unclecode-litellm remains 1.81.13; no unrelated dependency versions change.
Building the optional native source on 3.15+ requires Rust >=1.85 and a C linker.

On this supported macOS arm64 host, frozen all-extras installs on **3.14.6 and
stable 3.15.0** pass, with **237 consistent installed packages** on each.
The exact 3.15 command uses an isolated environment under the existing worktree
exclusion so frontend tools do not scan installed Playwright JavaScript:

```sh
# PY315 points to the stable 3.15.0 interpreter recorded in the provenance.
UV_PROJECT_ENVIRONMENT=.worktrees/validation315/.venv \
  uv sync --frozen --all-extras --python "$PY315"
uv pip check --python .worktrees/validation315/.venv/bin/python
.worktrees/validation315/.venv/bin/python -m playwright install chromium
.worktrees/validation315/.venv/bin/python scripts/check_optional_extras.py
```

The **48 upstream UUID tests** pass on each interpreter with Hypothesis's `ci`
profile (2,000 examples per property). Consumed API tests cover UUIDv4 strings,
JSON/pickle/copy round trips, version/variant/time semantics, binding comparisons,
errors and 4,096 threaded random identifiers. Source tests reconstruct the
patched archive byte for byte and ensure uuid/rand/getrandom versions and the
UUID implementation remain unchanged. Gzip compression level is explicit to
avoid differing Python default levels changing the reconstructed artifact.

Real offline Chromium extraction on 3.15 passes through Crawl4AI with
`process_in_browser=True` and `CacheMode.BYPASS`, verifies JavaScript-rendered
Unicode text, and feeds the result into application normalization and quality
checks (**795 characters, 113 words**). All page requests are intercepted and
blocked; the fixture attempts **zero**. A separate call exercises the exact
application lazy-import adapter on raw HTML. The public URL stage remains
intentionally fail-closed for SSRF protection, including when the optional
package is installed. A fresh subprocess checks that importing body_fetch and
calling the public stage do not import Crawl4AI or fastuuid. No product fetch
boundary is relaxed.

Fresh supported-runtime `make lint`, all typecheckers, `make test` and `make
build` pass: **3,651 backend/script tests, 2 documented skips, 88% coverage**,
**1,081 frontend tests**, and both npm security regressions. The focused 3.15
extraction/source/API selection passes **90 tests**. Full frozen all-extras 3.15
passes **3,651 backend/script tests, the same 2 skips, 88% coverage**. Dedicated
PostgreSQL URLs were verified with authenticated read-only queries before tests;
parallel query workers were disabled, with no shared reset or native 5432 use.
Native source-patch validation on head
`c645eaed84161aeae8cc4bb836cce9e78d648146` completed successfully in
[run 38969645747](https://github.com/lihor-hub/news-dashboard/actions/runs/38969645747):
**12 successful installs**, frozen all-extras and ordinary unconstrained pip on
every pair below, each with consistency checks, native imports and real offline
browser/application extraction. This preparatory run exercised the patched
native source on both interpreters. The final marker restores 3.14 registry
wheels; final-head checks and version evidence are linked from
[PR #1550](https://github.com/lihor-hub/news-dashboard/pull/1550).

| Native runner | Stable interpreter | Result | Evidence artifact |
|---|---|---|---|
| ubuntu-24.04 (x86_64) | 3.14.8 | Passed both modes; 17 API/source + 48 upstream tests | [Logs/versions](https://github.com/lihor-hub/news-dashboard/actions/runs/38969645747/artifacts/12076297340) |
| ubuntu-24.04 (x86_64) | 3.15.0 | Passed both modes; 17 API/source + 48 upstream tests | [Logs/versions](https://github.com/lihor-hub/news-dashboard/actions/runs/38969645747/artifacts/12077480228) |
| ubuntu-24.04-arm (aarch64) | 3.14.8 | Passed both modes; 17 API/source + 48 upstream tests | [Logs/versions](https://github.com/lihor-hub/news-dashboard/actions/runs/38969645747/artifacts/12076367169) |
| ubuntu-24.04-arm (aarch64) | 3.15.0 | Passed both modes; 17 API/source + 48 upstream tests | [Logs/versions](https://github.com/lihor-hub/news-dashboard/actions/runs/38969645747/artifacts/12076716316) |
| macos-15 (arm64) | 3.14.7 | Passed both modes; 17 API/source + 48 upstream tests | [Logs/versions](https://github.com/lihor-hub/news-dashboard/actions/runs/38969645747/artifacts/12075694018) |
| macos-15 (arm64) | 3.15.0 | Passed both modes; 17 API/source + 48 upstream tests | [Logs/versions](https://github.com/lihor-hub/news-dashboard/actions/runs/38969645747/artifacts/12076457777) |

Frozen optional versions are Crawl4AI 0.9.4, unclecode-litellm 1.81.13, SciPy
1.18.1, Shapely 2.2.0 and Playwright 1.61.0. Unconstrained pip selects Crawl4AI
0.9.5 and Playwright 1.64.0, with the same LLM owner and scientific versions;
both combinations pass. Artifact logs retain exact installed versions.

The opt-in `Python extras compatibility` workflow uses native Linux amd64,
Linux arm64 and macOS arm64 runners, for 3.14 and 3.15. Each pair runs frozen
`uv sync --frozen --all-extras`, consistency and source/API/upstream tests, then
real offline extraction. It separately tests ordinary unconstrained production
`pip install '.[crawl4ai]'`, `pip check`, native imports and offline extraction.
The first Linux 3.15 attempts reproduced missing libxml2/libxslt headers while
building unchanged lxml 6.1.1. The validation stage installs those upstream
[documented source prerequisites](https://lxml.de/installation.html), plus zlib
headers, alongside GCC/Rust/libffi; it does not alter lxml or bypass compilation.
The workflow uploads installed versions and command logs. It does not certify
containers, devcontainer lifecycle, runtime cutover or deployment.

The fresh all-extras `pip-audit` scan reports **37 existing findings**: one each
in langgraph-sdk 0.4.2 and multidict 6.7.1, plus **35 in NLTK 3.10.0**, all three
versions unchanged from origin/main. Core remediation remains in #1539/#1540;
NLTK remediation is separately tracked by
[#1549](https://github.com/lihor-hub/news-dashboard/issues/1549); one finding,
PYSEC-2026-3740, currently has no published fix version.
The 3.15 local fastuuid version is unknown to PyPI's vulnerability service. A separate
normal dependency audit of upstream fastuuid 0.14.0 reports no findings;
**cargo-audit 0.22.2** checks the patched Cargo.lock against RustSec commit
`f28da8c5d386e507fac79153655184056a20c054`: **zero vulnerabilities**. Its inherited
informational rand 0.8.5 warning RUSTSEC-2026-0097 requires the `log` feature,
which the actual native feature graph does not enable. No finding is hidden,
no allowlist added and no security policy changed. This is not a claim of zero
vulnerabilities across all extras.

## Failed attempts and the working core candidate

The original runtime/dev install exited 1: **ormsgpack 1.12.2**, using PyO3
0.27.2, rejects interpreters above 3.14. Isolated **fastuuid 0.14.0** also failed,
using PyO3 0.26.0. No compatibility override was used. Missing wheels alone are
not incompatibility evidence: many locked packages built and imported on the
audit host.

Old pydantic-core, jiter and tiktoken built successfully but failed loading with
a **mis-aligned LINKEDIT string pool**. Those are host-specific macOS observations,
not demonstrated Linux failures. Candidate wheels resolved these imports.

The targeted candidate used this command on copied manifests:

```sh
uv lock --upgrade-package ormsgpack --upgrade-package jiter \
  --upgrade-package tiktoken --upgrade-package pydantic --upgrade-package beartype
```

| Package | Original selection | Tested candidate |
|---|---|---|
| ormsgpack | 1.12.2 | [1.13.0](https://pypi.org/project/ormsgpack/1.13.0/) |
| jiter | 0.16.0 | [0.17.0](https://pypi.org/project/jiter/0.17.0/) |
| tiktoken | 0.13.0 | [0.14.0](https://pypi.org/project/tiktoken/0.14.0/) |
| pydantic / pydantic-core | 2.13.4 / 2.46.4 | [2.14.1](https://pypi.org/project/pydantic/2.14.1/) / [2.50.1](https://pypi.org/project/pydantic-core/2.50.1/) |
| beartype | 0.22.9 | [0.23.1](https://pypi.org/project/beartype/0.23.1/) |
| typing-extensions | 4.15.0 under the original 3.15 marker | 4.16.0 |
| typing-inspection | 0.4.2 | 0.4.4 |

This is a working set, not proof of lowest compatible versions. The v2 candidate
still had beartype 0.22.9, which imports the removed
[`typing.no_type_check_decorator`](https://docs.python.org/3.15/whatsnew/3.15.html#typing).
V3 changed beartype to 0.23.1 and verified FastMCP Client import and full collection.
The ten v2 native/API checks were not all rerun after that change.

| Executed check | Result and limit |
|---|---|
| Ruff 0.16.9 lint and format | Passed on backend snapshot with intentional py313 retained; py315 smoke accepted with development warning |
| mypy 2.3.1 | Explicit 3.15 target passed for 359 source files |
| ty 0.0.84 / pyrefly 1.3.1 | Explicit 3.15 targets and candidate interpreter passed; existing suppressions/warnings retained |
| pytest 9.1.1 / xdist 3.8.0 / pytest-cov 7.1.0 | Toolchain scratch test passed; not application coverage evidence |
| V3 backend collection | **3,405 tests collected**, exit 0 |
| V3 `test_database_config.py`, `test_prompt_catalog.py`, `test_url_safety.py` | **58 passed in 4.74 seconds**, exit 0 |
| Broader v2 attempt | **1 failed, 5 passed, 4 errors**, interrupted at 119.11 seconds, exit 2 |
| Full backend and mandatory delivery gates | **Incomplete**; collection/focused success does not supersede the broader failed attempt |

The broader attempt encountered three beartype-related FastMCP Client collection
errors (subsequently fixed in v3), application lifespan pool timeout, and refused
PostgreSQL connections at localhost:55432 despite a non-DB selection. The original
audit's Podman socket and dedicated database were unavailable. These are local
test prerequisites, not evidence of a Python database defect.

## Optional extra, images and security prerequisites

The original frozen all-extras install exited 1 on Shapely 2.1.2, lacking GEOS
and NumPy headers during source build. SciPy 1.18.0 also failed without Fortran.
Later no-build installations and imports of **SciPy 1.18.1 and Shapely 2.2.0**
passed on macOS. Those original failures are qualified, not erased.

The candidate all-extras install still fails on fastuuid. At audit time,
[fastuuid metadata](https://pypi.org/pypi/fastuuid/json) listed latest 0.14.0
with no cp315/abi3 wheels; the executed source build rejected 3.15.
[crawl4ai 0.9.5](https://pypi.org/pypi/crawl4ai/0.9.5/json) retains
`unclecode-litellm==1.81.13`, whose
[dependency metadata](https://pypi.org/pypi/unclecode-litellm/1.81.13/json) requires
**fastuuid>=0.13.0**. Version 0.14.0 was the lock selection, not an upstream exact
pin. A supported future release could satisfy the range. Browser download and
extraction were not attempted in the original audit. A supported dependency
replacement or tested custom implementation is an authorized path for #1530;
it must preserve behavior and pass the all-extras and browser gates. Do not
remove the extra or use a PyO3 compatibility override to claim success.

The [MCR tags API](https://mcr.microsoft.com/v2/devcontainers/python/tags/list)
had no 3.15 tags. Manifest GET for `3.15-bookworm` returned 404; the `3.14-bookworm`
control returned 200 with OCI-index/Docker-manifest-list Accept headers. An
initial single-image-only Accept header returned 404 even for the control.
Use a tested official-Python-based development image, or a subsequently verified
MCR artifact. Preserve Node 26, PostgreSQL wiring, hooks and editor tooling.

The [official Python image catalog](https://raw.githubusercontent.com/docker-library/official-images/master/library/python)
and registry indexes supplied these artifact observations, including Linux amd64
and arm64. **Neither image was built or executed by the audit.** Resolve fresh
digests during implementation; these are historical observations, not deployment pins.

| Tag | Observed index digest |
|---|---|
| `python:3.15-slim` (also `3.15.0-slim`) | `sha256:f48fda6d59b2b3437781d1c3ccf4aa0e26ae871de3cdd758b49ab45ee7291619` |
| `python:3.15.0-slim-bookworm` | `sha256:122756f3fe72c4f5d3d71897888204ee85774bc79de952555b8a474e1d0a5d53` |

Current [production Dockerfile](../Dockerfile) uses unlocked `pip install .`
without a C/Rust toolchain. CI/bootstrap use frozen all-extras; nightly, timing
and devcontainer installs also differ. Each path needs its own evidence.

The [CodeQL support table](https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/)
listed Python through 3.14 at audit time. Preserve existing source grammar and
verify actual Python and JS/TS extraction/analysis. This is a grammar-validation
hazard, not proof that unchanged source cannot be analyzed. Dependency Review,
dependency CVE audit, npm policies, Trivy HIGH/CRITICAL and SARIF, OS updates,
SBOM/provenance and multiarchitecture checks must remain effective. Python 3.15
CI/security and deployment validation are **incomplete**, not waived by this report
or by passing the supported-3.14 documentation checks in the delivery refresh.

## Platform and wheel evidence matrix

These 61 rows preserve the public audit summary. Wheel columns describe
**published artifacts for the original selected version**, including compatible
pure-Python and abi3 wheels, not just cp315 binaries. Order: macOS arm64 (M),
Linux amd64 (Lx), Linux arm64 (La), Windows amd64 (W). Linux metadata used glibc
manylinux tags, not an Alpine/musl promise. Install/import columns are executed
macOS observations from isolated probes, not a complete environment or functional
test. **— means unexecuted/unknown, not pass.** Later candidate fixes above do
not rewrite the original results. Windows artifact metadata does not certify a
Windows runtime; the original audit contains no Linux/Windows executable evidence.

| Component | Original selected | Wheels M/Lx/La/W | macOS install | macOS import |
|---|---|---|---|---|
| aiohttp | 3.14.3 | no/no/no/no | PASS | PASS |
| ast-serialize | 0.6.0 | yes/yes/yes/yes | PASS | PASS |
| bcrypt | 5.0.0 | yes/yes/yes/yes | PASS | PASS |
| brotli | 1.2.0 | no/no/no/no | PASS | PASS |
| caio | 0.9.25 | yes/yes/yes/yes | — | — |
| cffi | 2.0.0 | no/no/no/no | PASS | PASS |
| chardet | 7.4.3 | yes/yes/yes/yes | — | — |
| charset-normalizer | 3.4.7 | yes/yes/yes/yes | — | — |
| coverage | 7.14.1 | yes/yes/yes/yes | PASS | PASS |
| crawl4ai | 0.9.4 | yes/yes/yes/yes | — | — |
| cryptography | 50.0.0 | yes/yes/yes/yes | PASS | PASS |
| fastuuid | 0.14.0 | no/no/no/no | FAIL | — |
| frozenlist | 1.8.0 | yes/yes/yes/yes | — | — |
| greenlet | 3.5.3 | yes/yes/yes/yes | PASS | PASS |
| hf-xet | 1.5.1 | yes/yes/yes/yes | PASS | PASS |
| httptools | 0.8.0 | no/no/no/no | PASS | PASS |
| jiter | 0.16.0 | no/no/no/no | PASS | FAIL |
| librt | 0.13.0 | no/no/no/no | PASS | PASS |
| lxml | 6.1.1 | no/no/no/no | PASS | PASS |
| markupsafe | 3.0.3 | no/no/no/no | PASS | PASS |
| multidict | 6.7.1 | yes/yes/yes/yes | — | — |
| mypy | 2.3.1 | yes/yes/yes/yes | PASS | PASS |
| numpy | 2.5.3 | yes/yes/yes/yes | PASS | PASS |
| orjson | 3.11.9 | no/no/no/no | PASS | PASS |
| ormsgpack | 1.12.2 | no/no/no/no | FAIL | — |
| patchright | 1.61.2 | yes/yes/yes/yes | PASS | PASS |
| pillow | 12.3.0 | yes/yes/yes/yes | PASS | PASS |
| playwright | 1.61.0 | yes/yes/yes/yes | PASS | PASS |
| pre-commit | 4.6.2 | yes/yes/yes/yes | PASS | PASS |
| propcache | 0.5.2 | yes/yes/yes/yes | — | — |
| protobuf | 6.33.6 | yes/yes/yes/yes | — | — |
| psutil | 7.2.2 | yes/yes/yes/yes | PASS | PASS |
| psycopg | 3.3.6 | yes/yes/yes/yes | PASS | PASS |
| psycopg-binary | 3.3.6 | yes/yes/yes/yes | — | — |
| pydantic | 2.13.4 | yes/yes/yes/yes | PASS | FAIL |
| pydantic-core | 2.46.4 | no/no/no/no | PASS | FAIL |
| pyrefly | 1.3.1 | yes/yes/yes/yes | PASS | PASS |
| pytest | 9.1.1 | yes/yes/yes/yes | PASS | PASS |
| pytest-cov | 7.1.0 | yes/yes/yes/yes | PASS | PASS |
| pytest-xdist | 3.8.0 | yes/yes/yes/yes | PASS | PASS |
| pywin32 | 312 | no/no/no/yes | — | — |
| pyyaml | 6.0.3 | no/no/no/no | PASS | PASS |
| rapidfuzz | 3.14.6 | yes/yes/yes/yes | PASS | PASS |
| regex | 2026.6.28 | no/no/no/no | PASS | PASS |
| rpds-py | 2026.6.3 | yes/yes/yes/yes | PASS | PASS |
| rtree | 1.4.1 | yes/yes/yes/yes | PASS | PASS |
| ruff | 0.16.9 | yes/yes/yes/yes | PASS | PASS |
| scipy | 1.18.0 | no/no/no/no | FAIL | — |
| shapely | 2.1.2 | no/no/no/no | FAIL | — |
| tiktoken | 0.13.0 | no/no/no/no | PASS | FAIL |
| tokenizers | 0.23.1 | yes/yes/yes/yes | PASS | PASS |
| ty | 0.0.84 | yes/yes/yes/yes | PASS | PASS |
| uuid-utils | 0.17.0 | no/no/no/no | PASS | PASS |
| uvloop | 0.22.1 | no/no/no/no | PASS | PASS |
| vulture | 2.16 | yes/yes/yes/yes | — | — |
| watchfiles | 1.2.0 | yes/yes/yes/no | PASS | PASS |
| wrapt | 2.2.1 | yes/yes/yes/yes | — | — |
| xxhash | 3.8.1 | no/no/no/no | PASS | PASS |
| yarl | 1.24.2 | yes/yes/yes/yes | — | — |
| zstandard | 0.25.0 | no/no/no/no | PASS | PASS |
| beartype | 0.22.9 | —/—/—/— | — | — |

## Bounded standard-library assessment

The actionable preparation is explicit `encoding="utf-8"` on six owned text-file
operations: changelog reader, version reader, three changelog CLI reads/writes,
and generated configuration output. Keep binary input unchanged. Non-ASCII
round-trip tests belong in [#1527](https://github.com/lihor-hub/news-dashboard/issues/1527).
[PEP 686](https://peps.python.org/pep-0686/) explains the default-encoding change;
preparation must work without raising the Python minimum.

Stable 3.15 email probes distinguished direct default serialization from real
[`SMTP.send_message`](https://docs.python.org/3.15/library/smtplib.html#smtplib.SMTP.send_message).
ASCII mailboxes with Unicode display name/subject serialized. Internationalized
local parts/domains raised `HeaderWriteError` under direct serialization, while
the real method with a transport stub succeeded when SMTPUTF8 was advertised
(SMTPUTF8 and BODY=8BITMIME options), otherwise raising `SMTPNotSupportedError`.
The [email policy documentation](https://docs.python.org/3.15/library/email.policy.html#email.policy.EmailPolicy.utf8)
explains the UTF-8 serialization policy. There is **no confirmed production email
defect**: the existing fake serializes directly and misses negotiation. Add
transport-level regressions in #1528; do not blanket-enable utf8 or weaken header
injection checks.

| Candidate adoption | Decision and reason |
|---|---|
| [profiling.sampling](https://docs.python.org/3.15/library/profiling.sampling.html) | Deferred development-only follow-up after cutover: test permissions, platform support and a real ingestion/briefing workload; no production privileges, default profiling or unmeasured speed claims |
| `bytearray.take_bytes` | No demonstrated benefit: TTS already writes its bytearray directly |
| `re.prefixmatch`, `TaskGroup.cancel`, `sentinel`, `frozendict`, unpacking comprehensions | No matching need or meaningful improvement demonstrated; avoid cosmetic/new-syntax rewrites |
| New typing forms, closed TypedDicts, replacing typing_extensions around LangGraph | Separate checker/framework and CodeQL evidence required; retain intentional TypedDict workarounds |
| URL empty-component semantics, ancestor-directory modes, concurrent iterators | Behavior changes need product requirements, including URL deduplication identity |
| XML validation, grapheme truncation, JSON hooks, math.integer | No demonstrated requirement; preserve defusedxml and current semantics |

Free-threaded Python, Windows runtime certification and broad modernization are
outside this migration's executable acceptance scope.

## Refresh the evidence safely

Run isolated probes first. Keep the supported checkout, its environment and
runtime declarations untouched. These commands reconstruct the audit process;
the public report is not a copy of the original candidate lock or raw probe
scripts. New resolutions may select different transitive versions. Record the
actual candidate set rather than calling a fresh resolution the historical set.
The full gates below remain separate from these probes.

### 1. Create an isolated snapshot and provision the stable interpreter

From this repository, use a fresh temporary directory. `git archive` excludes
ignored `.env`, environments and caches. Check the recorded commit out only in
the snapshot; use a newly recorded commit for a current-main refresh.

```sh
audit_root=$(mktemp -d "${TMPDIR:-/tmp}/nd-python315.XXXXXX")
audit_commit=d708d05c5c43dfa6cd8720bfe15545400eab5546
mkdir "$audit_root/snapshot"
git archive "$audit_commit" | tar -x -C "$audit_root/snapshot"
python3 -m venv "$audit_root/tools"
"$audit_root/tools/bin/python" -m pip install 'uv==0.13.1'
export PATH="$audit_root/tools/bin:$PATH"
export UV_CACHE_DIR="$audit_root/cache"
export UV_PYTHON_INSTALL_DIR="$audit_root/python"
unset DATABASE_URL TEST_DATABASE_URL POSTGRES_HOST POSTGRES_PORT POSTGRES_DB
unset POSTGRES_USER POSTGRES_PASSWORD
uv --version
uv python install 3.15.0
cd "$audit_root/snapshot"
uv run --isolated --no-project --python 3.15.0 python -c \
  'import platform, sys, sysconfig; print(platform.platform(), platform.machine(), sys.version, sysconfig.get_config_var("Py_GIL_DISABLED"))'
```

Confirm final 3.15.0 and a standard-GIL build. Record each command's exit status;
a provisioning failure stops executable claims. Do not set
`PYO3_USE_ABI3_FORWARD_COMPATIBILITY` or similar overrides.

### 2. Preserve original failures, then probe the candidate separately

Keep the original and candidate manifests/environments separate. Run the failing
install attempts individually; record exit status without treating an expected
failure as a pass. The audit's install commands omitted project installation and
used the source snapshot through `PYTHONPATH`.

```sh
uv lock --python 3.15.0 --locked
UV_PROJECT_ENVIRONMENT="$audit_root/original-dev" \
  uv sync --python 3.15.0 --frozen --extra dev --no-install-project
UV_PROJECT_ENVIRONMENT="$audit_root/original-all" \
  uv sync --python 3.15.0 --frozen --all-extras --no-install-project
mkdir "$audit_root/candidate"
cp pyproject.toml uv.lock "$audit_root/candidate/"
cd "$audit_root/candidate"
uv lock --python 3.15.0 --upgrade-package ormsgpack --upgrade-package jiter \
  --upgrade-package tiktoken --upgrade-package pydantic --upgrade-package beartype
export UV_PROJECT_ENVIRONMENT="$audit_root/candidate-dev"
uv sync --python 3.15.0 --frozen --extra dev --no-install-project
uv pip check --python "$UV_PROJECT_ENVIRONMENT/bin/python"
```

Stop if candidate installation or consistency fails. Only after both succeed,
run the following in the same shell; confirm the selected interpreter before
running tools so a partial environment cannot silently fall back to host Python.
Database variables remain unset for these isolated, non-DB probes. Do not load
the delivery worktree's `.env` here.

```sh
export PATH="$UV_PROJECT_ENVIRONMENT/bin:$PATH"
python -c 'import sys, sysconfig; assert sys.version_info[:3] == (3, 15, 0); assert not sysconfig.get_config_var("Py_GIL_DISABLED"); print(sys.executable, sys.version)'
cd "$audit_root/snapshot"
export PYTHONPATH=.:backend
python -c 'import news_dashboard.main; from fastmcp import Client; print(len(news_dashboard.main.app.openapi()["paths"]))'
ruff check backend
ruff format --check backend
mypy --python-version 3.15 backend
ty check --python "$UV_PROJECT_ENVIRONMENT/bin/python" --python-version 3.15 backend
pyrefly check --python-interpreter-path "$UV_PROJECT_ENVIRONMENT/bin/python" --python-version 3.15 backend
pytest --collect-only -q backend/tests
pytest -n 0 backend/tests/test_database_config.py \
  backend/tests/test_prompt_catalog.py backend/tests/test_url_safety.py
```

Test collection is not execution. Run the ten native/API functional probes and
SMTP transport cases as separately reported checks; imports alone do not
recreate them. For all-extras, use a separate copy of the candidate, target SciPy
and Shapely updates, then run frozen all-extras installation and actual browser
extraction only if installation succeeds. Recheck PyPI wheel filenames and
requirements for each version; use compatible cp315/abi3/pure-Python tags for
each platform. Metadata and `--no-build` dry runs cannot certify Linux/Windows
execution. Test the unlocked production pip path independently on Linux amd64
and arm64, including native imports and image health/readiness/CLI/MCP probes.

### 3. Run repository gates only against the authorized test database

In an isolated delivery worktree based on freshly fetched/rebased main, run
`scripts/bootstrap-worktree.sh` before testing/committing and keep its `.venv/bin`
on PATH. Bootstrap retains an existing environment: for 3.15 work explicitly
create a separate migration environment, never alter another worktree's venv.
Confirm `podman ps --filter name=nd-test-pg` and that **both** `DATABASE_URL` and
`TEST_DATABASE_URL` select PostgreSQL role `news_dashboard`, database
`news_dashboard_test`, host localhost (or 127.0.0.1), port **55432**. Validate
destinations without printing passwords or full URLs. If unavailable, safely
start the existing machine/container or report the prerequisite; do not reset
unrelated data or connect to native host 5432. Container-internal `db:5432` is a
different namespace, not permission to use native PostgreSQL.

After those checks, run the repository commands from that worktree:

```sh
export PATH="$PWD/.venv/bin:$PATH"
make lint
make typecheck
source .env && export PGOPTIONS='-c max_parallel_workers_per_gather=0' && make test
make build
pre-commit run --all-files
```

Run applicable pre-push hooks and required CI/review/merge-queue gates without
bypasses. Runtime cutover additionally requires frozen all-extras and unlocked
production/devcontainer installations, Linux amd64/arm64 builds and execution,
security scans, and post-deployment image digest/readiness/public TLS evidence.
Preserve PostgreSQL-only psycopg SQL, intentional lazy imports, Ruff py313,
stdlib system-Python release helpers and interpreter-neutral compose/Helm probes.
No failed, pending or unavailable gate is a success.

For each refresh append date, repository SHA, interpreter/build/GIL, OS/arch,
tool/package versions, exact command, exit status and bounded result. Report
resolution, artifact, install, import and functional evidence separately. Link
sanitized results from the umbrella; never publish `.env`, tokens, connection
strings, environment dumps, caches or unsanitized logs. Keep failed attempts and
add their qualifications rather than silently replacing them.

## Ordered delivery and outstanding gates

| Child | Scope | Dependency or outstanding evidence |
|---|---|---|
| [#1526](https://github.com/lihor-hub/news-dashboard/issues/1526) | This versioned report and index | Documentation-only, independently mergeable through applicable delivery gates |
| [#1527](https://github.com/lihor-hub/news-dashboard/issues/1527) | Explicit UTF-8 preparation | Independent, retain 3.14 and prove non-ASCII round trips |
| [#1528](https://github.com/lihor-hub/news-dashboard/issues/1528) | Core runtime/dev dependencies and SMTPUTF8 regressions | Implemented in [PR #1547](https://github.com/lihor-hub/news-dashboard/pull/1547); full scoped suites/native production installs pass, CVE findings remain in separate PRs |
| [#1529](https://github.com/lihor-hub/news-dashboard/issues/1529) | Validated stable-3.15 devcontainer | Needs #1528 and working container runner; missing MCR tag has an official-base alternative |
| [#1530](https://github.com/lihor-hub/news-dashboard/issues/1530) | Supported crawl4ai all-extras path | Identified supported native source patch and local 3.15 browser evidence added; see optional preparation and PR acceptance for native matrix/security limits |
| [#1531](https://github.com/lihor-hub/news-dashboard/issues/1531) | Atomic runtime/tooling/CI/current-docs cutover | Needs all five preceding items and full test, multiarchitecture, CI/security and deployment evidence |

The requested delivery order is serial; steps 1–3 have no hard technical
dependency on each other. Steps 4–5 can each proceed when their actual
prerequisites pass. Do not close the umbrella or describe Python 3.15 as
supported until the cutover's acceptance gates are observed on its actual head.
