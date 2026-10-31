# Historical-v1 operator runbook (#1629)

## Authorization boundary — STOP before real data

This is tooling, not permission to operate. No actual-user inventory, dry-run,
apply, retention pause/drain, deployment, production connection or sends have
been authorized or executed for this slice. All verification uses newly seeded
fixtures in the existing dedicated PostgreSQL test container. Do not copy test
fixture commands into production.

The operator's `--protection-ref` is an audit reference to external authorization
and evidence, **not proof of human approval or effective retention protection**.
The CLI cannot verify an instance-wide retention pause, drained in-flight tasks,
or all deployed writers. Do not prepare/apply without the checks below.

## Separately authorized operational sequence

1. **Inventory approval:** obtain separate authorization for read-only aggregate
   retained evidence/date quality, legacy keys, identity availability and volume
   inventory. Do not use achievements GET to infer eligibility. Missing/deleted
   evidence is unrecoverable; never infer missing reads from a badge. No inventory
   was run here.
2. **Protection approval:** approve a rollout window, retention protection and
   rollback owner. Deploy all cooperating live/manual/automatic/List/import
   writers and calibrated attribution before capture. Confirm no older writer
   instances remain. Separately authorize pause of every article cleanup/deletion
   path affecting retained evidence, then drain in-flight deletion transactions.
   Do not pause account deletion: the shared account lock and cascade handle it.
   Prevent administrative/global source deletion for the protected window too.
   A cursor is not a snapshot and row locks only protect the current batch.
3. **Dry-run approval:** separately authorize read-only dry-run against the
   approved target. It reports source rows, not deduplicated counts or promised
   awards. It performs no init/schema writes, credit inserts or cursor capture.
4. **Capture/apply approval:** separately authorize prepare and batch execution.
   With retention still protected, prepare one account. Server time is the cutoff;
   the maximum retained account UAS article ID is its protected upper horizon.
   Both freeze on the first prepare. No client-uploaded dates/cursors/claims can
   set them. Cutoff is a processing boundary, not an earned date or a filter on
   uploaded updated_at/done_at. Future imports of old IDs synchronously credit
   on their own transaction even behind a completed cursor.
5. **One worker:** enumerate accounts only through the separately approved
   operational inventory. Run serial account batches, 200 source rows per
   transaction. Commit successful batches; on timeout/error roll back and retry
   that account. No SKIP LOCKED, no silently failed rows, no auto-advance. An
   exact 200-row last batch requires one EOF batch. Status is read-only. Do not
   parallelize this initial rollout; account locking still fences duplicate workers.
6. **Finish:** verify every intended account is complete, retained evidence has
   been protected throughout, and approved reconciliation checks agree. Separately
   authorize releasing protection/resuming retention. Record any protection lapse;
   do not claim complete lifetime totals even when the scan completes. Deleted
   evidence cannot be reconstructed. No email, push or recap campaign is generated.

## Explicit CLI (examples are syntax, NOT execution authorization)

Use the deployed application's PostgreSQL configuration and already-applied
additive schema, never a second database implementation. A missing table is a
rollout error; the operator never initializes schema. Commands require an exact
server policy and account. Default behavior is no action: an action is mandatory.

```text
python -m news_dashboard.reading_progress.history status --user-id ACCOUNT --policy historical-v1
python -m news_dashboard.reading_progress.history dry-run --user-id ACCOUNT --policy historical-v1
python -m news_dashboard.reading_progress.history prepare --user-id ACCOUNT --policy historical-v1 --protection-ref APPROVED_EXTERNAL_RECORD
python -m news_dashboard.reading_progress.history batch --user-id ACCOUNT --policy historical-v1
```

Each `batch` opens and commits one transaction only. Keep running until `complete`.
A failed process before commit rolls everything back; a lost response after commit
resumes from the durable cursor. Session-local 5s lock/30s statement timeouts bound
waiting. The connection-taking functions also support caller savepoints and never
commit/init/open another connection. Logs/output contain bounded counters, policy,
IDs and processing timestamps, never article text/URLs or uploaded timestamps.
No public backfill endpoint, startup scan, GET writer or scheduled backfill exists.

## Policy and user-facing result

Eligibility is account-attributed retained `user_article_state.done_at IS NOT NULL`
regardless current state, or current `state='done'` without a date. Future uploaded
dates do not become exact historical dates. Global article state, events, badges,
opens, active-time histories and daily visits are not sources. Historical scan
covers UAS articles; article-kind Reading List completions use the already-active
shared live/import hook, not an inference from nonarticle list entries.

Immutable v1 URL identity, first attribution including zero topics, first provenance
and existing award engine are reused. Duplicate live/import winners remain winners.
Every old award/key/date/metadata survives, including unknown and retired keys.
Historical awards are silent, unknown-earned-date, with separate process recording
time. No historical live groups, visits, active time or recent live recap outcomes.

On completion, nonempty credited history OR preserved awards creates one stable
`historical:v1` group in the existing group engine. The existing exact-target atomic
welcome/history claim consumes it once across devices; welcome disabled uses the
existing nonmodal inline path. Lost committed response can lose the introduction,
not the progress. Dismissal/CTA ACK is idempotent; no replay on reload. The permanent
Progress section retains the completed summary, unknown-date labels and explicit
incomplete-lifetime disclosure after dismissal. Progress DTO/export are read-only;
archive uploaded state/counters/claims remain informational and are never restored.
Account deletion cascades the state and presentation with all personal progress.

## Rollback (separate authorization)

Stop the operator and disable introduction presentation/new writers as coordinated
with core rollout. Roll back uncommitted batches; keep committed credits, awards,
first provenance, groups and cursor. Never delete earned rows, reset the cursor,
clear claims, alter original dates or rerun a new policy to repair presentation.
Keep evidence protection until the separately authorized rollback/recovery owner
has assessed the remaining scan. Resume the same policy/state after ordinary
technical repair; no operational repair was performed by implementation tests.
