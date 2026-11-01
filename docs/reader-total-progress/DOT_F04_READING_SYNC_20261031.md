# Latest continuation — 2026-11-01 08:21 UTC

## Sealed foreground round: identified environment blocker
- **41287434330 A1**, source **5394ec6dc8aa6da7227bb7876609a235aa164f3d**, job **124791485333**, **failure**, original UI test **223.783 seconds**; other 27 jobs skipped. One Mac15 budget consumed, no retry.
- Artifact **13075384078**, **42355931 bytes**, SHA256 **e41dadfb05de1d9518ac06fa2a909f12f0f8baf6316459615d4c95f581f163ad**, same run/source. Actual UI 9653680 bytes, SHA256 **077d22d425c96fca4f3254c0e5901f10a832843c4a27f8c0a6b83e46cbc9b317**. diagnostic_only=true, passed=false, F04_accepted=false.
- API updated_at **09:17:45Z** and artifact time **09:17:43Z** are one hour ahead of runner upload log **08:17:43Z**. They are retained separately, not silently rewritten. Runner logs identify a GitHub-hosted macos-15-arm64 VM in westus, not a user computer.
- Original position/bookmark/note checkpoints passed at t24.41/t41.29/t63.25, with one native click each on jump.0/.2/.3. At t71.53 the app was activated once. save-progress stayed enabled=true, hittable=false; no save/edit/upload action followed.
- Before activation (08:14:52Z), after (08:14:54Z), and timeout (08:17:22Z), simultaneous bounded evidence showed exactly one UserNotificationCenter dialog at (382,104,260,248), covering save-progress. Its text was **Allow “Python” to find devices on local networks?** and explained network-device access. The app was already foreground; busy/pending/cancel were absent. No permission button was clicked.
- Previous evidence captured blank button labels, not title/value; action-button identifiers alone do not establish semantic choices. Public XCUIElementAttributes title/label/value and snapshot hierarchy provide a supported next semantic check.

## Explicitly authorized minimal denial round
- User approval **2026-11-01 08:21:55 UTC**, **Sentinel_1e8e3ff427048191a3adc3fbac94dab0**: same three existing files and one Mac diagnostic at most **15 runner-minutes**, no retry, plus one precise **Don't Allow** choice for this Python local-network request on the next temporary GitHub Mac runner.
- Only the Mac diagnostic branch may act. Require one current positive-size dialog with the exact normalized question and explanation, then one real button whose public title/label/string value/descendant static text identifies only Don't Allow. Normalize typographic quotes/whitespace, deduplicate repeated attributes per button, never infer meaning from substring, identifier number or position.
- Requery exact prompt and semantic candidate, require enabled/hittable, set the whole-test attempted flag before one native click. Ambiguous/empty/conflicting semantics, unknown dialogs or a repeated request stop without an Allow fallback. Existing target wait deadline observes actual prompt dismissal then the original fresh target readiness; no new wait window.
- No TCC/defaults/permission database changes, system app activation, process killing or coordinate action. Original five fixed-control whitelist, list helper, iOS behavior and successful save/edit/upload/location assertions stay unchanged.
- Both fixture services bind **127.0.0.1 with OS-assigned ephemeral ports**: HTTPS DAV transfers genuine app-authored state and HTTPS controller receives authorized read-only checkpoints. They do not require LAN device discovery. Denial is the least-privilege choice, but unidentified indirect networking could still be affected; this round must prove the unchanged real chain rather than assuming success.
- F12 actual-diff review precedes F03 sole canonical composition/trigger. No local source execution/tests/ZIP. Historical failure evidence, atomic inputs and production-equivalence allowlist retained; formal acceptance **96/108**, F04 incomplete.

---

# Latest continuation — 2026-11-01 07:59 UTC

## Sealed snapshot round
- **41286210606 A1**, source **e902aceb8ff7093902b90e8eb9c62e33f7d868ef**, Mac job **124787924916**, terminal **failure** at 07:55:17 UTC. Original UI test **263.888 seconds**; all other 27 jobs skipped. One Mac15 authorization consumed, no retry.
- Artifact **13075777205**, **42356371 bytes**, SHA256 **9943c91bc87f38bd82d5b497991949fee48d8e0f48025ea097a63a5fc1f11b56**. Actual UI **9653680 bytes**, SHA256 **987bc219d8ba837df6a9a0819e3c947c8e5f3cb49b694111a1b8f82245baef65**. Controller/UI source and input/production-equivalence receipt match; diagnostic_only=true, passed=false, F04_accepted=false.
- jump.0/.2/.3 each received exactly one native click. jump.2 took three small scrolls; jump.3 went from live zero-size representation through seven native scrolls to y450 inside list y261..474. Original exact-location checks passed; incoming-bookmark checkpoint at test t67.14 and incoming-note at t101.58. Three original reading.close taps succeeded.
- First failure was original tap readiness for **reading.save-progress**, before any save click. Its frame (427,230,94,20) is fully inside the fixed records sheet (277,186,470,360), outside the list. Logs support enabled but non-hittable; no busy/cancel/pending evidence. A repeatedly unhandled UserNotificationCenter dialog at (382,104,260,248) geometrically covers it, but the last recorded system dialog was t88.98 and save wait began t108.55. No simultaneous system title/body/button semantics were captured: overlay remains a strong candidate, not a proven cause.
- Both edit actions, note saves and final upload were not reached. Their original success assertions remain, not a claim of coverage.

## Approved foreground preparation and bounded evidence
- Explicit approval **2026-11-01 07:59:21 UTC**, **Sentinel_18b31759a61081919792cfc03cd490db**: same three existing files, one Mac diagnostic at most **15 runner-minutes**, no automatic retry; F12 actual review then F03 sole canonical writer/trigger.
- Only whitelisted fixed controls and editor-input readiness may request one activation per logical interaction. Original ready predicate comes first. Immediately before activating, require already-running foreground/background state; otherwise fail without deliberate relaunch. Apple documents that activate can launch a stopped app, so no launch fallback is permitted. State is asynchronous: this guard does not claim atomic protection against process-exit races.
- After native activation, requery the original readiness predicate within the original polling budget. Activation is not success; save/edit/upload/location assertions, editor input semantics, existing row helper and iOS are unchanged. Fixed controls do not borrow list/account-form scrolling.
- Before/after activation and at final readiness timeout, collect bounded timestamped own target/container/status plus current UserNotificationCenter dialog semantics. System app is read-only, never activated or clicked; no action-button guessing, notification settings, process killing, permission changes or coordinate bypass. Input/editor values are excluded; credentials/root/token, URLs and account emails are redacted, text/dialog counts bounded, no notification history or raw whole-app dump.
- This preparation may restore foreground but does not promise to remove a system modal. Unknown blocking UI is evidence, not permission to dismiss it.
- Preparation pending independent actual-diff review. No local execution/tests/ZIP handling. Fixed atomic inputs, workflow/runtime and production-equivalence allowlist unchanged; formal acceptance still **96/108**, F04 incomplete.

---

# Latest continuation — 2026-11-01 07:43 UTC

## Sealed virtual-row preparation failure and review correction
- Run **41285517057 A1**, source **436ff37b03782d6e4bbab72a1513ed9ce3f6c628**, Mac job **124785888456**, terminal **failure** at 07:40:30 UTC; original UI test **37.813 seconds**. Other 27 jobs skipped. Budget 1/1 consumed, no retry.
- Artifact **13075451161**, **42340516 bytes**, SHA256 **e4f6983d884a8c90ce31308f7fb3d50863e93facf0e60a4f0de01c9c16ce28a7**; exact run/source confirmed. Diagnostic-only, passed=false, F04_accepted=false.
- Actual UI built successfully (9653680 bytes, SHA256 **6c2df1738aafbad24bfc82c5e35ef6bcc3152460756aeefca7a240c1df3ec920**). Fixed input authentication and production-equivalence receipt succeeded.
- First jump.0 preparation began at test t28.72. Target/list reads reached t29.52; candidate enumeration began t29.63; 18 anchors each required identifier/frame reads (36 remote AX Find calls), ending t33.87. One observation exceeded the three-second window. No native scroll or jump click occurred. This is a newly introduced test-driver sampling regression, not demonstrated product instability.
- Review missed AX call cost, forced preparation for already admissible actions, and stable=0/>=3 requiring four observations. Static review is not runtime proof. Later jump.2/jump.3, both edit actions, original row discovery and editor waits were not reached; no claim that this chain passed. Previous results remain sealed below.

## Approved minimal snapshot round
- Explicit authorization **2026-11-01 07:43:57 UTC**, message **Sentinel_e0c21a23187481919bf2e3dd4a3d0fd6**: same three existing files, one Mac diagnostic at most **15 runner-minutes**, no retry. F12 actual-diff review precedes F03 sole canonical composition/trigger.
- Single loop: **21 fresh original admission checks**, at most **20 snapshots and 20 native scrolls**. Every cycle first checks actual unique list/target, positive dimensions, complete containment, enabled/hittable; success immediately performs the original single native click. No settling clock, stable-count qualification or prior-anchor requirement blocks an admissible target.
- Only an unsuccessful nonfinal admission obtains one public list snapshot. Target and anchor attributes are traversed in the returned hierarchy, without live per-descendant AX property requests. The final cycle still admits after the twentieth scroll, without another snapshot/scroll.
- Real target geometry or visible row indices guide the first ≤16px probe; subsequent steps remain ≤24px and ≤20% viewport height. Same-index guidance uses only the real sibling action in the same HStack when it overflows; no kind/body midpoint guess or invented target rectangle. Same real nonzero anchor/target displacement calibrates direction. Missing/conflicting movement or insufficient direction consumes a pending observation rather than blind scrolling. Snapshot/geometry limits terminate as preparation-incomplete, not product failure.
- The three-second/three-stable-observation requirement is removed, not enlarged. All original exact-location/data assertions and iOS bytes remain unchanged. Product/SDK/workflow/runtime files, fixed input pins and cumulative six-path equivalence allowlist are unchanged.
- Prepared only, pending independent actual-diff review and canonical trigger. No local code execution, testing or ZIP handling. Original formal acceptance remains **96/108**, F04 incomplete.

