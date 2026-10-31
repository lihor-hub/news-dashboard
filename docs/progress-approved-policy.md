# Progress program #1623 — approved policy and delivery boundaries

## Approval source and precedence

The chief-of-staff thread `thr_ssv89eewik` relayed that the user replied **approve** directly to the A–G table linked to `1623-delivery-decision-packet.md`. All seven groups below are approved as documented. Existing authority covers implementation, tests, independent review, push and PR creation. No redundant generic implementation approval is needed.

The immutable discovery packet is preserved in delivery-lead thread storage `/Users/ioachimlihor/.bb/thread-storage/thr_ktxa9nqzqk/1623-delivery-decision-packet.md`; detailed source evidence and acceptance matrix are in `1623-reviewed-detailed-proposal.md` beside it. Discovery workflow `wfr_d8928d1f-f1fb-4500-9ee0-093d04994715` succeeded with 11/11 calls. Its old NOT APPROVED labels describe the earlier state; this approval record supersedes those labels, not the documented values/tradeoffs. This document records approved product policy, not completed implementation or passed tests.

Technical choices should implement these policies minimally and receive independent review. Return only NEW material product tradeoffs for approval, not ordinary technical problems. Fixed milestones and five-minute idle window remain exactly as specified by #1623.

## A. Daily calendar and welcome

- Independent saved `progress_timezone`, initialized once from valid saved briefing zone else UTC; never silently reschedule email. Freeze past dates.
- Visible authenticated entry/navigation/resume and continuously visible local midnight count. No email-open or offline retro-credit.
- Require strictly newer local date AND the previous credit's frozen next-local-midnight instant; timezone edits cannot shorten this guard. Travel may suppress credit or restart a streak; preserve best and rewards.
- Exact visit/group claim targets, atomic optional welcome/history bundle, consume-on-claim. Lost response/crash can lose feedback rather than duplicate it. Ordinary welcome highlight is a repeatable collection summary, not another newly-earned toast.
- Welcome and animation preferences independently default on; neither disables tracking. Shared `/reading-dna#progress` destination, protected standalone readers included, accessible popup/sheet/indicator and reduced motion.

## B. Qualifying reads and identity

- Automatic completion: >=90% article-body progress AND `clamp(30,120,ceil(words/240*60*0.5))` attentive seconds AND >=2 seconds end-region visibility. The consolidated 30–120s proposal supersedes discovery's alternative 20s–5min/200wpm proposal. Generic app time never qualifies an article.
- Exclude loading/summary-only/external/hidden/unfocused evidence. Long-body skimming at the120s cap is an accepted limitation; manual Done remains available.
- Manual Done is a declaration. Unread restores inbox state but never revokes immutable credit or awards. Explicit manual/legacy/GReader/approved-agent sources qualify; audio auto-finish is workflow-only. Signed-email GET does not earn credit: human POST confirmation required.
- Article-kind Reading List items qualify/dedupe with feed items; nonarticle kinds do not.
- Freeze v1 digest of own normalized canonical URL (fallback authorized URL), surviving deletion/recreation. Do not use mutable fuzzy roots. Different URLs for one story can count separately; accepted limitation. Future identity-version migration requires dedup treatment.

## C. Topics

- Eleven tracks: Python; Large language models; AI agents; AI research; Cloud infrastructure; Security; Data engineering; Web development; JavaScript & TypeScript; Software engineering; Ruby.
- Deterministic subject match in title OR two distinct subject terms in summary; no source-category/onboarding/user tags/AI eligibility. Cap2 tracks/read; rank title, summary, stable ID. Freeze first attribution including zero topics; no silent retroactive reclassification.
- Before enabling: labeled100-article corpus, >=95% selected-pair precision, >=5 positives+1 near miss per track, >=80% per-track recall. These are calibration requirements, not measured results/statistical claims. Breadth10 remains unchanged despite demanding11-track coverage.

## D. Measurement/privacy

- Connected-only approximate foreground visible+focused use; pause after five minutes without interaction. No offline outbox/catch-up. Validate web/PWA/Electron/Android TWA/mobile Safari/PWA lifecycles before parity claims; no invented extension support.
-15s heartbeat,30s server window,120s logical overlap/retry accounting, <=180s transient cleanup,400d local-day aggregates, lifetime totals+awards. Server interval union deduplicates overlapping tabs/devices. Modified clients may simulate attention up to bounded elapsed time; no intrusive surveillance.
- Article evidence is separately authorized/validated, not generic app-active time. Honor existing analytics opt-out/global disable for automatic evidence/time; manual progress remains. Functional visit dates/credits/awards persist until account deletion independently of optional analytics.
- Historical global availability cannot be proven from current environment flags; conservatively label partial/unknown coverage, never invent complete zero. No need to implement a new global availability platform.

