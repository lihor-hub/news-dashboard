# Progress program technical contracts (#1623 / #1628)

Status: sequenced technical handoff. The daily foundation is implemented in #1624; the completion seams in section 10 are implemented in the uncommitted #1625 slice pending independent review. Earlier design-only statements describe their original tranche, not a claim that all future domains are implemented. Product authority is [approved policy](progress-approved-policy.md) and [approval comment](https://github.com/lihor-hub/news-dashboard/issues/1623#issuecomment-6526348156). Those override obsolete discovery approval labels, not their numeric policy. This document fixes implementation names and seams, not new product policy.

## 1. Ownership and first delivery boundary

| Issue | Owns | Shared-file handoff |
| --- | --- | --- |
| #1624 | Daily dates/state/awards, initial protected lifecycle controller, persistent indicator, welcome sheet/dialog, initial Reading DNA Progress section and daily controls | First implementation writer of `reading_progress`, protected-route host and initial home. Covers shell **and** `/a/:id` and `/shared/:shareId/article`. Hands these existing components to #1628 for extension, not replacement. |
| #1625 | Completion transaction seam, immutable identity/read credit, all completion callers, article reader evidence and article-kind Reading List | Supplies connection-taking helper and caller-origin matrix; no independent reward store or lifecycle host. |
| #1626 | Versioned deterministic taxonomy, frozen attribution including zero, topic/breadth predicates and UI fragment | Depends on #1625; calibration required before topic earning is enabled. |
| #1627 | Activity windows/union/lifetime/day aggregates, consent revision/invalidation, conservative coverage and activity UI fragment | Reuses #1624 protected lifecycle boundary but a separate visible+focused recorder. Supplies settings/cleanup fragments to central editor. |
| #1628 | Shared schema, award catalog/DTO/claims, progress preferences, archive/privacy integration, final collection/emblems/coordinator and Reading DNA composition | Central integration responsibility; domain writers provide sequenced fragments. Initial schema/claim primitives travel with #1624, not a second full reward implementation. |
| #1629 | Historical/import coordination, resumable tooling, protected-horizon runbook and one introduction | No operational inventory, retention pause/drain or dry-run/apply authorized by implementation. |
| #1630 / #1631 | Frozen recap / existing canonical and legacy email paths plus preview | Read-only consumers of shared contracts; mail overlap reconciled by delivery lead before edits. |

One writer at a time, explicit paths staged. Scope of the first DDL tranche below is users' progress preferences, daily state/visits, and shared award/group fields required by the daily producer. **No read/topic/activity/backfill runtime tables yet.** No runtime edits are part of this contract-writing stage.

## 2. Award identity and persistence authority

Reuse `user_achievements`, unique `(user_id, achievement_key)`. Never derive credits from an award. Award definitions/predicates belong to domains; insertion, descriptor serialization and presentation grouping belong to the shared `reading_progress` service. Keys never change when copy/artwork changes.

| Domain owner | Canonical keys (decimal suffixes are literal thresholds) |
| --- | --- |
| #1624 | `daily_streak_3`, `daily_streak_7`, `daily_streak_14`, `daily_streak_30`, `daily_streak_100` |
| #1625 | `articles_read_1`, `articles_read_10`, `articles_read_50`, **`hundred_articles_read`**, `articles_read_500` |
| #1626 | `topic_{topic_id}_{1|10|30|100|250}` (one emblem per level, not an extra badge); `breadth_3`, `breadth_5`, `breadth_10` require >=3 credits in each of that many tracks |
| #1627 | `active_time_900`, `active_time_3600`, `active_time_18000`, `active_time_72000` (seconds, totals measured in integer milliseconds) |
| Legacy quiz | `first_quiz_passed`, score >0 on an authorized submitted quiz, transactionally at submission |
| Retired earning | `seven_day_streak` (legacy UTC reading/open streak), `inbox_zero` (legacy global inbox criterion). Keep stored rows and original dates; never earn these anew after cutover. |

Stable topic IDs: `python`, `large_language_models`, `ai_agents`, `ai_research`, `cloud_infrastructure`, `security`, `data_engineering`, `web_development`, `javascript_typescript`, `software_engineering`, `ruby`. Level names at 1/10/30/100/250: Explorer/Enthusiast/Regular/Trailblazer/Pathfinder. At 7 reads, Explorer toward Enthusiast, not already Enthusiast.

`origin = live | historical | import | legacy`. `unlocked_at` remains the original recording timestamp (DTO `recorded_at`); do not update it on conflict. New live `earned_at` is the server crossing instant. Historical/import/legacy exact earned time is NULL, not the processing date. Existing metadata and unknown/retired keys survive unchanged; old rows default legacy without fabricated dates. First award insert wins permanently. A later distinct live crossing can use historical/import prerequisites but cannot upgrade a previously stored award's provenance.

Shared operation, on the caller's connection with the account lock already held:

```python
award_rewards(conn, user_id, *, cause_key: str, origin: str,
              earned_at: datetime | None, candidates: list[RewardCandidate]) -> AwardResult
# Candidate = {key: str, criteria_version: int, progress: int, target: int}
# Result = {newly_unlocked: list[str], reward_group_id: str | None}
```

