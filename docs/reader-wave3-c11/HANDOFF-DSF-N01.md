# DSF Android 接手 N01（收尾轮）

工作树：`C:/Users/Oscar/exreader-team24-20261026/dsf-android`，分支 `codex/dsf-android-ui-close`，
起点 `59f8ca9607cf9e2a864f2a1f57bd1c40f2c76baf`。原 `team24-android` 目录保持只读，未写入。
本包只做失败收尾：不加新功能，不改 SDK / 公开 ABI、不改 `apps/reader/**` 等保护树、
不改旧 driver 与既有预算。本地只改源码、文档与 Git；构建、测试、语法检查、夹具、截图与
工件下载/解包/解析全部只在 GitHub Actions 内执行。

## 1. 结论与三个真实首错

首错不是从 summary 列单推的，全部来自同轮 Actions 工件原文。

| # | 原始首错（同轮证据） | 位置 | 本包处理 |
| --- | --- | --- | --- |
| 1 | frozen 走查 45 项里 `font_increase`/`font_decrease` 报 `font status missing`；review `selection_invalidated_while_busy` 报 `missing status: Review page-before-render`（detail 里 reader_status=`阅读设置已保存`）；bounded `bounded_cross_chapter_font`/`bounded_budget_limit_preserves_frame` 报 `actual reader did not reach page 2` | `READER_PREFERENCES=true` 的构建把 A+/A− 从普通翻页事务改走 `preferencesApply`：无 loading/cancel gate、状态写「阅读设置已保存」、位置落到章首 | 已修：快捷字号回到 `runPage` 普通翻页事务，仍把字号写进 preferences 模块 |
| 2 | wave3 `original_export_cancel_receipt_and_ordinary_exception_under_checkjni` 报 `cooperative cancellation returns the real receipt: status=6 items=1`（6=ROE_IO） | 冻结模块 `apps/reader/original-export/src/original_export.cpp:121` 先 `open("/",O_RDONLY\|O_DIRECTORY\|O_CLOEXEC)`，取消回调根本没被问到 | 不可改（冻结模块），只记录真实首因 |
| 3 | wave3 `local_font_saf_import_select_lease_and_release` 报 `UI expected 字体状态 containing 已导入; observed 字体状态=字体未导入：open root (font 4)，原有字体保留` | 冻结模块 `apps/reader/font-library/src/library.cpp:91` 同一个 `open("/")` 失败；`RFL_IO=4`，消息就是 `open root` | 不可改（冻结模块），只记录真实首因 |

第 2、3 项是同一根因：两个 reviewed 模块的目录遍历都从 `open("/")` 起步，而本机
API34 x86_64 镜像上的应用进程拿不到该 open（字体模块直接把它命名为 `open root`）。
宿主侧经 `NativeOriginalExport`/`NativeFonts` 只能看到模块返回的状态码，无法在不改模块的
前提下绕过。宿主自己的「导出原件」入口走同一模块，因此同样受影响。

wave3 `cancel`/`restore` 两阶段在本轮**未执行**（`run_ui.py` 在 `first` 的首个断言即中止），
不计为通过；`report.py` 里「not passing: 18 项」是阶段整体缺失后的推导结果，不是 18 个独立 UI 失败。

## 2. 轮次、源码与工件身份

