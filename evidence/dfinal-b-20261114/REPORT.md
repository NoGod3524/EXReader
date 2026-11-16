# D-FINAL-B：F08 / F09 / F10 证据审计

基线：`origin/main` 的 `df8e6031`；工作分支：`codex/dfinal-b-f08-f10-audit`；PR base：`main`。
本机 Windows、MSVC 19.44 / MinGW、Python 3.14；本轮本机结果与 Actions 结果分开登记。
catalog 基线 blob：`a651be85af940dfa35d633e44d39cdda5e63e4b5`。
三项均保持 **pending**。台账仍为 verified 99 / partial 1 / pending 8，分母 108，group 为 12 / 84 / 12。

## 验收定义与原文

catalog v1 没有 `acceptance` 字段。以下逐字引用实际 `title`，与 scope_document 的产品要求共同解释；没有补造 acceptance 字段。

| 项 | catalog 原文及行号 | 什么证据才足以 verified（一句话） |
| --- | --- | --- |
| F08 | `docs/reader-total-progress/catalog.json:1704`：「固定书库/平台的产品帧时间、内存及可交互预算获真实验收」 | 对同源完整产品，在固定设备/runner、固定书库规模与工作负载下，保存产品呈现帧 p50/p95、峰值内存、首次可交互及冻结预算的真实验收产物；SDK或渲染函数计时不能代替产品 UI（`docs/READER-PRODUCT-PLAN.md:156`、`:195`、`:196`）。 |
| F09 | `docs/reader-total-progress/catalog.json:1712`：「默认简洁且完整功能可达，六端完整键盘/可访问性与读屏证据分列」 | 六目标分别保留默认入口与全部功能的真实可达流程、完整控件名称/角色/键盘焦点顺序，并把读屏实际语音结果独立登记（`docs/READER-PRODUCT-PLAN.md:157`、`:191`、`:192`、`:193`）。 |
| F10 | `docs/reader-total-progress/catalog.json:1720`：「全链路隐私/凭据/文件稳定性/临时文件清理的真实安全出口」 | 对六目标宿主全链路验证安全存储/不可用时会话回退、日志/书库/载荷无凭据、TLS与跨源隔离、稳定私有文件、原子发布及正常/失败/崩溃后的临时文件处置（`docs/READER-PRODUCT-PLAN.md:165`、`:168`、`:185`、`:186`、`:187`）。 |

历史组件验证覆盖 82 个用例、880 项断言和 38 项负向测试。完整 F10 的补充验证见下文。

## F08

已有证据（下表为仓库存档结果；本轮通过 GitHub 连接器重新核对七份历史 run 的 job 结论，见 `historical-run-api.json`，未冒称全部原 ZIP 都重新认证）：

| 文件 / 测试入口 | 最近的该记录运行结果 | 限制 |
| --- | --- | --- |
| `docs/validation/reader-perf-windows.json`；`tests/reader_perf_windows/perf_windows.py`、`verify_perf_windows.py` | round 2 run `40086319655` success；固定 2202 原件书库、外部 UI 延迟和峰值工作集；原始 TXT 超限拒绝记录保留 | `not_granted` 明列无产品性能预算验收、无帧时间/呈现证据。 |
| `docs/validation/reader-perf-gtk.json`；`tests/reader_perf_gtk/` | run `40086971620`；记录为 cloud-verified | `frame_time_percentiles=false`；旧源码、没有当前六端共同预算。 |
| `tools/perf/` 与 `evidence/perf-e1-20261107/`、`evidence/l08-reflow-perf-20261113/` | 留有 SDK/重排性能实测日志 | 不是固定产品书架规模/完整 UI 验收。 |

本轮补充：`examples/windows/check_shell_budget.inc` 复用生产 `prepare_layout` / `render_reflow` / `load_frame`，每 cohort 8 次预热、64 次 0/1 页交替，输出 nearest-rank p95 和中间两样本均值 p50、进程峰值工作集。两个 cohort 同进程、同字体、同书、同几何；只约束重复 p95 比值 <2.5、峰值比值 <1.25，不设置绝对毫秒门槛。峰值是进程生命周期 high-water mark，第二 cohort 与第一共享累计峰值；这不是跨 revision 的回归验收。