Validate candidates against the server catalog; domain producers, not clients, supply eligibility. Insert `ON CONFLICT (user_id, achievement_key) DO NOTHING RETURNING ...`; link only new awards. One logical cause, one live group even when it crosses reading/topic/breadth thresholds together. Source keys are server-generated (`daily:2026-10-30`, `read:<credit_id>`, `activity:<window_id>:<sequence>`, `quiz:<id>`). Unique account/source makes retries converge. Never commit an empty live group: create lazily after first successful award insert, then attach the returned new rows in that transaction. Historical/import awards are silent and ungrouped; #1629 creates a single `historical_intro` summary group only when reconciliation is complete. No per-import/read historical groups. Group/ACK are presentation state, never eligibility authority.

## 3. First #1624 PostgreSQL DDL contract

Use existing `db.py` statement lists/initializer; psycopg `%s`, no new migration framework. SQL below specifies the final constraints, not an instruction to execute migration now. Add idempotent ALTERs and named constraint existence checks in the existing schema runner where PostgreSQL has no `ADD CONSTRAINT IF NOT EXISTS`. No initialization-time scan/backfill. Users already have INTEGER IDs.

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS progress_timezone TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_welcome_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reward_animations_enabled BOOLEAN NOT NULL DEFAULT TRUE;
-- Named CHECK progress_timezone_length:
-- progress_timezone IS NULL OR char_length(progress_timezone) BETWEEN 1 AND 255
-- ZoneInfo validation is at the write boundary; DB length alone is not timezone validation.

CREATE TABLE IF NOT EXISTS user_daily_visit_state (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  last_credited_date DATE,
  current_streak_days INTEGER NOT NULL DEFAULT 0 CHECK (current_streak_days >= 0),
  best_streak_days INTEGER NOT NULL DEFAULT 0 CHECK (best_streak_days >= current_streak_days),
  next_credit_at TIMESTAMPTZ,
  CHECK ((last_credited_date IS NULL AND next_credit_at IS NULL AND current_streak_days = 0)
      OR (last_credited_date IS NOT NULL AND next_credit_at IS NOT NULL AND current_streak_days > 0))
);
CREATE TABLE IF NOT EXISTS user_daily_visits (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  local_date DATE NOT NULL,
  timezone TEXT NOT NULL CHECK (char_length(timezone) BETWEEN 1 AND 255),
  first_visited_at TIMESTAMPTZ NOT NULL,
  credited BOOLEAN NOT NULL DEFAULT FALSE,
  visit_kind TEXT CHECK (visit_kind IN ('first', 'continuing', 'restart')),
  welcome_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (welcome_status IN ('pending', 'claimed', 'suppressed')),
  welcome_consumed_at TIMESTAMPTZ,
  PRIMARY KEY (user_id, local_date),
  CHECK (credited = (visit_kind IS NOT NULL)),
  CHECK ((welcome_status = 'pending' AND welcome_consumed_at IS NULL)
      OR (welcome_status IN ('claimed', 'suppressed') AND welcome_consumed_at IS NOT NULL)),
  CHECK (welcome_status <> 'claimed' OR credited)
);
CREATE TABLE IF NOT EXISTS user_reward_groups (
  id UUID PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_key TEXT NOT NULL CHECK (char_length(source_key) BETWEEN 1 AND 200),
  kind TEXT NOT NULL CHECK (kind IN ('live', 'historical_intro')),
  recorded_at TIMESTAMPTZ NOT NULL,
  claimed_at TIMESTAMPTZ,
  acknowledged_at TIMESTAMPTZ,
  summary JSONB,
  UNIQUE (user_id, source_key),
  UNIQUE (user_id, id),
  CHECK (acknowledged_at IS NULL OR claimed_at IS NOT NULL),
  CHECK ((kind = 'live' AND summary IS NULL)
      OR (kind = 'historical_intro' AND summary IS NOT NULL AND jsonb_typeof(summary) = 'object'))
);
CREATE INDEX IF NOT EXISTS user_reward_groups_pending
  ON user_reward_groups(user_id, recorded_at, id) WHERE claimed_at IS NULL;

ALTER TABLE user_achievements ADD COLUMN IF NOT EXISTS earned_at TIMESTAMPTZ;
ALTER TABLE user_achievements ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE user_achievements ADD COLUMN IF NOT EXISTS reward_group_id UUID;
-- Named CHECK user_achievements_origin:
-- origin IN ('live', 'historical', 'import', 'legacy')
-- Named CHECK user_achievements_earned_time:
-- (origin = 'live' AND earned_at IS NOT NULL) OR (origin <> 'live' AND earned_at IS NULL)
-- Named CHECK user_achievements_live_group:
-- reward_group_id IS NULL OR origin = 'live'
-- Named FK user_achievements_group_owner:
-- FOREIGN KEY (user_id, reward_group_id) REFERENCES user_reward_groups(user_id, id)
-- DEFERRABLE INITIALLY DEFERRED
CREATE INDEX IF NOT EXISTS user_achievements_group
  ON user_achievements(user_id, reward_group_id) WHERE reward_group_id IS NOT NULL;