| 轮次 | source / run / attempt | 实际结果 |
| --- | --- | --- |
| 原 C11（接手前） | `28f49ee0399d48518cc2afb0048009b6c38edcfa` / [40274139390](https://github.com/NoGod3524/EXReader/actions/runs/40274139390) / 1 | 失败：annotation-import 默认 OFF，无 APK、未跑 UI |
| team24 新增 1 | `0415b8b39d8f9025126b8f90ed17c206da17d787` / [40276105096](https://github.com/NoGod3524/EXReader/actions/runs/40276105096) / 1 | 失败：AAPT 缺 sync 夹具 CA，未跑 UI |
| team24 新增 2 | `0fe1bcb593b307eb85ebc63b5ed09990952e9402` / [40276608248](https://github.com/NoGod3524/EXReader/actions/runs/40276608248) / 1 | 失败：4 个 duplicate class，未跑 UI |
| team24 新增 3 | `ac2c6973204860a7c5a5a32967421e5fea3622c3` / [40277306694](https://github.com/NoGod3524/EXReader/actions/runs/40277306694) / 1 | 失败：6 处受检 JSONException 编译错误阻断整包，未跑 UI |
| 真实 Java 门禁 | `59f8ca9607cf9e2a864f2a1f57bd1c40f2c76baf` / [40279837852](https://github.com/NoGod3524/EXReader/actions/runs/40279837852) / 1 | 成功（只编译真实 host+test Java，不执行 native） |
| 完整轮 4（原基线） | `59f8ca96` / [40280046571](https://github.com/NoGod3524/EXReader/actions/runs/40280046571) / 1 | 失败：SDK/19 模块/host/全部 test APK 构建成功；设备上 walkthrough 43/45、review 8/10、bounded 9/11、navigation 18/18、reading 16/16、wave3 first 4/13，cancel/restore 未执行 |
| 本包完整轮（唯一新增） | `0e5c6cfa29cf8ec5a6ae4585d894391417698d59` / [40352736333](https://github.com/NoGod3524/EXReader/actions/runs/40352736333) / 1 | 失败：walkthrough 45/45、review 10/10、bounded 11/11、navigation 18/18、reading 16/16、wave3 first 4/13，cancel/restore 未执行 |
| 复核用 Java 门禁 | `0e5c6cfa` / [40352410741](https://github.com/NoGod3524/EXReader/actions/runs/40352410741) / 1 | 成功（不执行 native） |
| 工件审计 1 / 2 | [40351576951](https://github.com/NoGod3524/EXReader/actions/runs/40351576951) 审计 40280046571；[40360014172](https://github.com/NoGod3524/EXReader/actions/runs/40360014172) 审计 40352736333 | 成功：只在 Actions 内下载/解析原工件，打印逐 suite 汇总与逐例状态 |
| 提交顺序修复后的 Java 门禁 | `a2f6111eb71677d1fdc9c98fdbe81e55ded41b54` / [40361892311](https://github.com/NoGod3524/EXReader/actions/runs/40361892311) / 1 | 成功：guard 通过，真实 host+test Java（含新增两项检查与 `PagePublish`）编译通过，未执行 native |

工件身份（GitHub API 记录的 ZIP digest；本包没有在本地下载、解包或解析任何工件）：

| run / attempt | artifact | bytes | ZIP SHA-256 | 有效期 UTC |
| --- | --- | --- | --- | --- |
| 40280046571 / 1 | `reader-wave3-c11-android-40280046571-1` (12632967357) | 142195679 | `8ebc5e4d18d7381a100c3b6ebf9cee5bfa21829f5ee8463bcdc5114799615e9c` | 2027-01-24 06:28:47 |
| 40352736333 / 1 | `reader-wave3-c11-android-40352736333-1` (12665838771) | 144188492 | `55d185bb4f464faa57e8b18742542b96859c172e4ad8c437ac777fc84d550e11` | 2027-01-24 15:47:12 |
| 40352410741 / 1 | `reader-wave3-c11-java-40352410741-1` (12664461248) | 34962 | `d79e66bd3e7c16abdd9fd638812e9ef76c995410185a8b3e98d32d53c7ecbdef` | 2027-01-24 15:45:15 |
| 40361892311 / 1 | `reader-wave3-c11-java-40361892311-1` (12667034837) | 34967 | `4f3adaeae5a9646a48276ed01893b67be359fbcfaeea120dc4d6da6872f9c27f` | 2027-01-24 16:43 |

实际 APK（审计工件内 `artifacts/app-debug.apk` 的字节；与设备内 `pm path` 拉回的
`installed.apk` 逐字节相同）：

| run | app-debug.apk SHA-256 | bytes | 设备安装身份 |
| --- | --- | --- | --- |
| 40280046571 / 1 | `4907f4823823f17c082e45df52625b0c2f5aca6a340a660843309d28a47daac4` | 27378388 | `evidence/wave3/installed.apk`、`evidence/walkthrough/installed/app-debug.apk`、`evidence/reading-installed.apk` 同哈希 |
| 40352736333 / 1 | `881e985d6e22c49254d98b2f23d04dc4d084a84e86bd7189f3848e7f02d97488` | 27378388 | 同上三处同哈希 |

测试 APK（40352736333 / 1）：`app-debug-androidTest.apk` `2420567a63fb3aac2d7d62a24a4b89c75678f488edd57b0acfda590b4b1dba86`、
`navigation-debug-androidTest.apk` `b165288d450c71c59e64a9c7de4bac3ca31a4871170a05c636e6941a9cdee3dc`、
`reading-debug-androidTest.apk` `4eb240549f44ef73b5bd055652392f1be8cb0b24d4b0b1acc0c7a07413c6cb23`、
`uitest-debug-androidTest.apk` `75c005bead92cca2fefd01a0659484593d5f5abe291311f41aa19549fde69059`。

## 3. 逐 suite 实际执行 / 通过 / 失败 / 未执行

只写同 run/attempt 的证据；两个完整轮的 source 不同，不拼接。

| suite（冻结或本包 driver） | 40280046571 / 1（59f8ca96） | 40352736333 / 1（0e5c6cfa） |
| --- | --- | --- |
| walkthrough 45 | 执行 45，通过 43，失败 2（font_increase、font_decrease） | 执行 45，通过 45，失败 0 |
| review 10 | 执行 10，通过 8，失败 2（selection_invalidated_while_busy、duplicate_late_cancel_keeps_original） | 执行 10，通过 10，失败 0 |
| bounded 11 | 执行 11，通过 9，失败 2（bounded_cross_chapter_font、bounded_budget_limit_preserves_frame） | 执行 11，通过 11，失败 0 |
| navigation 18（16+2） | 执行 18，通过 18 | 执行 18，通过 18 |
| reading 16（14+1+1，3 个进程） | 执行 16，通过 16 | 执行 16，通过 16 |
| wave3 first（13 项） | 执行 13，通过 4，失败 9（2 真：export 取消回执、字体面板状态；7 级联：面板未关导致「UI expected shelf」） | 执行 13，通过 4，失败 9（2 真：export 取消回执 `status=6`、字体导入 `open root (font 4)`；7 级联） |
| wave3 cancel（1 项） | 未执行（run_ui.py 在 first 中止） | 未执行 |
| wave3 restore（4 项） | 未执行 | 未执行 |

级联说明：`local_font…` 失败后字体面板没有关闭，随后 7 项检查都停在 `shelf()`/`open()`
的「UI expected shelf」，属于同一上游失败的后效，不是 7 个独立产品缺陷。

## 4. Root 代码审查后续（本轮处理）

审阅点一：`0e5c6cfa` 的 `changeFont` 在 `runPage` 的 action 里先 `reflow.setFontSize`
生成尚未 accept 的 `PageLoad`，随后 `keepAppearanceSize` 立即 `NativePreferences.save`
并改 `readingPreferences`；`runPage` 之后才 `task.commit(persistPage + accept)`。一旦
保存后取消、或 `persistPage` 失败，屏幕上仍是旧页，而磁盘/内存设置已变。这是真实的
跨提交顺序缺陷，正常字号 UI 通过不能替代。

处理：`runPage` 增加 `PagePublish` 钩子，把「存储外观保存」并入同一次 `task.commit`，
顺序为 `persistPage` → `accept` → 保存设置。因此：

- 取消只可能在 commit 之前生效（`HostTask.commit` 一置 committing，后续 `check()` 不再抛），
  被取消的请求不会碰磁盘或内存设置；
- 进度/渲染任何一步失败都不会保存设置；
- 设置保存是 commit 里唯一的 fallible 步骤，失败时 `readingPreferences` 尚未替换，
  磁盘与内存一致，界面仍是旧 frame，`font_label` 仍是旧字号；
- 不靠屏蔽取消、也不靠吞掉保存错误。

审阅点二：`0e5c6cfa` 删掉了 `More → 本地字体` 前的 `operation==0&&!pageBusy`。复核真实
owner 路径后确认**这个删除没有必要**，已恢复：`leaveReader()`（`MainActivity:667`）在把
书架显示出来之前就把 `operation=0`、`pageBusy=false` 清零，driver 的 `shelf()` 又会先等
`import_button` 可见，所以点击发生时两个标志本来就是 0；`40280046571` 的字体面板也确实
已经打开（`invalid_font…` 随后报 `UI expected shelf More`，说明有面板盖住书架）。删除它
只是降低了产品约束，与 driver 无关。面板内的选择/删除/lease 仍走 worker 串行与模块 BUSY。

同时回退一处 candidate 越权：`candidate.py` 曾把冻结 driver 的
`device.wait(Until.hasObject(By.pkg(APP)), 10000);` 改成硬断言「picker must return to the
reader」。`40280046571` 的 review `duplicate_late_cancel_keeps_original` 正是栽在这条 10 秒
硬门上（冻结 driver 自身只做宽容等待，随后仍有 20 秒 `awaitText` 真判定）。candidate 现在
只做公开标题 stem+格式投影与 JSON 编译修复，并显式断言该冻结语句原样保留。

新增两个聚焦检查（真实取消 / 真实设置保存失败），注册进 `run_ui.py` 的 first 期望序列与
`report.py` 的必需集合（只增不减）：

| 新检查 | 做法 |
| --- | --- |
| `quick_size_cancel_keeps_accepted_frame_and_stored_appearance` | `review_pause page-before-render` 真实卡住 A+ 的翻页请求，点取消后核对：内存 `ReadingPreferences.font`、`reading-settings/preferences.json` 字节、已接受 frame 的像素哈希、`font_label` 四项全部未变；离开阅读后 lease 归零 |
| `quick_size_settings_failure_keeps_frame_and_stored_appearance` | `review_fail_preferences`（仅 DEBUG，与既有 `review_fail_progress` 同类注入）让设置保存真实失败，核对状态显示 `Reading settings were not saved`，且上述四项一致未变、lease 归零 |

## 5. 最小 diff

| 文件 | 改动 |
| --- | --- |
| `examples/android/app/src/main/java/org/exreader/host/MainActivity.java` | 快捷字号回到 `runPage` 普通翻页事务（真实 loading/cancel、`Font size N` 状态、保持已接受位置）；`runPage` 新增 `PagePublish`，把设置保存并入同一 commit 且置于 `accept` 之后；`keepAppearanceSize` 只在保存成功后替换 `readingPreferences`，含 DEBUG 注入；恢复 `More → 本地字体` 的 `operation/pageBusy` 约束 |
| `examples/android/app/src/main/java/org/exreader/host/FontPanel.java` | 面板常驻提示行（`字体仅用于 EPUB 阅读排版；选择后下次打开书籍生效`）不再被加载状态覆盖，状态用 `say()` 组合；不删除任何断言 |
| `tests/reader_wave3_c11/java/org/exreader/host/Wave3UiTest.java` | 新增 `quickSize()` 两个检查与 `settle/configure/byId/appearance/storedAppearance` 辅助；`described(value,contains)` 失败时附上实际状态文本；取消回执断言消息带上 `status/items/format` |
| `tests/reader_wave3_c11/candidate.py` | 回退对冻结 picker 语句的硬断言，并断言该语句原样保留 |
| `tests/reader_wave3_c11/run_ui.py`、`report.py` | 两个新检查加入 first 的期望序列与必需集合（18 → 20） |
| `tests/reader_wave3_c11/evidence.py`、`guard.py`、`.github/workflows/reader-wave3-c11-java.yml` | 新增 Actions-only 工件审计脚本；guard 自有路径不变；java 工作流增加 `audit_run_id` 输入与 `evidence` 作业（只下载/解析原工件，不构建） |

没有改动：`apps/reader/**`、SDK/`src`/`include`/`bindings`、旧 driver（`examples/android/uitest`）、
`tests/reader_android_*`、`tests/reader_host_session_android`、manifest、其它工作流。

## 6. 明确未主张与未执行

- wave3 `cancel`/`restore` 两阶段仍未执行，不算通过。
- wave3 first 仍有 2 个真实失败，首因都在冻结模块的 `open("/")`；宿主侧无法修复，
  需要模块 owner 或环境侧处理。
- 六平台、真机、TalkBack 人工读屏、性能、完整产品均未主张。
- 未创建 PR/tag/Release，未改默认分支，未使用 cpuse，未启动子代理。
- 本包只用了 1 次新增完整云端轮（40352736333），不重置原有失败预算；后续完整轮由 root 统一安排。

## 7. 复跑入口

```bash
# 只编译真实 host + test Java（不执行 native）
gh workflow run reader-wave3-c11-java.yml --ref codex/dsf-android-ui-close

# 在 Actions 内审计某个已完成轮的工件（不构建、不跑设备）
gh workflow run reader-wave3-c11-java.yml --ref codex/dsf-android-ui-close -f audit_run_id=<run_id>

# 完整轮（由 root 统一安排，本包不再自开）
gh workflow run reader-wave3-c11.yml --ref codex/dsf-android-ui-close
```