`tests/reader_perf_windows/render-corpus.json` 固定三本 Gutenberg 原始 EPUB（pg1 / pg10 / pg11）的 SHA-256；`render_budget.py` 每书新进程，校验原书哈希并保存二进制、字体哈希与原始输出。只保存散列，不复制用户本机书库。

缺失产物：

| 平台 | 缺什么 / 到哪里补 |
| --- | --- |
| Windows | 当前完整产品固定规模书架的真实 present 帧 p50/p95、首次可交互、峰值内存与同机基准 revision 相对预算；需交互桌面或可采集呈现事件的 Windows runner。当前三本顺序渲染不是已导入的数千书书架。 |
| Linux | GTK 当前宿主同一负载的帧时钟/首次可交互/内存与相对预算；需 GTK/AT-SPI 可用 Linux runner。 |
| macOS | 原生宿主固定书库的呈现帧/内存/可交互与相对预算；需 macOS runner。 |
| iPhone | 固定 iPhone 配置的完整采样和预算；模拟器与真机分列，需 iPhone 真机。 |
| iPad | 固定 iPad 配置的完整采样和预算；需 iPad 真机。 |
| Android | 固定 Android 配置的完整采样和预算；需 Android 真机，模拟器只作独立记录。 |

结论：pending，新增宿主渲染重复性证据不能填充产品 UI 预算缺口。

## F09

| 平台 | 已有文件 + 测试入口 + 存档最近运行结果 | 仍缺什么 |
| --- | --- | --- |
| Windows | `docs/validation/reader-a11y-windows.json`；`tests/reader_a11y_windows/run_audit.py`；run `40084309431` success，但 49 checks 中 34 pass / 9 fail / 5 gap / 1 not_verified，`accessibility_accepted=false`；另有 20261110 C2 run5 快照 | 当前源码全功能、全部面板的外部 UIA 树，真实 Tab/Shift+Tab/方向键顺序，NVDA/Narrator 语音实录；当前字体/DPI/对比度流程。 |
| Linux | `docs/validation/reader-a11y-gtk.json`；`tests/reader_a11y_gtk/audit_gtk_a11y.py`；run `40082300842` failure（拒绝门禁），六个 blocking finding | 当前 GTK/AT-SPI 全部控件与键盘遍历、Orca 语音；需 Linux 桌面 runner。 |
| macOS | `docs/validation/reader-a11y-apple.json`；`tests/reader_a11y_apple/A11yAuditTests.swift`；run `40096206815`，403 pass / 4 fail | 当前 macOS 全界面键盘顺序、VoiceOver 实录；需 macOS runner/桌面。 |
| iPhone | 同 Apple run，434 pass / 14 fail | 完整原生焦点/外接键盘及 VoiceOver，需 iPhone 真机。 |
| iPad | 同 Apple run，442 pass / 8 fail | 完整原生焦点/外接键盘及 VoiceOver，需 iPad 真机。 |
| Android | `docs/validation/reader-a11y-android.json`；`tests/reader_a11y_android/harness/a11y/src/androidTest/java/org/exreader/a11y/A11yAuditTest.java`；run `40082957400` success，但 `accessibility_accepted=false`、`talkback_speech_verified=false` | 当前全部控件、键盘/D-pad 顺序、TalkBack 实录，需 Android 真机；模拟器不等于真机。 |

本轮补充：