```

UUIDs are generated with Python `uuid.uuid4()`, not an extension. The composite FK prevents cross-account attachment. Groups are not individually deleted while referenced; account deletion cascades both tables in one transaction (deferred FK verified at commit). Claim lookup uses UUID PK plus authenticated owner; collection uses existing unique user/key index. Daily PK supports seven-day and period date ranges, no redundant date index. No JSON metadata index, identity table, general event log or mail cursor. The `historical_intro` kind reserves the shared claim shape, not speculative backfill storage.

Preferences initialize timezone **once on a mutation** from valid saved briefing zone else UTC; GET may report effective fallback with `timezone_initialized=false` without writing. Explicit PATCH timezone initializes it. Validate nonempty bounded ZoneInfo string, reject unknown keys/nulls/non-booleans with 422. PATCH only supplied fields. Never change briefing timezone/schedule. Popup and animation defaults are independently true; static feedback survives animations off. Daily rows and awards are functional, unaffected by analytics opt-out.

## 4. Daily calculation and DTOs

All routes below are under `/api/users/me`; current authenticated account only, existing same-origin/CSRF protections. No account/date/time input to `POST /daily-visit` (empty JSON object). Anonymous 401; guest durable-progress mutations 403 `progress_not_available`, reads return unavailable and UI hides durable recorders. Guest policy is a technical continuation of the discovery recommendation; do not let a guest shared identity accumulate cross-visitor personal data.

Sample UTC instants after acquiring the account lock, not transaction-start `NOW()` when lock wait can span midnight. On observed server-local date D, insert first observation only; existing row's timezone/first timestamp stay frozen. Credit iff no prior credit, or `D > last_credited_date AND now >= next_credit_at`. Extend only if D = last+1, otherwise restart at 1; best never decreases. Persist next midnight for the credited date in the zone used **at credit**, converted to UTC. A timezone edit never shortens that previous guard. Observed-but-uncredited D can qualify on a later request the same D; its original observation attribution stays unchanged. `visit_kind` freezes when credited. No timezone-save visit/award side effects.

Displayed current is the cached last-earned streak if last credit is today or yesterday in the current saved zone, otherwise 0 (including a last credit ahead of today's date after westward travel); never erase cached best/awards. Seven days are today and six preceding calendar dates; date-only labels must not parse through browser-offset JS instants. `visited` is observation, not necessarily credited; recap must not equate these. Suppressed dates are explained as timezone-guard observations, not missing API data.

`POST /daily-visit` and read-only `GET /daily-streak` share this snapshot:

```json
{
  "timezone": "Europe/Bucharest",
  "timezone_initialized": true,
  "local_date": "2026-10-30",
  "server_now": "2026-10-30T10:00:00Z",
  "next_local_boundary_at": "2026-10-30T22:00:00Z",
  "next_credit_at": "2026-10-30T22:00:00Z",
  "current_streak_days": 3,
  "best_streak_days": 5,
  "visit_kind": "continuing",
  "seven_days": [{"date": "2026-10-30", "visited": true, "credited": true}],
  "welcome_target": {"expected_visit_date": "2026-10-30"},
  "newly_unlocked": ["daily_streak_3"],
  "reward_group_id": "9f706788-a812-46ed-bd4d-e9745a9d4b6c"
}
```

Example abbreviates `seven_days`; runtime always returns seven ascending dates. Mutation-only `newly_unlocked`/`reward_group_id` are empty/null on GET and non-crossing POST. Missing visits yield `visit_kind=null`, `welcome_target=null`; GET never records a visit, earns or claims. Counters may legitimately be zero before first visit, but network error is not zero. Eligible welcome requires today's credited row, preference on and pending status.

`GET/PATCH /progress-preferences` returns exactly `{progress_timezone: string, timezone_initialized: boolean, daily_welcome_enabled: boolean, reward_animations_enabled: boolean}`. PATCH body permits the three preference fields, not `timezone_initialized`. Disabling welcome suppresses today's pending observed row under the same lock, with consumed timestamp; future observations while disabled are suppressed, even uncredited ones. Reenable does not revive a suppressed row. No stored claim can be remotely revoked after commit; local disable closes local popup.

Shared reward descriptor (preserve legacy `unlocked_at` alias for existing callers):

```json
{
  "key": "daily_streak_3", "title": "3-day daily streak",
  "description": "Visit on 3 consecutive saved-local dates.",
  "unlocked": true, "unlocked_at": "2026-10-30T10:00:00Z",
  "recorded_at": "2026-10-30T10:00:00Z", "earned_at": "2026-10-30T10:00:00Z",
  "origin": "live", "date_precision": "exact", "criteria_version": 1,
  "progress": 3, "target": 3,
  "href": "/reading-dna?reward=daily_streak_3#progress"
}
```

Non-live `earned_at=null`, `date_precision=unknown`. Locked definitions have null timestamps/origin, not fake legacy provenance. Unknown stored keys get readable escaped fallback key/title, original metadata/dates and `retired=true`; never drop them. Unbounded domain counts remain available separately from capped legacy achievement progress.

## 5. Exact-target and atomic presentation claims

Read-only discovery (`GET /progress` once composed, daily snapshot initially) exposes current exact welcome target and at most 20 oldest pending live group IDs, ordered `(recorded_at,id)`; refetch after drain. Also exposes at most one completed historical introduction target. Reads never reserve or claim. A UUID is opaque, not permission.

### Live rewards

`POST /reward-events/{group_id}/claim`, body `{}`. Account lock, owner lookup, kind check, then `UPDATE ... WHERE claimed_at IS NULL RETURNING ...`. Foreign/missing targets uniformly 404; `historical_intro` kind returns 409 `wrong_claim_kind` with no writes. No client-selected award list.

Winning envelope:

```json
{
  "show": true, "reason": "claimed",
  "target": {"group_id": "9f706788-a812-46ed-bd4d-e9745a9d4b6c"},
  "authorization": {"welcome": false, "history": false, "rewards": true},
  "welcome": null, "history": null,
  "rewards": [{"key": "daily_streak_3"}]
}
```

Runtime `rewards` contains full descriptors. Retry of that exact target returns `show=false`, reason `already_consumed`, all authorization false, all content null/empty. It MUST NOT claim the next pending group. ACK (`POST /reward-events/{group_id}/ack`, body `{}`) sets acknowledgement only for an already claimed owned group, repeat idempotent; pending group gives 409 `not_claimed`. ACK never reauthorizes. No ACK required for daily welcome.

### Welcome with optional history (one transaction, no split requests)

Canonical `POST /presentation/claim`:

```json
{
  "expected_visit_date": "2026-10-30",
  "historical_group_id": "dbe6e296-9520-4410-809f-45de3fcdf14c"
}
```

`historical_group_id` optional/null. `expected_visit_date` is required as a key: ISO date for welcome mode, null **only** for explicit history-inline mode while welcome is disabled. No client-selected current day. `POST /daily-welcome/claim` is a compatibility convenience accepting `{expected_visit_date: "2026-10-30"}` and invokes the exact same operation without history, never an independent algorithm.

Under one account lock, validate owned history target/kind before writes (foreign/missing uniform 404, wrong kind 409). Sample saved-zone current date after lock. For nonnull expected date that differs from current date, return **200** `show=false`, `reason=stale_visit`, no authorization, consume **neither** target, even if history was eligible. Missing/uncredited visit returns `not_eligible`, no consumption. Refetch and make a new deliberate claim; never automatically substitute today's date on a retry.

With welcome enabled, win today's pending credited welcome or consume nothing from this bundle. If welcome already consumed, return `already_consumed` and leave unclaimed history untouched. If welcome wins, consume it and selected eligible history atomically. If history already consumed elsewhere, welcome still wins alone. Winning example:

```json
{
  "show": true, "reason": "claimed",
  "target": {"expected_visit_date": "2026-10-30", "historical_group_id": "dbe6e296-9520-4410-809f-45de3fcdf14c"},
  "authorization": {"welcome": true, "history": true, "rewards": false},
  "welcome": {"local_date": "2026-10-30", "current_streak_days": 3, "highlight_kind": "collection_summary"},
  "history": {"group_id": "dbe6e296-9520-4410-809f-45de3fcdf14c", "credited_reads": 42, "exact_earned_dates_known": false},
  "rewards": []
}
```

`welcome` carries the full daily snapshot at runtime. Summary schema is server-generated bounded counters only, no URLs/body. Ordinary welcome highlight is at most one repeatable recent collection summary, **not** newly-earned toast authorization. Welcome does not consume a live group's toast; intentional overlap is allowed.

With welcome disabled, a nonnull date request returns `disabled`, consumes no history; it never silently converts to inline mode. Explicit `{expected_visit_date:null, historical_group_id:<exact-id>}` can claim history for nonmodal inline display without consuming welcome. If welcome has since been enabled, null-date mode returns `not_eligible`, no writes; refetch a dated bundle. Null date without a history target is 422. Every losing envelope has false flags and no content; echoed targets are not authorization. Repeated history-inline target returns `already_consumed`, never another group.

No lease, reclaim, reservation or generalized request ledger. Lost committed response/crash may lose feedback; progress remains in collection. Never claim before a host/placement is available. UI fences response by account generation and locally consumes each winning target envelope once even under StrictMode/remount. Modal priority: onboarding -> What's New -> bundled welcome/history -> nonblocking live reward. #1624 initially has no history target; #1628 extends the same host. Historical intros are never generic live toasts.

## 6. Transaction and lock contract

Use PostgreSQL transaction advisory lock with **two int4 keys**:

```sql
SELECT pg_advisory_xact_lock(1623, %s); -- second key = authenticated INTEGER user_id
```

Namespace 1623 is program-owned and distinct from the house single-bigint schema advisory lock. Do not hash Python strings or use process locks. Lock before reading mutable eligibility or acquiring article/Reading List/domain row locks. All cooperating visit, preference, credit, import, consent, claim, quiz, historical-batch and account-deletion writers use the same namespace. Pure GETs do not lock or write. Multi-account operations acquire ascending account IDs before any dependent rows; prefer bounded one-account transactions.

Order within a transaction:
1. Account advisory lock; confirm account exists/non-guest (deletion uses existing guards).
2. User row when updating preferences/deleting; article rows in ascending ID with existing `FOR NO KEY UPDATE`, then Reading List rows by ID if needed. Do not weaken source authorization.
3. UAS / daily-state / reader-evidence / activity-window / historical cursor rows as applicable (stable ascending keys for multiple rows).
4. Immutable read/topic rows; then award inserts and group linkage. Same connection and transaction, including per-item import savepoints.

No helper may open a hidden second connection, commit the caller, invoke schema initialization under these locks, or do network/AI work while locked. Outer public wrapper may initialize schema before starting its transaction. Sample authoritative wall clock after acquisition. Rollback covers workflow state + credit + attribution + awards + cursor together. Bulk callers acquire account first, then sort article IDs. Retention/global article deletion must not acquire account advisory locks while holding article locks; no new retention behavior in #1624. Account deletion locks before deleting the user; FK cascade removes personal rows. Two-connection import/delete/consent/retention tests must validate actual ordering later; this design is not a deadlock-free runtime claim.

Source feasibility: `ingest.service.transition_article_state` currently owns its connection and returns early on same-state. #1625 splits out a connection-taking internal transition/credit seam, used by the existing public wrapper and import. Same-state explicit Done still attempts credit. `article_visibility.get_visible_article_row` already locks `FOR NO KEY UPDATE`; retain it. `restore_user_archive` already owns the outer connection; take account lock before `_restore_articles`, use its savepoints, credit resulting completion state in the same item savepoint. No route-only completion implementation.

## 7. Future-domain typed seams (no DDL in this tranche)

### Completion, identity and provenance — #1625/#1626/#1629

```python
ReadCredit = {
  'id': int, 'identity_version': 1, 'identity_digest': str, # lowercase SHA256 hex
  'origin': 'live | historical | import',
  'method': 'manual | automatic | legacy | greader | agent | import | historical',
  'recorded_at': datetime, 'effective_at': datetime | None,
  'article_id': int | None, 'topics_finalized_version': int | None,
}
CreditResult = {'credit_inserted': bool, 'progress_changed': bool,
                'newly_unlocked': list[str], 'reward_group_id': str | None}