## E. Legacy/history/import

- Preserve every old award and original dates, including unknown/retired keys. Sole100-read key `hundred_articles_read`; distinct new daily-streak keys. Stop future old-open-streak/global-inbox earning; continue valid quiz awards transactionally. Coordinate producer/read-only GET cutover.
- Historical evidence: retained done_at regardless current state, or current done with unknown date. Never infer app visits/time or exact earned dates. Processing date is separate.
- Post-cutover archive article completions qualify as self-reported import credit, unknown earned date, silent presentation. Uploaded progress totals/rewards/time/claims are informational, never authoritative eligibility. First accepted live/import credit freezes provenance; later distinct live threshold crossing can use imported/historical prerequisites.
- Implement resumable/idempotent backfill tooling (proposed200 rows/transaction, one worker), all cooperating live/import writers, protected evidence horizon protocol and one introduction. Implementation and test fixtures are authorized; actual user-data inventory, retention pause/drain, backfill dry-run/apply are NOT authorized.

## F. Recap periods

- Seven completed saved-progress-local dates, frozen half-open boundaries; intended period fixed before generation delay. Briefing schedule remains in briefing timezone. Past snapshots do not rebucket; coverage explicit.
- Frozen v2 first-wins, legacy snapshots untouched, late activity does not rewrite snapshots. Actual persisted winner controls narrative and existing push; losing generation cannot announce its local payload. No new campaign/push or catch-up system.

## G. Existing email and portability

- BOTH canonical briefing mail and legacy digest plus preview, HTML+text. No new campaign, news-empty send or email-open measurement. <=2 live achievement/promotion highlights, else useful valid daily streak>=3, omit useless/uncertain section. Canonical saved bounds, legacy trailing24h. Accept repeated highlights across channels, no new mail cursor.
- Legacy personal section requires exactly one matching non-guest account mailbox; omit progress on ambiguity. Preserve consent/scheduling/delivery and authenticated destination through auth. No topic content in subject/preheader/logs/AI. SMTP forwarding/delivered-mail erasure limits accepted and disclosed.
- Additive archive-v2 progress/recap/preferences sections. Validate preferences; uploaded rewards/time/claims/snapshots informational with explicit not-restored notice, not full progress roundtrip. Existing article restore can independently establish import-provenance credit under E. Account deletion cascades personal progress; sent mail cannot be recalled.
- Parent's unrelated dirty email changes must not be included; reconcile exact overlapping hunks before #1631.

## Delivery controls

One shared-file editor at a time. Ratified delivery-lead assignment: shared contract/DDL/award DTO/preferences/archive/privacy and final ReadingDna composition are centrally integrated under #1628 responsibility; initial lifecycle/progress host belongs to #1624, completion/identity to #1625. Domain slices supply fragments through sequenced commits. Review technical contracts before producer implementation. No second reward engine, generic event bus, new dependency/framework or unsolicited feature.

After relevant contracts: #1624/#1625/#1627; #1626 after #1625; complete #1628 after core four; #1629 tooling after those; #1630/#1631 independently after core measurement/provenance/destination. Every slice includes backend, usable user-facing outcome, tests, separate review, fixes, verification and PR acceptance/CI evidence. Do not call mock-only/browser-only/backend-only partial work complete.

Dedicated PostgreSQL only: `nd-test-pg`, host localhost:55432/news_dashboard_test as news_dashboard. Bootstrap isolated worktree before tests/commits; verify BOTH DATABASE_URL and TEST_DATABASE_URL safely without secrets. Serialize all shared truncating suites; full suite PGOPTIONS='-c max_parallel_workers_per_gather=0'. No native5432, SQLite runtime, hook bypass or destructive reset.

Superseding delivery authorization permits completed PROGRAM PRs to merge after independent review findings are resolved, acceptance tests pass, and required CI checks, protections and repository rules permit. The orchestrator owns merge; implementation/review workers remain publication-only. Normal Fixes closure is permitted only for a fully satisfied slice. Parent PRD #1623 remains open until all its criteria are verified. No deployment, production sends, operational user-data historical inventory, retention pause/drain, backfill dry-run/apply or destructive operations are authorized. Rollback must not erase earned rewards.