- `inventory_controls.py` 清点 `examples/reader.c` 和全部 `shell_*.inc` 中原生构造位置及显式名称注册。输出 `control-inventory.json`，每位置带源文件/行号、构造表达式、原生角色提示、WS_TABSTOP 声明。循环位置不是实例总数；动态名称、焦点顺序与运行时角色均未推定通过。
- `control_contract.py` 递归遍历所有 UIA 节点，不使用固定控件 ID 白名单；交互角色或可聚焦节点必须有名称和合法角色，拒绝截断/错误/空树。系统 TitleBar 容器允许未命名，其最小化/最大化/关闭按钮仍分别断言。嵌套新增控件、空名称、null 名称、缺角色和树截断都有反例测试。
- `run_audit.py` 每份 UIA 捕获都纳入 blocking 检查并生成 `all-controls.json`；焦点顺序、读屏输出仍写 missing。
- 实际重读 `docs/ui/evidence/a11y-uia-20261110/run5/uia-{closed,search-open,settings-open,toc-open}.json`，逐控件结果在 `historical-control-contract.json`。这证明新断言对历史采样面的处理，不能证明当前程序或未打开面板的行为。
- `historical-name-role-focus.json` 把同一历史 run5 的真实 Tab/Shift+Tab 轨迹与控件名称/ID 合并：关闭/搜索/设置/目录四种采样面分别有 11/20/47/154 个名称角色通过的控件，其中 5/9/36/5 个能关联已测焦点步骤；其余控件焦点仍缺。每个命中带轨迹名、步骤号和原始记录，当前完整键盘验收没有转为通过。

本轮没有写字体轮廓、固定字形尺寸或特定 CJK 字形的断言；继续沿用宿主字体回退，不据缺字推导 UIA 失败。

结论：pending；六端键盘、a11y 与真实读屏分别保留缺口。

## F10

已有证据：

| 文件 / 测试 | 存档运行结果 | 边界 |
| --- | --- | --- |
| `docs/validation/reader-credentials.json`；`tests/reader_credentials/consumer/suite.c` | run `40057087875` success；Windows 24 checks，Linux 34 checks；Apple/Android 原生存储分别留档 | 独立可选凭据模块，不覆盖实际壳；Windows unavailable 场景仍 pending。 |
| `docs/reader-total-progress/webdav-suite-results.md` | F10 component seal `4db961144b00c9004e2775b9e1e57e6ea7a31cb7`，82 cases / 880 assertions / 38 negatives | 记录明确不授予完整 F10。 |
| `examples/windows/check_shell_sync.inc`；`windows-selection-sync` | 历史 headless C2 留档；本轮全量 CTest 与 `new-checks.txt` 已实际复跑通过 | 真 TCP/WinHTTP、密文落盘、日志/库文件扫描、篡改拒绝、删除；不覆盖跨用户读取与完整 TLS。 |

凭据与文件路径审计：

| 实现 | 位置 / 权限 / 清理 |
| --- | --- |
| `extras/credentials/src/windows.c` | Credential Manager 的 `EXReaderCredentials/<namespace>/<account>`，CRED_TYPE_GENERIC / CRED_PERSIST_LOCAL_MACHINE；由 Windows 当前用户凭据存储隔离，不是明文文件。 |
| `examples/windows/shell_sync.inc` 的 `sy_default_paths`、`sy_cred_save/load/delete` | 当前壳实际为 `<g.data_dir>/sync.cred`，DPAPI 当前用户加密，固定 entropy；`CreateFileW(..., NULL, ...)` 继承目录 DACL，没有显式收紧 ACL。新测试记录真实 owner/DACL，不把 DPAPI 推导成跨用户权限测试通过。前期 commentary 中 `sync-credentials.bin` 为路径口误，以源码 `sync.cred` 为准。 |
| `extras/credentials/src/apple.c` | Apple Keychain；macOS/iOS 模块证据分别存在，iPhone/iPad 真机的实际宿主访问控制仍缺。 |
| `extras/credentials/src/linux.c` | libsecret / Secret Service；服务不可用和锁定有模块记录，实际宿主环境与会话回退需复验。 |
| `extras/credentials/android/credentials/src/main/java/org/exreader/credentials/CredentialStore.java` | Android Keystore 保护的加密存储；实际宿主、设备锁定/备份/重装边界需 Android 真机。 |
| `examples/windows/shell_sync.inc` 的 `sy_write` | 目标同目录 `<path>.tmp`；写入、FlushFileBuffers、关闭、MoveFileEx(REPLACE_EXISTING|WRITE_THROUGH)；失败删除临时文件。没有据此推断崩溃自动回收。 |
| `examples/windows/opds_net.h`、`shell_opds.inc` | `.part` 下载和取消/失败 DeleteFile 路径；完整网络中止/进程崩溃/启动残留与选择器生命周期仍需专项验证。 |
| `extras/webdav/src/webdav.cpp` | Windows CREATE_NEW、OPEN_REPARSE_POINT 及析构 DeleteFile 路径；与当前壳不是同一个入口，不能转授。 |