```

For v1, digest = SHA256 of UTF-8 bytes of `ingest.service.canonicalize_url(own canonical_url or authorized url)`, no extra prefix in digest bytes; identity version stored separately. Freeze the v1 implementation/fixtures (tracking removal, sorted query, lowercase scheme/netloc, fragment removal, trailing-slash behavior); future normalizer edits must not silently change progress v1. Read own article URL, never fuzzy duplicate root. Reading List article-kind passes raw authorized URL through that same v1 algorithm, **not** its different `normalize_url`. Unique account/version/digest; article deletion SET NULL, user deletion CASCADE; digest retained only with account, no URL/title/body copy. Different URLs for one story can count separately. Version changes require an explicit dedup migration.

Manual and approved legacy/GReader/agent declarations qualify regardless analytics opt-out. Audio auto-finish changes workflow only; signed-email GET does not earn, human POST confirmation does. Automatic evidence requires authorized real body/version, >=90% body progress, `clamp(30,120,ceil(words/240*60*0.5))` attentive seconds and >=2s end visibility. Exclude summary/loading/external/hidden/unfocused; unsupported tokenization uses 120s. Separate reader protocol: 10s evidence cadence, <=15s accepted increment, 20s lease, 24h pending TTL. App activity accepted milliseconds are never accepted as article evidence. Consent/global-disable fences apply to automatic evidence as to activity.

First inserted read freezes provenance/effective date, including import-first/live-first races. Historical/import effective time unknown even if uploaded `done_at` exists. Historical eligibility is retained done_at regardless current state, or current done-undated; unread never revokes immutable credit. Future archive restores of that evidence call shared import-origin credit even for old IDs, behind the scan cursor, or already-done rows. Uploaded progress sections never establish eligibility. Topic attribution, including zero, freezes on first accepted credit using rule/taxonomy version. #1625 can be implemented/tested before #1626, but integration release must not enable new production credit writes until the calibrated attribution helper can run in that first-credit transaction. Do not store a fake finalized zero or defer classification against later mutable text. No silent later reclassification of finalized credits.

### Activity, consent and coverage — #1627

```typescript
type Coverage = {
  status: 'partial' | 'unavailable' | 'unknown';
  reasons: Array<'pre_measurement' | 'consent_gap' | 'global_gap_or_unknown' |
    'timezone_change' | 'retention_unknown' | 'transport_incomplete'>;
};
type Activity = { total_ms: number; measured_since: string | null;
  approximate: true; coverage: Coverage };
