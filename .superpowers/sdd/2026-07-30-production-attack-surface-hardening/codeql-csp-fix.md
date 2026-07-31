# CodeQL CSP closing-tag fix

## Outcome

CodeQL check-run `91085156505` reported a high-severity `Bad HTML filtering
regexp` finding in `scripts/check-csp-build.mjs`: the script-tag matcher did
not recognize valid closing tags with whitespace before `>`, such as
`</script >`. That could make external-script extraction treat markup between
two external script tags as an inline script, or miss the service-worker
registration script.

The matcher now accepts HTML whitespace before the closing `>`:

```text
</script\\s*>
```

No dependency or parser refactor was introduced.

## TDD evidence

### RED

The CSP checker was run through its real temporary-build harness after adding
external-script fixtures for:

- `</script >`
- `</ScRiPt>`
- `</SCRIPT\n\t >`

Before the implementation change, the whitespace cases failed with:

```text
check-csp-build: no external service-worker registration script was emitted
```

The mixed-case-only fixture already passed because matching is
case-insensitive. An inline-body fixture using `</script >` was and remains
rejected, proving the regression does not weaken the fail-closed body check.

### GREEN

```text
npm run test:frontend -- frontend/src/__tests__/pwa.test.ts
1 test file passed, 21 tests passed
```

The focused suite also retains real-script rejection tests for inline
service-worker code, HTML event handlers, and `javascript:` URLs.

## Verification

```text
npm run lint
exit 0

npm run format:check
exit 0

npm run typecheck
exit 0

npm run test:frontend
97 test files passed, 1023 tests passed

npm run build
exit 0; CSP checker reported the external service-worker registration as
CSP-compatible

git diff --check
exit 0
```

The unrelated CodeQL scraper cyclic-import notice was intentionally left
unchanged.

## Follow-up: exact HTML whitespace semantics

The first fix used JavaScript's `\s` class. That class is broader than HTML's
definition of whitespace: it also accepts Unicode characters such as NBSP
(`U+00A0`) and em space (`U+2003`). A browser does not close a script element
at `</script\u00a0>`, but the checker did, allowing the checker to ignore an
inline body before a later valid `</script>`.

The end-tag matcher now uses the exact HTML ASCII whitespace set:

```text
</script[ \t\n\f\r]*>
```

### Follow-up TDD evidence

RED:

```text
npm run test:frontend -- frontend/src/__tests__/pwa.test.ts
2 failed, 24 passed
```

Both NBSP and em-space fixtures expected the checker to reject an inline body,
but the checker exited 0.

GREEN:

```text
npm run test:frontend -- frontend/src/__tests__/pwa.test.ts
1 test file passed, 26 tests passed
```

The suite explicitly accepts space, tab, LF, form-feed, and CR before `>`,
including a mixed-case closing tag, and rejects NBSP and em space as end-tag
whitespace.

Fresh follow-up verification:

```text
npm run lint
exit 0

npm run format:check
exit 0

npm run typecheck
exit 0

npm run build
exit 0; CSP checker accepted the generated external registration script
```