本轮 `windows-privacy-cleanup`：在唯一自建临时目录运行生产 `sy_cred_save` 并读取 DACL，删除凭据；成功发布后 `.tmp` 不存在；锁住目标使 MoveFileEx 失败时旧文件字节保持且 `.tmp` 被删。子进程写入并 flush 一个模拟“写完未发布”侧文件后 `ExitProcess(77)`，真实保留了 `.tmp`，旧文件未变；这不是精确杀死生产 sy_write 某条指令的故障注入。测试明确记录启动清扫缺口，再只清理测试自有目录并断言为空及 RemoveDirectory 成功。

缺失：Windows 当前真实启动对中断 `.tmp` / `.part` 的安全识别与回收、跨用户 DACL/DPAPI 拒绝、稳定文件/链接替换/失败与取消全过程；六端同源 HTTPS 证书/跨源凭据隔离及日志扫描的联验；Linux Secret Service 权限/锁定，macOS/iPhone/iPad Keychain 权限，Android URI/Keystore/崩溃与卸载备份；移动项目需真机，Apple/Linux 部分需特定 runner。测试自清理不能授予产品崩溃恢复。

结论：pending，异常退出残留与全链路缺口不能用正常路径绿灯抵消。

## 运行输出与交付检查

最终实测：本机 MSVC 编译 exit 0，全量 CTest 597/597，补充复跑 5/5，prepush exit 0；最终代码 Actions 编译与全量 CTest 597/597。原失败日志保留。

