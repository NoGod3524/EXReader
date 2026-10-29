# EXReader execution resumed — 2026-10-29

This checkpoint continues the complete handoff. The fixed catalog remains **95/108**; no catalog row or denominator has changed. All build, syntax, test, fixture, benchmark and artifact inspection work runs in GitHub Actions. The original dirty checkout is preserved. No PR, default-branch update, tag or Release is authorized.

## User correction: local background subscription usage

The user explicitly corrected the dispatch mode: **not Claude cloud tasks; use local background Claude with the user's own usage**. Stop-work messages were delivered through the official CLI to all three mistakenly created cloud sessions (`ok:true` delivery receipts); cloud termination itself is not exposed by the available CLI attachment capability. Do not create further cloud tasks.

Three replacement local `--bg` sessions are actually working, in separate source worktrees under `C:/Users/Oscar/exreader-local-usage-20261029/`:

| Task | Local background ID | Dedicated branch |
| --- | --- | --- |
| C1 Android installed Sync | `73f87c47` | `claude/local-c1-android-sync-20261029` |
| C2 product performance | `4e0c44a1` | `claude/local-c2-product-performance-20261029` |
| C3 delivery/licenses | `c0da3128` | `claude/local-c3-delivery-licenses-20261029` |

`claude agents --json` reports all three as `kind=background`, `state=working` with local process IDs and their expected working directories. Each actual startup log displays **Sonnet 5.5 with medium effort · Claude Pro**. Normal CLI auth is `claude.ai` / firstParty / Pro; API-key, auth-token and custom-base-URL environment overrides are absent. No credential file was read or exported. These local processes receive the original Actions-only constraints and cannot grant catalog acceptance.

This correction supersedes the cloud-dispatch section below, which is retained as historical evidence of what was mistakenly created.

## Refreshed historical state

- `40935165396` / `55ec49020383ef5073f47502b300ab0b5d0a7cae`: completed failure. Both mobile hosts failed; macOS passed. The dependent independent audit `40937262016` completed failure and grants no mobile credit.
- `40937013878` / `6be10b3de1e7f9e98bab72db586a66e571199034`: both SDK builds and macOS native passed; both mobile native hosts failed. Authentication was still running at the initial refresh.
- `40937997549` / `bd28d4946f17a184dd3cd47a584cf49fce34e973`: completed failure at the independent OPDSHash prefix requirement.
- Windows qualification `40938221167` / `7c769dc1b80cd70cbddd0240dcb5de57729104d0`: success, 67/67. Actual Windows startup `40939979816` / `2fff53ff6734ec2b495c841e6669aef562e170d7`: success, 10/10. Neither result grants full Windows recovery or final-product credit.

## New independent acceptance

[40946443596](https://github.com/NoGod3524/EXReader/actions/runs/40946443596), source `81ecfbf8134a830262a7198972a36cba522fa8e1`, job `123702940582`, succeeded. It independently reread original Windows startup ZIP `12926312358` (4,194,330 bytes, SHA256 `dca517038d2a92e0da834fd2870f516e861f061817b0fbbda023f6e35645f850`). It checked exact source-file identities, all ten final passing cases, retained marker/file digests, actual schema 7 databases for clean and legacy-only fixtures, the retained visible Chinese dialog, and actual product executable hash `80c191f44131c7fb157bb58a5f894332797532c6666c52fb7f52ad444094cc66`.

Independent result artifact: `12930300460`, `windows-startup-independent-40946443596-1`, 893 bytes, SHA256 `0509b98608ae5b215e9b7ef050ab6d1687ad370f9283f766798ec8d7043d1af8`. This accepts the original cooperative startup scope only. It does not transfer that result to later product sources.

## Claude backend connection recovered

The new execution environment has no `CODEX_SANDBOX_NETWORK_DISABLED` marker. Normal DNS resolution and an HTTPS request to `api.anthropic.com` succeeded. No guard, proxy, route, TLS setting or credential file was changed. Official Claude CLI 2.1.310 created these real cloud sessions; all three supplied repository receipts with `claude-sonnet-5-5` and `medium` from session metadata.

| Task | Actual session | Dedicated branch | Receipt source |
| --- | --- | --- | --- |
| C1 Android installed Sync | [session_01YAwfwo2WUHPq4dKD1re5KQ](https://claude.ai/code/session_01YAwfwo2WUHPq4dKD1re5KQ) | `claude/handoff-c1-android-sync-20261029` | `879b293b3ce7972b693808b73482fd32454dee50` |
| C2 actual product performance | [session_01YAwfwoHbL5axuRuBF5dbGF](https://claude.ai/code/session_01YAwfwoHbL5axuRuBF5dbGF) | `claude/handoff-c2-product-performance-20261029` | `6cccac0f9d5bcf350c5281360012809f384a1e3d` |
| C3 delivery and licenses | [session_01YAwfwnieRNhVf6mx6d9V68](https://claude.ai/code/session_01YAwfwnieRNhVf6mx6d9V68) | `claude/handoff-c3-delivery-licenses-20261029` | `73665f53d31bfac6c27714c459bcc34029d88d7b` |

C1 initially launched from an old pushed commit because its local remote tracking ref was missing. A backend correction was delivered before implementation; its receipt confirms fetch/switch to exact `bd28d4946f17a184dd3cd47a584cf49fce34e973`. C2/C3 started after fetching their real remote refs, with the full model ID explicitly selected. C3's first receipt also named an automatic session branch; a backend instruction requires only the dedicated branch and requires reporting any environment-policy conflict instead of bypassing it.

CLI cloud attachment is not enabled for this account. Backend follow-ups are supported and returned `ok:true`; repository receipts provide observable progress without computer/browser UI. Session creation and model/branch receipts are not code or acceptance results.

## Active repairs

Three isolated built-in agents were actually started: mobile annotations, Apple public SDK integration, Windows migration. These are distinct from the three Claude cloud sessions.

- Apple OPDSHash patch: `329d676880c9c5f653b48f2ed6179bd1d7f97b28`, branch `codex/apple-opdshash-resume-20261029`, [40946118946](https://github.com/NoGod3524/EXReader/actions/runs/40946118946). It builds/installs the existing independent hash package first and passes its canonical prefix; original checker, core and tests remain unchanged. Results are pending.
- Mobile retained-failure inspection runs only in Actions. New original iPad ZIP is `12928855897`, 485,229,238 bytes, SHA256 `6f576fe25c63e1ce2571c6672430d809da32eb269332143a9b24bcc483f86d02`. Native trace proves the old directory blockage was passed; repeated navigation later consumed the original four-minute budget. Helper repair must preserve the five test bodies and all original budgets.
- Windows public-source startup patch first ran at `63ec64cce301a9687fbda88b92308d839bc486cc`, [40946049068](https://github.com/NoGod3524/EXReader/actions/runs/40946049068). SDK and hash installation passed, but Windows path spelling failed the strict canonical-prefix admission before product tests. The workflow path normalization is being corrected; the failed run remains retained.

New common-source composition and mobile catalog updates require their own completed runs and independent evidence. No active candidate is counted here.
