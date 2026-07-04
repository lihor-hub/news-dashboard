# vulture whitelist — symbols that appear unused but are kept intentionally.
#
# Nothing needs to be listed here today: the pytest-fixture and fake-signature
# false positives found so far are handled via `ignore_names` in
# `[tool.vulture]` (pyproject.toml), since vulture's whitelist mechanism only
# covers module-level symbols, not local variables/parameters. This file
# exists so `make dead-code` has a stable whitelist target to grow into.