---

# Latest continuation — 2026-11-01 07:32 UTC

## Sealed pixel-scroll round (not acceptance)
- Run **41284680303 A1**, source **13ae646b11353473bb09459603a16396c1aa89d5**, Mac job **124783470950**: **failure**, 78.244-second original UI test; other 27 jobs skipped. Single 15 runner-minute authorization consumed (1/1), no retry.
- Native pixel scrolling fixed jump.2: y512 → 496 → 472 → 450 inside actual list y261..474. Original native click, exact-position status and incoming-bookmark checkpoint passed.
- Next jump.3 was enabled but virtualized: frame (0,768,0,0), not hittable. The preparation positive-size gate failed before scrolling/clicking this row. This is not proof of a product resolver failure.
- Artifact **13075115412**, **42344277 bytes**, SHA256 **89e6a2c7c7db3878cbbc53d990f2ad17581a43b3a09f70fcfa57727601501ab1**, same source/run, diagnostic_only=true, passed=false, F04_accepted=false. Previous three-platform failed round and successful iPhone/iPad diagnostics remain separately sealed below.

## Approved virtual-row preparation round
- Explicit approval **2026-11-01 07:32:25 UTC**, message **Sentinel_c32e0fdac5d4819194b19d1a8e4f12f0**. Exactly the same three existing paths: apple_driver.swift, contract.json and this evidence document. One fresh Mac diagnostic, at most **15 runner-minutes**, no automatic retry; F03 is the sole canonical writer/trigger after F12 actual-diff review.
- Mac jump/edit share native materialization plus pixel convergence. Temporarily absent/zero-size target gets bounded three-second fresh queries; duplicates fail. Real positive visible same-list row anchors and their actual enumerated indices guide native scroll preparation. Placeholder rectangles never supply position or direction.
- Shared limit: **20 scrolls / 21 admission checks**. First step ≤16px; subsequent ≤24px and ≤20% viewport height. Direction calibration uses actual same-anchor/target signed displacement; stable visible-set turnover proves progress only. Three stable observations, 0.1-second sampling, 0.5px tolerance, three-second settle timeout. A newly materialized target may proceed on its own stable positive frame without requiring the old anchor to survive.
- Final admission remains unique target, positive dimensions, complete containment in actual bounds, enabled/hittable, exactly one native click, followed by every original exact-position and data assertion. Four-pixel margin guides scrolling only. Overshoot halves cap. No coordinate clicks, fake frames, product hooks or iOS changes.
- All original source/SDK/Android atomic pins, cumulative six-path production-equivalence allowlist, workflow and runtime entry are unchanged. No local execution, syntax/test run, or ZIP handling; all runtime verification is Actions-only.
- Preparation status: pending F12 actual-diff review and F03 trigger. This document does not claim a new run or test result. Formal acceptance remains **96/108**; F04 incomplete.

---

# Latest continuation — 2026-11-01 07:21 UTC

## Three-Apple diagnostic sealed; single Mac pixel-scroll round approved

[Run 41276273173 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41276273173), source `cc5a88f4de822ad8c235f9b903961cf2a793628e`, ended failure. iPhone job 124758969434 passed the original test in 212.940 seconds; iPad job 124758969626 passed in 276.083 seconds; both report one test and zero failures. Original precise location, record editing and upload assertions remained. Windows returns and graph audit did not run. The diagnostic receipts retain F04_accepted=false; formal catalog remains 96/108.

macOS job 124758969636 failed after 111.222 seconds: reading.jump.0 succeeded, but reading.jump.2 alternated y=512 and y=227 around the actual list viewport y=261..474 as whole-list swipes moved it 285 pixels. Ten attempts exhausted the visibility guard; no jump.2 click was issued. This is observed test scrolling overshoot, not evidence of a resolver failure after a visible button click.

| Target | Original artifact ID | Bytes | SHA256 |
|---|---:|---:|---|
| iPhone | 13072160640 | 42343661 | 3325f134e551274ebdd5deb0b1f2aa91f8c5512f35f23213eb8c2348480ee60d |
| iPad | 13072186647 | 42343769 | 65658e2ffff041942c79ee6e9a7189ec5d5f93cc70948e2964c2947cb6795001 |
| macOS | 13072026988 | 42344334 | 5392e1bfbabff6ef44172d82a6eb92d69ecc75c9efebe4df27a528d513334ae3 |

API identities and ordinary logs were read; no local ZIP processing or test execution was performed.

User approval at 2026-11-01 07:21:31 UTC (`Sentinel_4e552a792a7c81919a80e78887ce2244`) covers exactly three existing files: this document, contract.json and apple_driver.swift; preparation commit/push and one single Mac diagnostic capped at 15 runner-min, no automatic retry. Independent design review passed before implementation. Actual-source review is still pending at this preparation checkpoint. No new run has started.

The Mac-only implementation uses the original native list's pixel-precise scroll(byDeltaX:deltaY:), initially at most 16 pixels, then at most 24 pixels and 20% of the viewport height. Observed target movement calibrates direction; overshooting to the other side halves the cap, minimum 1 pixel. Each scroll requires movement above 0.5 pixel and three stable frame observations at 0.1-second intervals within three seconds. It re-queries the unique list and row action. There are at most ten scrolls and eleven admission checks, so the last scroll can succeed. Four-pixel padding guides motion only; original full-bounds containment, enabled/hittable checks and one native button.click decide success. Missing, unmoving, unstable or uncontained targets fail without a click. The iOS body, other controls and original precise-state/data assertions are unchanged.

Official native API: https://developer.apple.com/documentation/xcuiautomation/xcuielement/scroll(bydeltax:deltay:)

Reuse the existing f04/macos-state-diagnostic entry, Mac 15-minute job and authenticated historical SDK/Android inputs from 2cdad2057d4877b4712af8155da72fb92b50e411. No workflow or run.py change, no SDK rebuild, no iOS rerun, no product code change. The existing six-path equivalence allowlist describes the cumulative diagnostic delta versus that old producer and is not broadened. The new delta versus cc5a88f4 is only the three authorized paths.

F03 is the sole canonical composer/trigger after F12 actual-diff review. This preparation branch uses [skip ci]. New syntax/build/UI checks remain Actions-only. No formal F04 acceptance or new green run is claimed. All prior failed evidence below remains unchanged.

---

# F04 reading-state bidirectional preparation — 2026-10-31

## Status and authority

**Implementation-only preparation; no build, syntax check, test, ZIP parsing or CI
has run for these new files. This is not F04 acceptance.**

User approval at 2026-10-31 23:13:25 UTC permits exactly ten new files on
`dot/f04-reading-sync-20261031`, with **0 CI**. The fixed preparation source is
`94fb236a4a2da87dfbaf4f1dd2a47885d615a230`; SDK content remains
`8357eafa28423a7ab93ba08b823af80f01ad1505` (3.42.0).
The official catalog stays 96/108. No shared branch, product, SDK, old test,
external owner, PR, tag or release is changed.

Apple annotation product work remains with its owner. UI/F08, F03, F05, F07 and
F10 remain with their assigned writers. The new drivers invoke existing real
application UI; they do not write application databases or synthesize reading
revisions. Every raw revision is authored by the application and preserved by
the staged authenticated HTTPS service.

## Ten owned files

All eight files under `tests/dot_f04_reading_sync_20261031/`:
`contract.json`, `admission.py`, `fixtures.py`, `relay.py`,
`apple_driver.swift`, `android_driver.java`, `run.py`, `audit.py`;
plus `.github/workflows/dot-f04-reading-sync-20261031.yml` and this document.

The workflow has no push, pull_request or schedule event and its only job has
literal `if: false`. Preparation commits carry `[skip ci]`. Dispatch/build
wiring requires new bounded approval, not silent activation.

## Reused evidence, not transferred acceptance

