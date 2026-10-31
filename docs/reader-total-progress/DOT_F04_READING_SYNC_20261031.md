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