```

Measured zero is not complete zero. Current env flag cannot prove past global availability: v1 does **not** emit `complete`. Missing day is unavailable/unknown, never implicitly zero. Show “measured active time; coverage incomplete.” Functional visit coverage is separate. <=400d frozen local-day aggregates; lifetime totals/awards survive aggregate pruning. No retroactive timezone rebucketing.

Connected visible+focused use, idle pauses at five minutes, 15s heartbeat, 30s server-issued window, 120s logical overlap/retry accounting, transient cleanup <=180s. Window issuance binds user/consent revision and server time; server-bounded accepted interval union across tabs/devices increments lifetime total only by previously uncovered duration. Identical replay adds zero; changed replay 409; expired/pruned windows never remint. Acknowledge accepted interval/sequence only; client cannot submit arbitrary historical dates, outbox or unbounded elapsed time. Bound pending windows/payloads/rates in #1627 with tests, not speculative schema here.

Consent change takes the same account lock, increments revision, invalidates windows/reader evidence and monotonically marks gap coverage. Reenable cannot erase gaps. Server checks both saved consent and global switch at issuance/acceptance. Global switch has no invented durable chronology; no new availability platform. Functional dates/manual credits/awards remain. Actual web/PWA/Electron/TWA/mobile Safari/PWA lifecycle verification remains required before parity claims.

### Legacy cutover and history — #1625/#1628/#1629

Existing `list_achievements` GET currently mints all four legacy catalog rewards from mutable state. Before retiring it, wire transaction producers for qualifying read and quiz plus new daily awards; then remove **all** awarding from GET in the same integration change. Preserve `/streak` UTC reading semantics/response and stored awards. Stop future old streak/global-inbox earning immediately at that cutover; quiz submission uses `award_rewards` on its own transaction, not a later GET. No fallback GET writer. Existing-account collection must label legacy earned rows and history reconciliation pending, not present an unexplained new measured total as a complete lifetime zero.

Live/import producers must all participate **before** protected historical horizon capture; cursor/upper ID is not a snapshot of future restores. Tooling uses resumable 200-row transactions/one worker, committed cursor and one completed introduction; actual horizon capture requires separately authorized retention pause/drain. No visits or activity backfill, no exact historical earned-date reconstruction. Deploy/cutover/runbook is future work, not executed by this document. Rollback disables writers/presentation without deleting earned rows.

### Recap, email and portability — #1628/#1630/#1631

```typescript
type Period = { timezone: string; start_local_date: string; end_local_date: string;
  start_at: string; end_at: string }; // half-open in both representations
