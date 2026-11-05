# D06 — scope incomplete; three failed rounds retained

- Branch `codex/reader-final-d06`; tested harness `9e01b2b5b079d1058f3206052e21e63c97d32c94`.
- Final run [40217793667/1](https://github.com/NoGod3524/EXReader/actions/runs/40217793667), **failure**. No fourth run. Final commit is docs-only `[skip ci]` relative to this harness.
- Windows native job121242662412 and verifier: 47 scoped checks pass (default17 + text/repeat8 + compact22). Not full keyboard acceptance.
- GTK job121242662262 exits0; final verifier refuses bare AssertionError. Artifact ZIP authenticated, per-action grant withheld. Static narrowing: visible envelope meets contract; count/report-identity assertions carry diagnostics, unlike this bare error. ZIP safety or manifest byte/hash guard remain. openbox.log is hashed before background process teardown: concrete race candidate, not proven cause.
- Android job121242662311: original33 + added9 pass; picker-cancel wait fails. Back inside native provider need not exit it. No proven product defect. Some page-preservation assertions do not guarantee reader focus.
- macOS job121242662291: 6 action marks, immediate search-close disappearance assertion fails (timing hypothesis).
- iPhone121242662236 / iPad121242662363: 8 action marks each, generic reader.more isHittable predicate fails. Existing owner native descendant trigger workaround was not reused; not proven unreachable product menu.
- Guard121242611335 passes 13 negative controls. Verifier121250241559 fails, authenticating all7 ZIP IDs/bytes/SHA256/expiry. Full raw Actions report: `docs/reader-final-d06/actions-verification.json`; precise platform scopes, program hashes, jobs, artifacts: `docs/reader-final-d06/validation.json` and `docs/validation/reader-final-d06.json`.
- Apple final apps are unsigned source builds with PAGE_THEME, review macros explicitly absent, reader.state runtime absence guard passed. SDK3.41/ABI1/core3.40 authenticated separately. Earlier Apple round2 used HOST_REVIEW+IMPORT_REVIEW and is not default evidence.
- Earlier failures:40215158098 redirect401 (zero native),40215565178 Apple assertions and Windows separator verifier refusal. Original logs retained; round2 Apple ZIPs reauthenticated in final guard.
- Findings/unique owner recommendations: `docs/reader-final-d06/FINDINGS.md`; complete static action/context/focus map: `actions.md`.
- Root follow-up: authorize future harness repair/diagnostic run if desired; no production changes made. Fix D06 close wait, reuse existing native Apple records trigger, inspect Android provider cancel state, terminate background writer before GTK manifest and add failed-member diagnostics without relaxing checks.
- Pending: defaultGTK runtime; complete modal Tab/ShiftTab/submit/cancel/focus matrix; repeated-submit; physical mobile keyboard/DPAD; all screen readers; common-source product acceptance. `accepted=false`, `audit_completed=false`, `keyboard_accepted=false`, `complete_product=false`.