首轮 Actions run [`43646362628`](https://github.com/NoGod3524/EXReader/actions/runs/43646362628)，源码 `cc867526a15b83016d62574673e8b6b0b211bb30`：编译成功；新增四类检查 4/4；全量 **594/597**，结论 failure。原 ZIP 为 `actions-first.zip`，artifact `14134766239`，71041 bytes，SHA-256 `a2b31aec18eb8f0c4b4a6924bda6d944fe9464da81ab633baa6914157d632f31`，下载后已核对。展开的完整日志在 `actions-first/`。

三处失败与修正：

1. `native-docx-edit-e5`：Python 默认 cp1252 解码含中文的 CMake 文件失败；运行环境启用 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。
2. `native-pdf-hybrid-edge-encrypted-conflict`：该真实加密用例要求 PDF 密码支持，初始 profile 关闭了它；最终 profile 开启 `EXR_ENABLE_PDF_CRYPTO=ON`。
3. `windows-selection-sync`：拉取后 `shelf_load → shelf_refresh → shelf_cover` 获取 `g.library_lock`，控制台入口未初始化该临界区而崩溃；测试入口补齐与原生宿主一致的初始化/销毁。同步、合并、文件及凭据断言原样保留。

本机首次 MinGW 编译因现有 DOCX 壳的 `-Werror` 警告失败，见 `build.txt`；未关掉警告来冒充通过，改用本机 MSVC 进行完整编译。初次 CI hygiene 检查指出本轮新 PowerShell steps 缺显式错误传播；补齐后 `ci-hygiene-final.txt` 为 violations=0（既有 debt 另列，不更改基线）。

新 workflow 仅把 PATH/INCLUDE/LIB/LIBPATH 从编译环境传入后续步骤，避免传递整个环境。首次未进入默认分支的 workflow_dispatch 返回 404，随后用本 lane 分支限定的 push 触发；此调度失败没有冒充测试运行。

## 台账写入方式

仅三项 `note` 增加本报告引用及缺失项，`state=pending` 和 `evidence=[]` 保留。原因：`tools/reader_composition/total_progress.py:631`–`:632` 强制所有 evidence 元素必须是 catalog 顶层已登记的审计 run 键；本轮本地报告不是这些 run，直接塞入路径/缺口文本会破坏验证器。没有修改该验证器，没有添加虚构 run，也没有改任何其他条目或 108 分母。


## 最终运行记录（实际输出）

| 检查 | 结果 | 原始产物 |
| --- | --- | --- |
| 本机最终配置 / MSVC 编译 | exit 0 / exit 0；PDF crypto ON；Python UTF-8 | `configure-final.txt`、`build-final.txt`、`final-exits.json`（含完整命令） |
| 本机全量 CTest | 597/597，exit 0；只排除 `sdk-release|sdk-doc-coverage` | `ctest-final.txt`、`ctest-final.xml` |
| 新增及加强检查复跑 | 5/5，exit 0 | `new-checks.txt` |
| 最终 Actions | run [43650195610](https://github.com/NoGod3524/EXReader/actions/runs/43650195610)，源码 `bcedd78c7da0f60d0af64e411ed2967f73205ad4`；MSVC 编译成功，全量 597/597；新增四项 4/4 | `actions-final/ctest.txt`、`actions-final/ctest.xml`、`actions-final/new-checks.txt` |
| prepush | exit 0 | `prepush.txt`、`prepush-exit.txt` |
| CI hygiene | exit 0；本轮 violations=0 | `ci-hygiene-final.txt` |
| 固定真实原书基准 | 两本取得数据且重复比值通过；pg10 返回 EXR_LIMIT；整个基准 exit 1 | `render-realbooks.json`、`render-realbooks.txt`、`render-realbooks-exit.txt` |

最终 Actions 原 ZIP `actions-final.zip`：artifact `14135782556`，69762 bytes，SHA-256 `687928e7d4489953130e6f7acc21fc662b8886a777dd488420e876bf633472a8`。下载后逐字节核对该散列，再展开日志；job/源码/产物绑定见 `actions-final-identity.json`。修正途中 run `43649167487` 的成功 ZIP/日志另存 `actions-fixed.zip`、`actions-fixed/`，不覆盖首轮失败。

本 lane 证据目录使用 `.gitattributes` 的 `-text -whitespace` 保留原始 Windows 换行和测试输出尾空格；源码仍使用原有格式检查。

本机首次旧配置的串行运行保存在 `ctest-local-initial-cancelled.txt`，在已发现配置错误后停止，不能作为完整结果。最终配置使用 CTest `--parallel 4`；窗口选择/渲染测试仍保留 RUN_SERIAL。最终真实书籍采样在全量 CTest 完成后执行；宿主其他后台活动未控制，因此不授予产品预算验收。首轮并发负载下的原书数据保留在 `render-realbooks-initial.*`。

新增/加强的测试名与行为：

1. `windows-selection-render-budget`：同一宿主渲染路径的 p50/p95、峰值工作集、同进程重复比值。
2. `windows-a11y-control-contract`：所有捕获节点的交互名称/角色，空/截断/未知角色反例，以及新增嵌套/复合控件反例。
3. `windows-a11y-control-inventory`：全部原生构造位置、名称注册位置和未证实焦点/角色清单。
4. `windows-privacy-cleanup`：生产凭据写入的实际 DACL、原子发布失败保护、异常退出侧文件残留、测试自有目录清空。
5. 既有 `windows-selection-sync` 加强入口初始化后原断言全部复跑，保留真实网络、生产读取器和凭据扫描。

本机新增/加强检查输出摘录，完整逐测试输出见 `new-checks.txt`：

```text
498: CREDENTIALS password/username absent from all files; DPAPI blob roundtrip ok; tampered blob rejected; delete removes file
498: PASS sync: 15 scenarios; HWNDs created=0
499: PRIVACY sync.cred DPAPI current-user; actual inherited owner/DACL=O:S-1-5-21-4022989615-4255484600-3434952574-1001D:AI(A;ID;0x1301bf;;;S-1-5-21-4022989615-4255484600-3434952574-1002)(A;ID;0x1301bf;;;S-1-5-21-978422813-1620011744-854770701-2599054056)(A;ID;FA;;;SY)(A;ID;FA;;;BA)(A;ID;FA;;;S-1-5-21-4022989615-4255484600-3434952574-1001)
499: PRIVACY atomic publish failure: original preserved; .tmp absent
499: PRIVACY abrupt exit=77: original preserved; .tmp remains (startup scavenger MISSING)
499: PRIVACY isolated test directory empty and removed
501: PASS UIA contract: all nested controls; missing name/role, truncated/empty tree rejected; focus/speech never inferred
502: PASS inventory: 76 creation sites, 31 name registration sites; unnamed/dynamic sites retained
502: PASS negative controls: unnamed EDIT retained, comments ignored; runtime UIA/keyboard/speech remain missing
514: BUDGET cohort=0 n=64 render_p50_ms=0.526250 render_p95_ms=0.673300 peak_working_set_bytes=13029376
514: BUDGET cohort=1 n=64 render_p50_ms=0.528350 render_p95_ms=0.710000 peak_working_set_bytes=13082624
514: BUDGET same_process_repeat_p95_ratio=1.054508 limit=2.5 peak_ratio=1.004087 limit=1.25; present_frame=missing first_interactive=missing
100% tests passed out of 5
Total Test time (real) =  19.89 sec
```

本机全量输出尾部（完整输出在 `ctest-final.txt`）：

```text
        Start 511: windows-selection-dictionary-storage
596/597 Test #511: windows-selection-dictionary-storage ...............   Passed    0.18 sec
        Start 512: windows-selection-render-budget
597/597 Test #512: windows-selection-render-budget ....................   Passed    0.25 sec

100% tests passed out of 597

Label Time Summary:
headless    =  37.90 sec*proc (4 tests)

Total Test time (real) = 392.74 sec
```

最终 Actions 全量输出尾部（完整输出在 `actions-final/ctest.txt`）：

```text
596/597 Test #596: sdk-doc-pdf ........................................   Passed    0.01 sec
        Start 597: sdk-doc-dictionary
597/597 Test #597: sdk-doc-dictionary .................................   Passed    0.05 sec

100% tests passed, 0 tests failed out of 597

Label Time Summary:
headless    =  22.67 sec*proc (4 tests)

Total Test time (real) = 208.42 sec
```

真实原书最终输出（原样；pg10 失败没有转为通过）：

```text
pg1.epub exit= 0 
BUDGET cohort=0 n=64 render_p50_ms=13.026100 render_p95_ms=30.400800 peak_working_set_bytes=47104000
BUDGET cohort=1 n=64 render_p50_ms=23.879300 render_p95_ms=58.025400 peak_working_set_bytes=47104000
BUDGET same_process_repeat_p95_ratio=1.908680 limit=2.5 peak_ratio=1.000000 limit=1.25; present_frame=missing first_interactive=missing
PASS

pg10.epub exit= 1 
6: SDK call failed

pg11.epub exit= 0 
BUDGET cohort=0 n=64 render_p50_ms=7.039600 render_p95_ms=36.603500 peak_working_set_bytes=23126016
BUDGET cohort=1 n=64 render_p50_ms=7.202750 render_p95_ms=26.607000 peak_working_set_bytes=23539712
BUDGET same_process_repeat_p95_ratio=0.726898 limit=2.5 peak_ratio=1.017889 limit=1.25; present_frame=missing first_interactive=missing
PASS


```

`pg10.epub` 在本基准路径返回 `EXR_LIMIT(6)`（枚举见 `include/exr/base.h:30`），没有它的 p50/p95/内存样本；这不等同于宣称所有产品导入/有界阅读入口都拒绝该书。pg1 峰值 47,104,000 bytes，pg11 峰值 23,539,712 bytes。阈值只看同机重复比值；输出中的毫秒是观测值，不是绝对门槛。固定三原件中的一项缺数据，F08 继续 pending。

prepush 原始输出：

```text
ok    无冲突标记残留
ok    code/docs 结构扫描
ok    check_sdk_docs.py

全部通过 —— 可以推
exit=0
```

## catalog 实际 diff 与最终判定

以下是实际 `git diff df8e6031 -- docs/reader-total-progress/catalog.json`；另存 `catalog.diff`。只有 F08/F09/F10 三项 note 更新，state/evidence 数组和其他条目保持原值；台账引用约束的原因见上节。

```diff
diff --git a/docs/reader-total-progress/catalog.json b/docs/reader-total-progress/catalog.json
index a651be85..c2d9c090 100644
--- a/docs/reader-total-progress/catalog.json
+++ b/docs/reader-total-progress/catalog.json
@@ -1704,7 +1704,7 @@
       "title": "固定书库/平台的产品帧时间、内存及可交互预算获真实验收",
       "state": "pending",
       "evidence": [],
-      "note": "全目标范围未获共同源码验收，不由模块或单向/模拟器结果转授。"
+      "note": "evidence/dfinal-b-20261114/REPORT.md#f08：本机宿主渲染路径、固定原书散列和相对重复预算；缺六端固定规模产品书架的呈现帧 p50/p95、峰值内存、首次可交互预算及同源 runner 验收，保持 pending；本机/Actions 补充测试见报告，完整产品出口仍未验收。"
     },
     {
       "id": "F09",
@@ -1712,7 +1712,7 @@
       "title": "默认简洁且完整功能可达，六端完整键盘/可访问性与读屏证据分列",
       "state": "pending",
       "evidence": [],
-      "note": "全目标范围未获共同源码验收，不由模块或单向/模拟器结果转授。"
+      "note": "evidence/dfinal-b-20261114/REPORT.md#f09：全创建位置源码清单、递归 UIA 控件断言及历史快照重读；缺六端当前程序全部功能可达、完整键盘焦点顺序和独立读屏实录，移动端需真机，保持 pending；本机/Actions 补充测试见报告，完整产品出口仍未验收。"
     },
     {
       "id": "F10",
@@ -1720,7 +1720,7 @@
       "title": "全链路隐私/凭据/文件稳定性/临时文件清理的真实安全出口",
       "state": "pending",
       "evidence": [],
-      "note": "全目标范围未获共同源码验收，不由模块或单向/模拟器结果转授。"
+      "note": "evidence/dfinal-b-20261114/REPORT.md#f10：Windows DPAPI 实际 DACL、原子写入失败清理和异常退出残留诊断；缺崩溃侧文件启动回收及六端权限隔离、TLS/跨源凭据/文件稳定性全链路同源验收，保持 pending；本机/Actions 补充测试见报告，完整产品出口仍未验收。"
     },
     {
       "id": "F11",

```

`audit-scope.json` 逐字段核对：固定 108、12/84/12、99 verified / 1 partial / 8 pending；只有三条 note 改变；`tests/check_reading_release.py` 与基线字节相同；最终代码树与已测提交一致。真实出口判定为 F08 pending / F09 pending / F10 pending，原因分别是产品帧与交互预算缺失、六端完整键盘/读屏缺失、全链路权限隔离与崩溃清理缺失。

本机不能填补的产物已在三项平台表逐项登记：Linux GTK/AT-SPI/Orca 需要对应桌面 runner；macOS/Keychain/VoiceOver 需要 Apple runner/桌面；iPhone、iPad、Android 的性能、真实辅助技术语音、系统文件/安全存储与崩溃生命周期需要各自真机。Windows 当前完整产品的呈现帧、全功能 UIA/键盘与 Narrator/NVDA 实录同样尚缺。