- Run [40625252316](https://github.com/NoGod3524/EXReader/actions/runs/40625252316),
  source `0ec6d3aa34297f30e016af9f1cb2416ed79709f2`, proved SDK 3.41
  iPhone -> Android -> fresh iPhone single-EPUB progress (original anchors
  207 -> 878). Its own summary sets all_platform_F02_F04_accepted=false.
- Run [40181402323](https://github.com/NoGod3524/EXReader/actions/runs/40181402323),
  source `b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7`, accepted Android
  sender 138 checks, four originals, 19 revisions, 11 records; incoming Apple
  remained pending and bidirectional_interoperability_accepted=false.
- Run 41170540560's three green Apple sync jobs concern authorization failure,
  credential update and HTTPS retry. Their name does not prove F04.
- Formal catalog `5db41cb19673fb75bb0b498c677d770931ac33e8` leaves F04 pending
  and iPad annotation exchange partial. iPhone individual acceptance is not
  all-host interoperability.

## Prepared execution path

1. `admission.py` binds the base, SDK objects and exact ten-file path ownership.
2. `fixtures.py` acquires the original fixed real Alice EPUB using the retained
   manifest commit and exact 189249-byte/SHA256 identity. It does not choose a
   replacement after test results.
3. `run.py prepare`, only inside Actions, creates test adapter copies under
   build/f04-driver. It checks old source bytes against the fixed baseline,
   preserves original assertions and fails if any exact substitution drifts.
   It never overwrites the retained drivers or product code.
4. Apple creates actual progress, a point bookmark and a selected-text annotation
   through UI and syncs them. Android receives original bytes and exact records,
   uses real record-jump controls, verifies the displayed page contains original
   anchors, then creates return progress/bookmark/annotation by UI.
5. A fresh iPhone receives the Android progress and explicitly jumps to the
   returned bookmark and annotation. Read-only host-state checkpoints bind
   actual part/path/reading offset and rendered page identity.
6. `audit.py` first runs the retained relay strict assertions in an admitted
   generated copy, including program/ZIP identity and original retained suites.
   Then it verifies exact raw revision bytes, unique heads, point/range
   distinction and receiver landings. Even a passing stage leaves
   F04_accepted=false and six_target_accepted=false.

The Android instrumentation must be built using generated
`build/f04-driver/init.gradle`, class `org.exreader.host.F04AndroidTest`.
Apple uses the admitted 3.42 producer from
`tests/apple_sdk342_host/build.py`. Existing SDK artifact prefixes and retained
job roles are required by the unchanged original verifier. The later workflow
assembly must preserve them and the original 39 Apple cases, Android sync
phases and 24 receive checks. No old 3.41 program may be substituted.

## Remaining before any CI request

- Static independent review of these uncompiled drivers, including native UI
  labels, annotation kind after note edit, read-only owner queue usage, and
  exact source adapter substitutions.
- Build/workflow integration for SDK 3.42 Android and new instrumentation
  without mutating the retained workflow or product files.
- Decide and approve exact producer matrix, original affected regressions,
  job timeouts, one-run budget, and final gate. This document grants none.

Historical relay job runtime was about 130.05 runner-min; its original job
timeout caps sum to 700. Neither is a six-host estimate or an authorization.
A blanket 600-minute estimate was withdrawn before execution.

## Still required for complete F04

Windows, Linux GTK, macOS and iPad are not implemented by this stage. Full
six-host same-source proof must also cover required original-anchor formats,
bidirectional progress/bookmarks/annotations, non-FOUND/no-mislocation behavior,
and remote updates not forcibly moving an active reader. Existing old negative
tests remain; additional full-host evidence must be produced, not inferred from
this two-platform happy-path stage. Source compile/runtime defects are possible
until Actions validates them.

No runtime success or completion count is claimed. Failures and later fixes
must retain exact run/attempt/job/artifact identity. No new CI may begin under
this zero-CI preparation grant.

Static source follow-up: point records remain BOOKMARK after note-text edits (annotation_view.cpp classifies point before note_size). The new strict selector also refuses missing/foreign parents, duplicate parents and cyclic history before accepting one head. These are static findings, not executed tests.

Static review caught BookStore construction invoking repairMissingMappings(): the prepared Android driver now borrows the actual MainActivity worker/store for list, retained-wire and public original reads; it does not open a second application BookStore/SDK connection. Its independent chapter-boundary fixture remains a separate isolated test library. No runtime proof is claimed for this correction.

The singleTask MainActivity must first launch after instrumentation installs ActivityMonitor. The generated Android adapter prepares only its files/ test-input directory before instrumentation instead of prelaunching the Activity; the actual account/receive UI flow still launches it. This avoids an unobserved preexisting activity in the owner-borrow path.

## 2026-10-31 六 host 扩展准备（仍为 0 CI）

批准：用户 23:28:57 UTC 明确批准新增 Windows/GTK 两个 driver，原 10 文件适配；仅同一独占分支，产品/SDK/旧测试不动，所有构建和测试仍需另批 Actions 预算。
当前包范围为 12 个新增于 94fb 的文件；本节不将编写、静态检查或提交当作运行通过。

### 原文约束与最小覆盖图
- catalog F04：六目标进度/书签/标注与原始锚点双向互通，不误定位。
- PRODUCT-PLAN P5：六目标闭环，至少两设备同步原书、进度、标注和分类。
- READING-V2 必须出口 2：TXT 文首/多字节/文末点、EPUB 章/重复 spine、完整文档 chapter、PDF/CBZ 无文字页，在第二独立 SDK 库解析。
- 因而不把“四格式 × 三类型 × 六作者 × 所有端对”加成新门槛。原 18 锚点/17 FOUND/1 AMBIGUOUS 协议证据按原范围保留；无文字页不制造范围标注。
- 规划 Windows 与 GTK/macOS/Android/iPhone/iPad 五条双向边。每个接收端实际产品拉取和明确导航，返回端通过真实 UI 编辑/保存产生 outbox，再由另一真实客户端接收。不可将本地已下载但未发布的字节当作出站证明。
- 全局 ID 和原 wire 保真、SAFE+FOUND、活动阅读不被远端强跳仍是实质要求；没有六作者数或截图数量的额外拒绝门槛。

### 新增两个真实产品驱动
- windows_driver.py 使用正式旧 Windows host 的 RecordsApp/Account Device 控件；不是 Windows Studio。原生导入、账号、保存、记录打开、出站同步；SQLite 仅 URI mode=ro 观测原 wire。
- gtk_driver.py 使用实际 GTK 应用、AT-SPI 与 xdotool；系统导入、实际账号与阅读记录控件。编辑接收的书签/标注保留全局身份和原锚点，不调用测试修订提交器。
- Windows 活动页使用既有原账号验收的原生 page-label 控件 124，而不是会被任意状态消息改变的 status 文本作误导航判据。
- 所有桌面证书信任只设计在 Actions 临时 runner，记录指纹/路径并清理；不在用户电脑上安装证书。私钥不进入证据包。

### Apple / Android 适配
- apple_driver.swift 增加 macOS 菜单平台分支，iPhone/iPad 共用 iOS 真实控件；peer 通过现有产品记录编辑/保存返回，不改生产 hook。
- run.py 保持旧双端 adapter；另生成 iphone-peer/ipad-peer/macos-peer/android-peer 包装，设备选择、macOS app 路径、实际只读产品记录路径分开。旧 runner 仍逐字节锁定 94fb，旧断言保留。
- Android incoming-prefix 来自 runner 输入；原五检查与新增两检查分别记录，实际 app owner 队列只读规则不变。
- 原独立边界夹具、原真 EPUB 字节身份和原公开 API 检查不被此次图适配删去。

### 真实状态与下一步
- 尚未编译、语法检查、运行或下载解析任何工件；CI 0，workflow 的 job 仍 if:false。
- 图审计新增检查同源码/run/attempt、相邻真实传输、双向可达、六 host 程序身份、三类 wire 与实际导航；仍只给 graph_checked，F04_accepted / six_target_accepted 恒 false。
- **未完成**：六 host 的完整 producer 工作流与 artifact routing、保留协议及宿主 producer 的严格认证接线；编译/runtime正确性；完整六端无误定位验收。现阶段不是“已完成六端驱动验收”。
- 外部 Apple 标注产品 writer 仍归原 owner，任何实际生产能力缺口必须回报；不以 SDK consumer、数据库注入或测试内部函数冒充 UI 成功。
- 待独立静态复核后，汇总上述尚缺实施及实际 CI job/预算再申请。不自动重复旧昂贵整轮。

### 扩展静态复核修正
- GTK：补实际 Apply credentials (alt+a) 并等待绑定成功；每次扫描要求 session_generation 递增，运输完成后明确执行 Receive books (alt+r)，等待投影完成的独立 notice/状态，不拿旧 state=4 当新完成。
- Windows：只读核实 accounts_ui 原逻辑会在新 FINISHED attempt 自动开始接收；“同步完成：投影检查…”是接收结束分支，因此原真实账户 helper 的完成条件保留。
- macOS：原 relay.start 本来已有宿主证书信任（并非缺失）；统一为一次指纹记录的临时信任，正常/失败路径均移除该证书。macOS CODE_SIGNING_ALLOWED=YES 与 94fb supplemental 原真实套件一致；iOS 模拟器仍 NO。

- 静态清理复核：桌面 finally 不再串联可能短路的 close；逐项尝试实际应用、fixture server、信任、私钥及 AT-SPI 释放。清理错误记入结果并使本阶段失败，不覆盖正在传播的原测试异常。

- 接收端初始化自查：Windows 仅 seed 本地导入；peer 空库走实际账户同步自动 receive/import。GTK peer 空库执行 Receive 投影后真实书架 search/F2/Home/Return 云书打开。避免先本地导入再 stage bootstrap 产生与远端并发的 book root；没有测试合并或写入产品库。

- 公共 Alice EPUB 首屏是无文字封面；Windows seed 使用三次真实 next 后才捕获范围，不给空页制造文本。若最后关闭/清理失败，即使先写过state，也删除本阶段state并保留失败result，防止失败producer被图审计误接纳。

- 结果文件写入本身失败也会失效自身state；未来原始artifact认证同时要求producer success、result通过、state一致，不能只凭state的早期passed。

### 六端图原始工件认证准备
- contract 固定 1 个 Windows seed、5 个 peer、5 个 Windows return 的 job/artifact 绑定；这表示可连通双向图的生产者，不要求任意两个 host 全配对，也不以作者数量计分。
- audit.py --authenticate-graph 设计为只在 Actions 读取本 run/attempt 作业与原 artifact ZIP，核 job success、source、ZIP大小/SHA、result+state、实际 program.bin、证书/服务源码、真实请求和原件字节，再建立 predecessor SHA 图。它不解包生产者给出的路径。
- 每phase单独保留实际运行程序原字节。Apple是实际构建的app executable，Android为验证安装APK等于同run产物后读取的安装APK，桌面为实际启动的文件。
- 完整 producer workflow 仍没有启用；原协议18锚点与必要旧宿主断言的严格认证尚需接合，F04最终标志仍false。上述新代码未运行。

- Graph producer上传清单只取state/result（Android report）/requests/cert.pem/program.bin与明确证据；不得整目录带入profile、private或key.pem。原ZIP认证发现这些本包私有路径会拒绝，不下载用户凭据。

Producer contract explicitly marks current jobs `fresh_profile=true`: original GET is required for those non-seed jobs only, not a universal requirement for a future approved cached-profile return. Current drivers still create fresh profiles. No CI was run.

### Producer build recipe preparation (not executed)
`run.py build-{windows,gtk,android,macos,iphonesimulator}` first requires this package's exact admission, then invokes byte-locked 94fb SDK3.42 build recipes. Historical unrelated branch guards are not substituted for current admission; build assertions are unchanged. Android compiles the new instrumentation using the original named relay Gradle recipe, exact SDK3.42 selection, and verifies the app APK did not change during instrumentation build. Apple SDK steps explicitly do not claim to have built the UI executable. Workflow remains disabled; dependency setup, same-run routing, retained proof authentication and actual execution remain incomplete.

F06 static review found missing canonical OPDSHash owner in the retained Windows/Android/GTK build entrypoints. The wrapper now builds the public hash-only package before those recipes, in target-specific prefixes; Android uses NDK27/API26/x86_64, not a host archive. Its canonical environment selector remains set through installed ProductCatalog consumers. Apple retains its existing per-target hash setup. This corrects a statically identified dependency; only F10's Linux prior recipe has runtime evidence, not these new F04 platform builds.


### Continued F04-only preparation: retained evidence and artifact identity
The active F04 line does not wait for the independent F03 shared-suite run.
Graph artifact lookup now consumes explicit upload-result IDs and checks source/run/attempt/digest; unrelated same-name artifacts do not cause rejection.
The retained-protocol recipe selects the original 18/121 checks, original export, and native HTTPS 18-capture steps from the byte-locked workflow. Only SDK selection is adapted to 3.42. All assertions remain original. The historical complete four-ZIP aggregate is explicitly `not-run`.
The retained auditor authenticates same-run IDs, original ZIPs, original reports/raw checks and actual probe binaries. Each rejection probe begins from a separately validated positive bundle and asserts its exact rejection reason. These checks have not been executed.
Producer workflow routing and complete compiled/installed host evidence remain in progress. No workflow is enabled, no run is started, and no complete-F04 acceptance is asserted.


### Disabled producer routing and installed-program evidence
The existing workflow now describes 18 disabled jobs: four reusable Windows/GTK/macOS/simulator builds, eleven real UI phases in the bidirectional star, two original retained-protocol jobs, and one authenticated audit. Every job has literal `if: false`; timeout ceilings are NOT authorized runner-minute spend. No dispatch has occurred.
Android builds and runs its peer in the same job because the app embeds the fixture CA; fixture private keys never become handoff artifacts. Public build artifacts and UI artifacts expose distinct upload IDs.
`package-build` exports only explicit public program/SDK payloads. `seal-phase` binds the actual program to its same-run build receipt; Apple verifies its actual bundle source plus installed SDK manifest rather than comparing binaries across platforms. The graph auditor independently authenticates build IDs and raw ZIPs, verifies each installed SDK file, and binds phase receipts and program bytes to the appropriate target.
F07's limited static review found missing original WebDAV raw checks; these are restored (nonempty checks, native transport flag, original counters and summary/raw agreement). The original WebDAV fixture is wrapped with precise per-fixture cleanup, never cleanup of unrelated system trust.
All new wiring is unexecuted. The original four-ZIP aggregate remains `not-run`; full F04 still requires runtime evidence and clause-by-clause final review, not merely a new audit flag.

Final static hardening of this preparation restores the GTK executable bit after artifact download and restricts build-receipt recipe lookup to the five fixed target recipes (no artifact-supplied filesystem path is opened). F07 independently re-read and accepted the specific restored WebDAV raw-check fix; this is not a whole-workflow or runtime approval.

The limited full-package static review identified that fresh Apple UI jobs cannot inherit the SDK-build runner's Ruby gems. The original `xcodeproj` require/install prerequisite is restored separately in macOS, iPhone and iPad UI jobs. This remains disabled preparation, not executed installation.


## Approved first real case — 2026-11-01 01:35:33Z
User approval `Sentinel_dbf1e1cd310481918cf59dec9cedca3e` permits the exact 23-path canonical union (existing F03 eleven plus F04 twelve) and ONE Windows→Android→fresh Windows case, 120 runner-minutes total: 30/45/15/20/10 for Windows seed+build, Android peer+build, Windows return, Linux original retained checks and audit. No automatic retry is authorized.
This F04 branch only prepares its existing files. F03 remains sole writer/trigger for the canonical entry, after its current diagnostic reaches terminal state. This helper now has only `workflow_call`, never an independent push/dispatch trigger. Caller display name must be `F04 windows-android`; approved input case is `f04/windows-android`.
The canonical actual source must satisfy controller SHA = checkout HEAD = run head SHA. 94fb is only the product baseline; 8357 is only the frozen SDK source. Other-SHA artifacts are never reused. The executed graph has two actual host roles and two directed edges; the complete six-host goal remains pending. Linux original 18/121 evidence is included; cross-platform retained comparison is explicitly false in this case.
Syntax/generated-adapter checks are placed at the front of the actual producer jobs, not a separate validation run. On this branch no run has been started and the one-run approval has not been consumed.

Limited reusable-helper review found graph and retained job lookups still using unprefixed names. Both now use the same exact canonical caller-name helper as build authentication; matching is not broadened. No run was consumed.

## Approved round 2 repair (2026-11-01 02:04 UTC)

Round 1 run 41262238367, source a01e28bd02ef5fcbc1448f26dfd86da0b3499869 failed. Windows SDK build passed but synchronous first import BM_CLICK timed out; no claim of proven app deadlock. Linux legacy probe rejected mixed schema-1 revisions/schema-3 catalog. Android, return, audit never ran. Only public Windows build artifact 13065044582 exists (53052942 bytes, sha256 2db74a627d963e230ed2f105d60b3da757f2940052135df4a8595daecb5ff1ee).

User approved six-file correction and one new 120 runner-minute cap (30/45/15/20/10), no retry. Legacy 210403d121d6484a8fff4ea7ffd911efa3163535 catalog/revisions now use isolated v1 prefix; original 121/18 checkers and frozen SDK remain unchanged. Actual CMake caches and link map authenticate isolation. Windows import uses one physically targeted SendInput gesture, fresh empty shelf and bounded unique new row/idle result, never re-clicks after uncertainty. Always-upload diagnostics are separate from successful receipts and exclude profiles, databases, keys and credentials. Screenshots only cover pre-account import; authentication-bearing text is removed. No product/SDK/old-test changes. Implementation still requires independent review and the authorized new runtime; F04 remains pending.

## Round 2 terminal and authorized fixed diagnostic

Run 41264117725/source cb8b5e2d04a524a44a686eb8385872ee832d373e: original Linux retained producer succeeded; Windows single physical import never reached one visible shelf row within 120 seconds. Downstream Android/return/audit skipped. No F04 acceptance. User 02:20:04 UTC authorized exactly one 5-minute read-only Actions diagnostic of artifact 13066097833 (1638 bytes; SHA256 2f0916f73a040e9a0589c95fbcdb1f114d1468785235330e98477e9d97736a46), no build or product execution. Helper is selected only through canonical f04/diagnose-round2; producer and diagnostic-controller identities are explicitly separate. All whitelisted small text is re-redacted and printed in ordinary logs; original ZIP is retained. No automatic repeat.

## Compact picker root cause and Windows-only validation

The earlier inference that a filled hidden path bypasses the picker was incomplete: Windows Wave3 compiles EXR_READER_WINDOWS_COMPACT. WM_COMMAND dispatches compact_command first; the default compact Import action always calls GetOpenFileNameW. The fixed diagnostic run 41265285040 showed a live process and unchanged empty-shelf status; it did not prove a hang. Existing reader_windows_compact and reader_wave3_c09 tests already consume this real native picker. The new F04 adapter identifies the actual PID-owned modal and unique filename edit, submits one actual OK action, never retries import/OK, then requires fresh zero-to-one shelf, opening a nonuniform rendered page, and normal exit zero.

User 02:30:44 UTC approved six existing paths (five F04 files plus canonical entry) and one 10-minute Windows-only job. It authenticates/reuses build artifact 13067105719 from cb8b5e2d04a524a44a686eb8385872ee832d373e, without rebuild or DAV. Controller and producer remain separately recorded; no claim of current-source full runtime or bidirectional acceptance. All profiles/databases/private keys excluded. The old producer failure remains unchanged. Full F04 remains pending.

## Round 3 complete two-host chain authorized

Windows-only run 41265967021 (controller f2218d544330beb0f985cb12c1ea6d59b446a221; historical product cb8b5e2d04a524a44a686eb8385872ee832d373e) passed fresh single import, system picker accepted once, opened nonuniform page, and normal exit zero. Artifact 13066734468: 401007 bytes, SHA256 c0fa0f9dcb737b22dd748d0de8e8399a8c911e259fc0dc9228a4d28605a537f2. It does not grant current-source bidirectional acceptance.

The complete compact-entry sweep identified exactly three remaining hidden top-level buttons used by this package: account 137, records 210, select 107. The driver now verifies their existing native menu entries and enabled state, actual owner PID/foreground, then dispatches one normal menu WM_COMMAND; actual dialog/owner assertions remain unchanged. Book-open103 and next106 are visible in their corresponding compact views. No theme/font/format controls are invoked. Close now requires WM_CLOSE and exit zero; forced cleanup cannot count as normal success.

User 02:40:55 UTC approved only windows_driver.py/contract.json/this document, specified branch commit/push, and one fresh full 5-job Windows→Android→Windows run (30+45+15+20+10=120 minutes), no retry. All target programs are rebuilt at the new canonical HEAD; no historical build is substituted. Product, SDK, old test files/assertions are untouched. All prior failed runs remain evidence; complete six-host F04 still pending.

## Round 4 exact parser spelling compatibility

Run 41266444103/source 19566821ce7082ffb5cde6a538fdf163ab554902 passed Windows seed and Linux retained checks. Android received the same original and displayed Windows bookmark/note, then failed the first progress jump. The ordinary log preserves incoming bare parser 3.42.0 and unchanged cover. Source inspection identifies Android's rejection of that exact spelling; reverse Windows admission also rejects Android's exreader-sdk-3.42.0. No missing preview confirmation exists in this resolve route. The original runtime error is generic, so this identifies a definite admission defect, not proof that no other defect exists.

User 03:14:35 UTC explicitly transferred only accepts in ReadingParserPolicy.java and admitted_parser in windows_records_owner.cpp, plus six corresponding test/config/document paths, and approved branch commit/push and one new 120-minute five-job run without retry. Only the exact current 3.42 alternate spelling is added in each function. Original 3.41 rules, persisted records, SDK8357 and selectors are unchanged. Admission reconstructs the two expected one-line additions from base bytes, rejecting all other product changes; canonical union is25 and this branch14.

Android builds compile actual production policy with the unmodified original20 Java cases plus15 supplemental current-version positive/negative cases. Windows has independent precise source review and real return positive verification; no new Windows negative execution is claimed. The historical owner-probe parser rejection cases remain unchanged and are not relabeled as this SDK3.42 run. Complete F04 remains pending until real graph and final clause review.

## Round 4 authenticated two-host result and round 5 six-host graph
Run41268741338, source f003576d2acfbc2bcb9eaf8c8dcc06e02f9fd593, attempt1: all five jobs passed. Actual job durations were295/234/277/57/18 seconds (881 total runner seconds), not120 actual minutes. Android's actual policy original20 plus15 new cases passed. Real progress, bookmarks and notes traversed Windows→Android→Windows; the original retained authentication also passed. Authentication artifact13068433036 is572949 bytes, SHA2561a3cf5c556fa308fe14fdf8e1e31f1de21302f69530e2db2b399ba422b095485. Complete F04 remains pending.

User03:37:27 UTC approved total10 existing files, one Apple function transfer, specified branch commit/push, and one15-job230 runner-minute attempt, no retry. The only Apple production delta adds exreader-sdk-3.42.0 for actual3.42.0 in HostReadingWorker.acceptsParser; prior rules and stored wire are preserved. Canonical exact union26 includes exactly three production one-line deltas; all SDK and old tests remain frozen.

The new case f04/six-host uses a strongly connected directed graph: Windows→Android; Android→GTK/macOS/iPhone/iPad; Android and each of those four peers→fresh Windows receivers. Each peer consumes its exact predecessor's uploaded state, not a synthesized wire. There is no30-pair or six-author requirement. Five necessary platform builds at the same controller/run/source HEAD feed actual host execution; the two Apple SDK packages are shared by three independently built real UI binaries. iPhone/iPad use fresh erased simulators; this is not a claim of physical device verification or cloned-device deletion.

Caps: Windows seed20, Android25, GTK25, macOS SDK15, simulator SDK15, macOS UI15, iPhone UI20, iPad UI20, five Windows returns10 each, retained15, audit10 =230. Old run40678657371 at a different tree/same SDK provides GTK11:03, Apple SDK6:19/4:08, macOS UI4:45 and iPhone UI10:57 timing context. iPad has no prior measured duration, so its estimate is lower confidence. This is a cap, not a duration promise.

Original121/18, native HTTPS/raw counters and independent retained negative checks remain unchanged. Old four-ZIP aggregate is still not-run and not relabeled passed. Graph authentication and final F04 clause review remain necessary; no flags or total acceptance count are promoted by preparation.

## Round 5 environment failure and round 6 isolated Python
Run41270747157/source3e8ed8ccde4536a01cc6b57c3a00bfb7561c9b39: Windows seed, Android peer, GTK peer, both actual Windows returns and retained checks passed. The two Apple SDK jobs failed before compilation because system Python refused pip installation (externally-managed-environment). The three Apple UI jobs and their returns did not execute. Final audit correctly refused the missing macos_peer producer; this is a consequence, not a separate product failure. Nine non-skipped jobs totaled1435 seconds (23m55), not230 actual minutes.

User04:10:27 UTC approved only this document, contract.json and helper workflow, corresponding branch commit/push, plus one fresh15-job230-cap attempt without retry. All five macOS jobs now select Python3.12, create a RUNNER_TEMP-local virtual environment, expose only its bin via GITHUB_PATH, and install Python packages there. No break-system-packages/system override. Python/pip paths and version, Ruby, CMake and selected Xcode are recorded; the original Ruby gem fallback and native build recipes remain unchanged. Products, SDK, UI drivers and all assertions are unchanged. Every required target is rebuilt at the new common HEAD; no historical successful package substitutes for a current producer. F04 remains pending.

### Fixed original artifact inventory for failed round 5
API metadata checked after terminal failure; originals are not locally downloaded or parsed. Producer run41270747157 attempt1 source3e8ed8ccde4536a01cc6b57c3a00bfb7561c9b39 tree3ad079fdd63a3d23d2ae76272d697657eeccdde5.

|ID|Name|Bytes|SHA256|
|---|---|---:|---|
|13070080785|f04-diagnostic-audit-41270747157-1|332|4c09b1c7269f6d839eceaf47564d07e7f3b4f79f418ca95bd38ee108d69150bb|
|13069986075|f04-gtk-peer-41270747157-1|5165538|e045b33f451dd29d0183f25da25b45de9cc458f788b9edd7fd64d27ee5deeb7d|
|13069936228|f04-diagnostic-gtk-41270747157-1|5320|97a7c7ed05f937778bd00ea2d75476c0e61e46ccac5860f1e93589d13ce1583f|
|13069861545|f04-windows-return-gtk-41270747157-1|4205343|a65aa23061a16b8a4cee4af58299217137d94078f1b547332aaeec31af8faad9|
|13069800780|f04-android-peer-41270747157-1|20040511|d23e58ff5efcbbc243c8a62d44e2d0dd447e1d61a9e0b1393a795d6d06ee4de4|
|13069705252|f04-build-windows-41270747157-1|53053429|78c9c139bf8e48ae886c3f652f0b0835239c43d8c85660ecedf5e8bca60b5a48|
|13069642428|f04-diagnostic-windows_return_gtk-41270747157-1|4540|688c48324a8664b3bb7051c4575cf28515cde48b305d6286c8861bdd7fd0f166|
|13069436017|f04-diagnostic-windows_seed-41270747157-1|2554|1751ba85c864a742bfe28e97cd254772391ea61868e8d26e109e50a8eeffe670|
|13069371606|f04-build-android-41270747157-1|39938581|6e5c76445969b35886eabfbf25c5b6c2e178d600896207ad944f309fad8516f5|
|13069237533|f04-windows-seed-41270747157-1|4201209|f0ccfd59668e66afdfaa248f5bad2b2df5be7a61e37459d64f9d0257b1fbca00|
|13069203591|f04-windows-return-android-41270747157-1|4203667|584bdd1395075c611410ad17c81e16f4e7f2bc04d4590553de63159830260f05|
|13069183576|f04-diagnostic-android_peer-41270747157-1|311|a1933c82388819023eccac2c4353b479580d8bccf75fd180243d53fbf444cbe8|
|13069133801|f04-diagnostic-windows_return_android-41270747157-1|3833|68f50ff7e162b81e8727344e948f0dc751b6b85736c775a454e105682ba90aaf|
|13069089575|f04-build-gtk-41270747157-1|42095812|c39873a0fb5e8b410b5dbdb6ffe3251f8377c65ebe0edf2eecd2a04cabc09f6f|
|13068943721|f04-retained-linux-41270747157-1|14734881|746d3a19011893dc28e12a90c1ab2b19e19512426e83a1e99f6bd0055aaec17c|
|13068784496|f04-diagnostic-retained_linux-41270747157-1|7526|319cffcde8ac4e07771b8edf292aea3bb33783a57e352f074ce852b7d4a9e68f|

## 2026-11-01 04:48Z — narrow macOS state diagnostic, approved 15 runner-min

Six-host round 6 run [41272334508](https://github.com/NoGod3524/EXReader/actions/runs/41272334508), source `2cdad2057d4877b4712af8155da72fb92b50e411`, ended failure. Eight jobs passed: two Apple SDK builds, Windows seed, Android peer, GTK peer, Windows returns from Android/GTK, and original retained suite. Three Apple UI jobs failed; their three Windows returns skipped; graph audit rejected missing qualified macOS producer. Actual non-skipped job elapsed sum 3643 seconds, not the 230-minute ceiling.

- macOS job 124749643030: driver line 91 precise-success status wait timed out after real UI build/launch. The pre-close reading.status was not captured; resolver defect versus state observation is not established.
- iPhone 124749643051 and iPad 124749643098: reading.jump.3 existed below the visible reading.list bounds and failed the hittable requirement. No jump was performed at that point. This diagnostic batch does **not** change the iOS scrolling implementation.

This new case `f04/macos-state-diagnostic` has one macOS job, 15 minutes, no retries. It consumes exact old SDK/Android artifacts with API/run/job/source/size/SHA checks and preserves the original ZIP containers. Real UI and test code are compiled at the new controller HEAD; EXRSourceSHA remains that actual HEAD. A complete tree diff against the old producer allows only six approved non-production paths, demonstrating identical product/SDK/old-generator bytes, not identical historical UI binaries. The SDK and Android producer identities remain separately recorded. No formal graph/phase acceptance consumes this diagnostic; F04 remains false.

The test adds only whitelisted status/location/busy/target observation before/after jump and close plus deferred failure observation. Original precise-success assertions are unchanged. Native UI logs are sanitized with exact fixture secret removal before ordinary-log output or artifact retention; profiles, SQLite databases, credentials and private keys are excluded. Five F04-owned files plus the canonical entry owned by F03 form the exact six-file scope. No product/SDK/old assertion changes.

### Round 6 original artifact API inventory

| ID | Name | Bytes | SHA256 |
|---|---|---:|---|
| 13071095139 | f04-diagnostic-iphone-41272334508-1 | 954 | 7470c5962921743699b21e3c709cb1b31e9937a8266e0065583fa1cd05f660e7 |
| 13070795531 | f04-diagnostic-audit-41272334508-1 | 331 | e7056a283fcda8dd6a93631aea630034f25556ae59c552d94d7a6e84a91eed53 |
| 13070316646 | f04-diagnostic-windows_return_android-41272334508-1 | 3820 | 0ee447a385d3a3707239e13d5b701ee0f2e4abd1e2547f8a05c8965c86b54720 |
| 13070316514 | f04-android-peer-41272334508-1 | 20040466 | d734fa0187678d64c4e731108f44d7b1f6b98d2fcb12b3bb49685f86e72c8396 |
| 13070227157 | f04-diagnostic-android_peer-41272334508-1 | 313 | d4b60ce076414248e9e9a89a97c5172206308c4ada04c6228b144bcd4ffed165 |
| 13070191404 | f04-build-macos-41272334508-1 | 22475654 | 1643061900c24deac54d8c2ad59982323a8f8470baa6ecbf691d5dd7f99d32b2 |
| 13070097200 | f04-build-windows-41272334508-1 | 53053382 | 460a5da3d55c98999234bc0f57197e3614d05b2b6ec2ff0c902d93e354d8bafa |
| 13070082978 | f04-windows-return-android-41272334508-1 | 4203634 | 91e22e2fabc81bbf8e4c0a12c462ffa6f95f4b38f77d4616069089ae0e78427b |
| 13070052206 | f04-windows-seed-41272334508-1 | 4201214 | 9f1b62160fc735a00c9fefe45443995f694bd5838b68fe8f259e1273971f3389 |
| 13069932754 | f04-diagnostic-windows_seed-41272334508-1 | 2555 | 69c7255f3d06d8ffee68967191aab605236d680308773e0be416a7df95e6a7fd |
| 13069884438 | f04-diagnostic-windows_return_gtk-41272334508-1 | 4560 | c8500a5d6283cfe069c3b2b73e3a0f0fc2671f7a25680c39e857f17bd4808a53 |
| 13069878934 | f04-diagnostic-ipad-41272334508-1 | 950 | ebdd512821dd5c123f4a3c6b9b31c6b8f64c0e74f836be94f6ea3bf388657fc5 |
| 13069704952 | f04-windows-return-gtk-41272334508-1 | 4205390 | 948c8fc0acae03589256813bb4a1a50071f22b57f30efd222ddf08476827a6b8 |
| 13069704728 | f04-build-gtk-41272334508-1 | 42095816 | ed8aaea4f3261b13c5e476900bc42fb6acee07f2de3e65ed3e646ef7dbcbd8f8 |
| 13069558932 | f04-gtk-peer-41272334508-1 | 5165563 | 67c28d05269868dbd61653a48a5b7f689f636b4532befa403d551426f2885589 |
| 13069453009 | f04-build-iphonesimulator-41272334508-1 | 22468302 | 0a5eb08040efe6566fe79166a7f9b8ed4cdb12fc153652a32d7d25f6c00e9383 |
| 13069449125 | f04-diagnostic-macos-41272334508-1 | 845 | 0fb822800f51c4a9ef8fd3f79ac04eedd28b2bd10406d4f3d3e3537195c9bcef |
| 13069248597 | f04-retained-linux-41272334508-1 | 14734895 | bab25da5869c830b96adf6cbb2c6ed04e7342e9e566826590a48123eb6d90cc8 |
| 13069214894 | f04-diagnostic-gtk-41272334508-1 | 5323 | a6a1ba43cab9e866526fd104368a965a8eae23f89744f4e62d7b6dd01697673c |
| 13069099133 | f04-diagnostic-retained_linux-41272334508-1 | 7537 | c893c7b716c1f607853567fb42b23317551a58e19a0bc3eafa331780437df5f5 |
| 13069034697 | f04-build-android-41272334508-1 | 39938566 | bf79f1dfe54c352b172749febc97e4d7060e255aa88d79b1084e8260f050d7c6 |

## 2026-11-01 05:10Z — real list visibility and platform input diagnostic

The single macOS diagnostic [41274878352](https://github.com/NoGod3524/EXReader/actions/runs/41274878352), actual UI/controller `aec50c89a500ed5a1ae7aa1767435877c5dcf741`, failed the unchanged exact-success assertion. Fixed source equivalence and historical input authentication passed. Progress jump 0 and position checkpoint completed; bookmark jump 2 received an XCTest synthesized tap but before/after/close status stayed “本书的书签与标注”, location stayed chapter 2/page 7, with no recorded resolver error. This is not proof of an SDK failure. Artifact 13070923378: 42342626 bytes, SHA256 e147bf9f185c3141e3b01b4434c7124ca93c30ea5da48fa7da2f1b63a7ad29c7.

The approved next case `f04/apple-visible-diagnostic` has three independent UI jobs: macOS 15, iPhone Simulator 20, iPad Simulator 20 runner-min (55 ceiling total), one run, no retries. Same six non-production paths only. SDK and Android input producer remains fixed `2cdad2057d4877b4712af8155da72fb92b50e411`; actual UI builds record the new controller SHA. SDK is not rebuilt, other hosts/returns are not run, and this cannot grant full same-HEAD graph acceptance.

Only actual row actions reading.jump.N and reading.edit.N use the new visibility preparation. Require exactly one real reading.list and descendant Button, positive frames, target entirely in list viewport, enabled and hittable; otherwise ordinary bounded scroll in the actual container, requery every time, fail if target absent or no movement. Once visible, macOS click()/iOS tap() exactly once. Non-list close/save controls retain their prior route. No forced coordinates, repeated action, weakened success condition, product hook or new model behavior. iOS out-of-viewport was directly observed; macOS event delivery remains a hypothesis under test. Independent platform outputs keep fixed original ZIPs and sanitized state/logs, with F04_accepted=false.

## 2026-11-01 startup permission isolation (authorized 08:42:06 UTC)

- Previous run **41289052139 A1**, source `d3edf83e395190d6fc2f55c4f14fb99cbe702d86`, Mac job **124796294754**, failed after **246.788 s**. Only Mac ran; other 27 jobs skipped. Original position/incoming-bookmark/incoming-note passed; edits and upload were not reached.
- The exact Python Local Network **Don't Allow** native click succeeded at test t92.97. XCTest internally opened/activated UserNotificationCenter to deliver this authorized click; this was not an extra explicit system-app activation. Dialog dismissal was observed at t93.68. Save-progress then passed original readiness and emitted **Tap / Synthesize event** at t93.82, but the original 150-second saved-status assertion failed. Final reading.status and reader.status remained “本书的书签与标注”, reader busy was absent, and location remained chapter 2/page 7. This is not proof that Tap is unsupported or that the save handler executed.
- Artifact **13076039546**, **42,353,043 bytes**, SHA256 `5eba597868d3b1bf360bb99e9ae7a6b2384813249a7bf4c3cc5744cd9d0c10a6`. Actual UI bytes **9,653,680**, SHA256 `c2e0cf07e2698d019969a05da7fa7674138bf4b0ccbfc85c64e489c165384a92`. API updated_at **09:35:39Z** versus runner upload **08:35:35Z** are preserved separately; the API has an observed +1h discrepancy.
- Read-only production review found a concrete mechanism hypothesis: HostRootView resign-active/nonactive scene callbacks call closeAccountSession(), which calls readingRecords.bind(nil). This clears bookID/rows and makes complete=false while retaining status. performReading() can then silently return on its bookID guard. Internal binding was not observed in the failed run, so this remains a potential production lifecycle defect, not a confirmed root cause; production is unchanged.
- User **Sentinel_1a30811476448191a7a4241f18a3a338**, **08:42:06 UTC**, authorized only the same three existing paths, preservation of historical metadata, and one new **Mac 15 runner-min** run. No automatic retry; no six-host/230-minute execution. F12 independently reviewed the design; F03 alone may compose canonical source and trigger after actual-diff review.
- New Mac diagnostic preparation is **after app.launch and before account.choose**, with at most **10 seconds** observing the exact current prompt. That window is inside the original **150-second** library-readiness deadline, never restarted. No prompt is not failure. A matching prompt is denied once using the existing fresh unique semantic button; after actual disappearance, only an already-running app may be brought foreground once, then original library readiness is checked.
- After startup, any late/reappearing prompt is **environment-blocked**; no permission click, reopen, write replay, or permission fallback is allowed. No product/SDK change. **Tap is deliberately unchanged** to isolate preparation timing; the proven list helper and iOS remain unchanged. Save-progress, both edits, note-save, close, back and upload retain all original assertions.
- Bounded diagnostics add public UI proxies (actual record kind/jump/edit identifiers, next/pending/status/location, app state) before/after fixed taps, before editor input and at teardown. They do not reveal internal bookID, input/editor text or raw app trees, and do not become new success criteria.
- Historical failed rounds and both successful iOS artifacts remain intact. This is diagnostic-only, **F04_accepted=false**, formal acceptance **96/108**.

## 2026-11-01 diagnostic snapshot isolation (authorized 08:58:28 UTC)

- Run **41290204917 A1**, source `e67441671415766306473eccea9113ebe943e836`, Mac job **124799687522**, ended failure after **194.062 s**; other 27 jobs skipped. Startup semantic Python denial succeeded and did not recur. Original save-progress, both edits/note saves, close, and unchanged-location assertions passed. The **edited-records** checkpoint attachments were recorded at t183.99/t184.02. Final sync/upload was not reached.
- First failure is the added diagnostic at Swift **line 409: item.isEnabled**, not an original success assertion. reader.back Tap synthesized at t187.10 and returned to the library. Diagnostic exists checks at t187.44/.45 were followed by a now-missing element query at t187.47, two XCTest retries, then failure. Teardown shows library.title present and reader controls absent. This is a test-evidence race introduced by our instrumentation; both implementation and review missed it.
- Artifact **13077591165**, **42,357,495 bytes**, SHA256 `340484399a902e80bff80337e9445b01804515c59c5901f33df4d0f898430813`. Actual UI **9,653,680 bytes**, SHA256 `322bd6d57ec92703e36b99ae839405ba907432194dc83956f907b8c034102305`. API updated_at **09:56:27Z** and runner upload **08:56:20Z** remain separate.
- User **Sentinel_0116319a849c8191a5f639eaec55b66b**, **08:58:28 UTC**, approved only the same three paths, preservation of all history, and **one Mac 15 runner-min** verification, no retry. The startup permission choice remains exact Python Don't Allow once on this ephemeral runner; no six-host/230-minute execution.
- F12 independently approved a minimal diagnostic-only fix: delete normal before/after-fixed-tap and before-editor-input instrumentation. Both remaining diagnostic functions take at most one optional app root snapshot and inspect returned nodes in memory. Obstruction evidence alone may take one optional current UserNotificationCenter root snapshot; no extra system reads are added to jump evidence.
- Missing, duplicated, truncated or unavailable snapshot nodes are evidence, not failure. Diagnostic live enabled/hittable/frame reads and live window/sheet/list/dialog traversal are removed. Hittability is omitted rather than fabricated from geometry. Existing true readiness checks, fresh permission matching, native actions, startup deadline, row helper, iOS and all final assertions remain unchanged.
- No local tests, project execution or ZIP parsing. F12 actual-diff review precedes F03's unique canonical composition/trigger. Historical iOS successes and all failure artifacts remain intact; **F04_accepted=false**, formal acceptance **96/108**.

## 2026-11-01 Mac diagnostic passed; same-source six-host recovery authorized

- **41291277832 A1** succeeded, source `2fec8c7d3ef4a12ddba335c96da265843c7dcfe7`, Mac job **124802873944**, **80.263 s**, one test/zero failures. All other 27 jobs skipped. Original checkpoints **position**, **incoming-bookmark**, **incoming-note**, **edited-records**, **uploaded** passed; native UI/package exited zero and cleanup_errors was empty. Startup denied the exact Python prompt once; all original save/edit/location/sync assertions were preserved.
- Artifact **13077298124**, **42,354,209 bytes**, SHA256 `d900a58f9a5ea68e0cbcaa77274cb927d3bd263324522dc66228d2e120aba7fd`. Actual UI **9,653,680 bytes**, SHA256 `efd970c32ef17e4b06590de72641ede8f53fdd8dbfaed62c5dc499bfddbbe6eb`. API updated **09:05:12Z**, runner upload **09:05:07Z** now align; older clock discrepancies remain recorded. Receipt remains **diagnostic_only=true, F04_accepted=false**, not a historical substitute for a new full graph.
- Read-only integration review found full-suite Mac did not set the diagnostic placeholder, so its startup permission preparation would be disabled. The approved fix introduces a distinct **__MAC_PERMISSION_PREP__** switch instead of falsely enabling diagnostic mode or historical inputs.
- User **Sentinel_96e826274dec81918d2f37bb32827617**, **09:09:04 UTC**, explicitly authorized four existing files (Swift, run.py, contract.json, this document), submission/push, **one 15-job / 230 runner-min** six-host round, and exact Python Don't Allow once on that round's temporary Mac. No automatic retry. Product/SDK/old tests/assertions unchanged; all historical records preserved.
- Controller sets the new substitution explicitly to **0** for every Apple generator except **target=macos AND generic=True AND F04_SCOPE=f04/six-host**, where it is **1**. Only the four existing Mac permission behavior guards accept diagnostic OR permission preparation; both diagnostic-output guards stay diagnostic-only. iOS does not gain permission behavior.
- The exact reviewed startup behavior is reused: at most 10-second observation within original 150-second library-ready deadline before account/credentials/book/record actions, one exact semantic denial, actual dismissal then still-running own-app foreground restoration. Late/reappearing prompts stop without permission action, reopen or write replay.
- Existing workflows need no edits. Budget: Windows seed20; Android25; GTK25; macOS SDK15; simulator SDK15; Mac peer15; iPhone20; iPad20; five Windows returns10 each; original retained Linux15; graph/retained audit10 = **230 runner-min**. F03 alone composes canonical and triggers the existing **F04-SIX-230-ONE-RUN** entry after F12 actual-diff review.
- Five builds and eleven phase artifacts must come from the new same source/run/attempt through exact job outputs. Fixed historical diagnostic SDK/Android inputs and earlier iOS successes are not reused as formal graph nodes. Windows native progress/bookmark/note FOUND, immutable retained revisions, authenticated transport, original graph strong connectivity, exact predecessors, program/build/SDK/archive identities and retained original tests are all unchanged.
- Full F04 acceptance remains false in the original preparation audit; formal **96/108** is not promoted by this authorization. All runtime testing and archive processing remain Actions-only.


## 2026-11-01 09:40 UTC — iPhone bounded record search diagnostic

Full six-host run 41292070407 A1, source 91b2ee1ff98173ccaa9de52b4071821905bd1c07, ended failure: 12 planned jobs passed, iPhone peer and audit failed, iPhone Windows-return skipped. Retained tests passed but audit stopped at required producer iphone_peer before graph/retained authentication. Formal count remains 96/108; F04 is not accepted.

The iPhone original row search failed at F04_ANDROID_BOOKMARK after scanning indices without scrolling. Its visible row2 is F04_WINDOWS_BOOKMARK, not the target. Row3 is F04_ANDROID_NOTE below the viewport; row4 is absent from the AX tree. Android output contains the exact target bookmark; iPhone downloaded the pinned Android/SDK digests, but absence from its current virtualized tree does not prove retained data loss. iPhone diagnostic artifact 13078002995: 950 bytes, sha256 0d0b130cf042fae6c39dc9e12358f47cd3af65c0dd99a2d71f90ec01de905659.

User authorization 09:40:23 UTC, Sentinel_121e292081c08191a1ffc1d0f0ab0cfc: six existing paths, one iPhone20 runner-minute diagnostic, no automatic retry. F04 prepares five paths; F03 alone writes the canonical workflow sixth path and triggers after independent actual-diff review. Case f04/iphone-record-diagnostic; marker [F04-IPHONE-DIAG-20-ONE-RUN].

Only the explicit iPhone diagnostic row search uses at most21 actual list snapshots and20 native scrolls. Original kind equality/body substring/index order stay intact. Match first, then bounded traversal toward start and one reversal; start requires real positive row0 intersecting the list viewport. No movement only suggests direction change, not absence or early failure. Exhaustion reports preparation-incomplete. Existing real action unique/positive/fullcontain/enabled/hittable and exact position/edit/upload assertions remain unchanged. All non-iPhone behavior is unchanged.

Pinned successful producer source91b2ee1ff98173ccaa9de52b4071821905bd1c07/run41292070407/A1: simulator SDK job124805173497/artifact13076809707/22468259 bytes/sha256 fec0a4ed78566c20b48fdd24f46704ea29b868271d541f48139e127bbcdbca0e; Android job124806356213/artifact13078190982/20040487 bytes/sha256 3c83369dd780d065fb04b47ff8ab6a74d94355e1bde9ee7b63bf8eefa36337e1. New controller/UI identity is separate; not same-HEAD graph acceptance. No Mac permission processing, other-platform jobs, SDK rebuild or graph run. Product/SDK/old assertions/history remain unchanged. No local project execution or archive processing.


## 2026-11-01 09:57 UTC — restore full same-source graph after iPhone diagnostic

Single iPhone run41294552194 A1/controller0fb14eadc46d7392b5efaabe65ab9cf105008b36/job124812545025 succeeded: 135.370 seconds, one test, zero failures, all five checkpoints and cleanup_errors=[]; other29 jobs skipped. Native search swipe at t64.83 exposed reading.jump.4, incoming-bookmark passed t72.90; search swipe t94.08 exposed reading.edit.4. Incoming-note t85.42, edited-records t115.07 and uploaded t133.76 passed original assertions. This confirms the previously unscrolled target was row4 in this iPhone input. Artifact13078148508:42339480 bytes, sha2564d7104bc57af5ba59675879fc26eecb26b954cf6926112d95a91b4fa9165726c. Actual UI9653296 bytes, sha25668c06e80a9173b681f79789e7ee3cdd0ab1f76325a5fe30d5ae036197d986ca0. Historical producer remains91b2ee1ff98173ccaa9de52b4071821905bd1c07/run41292070407/A1, separate from diagnostic controller. Diagnostic success does not establish whole-graph acceptance; formal96/108 unchanged.

User09:57:06 UTC/Sentinel_ae42ab34269c8191b9b1111af0ac5d30 approved exactly three existing paths (run.py, contract.json, this document), preserving history, and one full fifteen-job230 runner-minute round without automatic retry. Only code delta is the existing iphone_record_prep scope condition accepting f04/six-host as well as its diagnostic scope, still requiring targetiphone+generic. Swift and both workflows remain byte-identical; no product/SDK/original assertion edits.

All five builds and eleven phase outputs must be freshly produced with the new source/run/attempt. Prior twelve green jobs and isolated diagnostic output cannot be spliced into this graph. Original Windows five return paths, retained tests and authentication remain unchanged. Existing Mac permission preparation remains a separate switch: this round only, exact Python Local Network semantic Don't Allow once during initial10-second observation within original150-second startup deadline, before credentials/book; later prompts block, no replay or Allow/settings/TCC fallback. Historical input loader and diagnostic mode remain diagnostic-only. F12 reviews actual three-file diff; F03 alone composes and triggers existing F04-SIX-230-ONE-RUN once. No local project execution or ZIP processing.


## 2026-11-01 11:23 UTC ? fixed seventeen-artifact inventory only

Full run41295456077 A1/sourcebdb2b93204e1268f7ae8336d4fd53f7e396f3c18 ended failure with14 successful jobs and only audit124820921786 failing. All six hosts and five Windows returns passed original interactions. Audit stopped at authenticated_builds line334: sdk/examples/android/.gitignore missing from archive. Both Apple build logs installed this file; package_build copies SDK/raw trees, while upload-artifact v4 default include-hidden-files=false omitted dot files. Original SDK manifest includes every installed file. This Git ignore-rule file is not executable runtime code, but its promised bytes cannot be waived or reconstructed into an alleged original archive. Original failure and acceptance rules remain intact; formal96/108 unchanged.

User11:23:26 UTC/Sentinel_ce75cdbea15c8191b940c022deb13357 approved five existing paths and one Ubuntu10 runner-minute inventory job, no retry. Four F04 preparation paths are helper workflow, audit.py, contract.json and this document; F03 exclusively owns the canonical workflow fifth path and trigger. Source/Git work uses lap25002 Desktop Commander -> normal saved-login instabox0.8.52 -> existing VM m_agqxv2s72g5vwdtsifu5cnmml4. No direct GitHub connector, local project execution or local archive processing.

Independent case f04/artifact-inventory / marker [F04-INVENTORY-10-ONE-RUN] authenticates exactly17 original archives (5build,11phase,1retained) using pinned producer source/run/A1, exact job IDs/names and original artifact IDs/bytes/SHA256. ZIP work is Actions-only, memory reads without extraction or execution. Duplicate/unsafe/special/encrypted/oversize entries stop inspection of that archive, not remaining archive reports. Inventory records member names/sizes/hashes, manifest expected/missing/mismatch, unexpected entries and critical identity findings; missing original bytes remain missing. Public metadata is explicitly expected; uncommitted package contents separately reported, never silently accepted. Original audit functions/assertions/manifest/ZIP are untouched. Completion is not certification: diagnostic_only=true/F04_accepted=false/original run failure retained. No SDK rebuild, permission interaction, product execution, alternate full graph or retry.


## 2026-11-01 11:40 UTC ? original SDK hidden upload preservation

Inventory run41302619548 A1/source0d36ff4d9bcaa4243679f040e959fde588bb9393/job124836527529 completed successfully in48 job-seconds. All17 original archives authenticated and inventory_complete=true, has_findings=true, F04_accepted=false. Only promised missing members: sdk/examples/android/.gitignore in Mac13078834935 and simulator13079078632 SDK archives. Hash mismatch, critical identity, missing-critical and inspection errors were empty, including11phase predecessor/build-receipt and retained program references. Windows36 and GTK31 extra package members were explicitly uncommitted package inventory, not an exhaustive package-manifest assertion. Platform-optional phase uploads were not classified as critical missing files. Inventory artifact13082067635:164030 bytes, SHA25624d5a2108237d63fa471ff2b005655ee03a425db493a0fb9ba271720804e9117. Original full-run audit failure and archives remain untouched; formal96/108 unchanged.

User11:40:55 UTC/Sentinel_7683d94faac88191b45211c7f6e008d1 approved exactly four existing paths (two workflows, contract.json, this document), preserving prior evidence, plus one15-job230 runner-minute full same-source run, no automatic retry. F04 prepares helper/contract/document; F03 exclusively handles the fourth canonical workflow route and sole trigger after F12 independent actual review.

Only the two Apple SDK uploads enable include-hidden-files:true, with a preceding per-root safety check: all hidden relative paths must be exactly sdk/examples/android/.gitignore, an ordinary non-symlink file. Upload root and all members must not be symlinks; no external link target is read. Any additional hidden path or missing known path stops upload. No content is logged, no whole workspace is uploaded, and other upload blocks remain unchanged. This confines disclosure of hidden files; it does not change product success conditions or invent a new full-manifest gate. run.py, Swift, audit functions/assertions, SDK and production code remain byte-identical. Old archives are not rebuilt or repaired in place.

The formal rerun uses entirely new five builds/elevenphase outputs under one new source/run/attempt, not prior greens spliced together. Existing precise Mac startup permission scope is unchanged. Original graph/retained semantic audit still must run and may reveal later findings; the successful inventory alone is not acceptance. All source/Git operations stay on lap25002 DC -> normal instabox0.8.52 saved login -> existing VM; all test/ZIP processing stays in Actions.


## 2026-11-01 Android ready-node isolated diagnostic (authorized 12:06:30 UTC)

- Prior full round 41303203935 A1 / source 3e78df2ed7aac1d45f75338d7c459f0280e76c57: four successful jobs, Android and audit failed, nine planned jobs skipped. Both Apple SDK uploads passed the precise hidden-file guard and included sdk/examples/android/.gitignore; the original full audit did not run past Android producer failure.
- Android job 124839406098 failed the unchanged native-forward assertion at helper line 247: actual reader_view was disabled. The original settled-frame predicate alone does not imply interaction readiness. Old status/frame may remain while a new jump task is pending; logs do not establish permanent product busy or exactly which task caused it.
- Independent F12 review: capture old and initial before from the same fresh enabled reader node satisfying the original settled predicate, then issue one native forward. False action remains failure; no catch/retry, token-increment or stability-count criterion. Preserve three actual movements, later location, save/new revision and subsequent bookmark/annotation/upload assertions.
- Exact approval: Sentinel_737c0bb7b13481918b0d4a5c20055d9d, 12:06:30 UTC, seven existing paths, one Ubuntu 22.04 Android job capped at 25 runner-min; no automatic retry. New Android SDK/host/instrumentation built using the unchanged existing recipe; no fabricated test-only APK toolchain and no reuse of old test APK.
- Historical Windows seed only: source 3e78df2, run 41303203935 A1, successful job 124838252020, artifact 13082079243 (4201198 bytes), SHA-256 92046b41532f0c78ab1fcfa26da7520d8575ebc52b769cb1c049c6423e870463. Authenticate API identity, original archive digest, safe members and original state identity; never rewrite producer fields. Separate current controller/new Android build identity from this input.
- Dedicated f04/android-ready-diagnostic route; all other jobs skipped. Original admission assertions remain, with only this explicit case added. No original audit/production/SDK-source changes; no claim of same-run full graph or acceptance. F04 remains false and formal count remains 96/108. Old failures and archives remain intact.
- This preparation commit does not trigger Actions. F12 reviews actual diff, then F03 alone composes and triggers one authorized run.
