# fastuuid native source patch

The news-dashboard maintainers own **0.14.0+nd.1**, a source patch of
[thedrow/fastuuid 0.14.0](https://pypi.org/project/fastuuid/0.14.0/), under its
unchanged BSD 3-Clause license (see LICENSE). This is the upstream Rust UUID
implementation, with an identified local version and supported Python bindings.
It does not substitute a Python module or implement a different UUID algorithm.
The final manifest activates this patch only on Python >=3.15. Python 3.14
retains published fastuuid 0.14.0 wheels, avoiding a new Rust prerequisite on
its supported development platforms.

Crawl4AI 0.9.4 pins unclecode-litellm 1.81.13, whose `litellm._uuid` aliases
fastuuid and supplies `uuid4()` and `uuid.uuid4()` to three callers. Those callers
serialize identifiers with `str()`. Rechecked Crawl4AI 0.9.5 keeps that dependency;
current upstream LiteLLM 1.105.1 also requires fastuuid. No released standard
library UUID dependency path was available on 2026-10-17. Patching the 18 KB
fastuuid source distribution avoids carrying the much larger LLM integration.

## Source and changes

The original archive is preserved byte for byte. Its authoritative artifact is
[fastuuid-0.14.0.tar.gz](https://files.pythonhosted.org/packages/c3/7d/d9daedf0f2ebcacd20d599928f8913e9d2aea1d56d2d355a93bfa2b611d7/fastuuid-0.14.0.tar.gz),
SHA-256 `178947fc2f995b38497a74172adee64fdeb8b7ec18f2a5934d037641ba265d26`.
`python315.patch` shows every changed line, including Cargo.lock:

- PyO3 0.26.0 → **exactly 0.30.1**. Its
  [release notes](https://github.com/PyO3/pyo3/blob/v0.30.1/CHANGELOG.md) explicitly
  support Python 3.15.0 final. Replace removed `downcast` with `cast`, and opt
  into the previous clone-based `FromPyObject` behavior for comparisons.
- Identify the local version, minimum Rust 1.85 and Python 3.9, and 3.15 classifier.
  The application continues to require Python >=3.14.
- Pin the build backend to maturin 1.15.0 and require its
  [locked Cargo build](https://www.maturin.rs/config). Keep all uuid, rand and
  getrandom versions/checksums unchanged; regenerate only PyO3's dependency path.

No UUID generation, randomness, parsing, serialization or version logic changed.
The unchanged uuid crate uses OS-backed randomness through getrandom. Sample
uniqueness tests supplement source verification; they are not an entropy proof.
No PyO3 forward-compatibility flag or unsupported ABI build is used.

## Rebuild and review

With Python >=3.14 on PATH, run from the repository root:

```bash
bash scripts/rebuild_fastuuid.sh
pytest backend/tests/test_fastuuid_source.py -n 0
```

The script verifies the original hash, applies the readable patch, then creates a
normalized source archive without network access or executing upstream build
code. The regression rebuilds it byte for byte and verifies that only binding
adaptations changed the Rust implementation. Both archives contain the full
upstream source, license and tests; extract with `tar -xzf <archive>` to inspect.
The patched archive SHA-256 is
`c025db54352c78802b919cc93504321f94f58974c4bebedf4ac7e323bc0d5c22`.

The optional dependency must reference this archive at an immutable Git commit
and include its SHA-256, for ordinary pip as well as frozen uv installation.
Building the 3.15+ source needs a C linker and Rust >=1.85. There are no prebuilt
local wheels; the built native wheel retains the upstream LICENSE.
The core production install does not request this optional dependency.

## Maintenance and security

Review PyO3 release notes, RustSec advisories for the patched Cargo.lock, and
Python dependency audits when updating. Audit results for a local version must
be interpreted against upstream 0.14.0 and the actual Cargo dependency graph;
an unknown local-version record alone does not establish safety. Never add an
audit exception for this patch. Existing unrelated findings remain separately
tracked, with their configured gates intact.

Run the upstream `tests/test_uuid.py` with Hypothesis's `ci` profile (2,000 cases
per property), the consuming API regressions, frozen all-extras installs, native
imports and offline browser smoke on macOS arm64 and Linux amd64/arm64 for both
3.14 and 3.15. Retire the patch once a released supported upstream path passes
those checks. Do not change the archive behind a published commit/hash; a new
patch needs a new local version and immutable artifact reference.