// Seven completed progress-local dates fixed from intended scheduled instant, before delay.
type SaveRecap = { snapshot: StoredRecap; inserted: boolean };
```

Consistent DB read snapshot freezes measurements/bounds; reuse recap JSONB/unique user/week key. V2 first-wins returns the actual persisted winner, legacy collision untouched. Narrative runs outside DB transaction from stored winner's legacy-field allowlist; conditional NULL fill only, never measurement rewrite. Only insertion winner may send existing push from stored winner. Crash may lose push; no outbox/new campaign/catch-up. Do not send topic/private progress through narrative, tracing, subject/preheader/logs.

One read-only selection per mail attempt feeds HTML+text: canonical saved period, legacy trailing24h; <=2 live highlights else useful valid daily streak >=3 else omit. Preserve canonical recipient/consent rechecks; legacy personal progress requires exactly one matching non-guest account mailbox, omit on ambiguity. Both existing mail paths and preview, no news-empty campaign or email-open measurement. Sender CTA and authenticated continuation preserve path/search/hash.

Archive remains v2 with optional `progress`, `weekly_recaps`, `preferences.progress`; only validated preferences restored from these new sections. Awards/time/claims/snapshots informational with explicit not-restored notice. Existing article restoration independently earns import-origin credit as above. No tokens/windows/body evidence export. Every new personal row cascades account deletion; preserve confirmation/last-admin guard. Privacy copy must disclose lifetime functional dates/digests/awards, bounded automatic measurement, optional consent, approximate/partial coverage, non-roundtrip restore, SMTP/forwarding and inability to erase delivered mail.

## 8. UI host/destination and handoff checks

#1624 owns one authenticated protected lifecycle boundary, gated on authenticated status **and actual user**, not `RequireAuth` children rendering alone. Visible entry/navigation/resume and continuously visible local midnight call daily visit using server boundary; hidden startup does not. On failure one retry after 5s while visible, then later lifecycle events; no offline retro-credit. Abort/ignore old-user responses on logout/account switch and reset caches by account. #1627 hooks this boundary, but has stricter focus/idle and consent checks; visit is not a heartbeat.

Use `/reading-dna#progress`; reward detail `/reading-dna?reward=<encoded-stable-key>#progress`; recap `/reading-dna?recap=<positive-id>#progress`. Validate identifiers; preserve through password/OTP/SSO. Explicit navigation focuses progress heading; background updates never steal reader focus. Keep existing DNA/Learning controls. Initial host includes shell and standalone reader indicator, mobile sheet <640px/dialog otherwise, Continue reading initial focus, Escape/outside close, focus restore or indicator fallback. System reduced motion overrides animation preference including overlays. At most one modal, one Sonner live slot with <=3 names +N and 8s hover/focus pause, polite once announcement, no autofocus. #1628 extends same host and collection, not a second provider or disconnected page.

