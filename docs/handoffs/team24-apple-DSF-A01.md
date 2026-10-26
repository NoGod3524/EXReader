# DSF-A01 独立 owner 收尾：链接表解码修复后三目标真实 UI 结果

工作树：`C:/Users/Oscar/exreader-team24-20261026/dsf-apple`。分支：`codex/dsf-apple-ui-close`。起点：`8ebef083aa17272c5019c8f778c03ace78e9ea96`。本轮唯一受测源码：`d9ca5805952f8069ecbdb7a724af43662d9b0a6e`。

授权范围：只做 root 已批准的唯一共享工具修复（`9979001fba4df9fceaed3ffc89d6d9e0bcc16337` 中的 `tools/check_apple_product.py`，仅一处解码变更）、本队 `run_ui.py` 同样的显式解码、新入口 guard 与工作流调用；不碰 root 其他 canonical 工具、不碰 `production --wave3`。全部构建/测试/语法/夹具/工件解析只在 GitHub Actions 内执行，本地只做源码/Git/文档。未创建子代理，未使用 cpuse。

## 一次完整三目标验收（唯一一轮）

| 项 | 值 |
| --- | --- |
| source | `d9ca5805952f8069ecbdb7a724af43662d9b0a6e` |
| run | [40350153254](https://github.com/NoGod3524/EXReader/actions/runs/40350153254) |
| attempt | 1 |
| 触发 | push `codex/dsf-apple-ui-close`（无同源码并行轮次；启动前查过无在跑） |
| 结论 | failure（UI 已真实执行，未达 5/13/21 全通过） |

| job | id | 结论 |
| --- | --- | --- |
| Team24 Apple installed macos | 121667676539 | success |
| Team24 Apple installed iphonesimulator | 121667676724 | success |
| Team24 Apple native macos | 121669981519 | failure |
| Team24 Apple native iphone | 121669981593 | failure |
| Team24 Apple native ipad | 121669981501 | failure |
| Team24 Apple original ZIP authentication | 121695937128 | failure（同 run 认证 job，因原生未接受而保持 failure） |

guard 在 sdk job 内通过，并按新准入证明共享工具身份：`root_commit=9979001f…`（从 `codex/team24-composition` 读取对象）、`root_blob=head_blob=ed7f62597e01d4e045f679369805d27abc20b7bc`、`seed_blob=c08a4b59…`、原 `guard.py` blob `9fad8c90…` 逐字未变、31 条负例控制全部拒绝。

## 每 phase 的真实业务与结果

三个 phase 都真实启动 UI（`xcodebuild test` 执行了用例，不是编译/打包冒充），三个平台并列结果一致：

| phase | 预算 | 实际业务 | macOS | iPhone | iPad |
| --- | --- | --- | --- | --- | --- |
| `wave3` | 5 | 阅读详情（More→「文件、字体与同步详情」）里的五个原生模块流程 | 2 过 3 败 | 2 过 3 败 | 2 过 3 败 |
| `base` | 13 | 原 `EXReaderHostUITests` 13 例（导入去重与错误、分页排版、选择复制标注、生命周期持久、取消恢复、固定版 PDF 锚点、无障碍大字体、忙碌守卫、书籍所有权、Unicode 跨书隔离、视口失效、非默认字体与精确进度、章节笔记） | 13/13 通过（accepted） | 13/13 | 13/13 |
| `control` | 21 | 原 reading 7 + navigation 6 + search 4 + page_theme 4，且启用 `EXR_APPLE_READING_REVIEW` 的额外阅读夹具按钮 | 18 过 3 败 | 18 过 3 败 | 18 过 3 败 |

预算一字未改，未缩小也未加宽（5/13/21）。base 阶段的 13 例在三目标全部通过，说明旧的导入/阅读/标注/大字体主链路在本源码上仍然成立。

`wave3` 通过：`testDirectoryPickerCancellationPreservesReader`、`testNativeAnnotationPreviewConfirmCancelAndDuplicate`（目录选择取消保留阅读、标注预览—取消—确认—重复导入确认）。
`wave3` 失败（三平台同）：`testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot`、`testNativeHistoryAfterFoundAndLargeRotationExit`、`testTypedNullAndConcurrentHeadsRequirePreviewConfirmation`。

`control` 失败（三平台同）：`testFindSelectAndProcessRestart`、`testExactly32HitsKeepFinalWindow`（原 search）、`testLiveSystemAppearance`（原 page_theme）。这三例的源文件哈希在 `result.json.unchanged_old_tests` 中记录并被认证 job 逐字节核对（`SearchUITests.swift` `423e5d98…`、`ThemeUITests.swift` `1bca59d2…` 等），即失败发生在未修改的原测试上，不是本队改写测试造成的。

## 首错（保留，不再开第二轮）

首错发生在第一个 phase 的 xcodebuild 结束处：macOS `2026-10-26T15:43:34Z` `wave3-native-ui failed: 65`；同一断言在 iPhone `15:59` 前后、iPad 同批同样出现。`run_ui.py` 对该失败只记录 `phase.failure` 并继续跑到 base/control，所以三阶段都完整执行、未被短路。

逐条 XCTest 断言文本位于工件内的 `evidence/wave3-native-ui.log`、`evidence/control-native-ui.log` 与对应 `.xcresult`；按规则工件只能在 Actions 内解析，本文件只引用 job 日志可见的用例级结论与失败尾部（macOS 尾部为最后一个失败用例的 accessibility tree）。“本机再跑一次”没有发生：授权的一轮已用完，未提新完整轮。

## 原 ZIP 与实际 executable 身份（Actions 解析）

认证 job 在 Actions 内下载原始 ZIP、逐个文件核对 `result.json.files` 的字节数与 SHA-256、并核对工件 digest，认证结论因原生失败而保持 failure（保留失败 job）：

| 平台 | Artifact ID | 原 ZIP 字节 | 原 ZIP SHA-256 | 到期 UTC |
| --- | --- | ---: | --- | --- |
| macOS | 12666310175 | 467513155 | `9d1f1ff7cba7c4f4c3a1b7a3e068a12e891aa99e2b4fae16a8ad7e2a493b7f10` | 2026-11-25 16:03:44 |
| iPhone Simulator | 12666891416 | 498552736 | `88e7a002ccce6681ffccfc2d97295e29f79b0efe7910a93512c7c9f952a06fea` | 2026-11-25 16:16:19 |
| iPad Simulator | 12667336303 | 551157105 | `3a39d13a6328c5c42b1029a531d7882ff6928f6d0a67f35a6e30c00c2ca6f845` | 2026-11-25 16:19:11 |

SDK 工件（同 run/attempt）：

| target | Artifact ID | 字节 | SHA-256 |
| --- | --- | ---: | --- |
| macos | 12662559736 | 22119231 | `bd6a9be6d9ce7dfad8efc0aa9c8d975181142bb49d30d76e8a071f5eba9bb7a1` |
| iphonesimulator | 12663252227 | 22122605 | `4777b4cd8f8b0be8e7d5f6c288fb95688fdce5aa45c389b0d065251eb3de1bf2` |

| 平台 | phase | 实际 executable 字节 | 实际 executable SHA-256 |
| --- | --- | ---: | --- |
| macOS | wave3 | 8324768 | `356fdcb28d62546b7a6240ab0fa1159ed28da2a6ce88c331144c61c812a5f7cd` |
| macOS | base | 8324736 | `a3691cc85d4a1e38c1a0a274e9b319d83fd010f35a7007076f4b8dcfd6fb297e` |
| macOS | control | 8339424 | `d802d774d15608994180929f5216863b4c32ef38d4fc89080925a0be9e2b54d1` |
| iPhone | wave3 | 8311872 | `c29158a90e86dbc9d800b3bf2de4600197e78417aaa120cd7a284d57e2a2e039` |
| iPhone | base | 8311840 | `e20413a95f84b4faaef1252b16f71359eca583c069e9e95e2a760e4124b8aaae` |
| iPhone | control | 8343040 | `c726d6532afb3e8d9e1e993ebf7e99bacb581abb179d90377a3fc4fb120e56c3` |
| iPad | wave3 | 8311824 | `8b041f0ffe5bb7fdaeb85e8b215c9f742d9b059fda59fa43cc729abc5e1fe2ff` |
| iPad | base | 8311808 | `c8b97c51bdfdc35cd6aa9748771aee1d0de5aaf1d698f61f12a0b28b49fce132` |
| iPad | control | 8342992 | `1d31ae1bb6546d1c16ac267ca8aca4f562fcdb450a7dd75caf07ed65fc449966` |

每个 phase 的 `Info.plist` 里 `EXRSourceSHA` 与本次受测 source 相等、`CFBundleIdentifier=org.exreader.host` 已在 `run_ui.py` 内断言。九份 `original_checker` 全部返回 accepted：产品 SQLite 由 `libreader_catalog_sqlite.a(sqlite3.c.o)` 唯一提供、无系统 `libsqlite3` 直链、动态 `libexreader` 存在于依赖、且七个原负例（`system_sqlite`/`missing_symbol`/`duplicate_symbol`/`duplicate_provider`/`wrong_symbol_owner`/`static_sdk`/`static_resolver`）仍被拒绝。

原 link map 未清洗：`shutil.copyfile` 逐字节保存为 `program-<phase>/link.map`，其字节数与 SHA-256 记在 `result.json.files` 并由认证 job 在 Actions 内逐项核对；解码只用 `encoding='utf-8', errors='surrogateescape'`，没有 `errors='ignore'`，没有删符号，SQLite/动态 SDK 判定沿用原实现。

## 旧失败与缺口（保留，不重写）

| 轮次 | source | run | 结论 |
| --- | --- | --- | --- |
| 旧 D15 | `4b0d44977c571efa3de2d7f73b6999343e08e438` | 40273780484 | 非本队新源码证据 |
| 第 1 轮 | `560eba3f84ab6c7e0d51de3ed0cf765c6e850c66` | 40276666182 | 三原生作业 `no such module 'CReaderProduct'`，0 个 UI 用例 |
| 第 2 轮 | `b9b923f558012fe98ea265ec8f832cad71729653` | 40279184530 | 缺 `reader_font_library.h`，0 个 UI 用例 |
| 第 3 轮 | `02dbb1a7cb0fa80920ad89dcdeec76bf3af5c6b0` | 40280431991 | 三 app 已链接并打包，原共享检查器严格 UTF-8 读 map 失败（Mac 2259028–2259029 等），0 个 UI 用例 |

本轮修复正是第 3 轮唯一阻塞点，本轮已证明它被解除：三个 phase × 三个平台都完成编译、链接、embed 检查与真实 UI 执行。剩余缺口：

- `wave3` 5 例中 3 例真实业务失败（字体借约回滚/原件导出/只读同步快照；跳转历史在定位后与大字旋转退出；typed NULL 与并发 head 的预览确认）；
- `control` 中 3 条未修改的原测试失败（search 两例、page_theme 的 live system appearance 一例）；
- 未做签名、未上真机，未做真机 VoiceOver；iPhone/iPad 仅模拟器；
- 未做完整实时网络同步声明；
- 按授权未再开第二轮，上述失败留给 root 决定。

## 最小 diff

`8ebef083..d9ca5805`，4 个文件，+164/−5：

1. `tools/check_apple_product.py`：把文件恢复成 root blob `ed7f6259…`，唯一变化 `mapping = Path(link_map).read_text(encoding='utf-8', errors='surrogateescape')`（原 map 字节、全部符号、SQLite、动态 SDK 与七个负例不变）。
2. `tests/reader_team24_apple/run_ui.py`：同一 map 的读取改为显式 `utf-8`/`surrogateescape`（第 109 行一行）。
3. `tests/reader_team24_apple/guard_owner.py`（新增）：保留原 guard 的 seed 祖先、allowed prefixes、frozen 集合（`src include bindings CMakeLists.txt cmake tests/apple_host tools tests/fixtures tests/reader_a11y_apple`）语义，只对 `tools/check_apple_product.py` 开一个精确例外：必须等于 root blob、seed→HEAD 只允许那一行替换、原 `guard.py` blob 必须不变，并自跑 31 条负例控制（多余 tools 改动、忽略/替换解码、多改一行、非法路径、错 blob 全部拒绝）。
4. `.github/workflows/team24-apple.yml`：该分支显式纳入 push 触发；guard 步骤改调新入口，其余 job/断言/预算逐字复用。

原 `tests/reader_team24_apple/guard.py`、`build.py`、`make_project.rb`、`verify.py`、`tests/apple_host/**`、SDK 源码与其余 canonical 工具在本次 diff 中逐字未变。

分支上另有文档提交 `46b729c0`（本文件与提案文档的“已应用”注记，`[skip ci]`，只改 `docs/handoffs/team24-apple*`）：未触发任何工作流，`team24-apple.yml` 的 `paths-ignore` 已覆盖该路径。该分支对应的工作流运行仍只有 `40350153254` 一次。

## 身份边界

三个 phase 的 app 仍是原 review 宏配置：`DEBUG`、`EXR_APPLE_PAGE_THEME`、`EXR_APPLE_HOST_REVIEW`、`EXR_APPLE_RAW3`、`EXR_APPLE_WAVE3`，仅 control 额外 `EXR_APPLE_READING_REVIEW`；Clang 侧 `EXR_READER_SELECTOR_BYTES_CANDIDATE=1`、`EXR_APPLE_WAVE3=1`，不定义 `EXR_APPLE_RAW3_REVIEW`。这些工件是 review 应用，不是无 review 宏的生产包，也不代表真机部署；生产 flags/package 绑定仍由 root 的 composition 入口承担，本包未改其工具。

## Root follow-up candidate: original identity before preview
Actions-only artifact inspection 40365635683 authenticated the original Mac ZIP and located the actual typed-NULL failure: Target store retains no original identity for this book. The existing round-trip test passed only after a local bookmark had caused book history to be established. Root added first-open original verification and book-history bootstrap, before later read-only annotation preview; existing history only checks identity and avoids another source export. Local source attachment semantics are unchanged, and preview still performs no bootstrap write. This candidate is not yet compiled or runtime-accepted. The font, search/history and OS theme failures are still open.

