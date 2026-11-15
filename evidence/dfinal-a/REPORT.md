# D-FINAL-A · F01 / F03 / F05 证据审计

本 lane 从 `origin/main` 的 `df8e6031` 新建 `codex/dfinal-a-evidence`，PR [#209](https://github.com/NoGod3524/EXReader/pull/209)，base 为 `main`。三项保持 **pending**。固定 v1 分母 108，状态仍为 **verified 99 / partial 1 / pending 8**，分组仍为 foundation 12 / host 84 / final 12。

## 1. 验收原文与 verified 所需证据

`catalog.json` 的实际 schema 没有 `acceptance` 字段；以下引用其 `title` 与 `note`，不补造字段。行号以起点 `df8e6031` 为准，修改后位置见 [catalog.diff](catalog.diff)。

| 项目 | 原文与行号 | 什么证据才算 verified（一句话） |
| --- | --- | --- |
| F01 | `docs/reader-total-progress/catalog.json:1638–1643`：六目标通过同一最终产品源码的完整功能验收；全目标范围未获共同源码验收，不由模块或单向/模拟器结果转授。 | 同一最终源码的 Windows、GTK、macOS、Android、iPhone、iPad 必须各有完整功能的实际运行报告，并能核对源码、程序、用例和产物身份；四端 build-only 只能证明构建。 |
| F03 | `docs/reader-total-progress/catalog.json:1656–1661`：六目标共享书架组织：子书架、分类、系列、删除与恢复一致；同上 note。 | 六目标同一最终源码上的 UI、持久化及跨平台同步必须证明子书架树、分类/标签、系列与成员关系、删除墓碑和显式恢复一致。 |
| F05 | `docs/reader-total-progress/catalog.json:1674–1679`：完整客户端离线重连、并发多头/墓碑、取消/崩溃恢复闭环；同上 note。 | 完整客户端经实际传输在离线/重连、并发分叉与墓碑、取消、进程终止及重开后恢复原书、SDK 映射、元数据和 UI，保留未决冲突并最终收敛，不能仅用协议或数据库探针授予。 |

对应 scope 原文：

- `docs/READER-PRODUCT-PLAN.md:5–6`：Windows、macOS、Linux、Android、iPhone、iPad 共用阅读核心和原生界面。
- `:153`（P1）：产品库含子书架、标签、系列顺序、离线数据；出口为约束、回滚、幂等、删除和分页，数据库检查不能冒充 UI 流畅性。
- `:155`（P3）：不可变原书、实体修订、离线 outbox、冲突和墓碑；出口包括两端往返、离线重连、并发、删除、断电重试、HTTPS 和凭据隔离。
- `:156–157`（P4/P5）：六目标实际流程和生命周期恢复；同一产品源码、相同协议、独立平台证据，至少两设备同步原书、进度、标注、分类，真机和读屏分列。
- `:173–175`：原书散列+格式为全局身份，本机 SDK ID 只是映射；子书架树、标签和系列分别建模，经宿主 owner 队列写入。
- `:180–187`：并发版本和删除墓碑均保留，时钟不裁决；校验原件后发布，区分移除下载与书库删除，安全凭据、HTTPS、限额和原子发布进入验收。

## 2. 已有证据盘点

下表保留原受测源码，不把不同提交的结果拼成最终产品通过。引用的 run/result 来自既有记录；本次另通过 GitHub API 读取的作业状态保存在 [historical-actions-jobs.json](historical-actions-jobs.json)，仅核对作业和步骤，不声称重新运行或重新散列全部历史 ZIP。[existing-evidence.json](existing-evidence.json) 保存台账原有 run、source、artifact、digest 指针。

| 项目/平台 | 已有文件、测试名及最近能核对的实际结果 | 尚缺的具体产物 |
| --- | --- | --- |
| F01 六目标包 | `docs/reader-total-progress/f06-sdk342-six-packages.md:7–35`：run [40678657371](https://github.com/NoGod3524/EXReader/actions/runs/40678657371)，source `8f8acf32`，六包 manifest/安装身份检查；本次 API 核对 12/12 jobs success。原文明确不授予 F01。 | 当前共同源码的逐平台完整功能用例报告、程序散列、包 manifest、原始日志及联合汇总；已有六包不是完整功能验收。 |
| F03 Windows | `docs/reader-team24-composition/PLAN.md`，run [40414564325](https://github.com/NoGod3524/EXReader/actions/runs/40414564325)，source `0b54a15e`；`tests/windows_organization_projection/check_ui.py` 的 `native-create-shelf-tag-series-and-child`、`native-created-groups-sync-to-second-host`、`native-shelf-series-memberships-sync`、`native-shelf-series-removals-sync`、`native-tag-membership-and-removal-sync` 等，原台账授予独立宿主范围。较新的 F03 run [41679502785](https://github.com/NoGod3524/EXReader/actions/runs/41679502785)，source `a375fd9b`：Windows job **failure**。 | 当前提交 Windows 实际 UI 的完整整理生命周期、删除恢复及与 GTK/其他端互通产物，不能继承旧 Windows 成功。 |
| F03 GTK | `docs/READER-GTK-341-FINAL.md`，run [40184639030](https://github.com/NoGod3524/EXReader/actions/runs/40184639030)，source `d05946f0`；`tests/linux_host/check_collections_ui.py` 的收藏整理用例，独立 GTK 范围已验。较新 run `41679502785` 的 gtk job **success**，整体仍 failure。 | 当前提交 GTK UI 全整理生命周期及与 Windows/四端同源往返；一项 gtk job 成功不能覆盖缺失 Android 和失败 Windows。 |
| F03 Android | `docs/READER-PRODUCT-PLAN.md:92–93` 及 catalog 的 `android_organization`，run [40059870895](https://github.com/NoGod3524/EXReader/actions/runs/40059870895)，source `3f50a165`：原生 8、UI 8、实际重启和 15 门禁及保留套件通过；驱动 `tools/check_reader_organization_android.py`。 | 当前最终源码 Android 的整理测试 APK、设备日志、UI 截图、两设备同步收敛及持久化读回；需 Android runner/真机，build-only APK 不授予这些行为。 |
| F03 macOS | `docs/reader-total-progress/macos-organization-original.md:6–34`，run [40635727935](https://github.com/NoGod3524/EXReader/actions/runs/40635727935)，source `716c1409`：原运行总体 failure，macOS 的 `testGroupLifecycleAndProcessRestart`、`testMembershipAndProcessRestart`、`testTagAndSeriesPersist`、`testStagedIntentSurvivesTerminationAndRetry`、`testNestedShelfSurvivesRestart`、`testStaleEditDoesNotOverwriteCompetingRevision` 六项成功。较新 `41679502785` 的 macOS job success。 | 当前源码 macOS 实际 UI、原始 XCTest/步骤附件、完整成员删除恢复和跨平台收敛。 |
| F03 iPhone/iPad | `docs/reader-total-progress/apple-ios-members-audit.md:3–5`，run [40911140164](https://github.com/NoGod3524/EXReader/actions/runs/40911140164)，source `b259db57`：上述原六项两套模拟器 suite 均通过，`testTagAndSeriesPersist` 加真实 EPUB 成员增删、恢复与三次重启；本次 API 核对两作业 success。较新 `41679502785` 的 iphone/ipad jobs success，但无 Android job，Windows failure。 | 同一当前源码两设备实时同步、完整 UI 闭环、原始 XCTest 和程序身份；需 macOS/Xcode runner；实际设备能力仍需 iPhone/iPad 真机。旧 `40817810353` 失败继续保留。 |
| F05 原生模块 | `docs/READER-SYNC-RESILIENCE.md`、`docs/validation/reader-sync-resilience.json`，`tests/reader_sync_resilience/check_resilience.py` + `boundaries.py`；run [40079870542](https://github.com/NoGod3524/EXReader/actions/runs/40079870542)，source `79a40700`：Windows/Linux/macOS 的原 20 项 session + 21 故障边界及 aggregate 全部通过，本次 API 核对 4/4 jobs success。具名用例包括 `offline_outbox_is_published_verified_and_acked_on_the_worker`、`explicit_retry_resumes_and_preserves_durable_history`、`same_account_reopen_after_forced_kill_resumes_without_rebinding`。 | 当前完整宿主而非模块 CLI 的相同边界、SDK 导入/映射、元数据/UI 恢复；原报告明列 host UI 未验和五个未覆盖窗口，不能挪给 F05。 |
| F05 Windows | `docs/reader-total-progress/windows-sync-account.md:3–24`，producer [40642072411](https://github.com/NoGod3524/EXReader/actions/runs/40642072411)，source `42445abd`：Wave3 状态、32 原生账号检查、失败/取消/重试、映射恢复及重开通过；独立鉴证 `40643169696`。 | 当前共同源码 Windows 全流程、并发删除/恢复、实际崩溃与另一宿主收敛的联合输出。 |
| F05 GTK | `docs/reader-total-progress/linux-sync-account.md`，run [40629444286](https://github.com/NoGod3524/EXReader/actions/runs/40629444286)，source `6b2e3a2d`：原 27 + 2 项状态/生命周期检查通过。`EVIDENCE-CUSTODY-20261103.md:9–12` 中较新 run [41679586829](https://github.com/NoGod3524/EXReader/actions/runs/41679586829)，source `0be9b393`：本次核对仅 dry-run success，retained/native producer/independent audit 等五作业 **skipped**。 | 真正 GTK native producer 与独立 audit 的完整输出；dry-run 不是客户端运行，不能标通过。 |
| F05 Android | `docs/reader-total-progress/android-sync-account.md:3–16`，run [40630302205](https://github.com/NoGod3524/EXReader/actions/runs/40630302205)，source `c33455a9`：API34 x86_64 临时 HTTPS 账号状态、401、凭据修正、阻塞传输取消、重试和 Keystore 等通过；`tools/reader_composition/android_sync_evidence.py` 固定核对原 artifact 的 `initial_read_only_status`、`authentication_failure_visible`、`correct_credentials_cancel_and_retry`、`forget_keeps_binding`、`sync_status_view_without_session_and_real_failed_session`。 | 当前共同源码完整 Android 原书/映射/组织/冲突/终止恢复与第二设备读回；Android runner 与真机。 |
| F05 Apple 三端 | `docs/reader-total-progress/apple-sync-details-audited.md:3–7`，producer [40914421686](https://github.com/NoGod3524/EXReader/actions/runs/40914421686)，source `6c7d043d`：实际 TLS 的取消/完成详情、401→授权修正→重试、原书保留通过；audit `40920468235` 复核三个 XCTest、失败时 pending revision 及 256 shards 恢复，本次 API 核对 producer 3/3 success。 | 当前共同源码三宿主完整并发/墓碑/取消/终止恢复、原书/SDK 映射/UI 和另一设备收敛的独立证据；macOS runner，移动端真机。 |

既有记录还读了 `README.md`、`SESSION-CONTRACT.md`、`apple-continuation-20261029.md`、`apple-ios-organization-original-20261029.md`、`apple-four-audited-20261029.md`、`EVIDENCE-CUSTODY-20261103.md` 以及 `EXREADER_C02_WEBDAV_HANDOFF_20261031.md` 中 F03/F05 的后续诊断/失败/权限记录；custody patch 只是保存，不在本 lane 自动套用。

该 handoff 的“F05 GTK observation correction: executed once, failed in cleanup”还保留真实 native run [41629004820](https://github.com/NoGod3524/EXReader/actions/runs/41629004820)，source `834aac8adea2f19b3ccda832608ffacc4049449f`：原 producer 的 48 保留检查通过，新场景在 cleanup guard 失败，`accepted/fullF05/delete_detail=false`。本次 API 再核对 native producer `125893568906` 和 independent audit `125902684393` 均为 failure，见 [historical-gtk-failed-41629004820.json](historical-gtk-failed-41629004820.json)。它不被后来的 dry-run success 覆盖。

补充具名用例索引（相应历史 run 的限定范围如上）：

- GTK 整理：`tests/linux_host/check_collections_ui.py` 的 `enter_shelf_creates_a_child_with_explicit_parent_and_position`、`adding_a_removed_membership_explicitly_restores_its_tombstone_history`、`removed_child_restore_refuses_deleted_parent_without_writing_anything`、`native_series_membership_accepts_and_edits_the_reading_order`。
- Android 整理：`tools/check_reader_organization_android.py` 固定核对 `org.exreader.host.OrganizationTest` 的 `groupAndRemovedKeysetsStayBounded`、`membershipDeleteRequiresExplicitRestore` 等八项，以及 UI 的 `more_create_edit_and_nested_shelves`、`remove_and_explicitly_restore_membership`、`series_ordinal_changes_visible_order`、`group_delete_and_full_removed_restore` 等八项。
- Windows 账号：`tests/reader_windows_account/check_account_ui.py` 的 `fault_round_1_network_interruption_fails_visibly_and_explicit_retry_completes`、`network_cancel_is_visible_and_retry_resumes_to_completion`、`reopened_library_resumes_after_closing_mid_scan`；同源 Wave3 只读状态由原 producer 的对应 UI 步骤提供。
- GTK 账号：`tools/reader_composition/gtk_sync_evidence.py` 的固定名单含 `real_paused_tls_scan_leaves_gtk_responsive_and_cancel_is_nonblocking`、`server_failure_is_visible_and_only_explicit_retry_resumes_the_scan`，新增两项为 `live_status_widget_is_noneditable_and_matches_capture` 和 `closed_session_retained_until_pending_capture_releases`。
- Apple 账号：`tools/reader_composition/apple_sync_details_independent.py` 固定核对 `test01RootValidationAnonymousRestartAndUpdate()`、`test02SeparateAccountLibrariesAndRestart()`、`test03NativeHTTPSBackgroundCloseAndRetry()`，以及独立失败恢复用例 `testAuthorizationFailurePreservesBookAndRetry()`。

## 3. 新增实现与真实输出

新增 `tests/reader_final_a/` 和 `.github/workflows/reader-final-a.yml`，并修正 `tools/build_android_host.py` 的产品归档构建和 SDK 版本传参、Android 消费者的精确版本白名单。无 SDK、产品数据库或传输实现改动。

- `CMakeLists.txt`：链接本次源码实际安装的 catalog/revisions 包，复用 `tests/reader_revisions/consumer/main.cpp`，注册三项 CTest；Windows 明确链接 shell32。
- `check_clients.py`：两个独立持久产品库，所有修订/投影/outbox 操作都经过真实原生公开 API；Python SQLite 只用于读回和可观察崩溃点触发器。每个 consumer 调用都是新进程，验证重开持久化；删除/恢复对比七张产品表，校验 integrity 和外键。
- F03 检查父/子书架、分类、系列顺序、三类成员、书籍删除、禁止隐式复活及显式恢复；除两库逐次一致，还断言实体 deleted=1、成员行实际移除、恢复后整行与删除前完全相同。
- F05 检查离线两端各自提交编辑和删除，重连保留两个 heads，拒绝默选赢家，覆盖全部 heads 的显式 restore；收到修订但未 ack 的模拟取消及幂等重传。
- 两个实际进程终止点分别位于 history/outbox 写入后、metadata 前，以及原子提交后；通过外部 marker 确认到达再执行 `process.kill()`，重开要求全无或全有，重试不重复，第二客户端实际 receive/project。
- `build_android.py`：复用已有构建函数为当前源码生成 APK 和散列 manifest，独立标注 build-only；不调用/更改旧 frozen-source 验收或冒充其通过。
- Android 公共构建函数：安装时同时导出 catalog、original-import 等归档，因此构建全部导出目标；Gradle 的 `exrSdkVersion` 读取已安装版本头，不再依赖工程中旧的 3.41 默认值。
- `examples/android/app/src/main/cpp/CMakeLists.txt` 在现有 3.40/3.41 白名单中增加精确的 3.42.0；仍使用 `find_package(... EXACT)`，不开放任意未来版本，也不移除可选功能约束。Android 仅授予实际编译的基线 profile。
- Actions：同一 SHA 的 Windows/Linux 安装包集成测试和宿主基线；Android/macOS/iPhone/iPad 四项 build-only，保留 APK/app、构建 manifest、原始 CTest 与 CMakeCache。iPhone/iPad 使用同一 universal iOS app 构建路径，但两目标分别登记，不表示真机运行或可分发签名。
- 原有 `check_session.py` / `check_resilience.py` 在新工作流真实 Actions 环境原样重跑；未改它们的用例、守卫、预算、TLS/失败断言或报告。run [43646633278](https://github.com/NoGod3524/EXReader/actions/runs/43646633278)，source `f530de56524174b1d1149125d7dd90ee2d114f85` 的 Windows/Linux 两个 native HTTPS jobs 均已 success，覆盖原 20 + 21 项；两端新集成和 store CTest jobs 也都 success。该次运行的宿主 CTest 和 Android 环境步骤失败、Apple 排队，整体未授予通过。

本地初跑：[clients-ctest-initial.log](clients-ctest-initial.log)。业务断言通过后 TemporaryDirectory 清理失败：Python 的 SQLite connection context manager 只提交、不关闭连接；Windows 文件仍被占用。已改用 `contextlib.closing`，未跳过清理或修改业务断言。初始 Actions Windows 同样失败，Linux 通过；保留原结果。

本地复测：[clients-ctest.log](clients-ctest.log)：

```text
PASS offline_nested_shelves_tags_series_memberships_converge_after_reopen
PASS series_44444444444444444444444444444444_delete_blocks_put_explicit_restore_converges
PASS tag_33333333333333333333333333333333_delete_blocks_put_explicit_restore_converges
PASS shelf_22222222222222222222222222222222_delete_blocks_put_explicit_restore_converges
PASS shelf_11111111111111111111111111111111_delete_blocks_put_explicit_restore_converges
PASS membership_shelf_delete_blocks_put_explicit_restore_converges
PASS membership_tag_delete_blocks_put_explicit_restore_converges
PASS membership_series_delete_blocks_put_explicit_restore_converges
PASS book_txt_delete_blocks_put_explicit_restore_converges
PASS both_catalogs_integrity_and_foreign_keys_ok_no_remote_echo
PASS two_disconnected_clients_persist_independent_edit_and_tombstone
PASS reconnect_preserves_both_heads_replay_is_idempotent_no_silent_winner
PASS explicit_restore_covers_all_heads_and_converges_without_outbox_echo
PASS crash-project-before-metadata_real_kill_atomic_recovery_retry_and_second_client_receive
PASS crash-project-after-commit_real_kill_atomic_recovery_retry_and_second_client_receive
100% tests passed out of 3
Total Test time (real) =   7.12 sec
```

上述本地 relay 是模拟网络的测试调度，不运行真实 WebDAV、TLS 或账号 session；取消是 ack 前中断调度，不是原生传输取消。新 Actions 的原有原生 HTTPS 套件另有真实传输结果，但完整宿主闭环仍缺。

额外尝试旧 store CTest 的本地输出：[store-ctest.log](store-ctest.log)，两项因原本的 `GITHUB_ACTIONS` 守卫失败（0/2）；未伪造 Actions 环境，未更改守卫。这两项在新增 Actions 的实际运行结果另列。

Actions 首轮错误摘要保存在 [initial-actions-failures.log](initial-actions-failures.log)：Windows 的 `native-docx-edit-e5` 使用默认 cp1252 读取 UTF-8 fixture；Linux 的 `native-pptx-real-matrix` 因 Calibri 回退的文本 bbox 不匹配失败（14/15 文件通过，CJK 按既有分流通过）；Android 的 sdkmanager 未在 PATH。修复为 workflow 的 `PYTHONUTF8=1`、Linux 安装 Carlito 等度量字体、调用 SDK 下的 sdkmanager。未放宽/删除任何测试或扩大排除项。

后续驱动接线修复：Windows 校验器的输入目录改为实际生成的 `windows-package/EXReader`；GTK 补齐实际驱动调用的 `xprop`、`xwininfo`、`xclip` 和 ImageMagick `import`。原 57cd72a5 的 GTK 因缺 xprop 失败，c7379d7d 因缺 xclip 失败，均保留原日志和产物。

Windows 的当前 Shell 与旧 toolbar 验收不一致：run `43649931847` 的自检 **26 项通过**，但旧 A/B/C UI suite **失败**。A 的 `font_inc` 后，step 24 的 `check|font|160` 读取 `g.font_percent=150`；`examples/reader.c` 的 `change_font()` 已转到 `shell_step_font()`，实际字号归 `shell_font`，`examples/windows/shell_drive_test.inc` 的旧 `check|font` 仍读取 `g.font_percent`。当前 Shell 始终启用，旧 toolbar 没有构建入口。当前 42efccd3 日志还记录标注跳转、高亮/标注计数、重开状态等失败，不能把全部失败归因于字号旧字段。未修改产品字号或放宽 UI 断言；F01 缺当前 Shell 的完整 UI 验收。

## 4. 全量构建、CTest、Actions 与 prepush

本地 catalog、revisions、consumer 及完整 SDK 的 Release 编译均实际完成，exit 0。输入、核心源码树 blob、DLL/consumer SHA-256、编译选项和复用的依赖源码缓存位置见 [source-identity.json](source-identity.json)。SDK 的 `src/include/cmake/CMakeLists.txt` 及禁止修改的 release checker 与基线逐项相同。

| 实际运行 | 输出 | 结果 |
| --- | --- | --- |
| 本机全 SDK `cmake --build build/dfinal-a/sdk --parallel 8` | [sdk-configure.log](sdk-configure.log)、[sdk-build.log](sdk-build.log) | Release 真编译，exit 0；未复用其他源码树的 SDK 二进制。依赖使用本机已有源码缓存。 |
| 本机全量 CTest，`--parallel 2 -E '^sdk-(release\|doc-coverage)$'` | [sdk-ctest.log](sdk-ctest.log) | **581/581，exit 0，574.17 秒**；只排除指定两项。 |
| 本机新增集成 CTest | [clients-ctest.log](clients-ctest.log) | **3/3**，15 条具名断言阶段，7.12 秒。 |
| Actions Windows SDK，source `57cd72a5` | [actions-57-windows-sdk-ctest.log](actions-57-windows-sdk-ctest.log) | **581/581**，191.39 秒。 |
| Actions Linux SDK，source `57cd72a5` | [actions-57-linux-sdk-ctest.log](actions-57-linux-sdk-ctest.log) | **580/580**，72.55 秒；平台条件使注册数不同。 |
| Actions Windows 原生 HTTPS，source `f530de56` | [native-https-Windows-f530.json](native-https-Windows-f530.json) | **20/20 session + 21/21 fault boundaries**，两份原报告 `accepted=true`。 |
| Actions Linux 原生 HTTPS，同上 | [native-https-Linux-f530.json](native-https-Linux-f530.json) | **20/20 + 21/21**，两份原报告 `accepted=true`。 |
| prepush | [prepush-final-code.log](prepush-final-code.log)、[prepush-gtk-dependencies.log](prepush-gtk-dependencies.log) | **exit 0**。 |

完整本机 CTest 结尾原样：

```text
581/581 Test #581: sdk-doc-dictionary .................................   Passed    0.22 sec
100% tests passed out of 581
Label Time Summary:
headless    =  14.60 sec*proc (1 test)
Total Test time (real) = 574.17 sec
ctest exit=0
```

HTTPS 工件已通过连接器实际下载，并再次核对原 ZIP 字节数与 SHA-256，再提取两份 result.json，未仅依赖 job success：Windows artifact `14134042598`，246080 字节，`3140964c0d69024ab81555f246838f0af65738161277c55d0baef5225fe6e717`；Linux artifact `14134377986`，270804 字节，`da7cef696388d96aff81becb10869026ee4fcbb0a673d28e2525de97f9f6b6eb`。API 元数据见 [actions-f530-artifacts.json](actions-f530-artifacts.json)。

本次产品构建/真实协议快照为 `42efccd3d6a90cc94d1bfbcb12d061d1c7b6e7e0`，run [43653480030](https://github.com/NoGod3524/EXReader/actions/runs/43653480030)。Windows 全 SDK **581/581（194.45 秒）**、Linux **580/580（125.52 秒）**，原始完整输出见 [Windows](actions-42-windows-sdk-ctest.log)、[Linux](actions-42-linux-sdk-ctest.log)。Windows 自检 26 项通过，旧 A/B/C UI 仍失败，见 [原始失败输出](windows-ui-42.log)；该 run 不会记为全绿。GTK 基线 UI **20/20**，程序和截图已从 ZIP 实际读取并散列，见 [gtk-ui-final.json](gtk-ui-final.json)。两端原有原生 HTTPS **20+21** 全通过，报告见 [Windows](native-https-Windows-final.json)、[Linux](native-https-Linux-final.json)，逐 ZIP 核对记录见 [artifact-verification.json](artifact-verification.json)。

加强实际删除/恢复语义的测试提交为 `773cd788a1bb52ca2ef6308855c27fb9b06274d3`；手动 `clients_only=true` run [43654524720](https://github.com/NoGod3524/EXReader/actions/runs/43654524720) 在 Windows/Linux 各自重新编译 consumer，并通过新增 **3/3** 和原 store **2/2**。原始输出：[Windows 新测试](actions-Windows-clients-ctest.log)、[Linux 新测试](actions-Linux-clients-ctest.log)、[Windows store](actions-Windows-store-ctest.log)、[Linux store](actions-Linux-store-ctest.log)。此运行其余 job 按明确输入 skipped，不能计通过。初次本机正向结果 11.54 秒保存在 [clients-ctest-first-pass.log](clients-ctest-first-pass.log)；加强后当前结果 7.12 秒。

产品/SDK/构建脚本相关路径从 `ef6bfdb5` 至 `773cd788` 无变化；中间修正仅为 workflow 的 Android strict shell、macOS 非空参数数组/部署版本，以及新测试断言。实际源码比较和最终测试文件散列见 [final-source-identity.json](final-source-identity.json)、[source-preservation-check.log](source-preservation-check.log)。Mac 基线工作流使用 PR merge SHA `32c6094e`，**完整 Git tree 与 42efccd3 完全相同**，tree 为 `0c8af73fa201be6338a8f6b35e65b74ade7f1745`；不是凭包名推定同源。

早期 `ef6bfdb5` 的 macOS job 在 `set -u` 下读取 Bash 3.2 空数组、尚未进入 CMake 即失败；42efccd3 初始化 sysroot 参数并设置 macOS 12 deployment。Android setup 原来缺显式 strict shell，generic CI hygiene failfast 实际报三处；现已补齐，当前四个真实 CI hygiene jobs success，本机 `check_ci_hygiene.py --base df8e6031` **exit 0 / violations 0**，完整输出见 [ci-hygiene-final.log](ci-hygiene-final.log)。未修改 baseline、checker 或忽略规则。

### 四端 build-only 登记

以下产物均通过连接器实际下载 ZIP，核对 GitHub 原 ZIP 字节数和 SHA-256，再核对包内原生程序散列；Android 三 APK 另核对 manifest 的大小与散列，macOS 嵌套 app ZIP 逐文件核对 manifest。完整 digest/source/run/program 清单见 [artifact-verification.json](artifact-verification.json)。

| 目标 | Actions 产物 / 源码 / 实际范围 | 尚缺 |
| --- | --- | --- |
| Android | run `43653480030` artifact `14137256621`，source `42efccd3`；x86_64 debug APK（含测试 APK）真实构建，`device_tests_run=false`；[manifest](final-a-build-only-android-42efccd3d6a90cc94d1bfbcb12d061d1c7b6e7e0-build.json)。 | 未安装/运行设备，没有当前整理/恢复 UI 或真机证明。 |
| macOS | Native C engine run [43653483106](https://github.com/NoGod3524/EXReader/actions/runs/43653483106)，desktop job `132626849838` success；artifact `14137433609`，source `32c6094e`（与 42 完整 tree 相同）；arm64 macOS 12 app，所有 manifest 文件散列实际匹配；[manifest](macos-build.json)、[核对输出](mac-artifact-verification.log)。 | 仅按 build-only 登记；不授予当前六端完整功能、整理或 F05。专用 macOS build-only job 仍以最终快照状态为准。 |
| iPhone | run [43650961238](https://github.com/NoGod3524/EXReader/actions/runs/43650961238) artifact `14136667353`，source `ef6bfdb5`（上述产品路径与 42/773 相同）；arm64 iOS 15 universal app + unsigned IPA；[manifest](final-a-build-only-iphone-build.json)。 | 当前 42 的独立 iPhone 作业若仍 queued，不能称成功；已有实际构建仅授予相同产品源码路径，不称整个工作流 tree 相同。需 owner 签名和真机功能验收。 |
| iPad | run `43653480030` artifact `14137602353`，source `42efccd3`；arm64 iOS 15 universal app，Info.plist `UIDeviceFamily=[1,2]`；[manifest](final-a-build-only-ipad-42efccd3d6a90cc94d1bfbcb12d061d1c7b6e7e0-build.json)。 | 同一 universal 构建支持两类设备，但没有 iPad 实际运行；需 owner 签名和真机。 |

最终作业快照：[专用工作流](actions-43653480030-jobs.json)、[Native C engine](actions-43653483106-jobs.json)。排队、运行中、skipped 均不计通过。为释放 runner，只取消本 lane 被后续代码替代的旧运行，完成的失败步骤与原工件未删除，取消记录见 `superseded-actions-cancel*.json`。

## 5. 台账判定与缺口归属

仅变更 F01/F03/F05 的 evidence 引用和 note，state 均保持 pending。`evidence` 在 v1 schema 中必须引用顶层已有 key，因此新测试路径、运行和缺口放在三项 note 与本报告中，没有写入无法解析的伪 evidence key，也没有新增/修改顶层 evidence 定义。

[catalog.diff](catalog.diff) 是完整台账差异；[catalog-check.log](catalog-check.log) 验证只有三个 ID 变化，所有引用可解析，固定 108 和计数未改。本次没有运行下载所有历史 ZIP 的全台账鉴证，所以不把静态计数称为新的 evidence_ok 审计结果。

| 项目 | 最终 state | 理由 |
| --- | --- | --- |
| F01 | pending | 同源构建、基线和模型测试不足以证明六目标完整功能；四端依要求是 build-only。 |
| F03 | pending | 新增模型/存储测试可重复验证组织生命周期；缺当前同源六端 UI 及跨平台往返一致性的完整产物。 |
| F05 | pending | 新增真实原生双库和实际进程终止恢复；模拟 relay 不代替完整宿主真实传输和六端客户端闭环。 |

本机不能提供：GTK/X11 UI（需 Ubuntu runner）、macOS/Apple XCTest 及 iPhone/iPad 编译（需 macOS/Xcode runner）、Android NDK/Gradle APK（当前 Windows 环境未配置，交 Ubuntu Actions）、移动端设备锁屏/后台/断电/凭据和部署能力（需 Android/iPhone/iPad 真机及相应签名）。实际终止进程不证明存储设备掉电或 SQLite torn-write。所有 UI、真机、真实用户云盘互操作的缺项均不授予。

性能门槛和字体断言未改；本 lane 未新增性能或 CJK 画面断言，不产生新的性能/字体验收。

最终 prepush 的逐条真实输出见 [prepush-final.log](prepush-final.log)，exit 0。