Before accepting #1624: real PostgreSQL boundary/concurrency/rollback tests (same date, 23h/25h DST, travel guard, midnight waiting lock, lost response, suppression/re-enable); authenticated real-backed return/direct-reader browser flow; preference/API/component tests and actual keyboard/focus checks. No mock-only, unsupported native or unperformed a11y pass claims. Later contract tests must cover two pending groups + lost first response, two-device merged history, stale date consumes neither, history-disabled inline races, cross-owner claims/FK, same-state Done/import behind cursor, consent revision and persisted recap winner side effects.

## 9. Source feasibility and evidence boundary

Static source rechecked for this handoff: `db.py` existing users/achievements and house advisory initializer; `reading_progress/service.py` catalog/GET writer/legacy UTC streak; `ingest/service.py` canonicalizer and connection-owning early-return transition; `article_visibility.py` authorization/lock; `user_settings/service.py` ZoneInfo validation and unfenced analytics preference; `import_export.py` outer restore transaction; `quizzes/service.py` submit transaction; `RequireAuth.tsx` and all protected `AppRouter.tsx` branches. Full discovery artifacts and independent review were reused, not repeated broad research. The required changes fit these existing seams; concurrency/schema/lifecycle correctness still needs implementation tests.

The original contract-writing tranche defined DDL only and executed no runtime verification. Subsequent slice acceptance evidence belongs to each worker's handoff, not this design document. No operational historical inventory/backfill, production send or deployment is authorized by these contracts.

## 10. Implemented #1625 completion handoff (uncommitted, review required)

### Storage and transaction entry

`reading_progress/credits.py` freezes the v1 normalizer and SHA256 fixtures independently of
future ingest-normalizer edits. `user_read_credits` has a bigserial credit ID, account/version/
digest uniqueness, own article SET NULL, account CASCADE, first-wins origin/method/recorded_at/
effective_at and nullable `topics_finalized_version`. A stored legacy badge never synthesizes
credits. Lifetime totals count immutable rows; unread, archive and retention never decrement.
The collection explicitly says historical reconciliation pending rather than presenting tracked
zero as a complete lifetime total. No initialization/GET historical scan was added.

`transition_article_state_on_connection(conn, article_id, state, *, user_id, method)` is the
caller-connection entry; the public wrapper initializes before opening its transaction. The
entry acquires `(1623,user_id)` before article `FOR NO KEY UPDATE`/UAS and does not commit.
Same-state Done attempts credit; done→today restores workflow without revocation. Archive
restore prelocks all authorized existing article rows in ascending ID before per-item savepoints,
then processes URLs in stable sorted order for concurrent new inserts; URL conflicts use
`DO NOTHING` plus lookup instead of taking an out-of-order no-op update lock. Per-item rollback
and private-source checks remain unchanged. Guest workflow remains uncredited. Existing article/Reading List/quiz workflow and analytics opt-out
use `lock_account(..., mutation=False)` and skip durable rewards for guests; dedicated progress
mutations retain the default personal-account guard. This preserves existing guest workflow
and consent rather than turning an award producer into an unrelated 403. `credit_read`/`credit_article` require the caller account lock and
never initialize/connect/commit; insert, source freeze, total predicates, existing award insert
and lazy live group are in the same transaction. Quiz submission uses the same award helper.
`award_rewards` validates the daily/read/first-quiz catalog; GET achievement endpoints are now
read-only. Retired open-streak/global-inbox earning stops without deleting any legacy award,
metadata or original recording date; unknown keys remain visible.

### Caller-origin matrix

| Writer | Method / origin | Notes |
| --- | --- | --- |
| Modern `/state`, all shared triage/keyboard/row/bulk callers | manual / live | Default compatible declaration. |
| Legacy `/status` read | legacy / live | Existing state mapping retained. |
| Google Reader edit-tag | greader / live | Each authenticated declared read uses shared entry. |
| Approved agent mark_done | agent / live | Existing approval boundary unchanged. |
| Signed digest link | email / live | GET renders an accessible no-store confirmation, no workflow/credit mutation; POST verifies same token and declares Done. |
| Listen queue ended | audio_finish / no credit | Validated modern origin; workflow-only, later explicit same-state Done can qualify. |
| Reading List article Done | manual / live | Authorized raw URL uses credit v1, not Reading List normalization. Other kinds excluded. |
| Personal archive restore | import / import | Resulting retained done_at OR current done; same item savepoint/outer account lock, including old/already-done IDs; foreign private sources skipped. Uploaded progress ignored. |
| Third-party Reading List archived article | import / import | Self-reported completion, same URL dedup, unknown effective time, silent even on duplicate existing item. |
| Authorized body evidence | automatic / live | Separate protocol below, no app-time inputs. |

