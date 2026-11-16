# D-FINAL-B · F08 / F09 / F10 补充证据审计

本轮出口：**F08 pending / F09 pending / F10 pending**；最终本机与Actions全量CTest均**598/598**，加强检查均**7/7**，prepush **exit0**。[草稿PR #215](https://github.com/NoGod3524/EXReader/pull/215)，base=main。

基线 `origin/main` = `38a7031827d5664fd4dd6e8166c9135a7d829355`，新分支 `codex/dfinal-b-evidence-followup`，PR base `main`。上一轮实现和报告已由 PR #210 合入，本轮保留它们并继续补缺口。本机 Windows 11 / MSVC 19.44 / Python 3.14；本机与 Actions 结果分别登记。

当前基线实数是 **99 verified / 0 partial / 9 pending**，固定 108，分组 12 / 84 / 12。任务中的 99 / 1 / 8 是较早快照；随后 D-FINAL-C 将 `H.ipad.annotation_exchange` 由 partial 改为 pending（`docs/reader-total-progress/dfinal-c-audit.md:66`–`:67`）。本轮不改回该条目，详见 [独立台账复核](ledger-review.md)。

## 验收原文与 verified 定义

实际 catalog v1 **没有 `acceptance` 字段**；下面逐字引用三项固定 `title`，结合 scope_document 解释所需证据，不补造字段。

| 项 | 原文及行号 | 什么证据才算 verified（一句话） |
| --- | --- | --- |
| F08 | `docs/reader-total-progress/catalog.json:1704`：「固定书库/平台的产品帧时间、内存及可交互预算获真实验收」 | 同源六目标完整产品在固定设备/runner、固定规模真实书库与负载上保留呈现帧 p50/p95、独立峰值内存、首次可交互和相对预算的真实验收产物，SDK/渲染函数结果不能替代产品 UI（`docs/READER-PRODUCT-PLAN.md:156`、`:195`–`:196`）。 |
| F09 | `docs/reader-total-progress/catalog.json:1712`：「默认简洁且完整功能可达，六端完整键盘/可访问性与读屏证据分列」 | 六端分别保留简洁默认入口和全部功能真实可达、每个交互控件的名称/角色/完整键盘焦点顺序，并独立登记真实读屏输出（`docs/READER-PRODUCT-PLAN.md:157`、`:191`–`:193`）。 |
| F10 | `docs/reader-total-progress/catalog.json:1720`：「全链路隐私/凭据/文件稳定性/临时文件清理的真实安全出口」 | 六端宿主全链路验证平台安全存储及不可用时会话回退、凭据不进入日志/库/载荷、TLS/跨源隔离、稳定私有文件、原子发布和正常/失败/崩溃后的临时文件处置（`docs/READER-PRODUCT-PLAN.md:165`、`:168`、`:185`–`:187`）。 |

已读 `docs/reader-total-progress/README.md`、`LEDGER-AUTHORITY.md`、C02 handoff 与上一轮 [REPORT.md](../dfinal-b-20261114/REPORT.md)。当前任务明确授权本机测试、三项台账更新及 main-base 分支交付；其余历史限制和未验证范围继续保留。

## F08

| 已有证据文件 / 测试名 | 该记录最近实际结果 | 限定范围 |
| --- | --- | --- |
| `docs/validation/reader-perf-windows.json`；`tests/reader_perf_windows/perf_windows.py` / `verify_perf_windows.py` | round2 run `40086319655` success；2202 原件书库，冷/热首屏可交互、翻页/搜索和进程峰值 | 原记录明确没有产品帧时间与预算验收；旧源码，不转授当前候选。 |
| `docs/validation/reader-perf-gtk.json`；`tests/reader_perf_gtk/` | run `40086971620` cloud-verified | `frame_time_percentiles=false`。 |
| `evidence/dfinal-b-20261114/new-checks.txt`；`windows-selection-render-budget` | 本机与 run `43650195610` 对应检查通过；旧全量 597/597 | 两 cohort 共享累计峰值，只检查宿主渲染重复性；真实原书基准整体 exit1，pg10 为 EXR_LIMIT。 |

以上为仓库存档最新结果；未把历史 ZIP 重新认证说成本轮重跑。上一轮 API 核对留在 `evidence/dfinal-b-20261114/historical-run-api.json`。

本轮修改 `check_shell_budget.inc` / `render_budget.py`：

- 每个 baseline/candidate 采样各启动独立进程，各书 3 对、顺序交替 AB/BA；每进程 8 次预热 + 64 次页 0/1 交替。默认同二进制重复性；可显式提供基线二进制和 source，不能把默认模式称作跨 revision 回归。
- 保存所有原始 render 样本，由 Python 独立复算 p50 和 nearest-rank p95，并核对 C 输出；内存峰值不再由同一进程共享。记录 book/font/binary/manifest/exporter 散列、源码、OS/CPU/核数/命令，未采集的 RAM/编译信息明确 unknown，实际编译参数另见 configure/build 日志。
- 门槛仅为同机相对比值：p50/p95/setup-render-ready <2.5、独立峰值内存 <1.25。setup 是布局至首张位图就绪，**不是首次可交互**。每份报告 `advisory=true / accepted=false / product_budget_accepted=false`。
- 三本原书仍固定 pg1 / pg10 / pg11 的原始 SHA-256；补原来源 URL，URL 当前内容若改变须拒绝换样本。pg10 的原失败没有改为预期通过。
- `windows-render-budget-report-contract` 覆盖原始样本缺失/重复/非有限/零值、摘要不一致、时间和内存超比值及阈值等号反例。`windows-selection-render-budget` 实跑生产宿主渲染路径并输出逐次样本。

缺失产物逐端登记：

| 平台 | 缺什么 / 需要什么环境 |
| --- | --- |
| Windows | 当前完整产品固定规模已导入书架的呈现帧 p50/p95、首次可交互、峰值内存及同机基线 revision 相对预算；需能采集真实呈现/交互的 Windows 桌面 runner。当前三本顺序渲染不代表数千书书架。 |
| Linux | GTK 当前宿主同负载的 frame-clock/交互/内存及预算；需 GTK 桌面 runner。 |
| macOS | 当前原生宿主固定书库的呈现/内存/交互与相对预算；需 macOS runner。 |
| iPhone | 固定 iPhone 配置上的完整产品采样；模拟器单列，**需真机**。 |
| iPad | 固定 iPad 配置上的独立完整产品采样，**需真机**。 |
| Android | 固定 Android 配置的完整产品采样；emulator 单列，**需真机**。 |

最终 **pending**：本轮增加可重算、独立峰值的宿主基准；完整产品呈现与交互预算仍缺。

## F09

完整六端表、控件清单及运行入口见 [F09.md](F09.md)。

| 平台 | 已有文件 / 测试名 / 存档最近实际结果 | 缺失产物 |
| --- | --- | --- |
| Windows | `docs/validation/reader-a11y-windows.json`；`run_audit.py`；run `40084309431` job success，但 34 pass / 9 fail / 5 gap / 1 not_verified，accepted=false；20261110 run5 四面 UIA 存档 | 当前全部功能和全部对话框、完整 Tab/Shift+Tab/方向键及 Narrator/NVDA 语音；当前完整产品入口。 |
| Linux | `reader-a11y-gtk.json`；`audit_gtk_a11y.py`；run `40082300842` failure，6 blocking finding | GTK/AT-SPI 全控件和键盘、Orca 语音；需 Linux 桌面 runner。 |
| macOS | `reader-a11y-apple.json`；`A11yAuditTests.swift`；run `40096206815`，403 pass / 4 fail | 当前全部功能键盘和 VoiceOver；需 macOS runner/桌面。 |
| iPhone | 同 Apple run，434 pass / 14 fail | 完整焦点/外接键盘和 VoiceOver，**需真机**。 |
| iPad | 同 Apple run，442 pass / 8 fail | 独立完整焦点/外接键盘和 VoiceOver，**需真机**。 |
| Android | `reader-a11y-android.json`；`A11yAuditTest.java`；run `40082957400` success，但 accepted=false、talkback_speech_verified=false | 全控件、键盘/D-pad 和 TalkBack，**需真机**；emulator 单列。 |

上表省略前缀的 JSON 均在 `docs/validation/`。

六端证据分列（历史回归通过数不授予当前完整范围）：

| 平台 | 控件名称/角色 | 完整键盘/焦点顺序 | 独立读屏语音 | 当前执行环境缺口 |
| --- | --- | --- | --- | --- |
| Windows | 本轮五面 12/21/48/30/8 控件通过；未打开面板缺 | 缺；本轮前台失败，SendInput 未执行 | 缺 Narrator/NVDA 实录 | 可取 UIA；需交互桌面完成键盘/语音及完整产品 |
| Linux | 旧 AT-SPI 审计含6 blocking；当前缺 | 缺 | 缺 Orca 实录 | 需 GTK/AT-SPI Linux 桌面 runner |
| macOS | 旧403 pass/4 fail；当前缺 | 缺 | 缺 VoiceOver 实录 | 需 Apple runner/桌面 |
| iPhone | 旧434 pass/14 fail，模拟器；当前缺 | 缺完整焦点/外接键盘 | 缺 VoiceOver 实录 | 需 iPhone 真机 |
| iPad | 旧442 pass/8 fail，模拟器；当前缺 | 缺独立完整焦点/外接键盘 | 缺 VoiceOver 实录 | 需 iPad 真机 |
| Android | 旧 emulator 审计未接受；当前缺 | 缺键盘/D-pad 完整遍历 | 缺 TalkBack 实录 | 需 Android 真机 |

本轮补强：递归检查所有捕获节点，不按 ID 白名单放行；将支持操作 pattern 的 custom 控件纳入名称/角色检查；UIA 子枚举异常、截断、子数不一致、错误属性类型均失败。焦点只能关联 SendInput 后实际观测、HWND/PID/automation_id/role/name 全部一致的节点；PostMessage、同名/复用句柄/另一进程均不授予键盘证据。修正 report scope，使全控件记录兼容现有 verifier，并把 all-controls.json 纳入 artifact 摘要。

`EXReaderAudit` 从当前生产 `examples/reader.c` 和现有壳源编译，供 `capture_shell.py` 在私有数据目录采集当前节点。名称/角色、实测焦点步骤、完整键盘、读屏分别标记；未采样面保留缺口。没有增加绑定字体轮廓或固定 CJK 字形的断言，沿用宿主字体回退。

本轮当前壳真实输出（完整日志 `F09-current-uia-final.txt`，逐节点 `F09-current-uia-final/all-controls.json`）：

```text
closed: controls=12 name_role_passed=True observed_keyboard_controls=0
search: controls=21 name_role_passed=True observed_keyboard_controls=0
settings: controls=48 name_role_passed=True observed_keyboard_controls=0
toc: controls=30 name_role_passed=True observed_keyboard_controls=0
shelf: controls=8 name_role_passed=True observed_keyboard_controls=0
complete_keyboard_verified=false; screen_reader_verified=false
exit=0
```

真实 SendInput 前台测试先 exit1：`RuntimeError: owned host cannot take foreground`，没有送出按键。之后仅用 UIA InvokePattern 采集，未把 Invoke 解释成键盘证据。前期 UIA 路由 ID 过时的失败另存 `F09-current-uia.txt`。`F09-surface-coverage.json` 清点全部 76 原生构造位置和 35 共享 helper 调用点；未唯一映射的构造位置和未打开面板逐行标缺（包括标注、词典、WebDAV、OPDS、书架 metadata、文档编辑、TTS、系统文件选择器）。

自动审批拒绝删除三份隔离 profile 的 host-data，仅返回 `blocked by policy`，没有重试；这些目录保留本机并由本证据目录 `.gitignore` 排除，不属于已通过的 F10 临时目录清理证据。

最终 **pending**：当前采样和断言不能覆盖六端全部功能与真实读屏。

## F10

凭据位置、权限、所有已追踪临时路径与六端完整表见 [F10.md](F10.md)。

| 已有证据 / 测试名 | 该记录最近实际结果 | 边界 |
| --- | --- | --- |
| `docs/validation/reader-credentials.json`；`tests/reader_credentials/consumer/suite.c` | run `40057087875` success；Windows24/Linux34/macOS29/iOS simulator23/Android emulator46 checks | 独立凭据模块；安全存储不可用、锁屏/故障和实际壳接入缺口保留。 |
| `docs/reader-total-progress/webdav-suite-results.md` | component seal 82 cases / 880 assertions / 38 negatives | 原文明确不授予 full_F10。 |
| `examples/windows/check_shell_sync.inc`；`windows-selection-sync` | 上一轮本机/Actions 通过；本轮再次保留 15 scenarios 的真实网络、落盘扫描、DPAPI 篡改拒绝与删除检查 | 不替代完整 TLS/跨用户和六端宿主链路。 |
| `check_shell_privacy.inc`；`windows-privacy-cleanup` | 上一轮测试观察到继承 DACL 与 exit77 侧文件残留；本轮增加真实生产修复和负例 | 正常测试目录自清理不等于产品启动清扫。 |

审计发现：`extras/credentials/src/windows.c` 使用当前用户 Credential Manager；当前 Windows 壳的 `shell_sync.inc` 实际保存 `<data>/sync.cred`，使用当前用户 DPAPI，旧版继承目录 DACL。它与计划要求的 Credential Manager 接入仍有差异。

本轮生产修复为 **新保存/替换的 DPAPI 凭据**创建 protected 当前用户/SYSTEM DACL，权限在写出任何密文字节前生效；私有侧文件 CREATE_NEW，拒绝已有占位/硬链接/目录。发布失败删除本次创建的侧文件并保留旧密文。真实测试读取 DACL 的 ACE/SID/继承标志，覆盖初建、替换、硬链接/目录碰撞、锁住目标的失败保存及旧凭据可读。旧文件权限没有自动迁移，未冒称已迁移。

| 平台 | 缺失产物 / 所需环境 |
| --- | --- |
| Windows | Credential Manager 与不可用时会话回退、旧文件 ACL 迁移、第二用户读取/DPAPI 拒绝；真实强杀后启动对 `.tmp/.part` 的安全回收；PDF/选择器/OPDS 稳定文件与链接替换全过程；当前候选 HTTPS/证书/跨源和全链路日志/库/载荷扫描。跨用户需 runner 配置第二身份。 |
| Linux | 当前 GTK Secret Service 权限/锁定/会话回退、稳定私有文件、TLS/日志与崩溃/重启残留；需私有 D-Bus/Secret Service 的 Linux runner。 |
| macOS | 当前宿主 Keychain 权限/锁定、安全作用域 URL、取消/强杀/重启临时清理及完整 TLS/隐私扫描；需 macOS runner/桌面。 |
| iPhone | Keychain 锁屏/解锁/仅设备保护、系统文件与 URL 生命周期、崩溃恢复及全链路输出，**需真机**。 |
| iPad | iPad 独立 Keychain/多窗口/后台/选择器持有及崩溃清理产物，**需真机**。 |
| Android | Keystore 故障/锁定/重装备份、URI grant/私有拷贝、强杀残留及 TLS/日志，**需真机**。 |

最终 **pending**：新凭据文件权限和私有侧文件碰撞问题已修复；崩溃回收与六端安全出口未完成。

## 台账与交付检查

`catalog.diff` 是实际 diff，仅改变 F08/F09/F10。三项 state 均保持 pending。F10 evidence 引用现有已注册历史组件键 credentials/sideload/batch/sync，并明确限定范围；F08/F09 没有合法 perf/a11y 证据键，仍为 []。`tools/reader_composition/total_progress.py:630`–`:633` 强制 evidence 元素为顶层注册键，因此缺口与本轮报告写在对应 note；没有把路径/缺口文字塞成无效证据键，也没有扩展未经验证的 schema。

`audit-scope.json` 验证 108、12/84/12、99/0/9；其他条目与顶层历史证据字节语义不变；`tests/check_reading_release.py` 与基线字节一致。性能毫秒为观测值，门槛只使用同机比值。

完整命令和 exit 分别保存在 `configure-exit.json`、`build-exit.json`、`ctest-exit.json`、`new-checks-exit.json`、`prepush-exit.json`。全量 CTest 仅排除 `sdk-release|sdk-doc-coverage`，完整逐项输出交付为 [ctest.txt](ctest.txt)，JUnit 为 [ctest.xml](ctest.xml)；新增/加强的完整原始输出见 [new-checks.txt](new-checks.txt)。

首次本机 configure 因 PATH 大小写遗漏导致找不到 cl，修正后又发现旧 cache 误用了 MinGW ld；随后显式指定 MSVC cl/link/lib，configure 和完整 build 均 exit0。两次失败保存在 `configure-initial-failed.*` / `configure-toolchain-failed.*`，没有关闭测试或编译警告掩盖错误。

最终实测结果在下面追加；原始文件中的失败与未测记录均保留。

## 首轮 Actions 输出（剪贴板修复前）

run [43668575262](https://github.com/NoGod3524/EXReader/actions/runs/43668575262)，受测源码 `3e6f792c90cad6d1154dd0a74b25dd176ebd2aba`，job `132673330025`，Windows-2022。Configure/Compile/Full CTest/New checks 全部 success。

```text
598/598 Test #513: windows-selection-render-budget .................... Passed 0.09 sec
100% tests passed, 0 tests failed out of 598
Total Test time (real) = 155.40 sec

100% tests passed, 0 tests failed out of 6
Total Test time (real) = 19.25 sec
```

完整逐测试原文：[actions/ctest.txt](actions/ctest.txt)、[actions/ctest.xml](actions/ctest.xml)、[actions/new-checks.txt](actions/new-checks.txt)，编译原文 `actions/build.txt`。这里仅排除 `sdk-release|sdk-doc-coverage`，没有跳过首轮本机失败的三项。Actions 和本机是独立环境，性能数据不互借。

原始 ZIP [actions.zip](actions.zip)，artifact `14143388512`，72927 bytes，下载后实算并匹配 API digest：`d1fd6de10b3ab1127b41ed083c99b75e61d36813d469e6b6788db75c1d4a7d6b`。源码/run/job/artifact 绑定见 [actions-identity.json](actions-identity.json)；原 ZIP 与解包日志一同保留。

## 夹具字体管线检查（保留）

该轮使用1176-byte测试字体 `tests/fixtures/fonts/primary.ttf`，只作为管线检查；下节为宿主字体实际原书负载。

完整命令/退出码：`render-realbooks-fixturefont-exit.json`；逐次原始输出：`render-realbooks-fixturefont.txt`；可重算数据及二进制/字体/导出器身份：`render-realbooks-fixturefont.json`。本轮在全量测试之间单独采样，基线和候选为同一二进制，3 对独立进程/书，不能称为跨 revision 产品预算。

下表 p50/p95 从每书候选侧 3×64=192 个原始渲染样本合并重算；峰值为三次进程生命周期峰值的最大值。相对诊断使用各进程统计量的中位数之比，四个比值依次是 render p50 / render p95 / peak working set / setup-render-ready。

| 原书 | 宿主渲染 p50 / p95 (ms) | 观测峰值 bytes | 四个同机相对比值 | 实际结果 |
| --- | --- | --- | --- | --- |
| pg1.epub | 21.416450 / 43.158000 | 47984640 | 0.963404 / 0.801597 / 0.999744 / 1.002600 | 数据采集成功；相对诊断未超门槛 |
| pg10.epub | 缺 | 缺 | 缺 | baseline/candidate 各3次均 exit1，EXR_LIMIT(6) |
| pg11.epub | 11.378750 / 19.875200 | 23998464 | 1.257775 / 1.212439 / 0.998124 / 1.114746 | 数据采集成功；相对诊断未超门槛 |

整个命令 **exit 1 / passed=false / accepted=false**，原因是固定书单中的 pg10 缺有效样本。没有替换原书、改失败期望或把它从分母中删除。上述时间是布局/渲染函数观测，不是真实显示帧或首次可交互。


## 新增/加强测试真实输出

本轮编译 exit0；测试名：`windows-selection-render-budget`、`windows-render-budget-report-contract`、`windows-a11y-control-contract`、`windows-a11y-control-inventory`、`windows-privacy-cleanup`，并保留 `windows-selection-sync` 原15场景；加强第七项 `windows-selection-keyboard` 的哨兵/序列检查。完整 verbose 原文交付在 `new-checks.txt`。

```text
498: CREDENTIALS password/username absent from all files; DPAPI blob roundtrip ok; tampered blob rejected; delete removes file
498: PASS sync: 15 scenarios; HWNDs created=0
499: PRIVACY sync.cred protected current-user/SYSTEM owner/DACL=O:S-1-5-21-4022989615-4255484600-3434952574-1001D:P(A;;FA;;;SY)(A;;FA;;;S-1-5-21-4022989615-4255484600-3434952574-1001)
499: PRIVACY sync.cred protected current-user/SYSTEM owner/DACL=O:S-1-5-21-4022989615-4255484600-3434952574-1001D:P(A;;FA;;;SY)(A;;FA;;;S-1-5-21-4022989615-4255484600-3434952574-1001)
499: PRIVACY sync.cred protected current-user/SYSTEM owner/DACL=O:S-1-5-21-4022989615-4255484600-3434952574-1001D:P(A;;FA;;;SY)(A;;FA;;;S-1-5-21-4022989615-4255484600-3434952574-1001)
499: PRIVACY private credential replacement: hard-link/directory collision refused; failed publish preserved old blob and removed owned .tmp
499: PRIVACY atomic publish failure: original preserved; .tmp absent
499: PRIVACY abrupt exit=77: original preserved; .tmp remains (startup scavenger MISSING)
499: PRIVACY isolated test directory empty and removed
501: PASS fresh-process budget contract: raw p50/p95 verified; missing/duplicate/nonfinite/zero/mismatched samples rejected; memory/time regressions rejected
502: PASS UIA contract: nested/action-pattern controls; malformed/incomplete trees rejected; exact observed focus identity only; complete keyboard/speech remain missing
503: PASS inventory: 76 creation sites, 31 name registration sites; unnamed/dynamic sites retained
100% tests passed out of 7
Total Test time (real) =  19.58 sec
```

## 首轮失败与复核

`ctest-first-failed.txt/.xml`：595/598，exit8，完整512.02s。`native-docx-footnotes-ui` timeout；`windows-selection-keyboard` 在读取系统剪贴板断言失败；`windows-selection-render-budget` 的同进程重复 p95 比值4.700786超过2.5，原始样本保留。

初期复核未放宽任何断言/门槛/timeout。独立复跑 `failed-isolated.txt` 两项2/2 exit0（DOCX UI1.20s，render p95 ratio1.162076）；`keyboard-isolated.txt`1/1 exit0。键盘测试用 SetKeyboardState/SendMessage，当时诊断不足，尚未证明剪贴板争用。随后 `--parallel 1` 本机第二轮仍597/598，exit8，928.40s，仅同一个键盘复制断言失败；原文 `ctest-serial-failed.txt/.xml`。进一步实测与修复如下，原始两个失败全量均保留。

## catalog 实际 diff

以下为基线 `38a70318` 至本轮的原始 diff；其他105条不变，state全保留pending，108分母不变。

```diff
diff --git a/docs/reader-total-progress/catalog.json b/docs/reader-total-progress/catalog.json
index bedefd21..ae1b9590 100644
--- a/docs/reader-total-progress/catalog.json
+++ b/docs/reader-total-progress/catalog.json
@@ -1704,7 +1704,7 @@
       "title": "固定书库/平台的产品帧时间、内存及可交互预算获真实验收",
       "state": "pending",
       "evidence": [],
-      "note": "evidence/dfinal-b-20261114/REPORT.md#f08：本机宿主渲染路径、固定原书散列和相对重复预算；缺六端固定规模产品书架的呈现帧 p50/p95、峰值内存、首次可交互预算及同源 runner 验收，保持 pending；本机/Actions 补充测试见报告，完整产品出口仍未验收。"
+      "note": "evidence/dfinal-b-followup-20261114/REPORT.md#f08：独立进程固定原书相对基准，保留原始样本并复算 p50/p95 与独立峰值内存；缺六端固定规模产品书架的呈现帧、首次可交互及同源设备/runner预算验收，保持 pending。"
     },
     {
       "id": "F09",
@@ -1712,15 +1712,20 @@
       "title": "默认简洁且完整功能可达，六端完整键盘/可访问性与读屏证据分列",
       "state": "pending",
       "evidence": [],
-      "note": "evidence/dfinal-b-20261114/REPORT.md#f09：全创建位置源码清单、递归 UIA 控件断言及历史快照重读；缺六端当前程序全部功能可达、完整键盘焦点顺序和独立读屏实录，移动端需真机，保持 pending；本机/Actions 补充测试见报告，完整产品出口仍未验收。"
+      "note": "evidence/dfinal-b-followup-20261114/REPORT.md#f09：全部捕获控件名称/角色断言、失败闭合的 UIA 遍历及精确焦点关联；当前 Windows 壳采样和六端已有证据分列。缺全部功能/控件完整键盘与独立读屏实录，iPhone/iPad/Android需真机，保持 pending。"
     },
     {
       "id": "F10",
       "group": "final",
       "title": "全链路隐私/凭据/文件稳定性/临时文件清理的真实安全出口",
       "state": "pending",
-      "evidence": [],
-      "note": "evidence/dfinal-b-20261114/REPORT.md#f10：Windows DPAPI 实际 DACL、原子写入失败清理和异常退出残留诊断；缺崩溃侧文件启动回收及六端权限隔离、TLS/跨源凭据/文件稳定性全链路同源验收，保持 pending；本机/Actions 补充测试见报告，完整产品出口仍未验收。"
+      "evidence": [
+        "credentials",
+        "sideload",
+        "batch",
+        "sync"
+      ],
+      "note": "evidence/dfinal-b-followup-20261114/REPORT.md#f10：evidence 仅为历史组件凭据/侧载/批量导入/同步证据，非全链路授予。本轮 Windows 新保存 DPAPI 凭据收紧当前用户/SYSTEM权限、独占临时文件及失败清理实测；缺 Credential Manager/会话回退、旧文件迁移、崩溃回收和六端安全链路验收，保持 pending。"
     },
     {
       "id": "F11",

```

## 宿主字体的真实原书基准

最终源码 `eb1813a9435b3c15d281044b6da638612da60998`；固定 `C:/Windows/Fonts/segoeui.ttf`，960076 bytes，SHA-256 `704eada12961a27fd271f7d3b09e2066520e758390c1776744eff430fee30f6e`。英文Gutenberg负载，未授予CJK字体/回退性能。完整命令、独立进程原始样本和身份：`render-realbooks-exit.json`、`render-realbooks.txt`、`render-realbooks.json`。修复前同宿主字体原始数据另存 `render-realbooks-before-clipboard.*`。

每书候选侧合并192原始样本重算p50/p95；峰值取3个进程高水位最大值。比值按每进程统计中位数计算，依次p50/p95/peak/setup-ready。采样在本机全量+补充测试结束后单独运行，其他后台负载未控制。

| 原书 | 宿主 render p50 / p95 (ms) | 峰值 bytes | 四个同机比值 | 真实结果 |
| --- | --- | --- | --- | --- |
| pg1.epub | 23.752600 / 53.535700 | 49135616 | 1.030011 / 1.045824 / 0.999666 / 1.079302 | 采集成功，相对诊断未超门槛 |
| pg10.epub | 缺 | 缺 | 缺 | 6次EXR_LIMIT(6)，缺样本 |
| pg11.epub | 8.032800 / 12.944200 | 25120768 | 1.043832 / 0.992572 / 0.998859 / 0.956600 | 采集成功，相对诊断未超门槛 |

整个基准**exit1 / passed=false / advisory=true / accepted=false**；pg10没有替换、移除或改为预期通过。真实显示帧和首次可交互仍缺，F08保持pending。

## 剪贴板真实故障、修复与加强检查

最终实现源码 `eb1813a9435b3c15d281044b6da638612da60998`。诊断版40次重复：38通过/2失败；两次失败都有 `write-open-failed` 和 `read-open-failed`，`error=5`、序列未变，`open_pid=6392`。进程核对是外部 `GameViewer.exe`，完整输出 `keyboard-repeat-40.txt`，进程记录 `keyboard-lock-process.json`，原因与历次假设分列在 `keyboard-diagnosis.md`。没有记录剪贴板内容。

另发现旧 Alpha 可能遗留，让一次失败的复制碰巧通过 substring 断言。本轮测试先写非 Alpha 哨兵，再保留原 Alpha 断言并新增 clipboard sequence 必须变化，避免遗留值假通过。生产 `clipboard_set` 与测试读取共用 `clipboard_open`：仅对 ERROR_ACCESS_DENIED 每5ms等待，200ms截止，其他错误/超时仍失败。这是共享资源获取期限，不是F08性能毫秒门槛。失败诊断仅编入 TEST_DRIVERS，不把选择文字写进普通产品日志。

重编译后40/40通过，harness exit0，原文 `keyboard-repeat-fixed-40.txt`；这40次每一次都包含新增哨兵与序列断言。DOCX隐藏窗口测试使用DirectWrite/D2D/GDI，与原有selection测试一样设RUN_SERIAL；保留原90s timeout和所有断言。真实CTest属性导出 `final-test-properties.json`，确认editor/keyboard/render三项独占。

最终当前壳再次实测 `F09-current-uia-fixed.txt`，12/21/48/30/8节点名称/角色均通过，exit0；逐控件 `F09-current-uia-fixed/all-controls.json`。最终EXReaderAudit二进制SHA-256 `0f1e6e04b98d09d613babb1fe9f059f7c3fb58ed39361c188499f4fdb6dd4d3d`。仍为UIA-only、0个实测键盘节点，完整键盘/读屏仍缺，不转授六端F09。

源码覆盖清单在修复后重新生成，包含最终文件SHA-256和全部76构造位置/35 helper调用位置；此前未打开的面板仍逐项缺证。

## 本机最终实测输出

最终源码 `eb1813a9435b3c15d281044b6da638612da60998`，MSVC完整编译exit0；全量CTest **598/598、exit0**；新增/加强verbose **7/7、exit0**。仅排除sdk-release和sdk-doc-coverage，原失败三项全部保留并实际通过。`audit-scope.json`核验其他条目、分母、禁改文件及受测实现字节语义未变。

```text
596/598 Test #504: windows-selection-copy .............................   Passed    0.06 sec
        Start 506: windows-selection-raster
597/598 Test #506: windows-selection-raster ...........................   Passed    0.06 sec
        Start 505: windows-selection-keyboard
598/598 Test #505: windows-selection-keyboard .........................   Passed    0.05 sec

100% tests passed out of 598

Label Time Summary:
headless    =  25.73 sec*proc (4 tests)

Total Test time (real) = 223.08 sec
```

prepush原始输出（命令/exit0见prepush-exit.json）：

```text
ok    无冲突标记残留
ok    code/docs 结构扫描
ok    check_sdk_docs.py

全部通过 —— 可以推
exit=0
```

## 最终 Actions 同源出口

run [43670328781](https://github.com/NoGod3524/EXReader/actions/runs/43670328781)，源码 `eb1813a9435b3c15d281044b6da638612da60998`，job `132678732957`，windows-2022；配置、编译、全量与加强检查全部success。

```text
598/598 Test #513: windows-selection-render-budget .................... Passed 0.10 sec
100% tests passed, 0 tests failed out of 598
Total Test time (real) = 156.08 sec

100% tests passed, 0 tests failed out of 7
Total Test time (real) = 18.79 sec
```

完整原始输出：[actions-final/ctest.txt](actions-final/ctest.txt)、[actions-final/ctest.xml](actions-final/ctest.xml)、[actions-final/new-checks.txt](actions-final/new-checks.txt)、`actions-final/build.txt`。完整原ZIP：[actions-final.zip](actions-final.zip)，artifact `14144500903`，72978 bytes；下载后实算SHA-256与GitHub API digest逐字节匹配：`9b78962b438563b28a5e0c7611494a6cac449090b0d8a216dcc15eafab009c4e`。绑定元数据：[actions-final-identity.json](actions-final-identity.json)。仅排除sdk-release/sdk-doc-coverage；JUnit 598、failures=0、skipped=0。

最终MSVC编译、全量CTest、7项加强检查、40次哨兵剪贴板重复与当前UIA采样均有真实产物。原两轮本机失败、修复前38/40、前台键盘不可用和pg10的EXR_LIMIT均保留。报告之后只提交证据/文档，不把它称为另一轮新代码验收。

## 最终 state 与本机不可验证的项

- **F08 pending**：新增宿主渲染基准已经可重算；缺六端固定规模完整产品的真实显示帧/首次可交互及冻结预算，固定原书pg10仍缺有效数据。
- **F09 pending**：当前采样面的名称/角色、复制稳定性有实证；全部功能/全部面板完整键盘、实际读屏语音仍缺，六端不能互相转授。
- **F10 pending**：Windows新凭据ACL与私有侧文件碰撞/失败清理已修复；安全存储接入/会话回退、旧文件迁移、第二身份权限拒绝、崩溃启动清扫和六端完整安全链路仍缺。

需特定runner：Windows交互桌面/呈现采集和第二身份；Linux GTK+AT-SPI+Orca及Secret Service；macOS桌面/Keychain/VoiceOver。**需真机：iPhone、iPad、Android** 的性能、外接键盘/焦点、辅助技术语音、系统文件权限、安全存储锁定与崩溃生命周期。模拟器旧结果保留独立范围。