First live/import winner permanently freezes provenance; a later distinct live read can cross
a threshold using earlier import prerequisites. Silent import awards have no group/exact earned
time. One existing `hundred_articles_read` at 100; new keys are `articles_read_1/10/50/500`.
`GET /progress-rewards` adds exact `reading_total`, `next_reading_target` and
`history_status=reconciliation_pending` alongside the existing item/group contract. The
existing ProgressSection renders this collection with vector/text earned/locked states,
requirements, exact/unknown dates, empty/error/retry and next milestone.

### Body protocol and privacy fence

`POST /api/articles/{id}/reading-evidence` requires current real authorization and body_status
ok plus a nonempty actual body (or its stored original-language variant). The client SHA256
must match the selected current body. Start `{body_version}` carries zero evidence and issues
a UUID token, sequence0, required_ms. Only one unexpired 20s lease/account; a second start
returns409. Subsequent `{body_version,token,sequence,attentive_ms,end_ms,progress}` uses strict
integer milliseconds <=15000, end<=attentive, finite progress0..1 and no unknown fields. Each
sequence must be previous+1. Accepted duration is min(client amount, elapsed server time,15s);
identical last-sequence replay returns the stored receipt without addition; changed replay,
expired/foreign token, unauthorized/body-replaced article fail. Start after expiry can resume
only the same article/body's pending aggregate; another body resets time. Pending logical TTL
24h, existing daily telemetry cleanup removes expired rows; per-account request cleanup also
runs. No reader aggregate/token/receipt is exported.

Shared ArticleBody installs the hook for page and pane only after actual body hydration.
250ms local geometry/focus/visibility/connection/idle sampling is aggregated into 10s evidence;
no detailed interactions are sent. Geometry uses body bounds and ancestor scroll clipping,
not header/summary/whole-reader progress. A short fully-visible body has progress1 but still
requires the full time. Original-body changes reset the lease; server independently derives
word threshold `clamp(30,120,ceil(words/8))`, using120s for unsupported unsegmented scripts.
Final qualification also requires progress>=.9 and >=2000ms end evidence. Automatic completion
uses shared credit and moves only today/later workflow to Done; it never overrides an explicit
skip/archive, navigates or steals reader focus. No offline outbox/catch-up. Local evidence is
not sent while hidden/unfocused/idle, and failed transport drops unsent time. Modified clients
can simulate attention only up to bounded server elapsed time, as approved.

Consent/global disable checked at issuance and acceptance; consent update takes account lock
and deletes the reader row, invalidating every prior token even after reenable. #1627 must add
its own consent-revision/window/gap state in this same transaction, not replace this fence.
Manual progress remains independent. API/body focus approximations are not native-device parity.

### Exact next-owner boundaries

- **#1626:** Before any new production credit activation, install the calibrated classifier in
  `credit_read`'s first-insert transaction; use frozen title/summary, including empty strings;
  finalize version even for zero topics; delete its pending source atomically. Never reread
  mutable article text for existing pending credits. This slice uses a separate temporary
  `user_read_credit_sources(credit_id,title,summary)` with credit CASCADE specifically to
  survive article retention and body replacement, not fake finalized zero. Source snapshots
  are exported, account-erased and privacy-disclosed; they are not a permanent ledger copy.
  This is the minimal transitional exception to the earlier no-title-copy design. A controlled
  implementation-fixture drain is allowed; no operational historical backfill is authorized.
  Add total/topic/breadth candidates to one cause `read:<credit_id>` and one shared award call;
  do not create a second group engine. Rollout remains gated until calibration and integration.
- **#1627:** Reuse the reader consent invalidation and account lock; generic active-time
  accepted milliseconds can never qualify a read. Extend existing lifecycle, not the reader
  hook, for app activity. Preserve connected/focused/body-only reader distinction.
- **#1628:** Compose the existing collection/host and canonical destination. No independent
  reading toast coordinator was added; live group IDs are ready for the shared coordinator.
  Retain unknown descriptors and metadata; archive progress is informational. Existing archive
  articles can independently earn import provenance, never restore uploaded awards or claims.
- **#1629:** Consume the connection-taking credit helper with historical origin/unknown date,
  frozen first attribution and same account lock. Implement cursors/introduction/eligibility
  tooling; no horizon capture, retention pause/drain, inventory or dry-run/apply ran here.
  Reconciliation status is deliberately pending until that owner has an authoritative state.
- **#1630/#1631:** Read live effective/earned times for current-period outcomes, not recorded_at
  of imports/legacy rewards. No recap/mail private-content outcome was implemented in #1625.

Verification commands, raw logs, real-cookie Chromium evidence and actual limitations are in
`/Users/ioachimlihor/.bb/thread-storage/thr_dbjkmtks2a/`; the final handoff identifies exact files.
Independent review, normal-hook publication and orchestrator merge gates are separate stages.
No production writer activation, user-data historical operation, deployment or merge is claimed.
