# D-FINAL-B：F08 / F09 / F10 证据审计与可实施部分

本轮从 `origin/main@e2d6f4d0aa58ea03135f3af1a7d4b9626190fa08` 新建 `codex/dfinal-b-budget-security-20261114`，PR base=`main`。F08、F09、F10 仍需各自完整产品证据，最终均保持 **pending**。本机 Windows/MSVC 与 Windows-2022 Actions 分别登记。

本机与Actions均真实编译成功，最终全量CTest均**600/600**，加强检查均**9/9**，prepush **exit0**；当前扩展UIA probe仍**exit1**，完整键盘和读屏未获通过。本机首轮PPTX计时失败与未知根因保留，下文给出原始记录。

固定三原书基准本机与Actions均完成18个独立进程、三书相对检查通过；它是宿主有界渲染基准，仍非产品呈现帧/首次可交互验收。

基线 catalog blob=`d2f0e19a211cab8733a22d936c7ba7fe34ecfd96`，状态实数为 **99 verified / 0 partial / 9 pending**，分母108，分组12/84/12。任务中的99/1/8是此前快照；D-FINAL-C已将 `H.ipad.annotation_exchange` 改为pending（`docs/reader-total-progress/dfinal-c-audit.md:66`–`:67`）。本轮不改其他条目；这些只是状态计数，不是重新认证历史证据后的授分。

## 验收原文与 verified 所需证据

catalog v1 实际没有 `acceptance` 字段，下表逐字引用对应固定 `title`，并依据其 `scope_document` 解释，不补造字段。

| 项 | 原文（路径与行号） | 一句话 verified 定义 |
| --- | --- | --- |
| F08 | `docs/reader-total-progress/catalog.json:1704`：「固定书库/平台的产品帧时间、内存及可交互预算获真实验收」 | 六目标同源完整产品在固定设备/runner、固定规模真实书库和固定负载上，保留产品呈现帧p50/p95、峰值内存、首次可交互及同机相对预算验收产物（`docs/READER-PRODUCT-PLAN.md:156`、`:195`–`:196`）。 |
| F09 | `docs/reader-total-progress/catalog.json:1712`：「默认简洁且完整功能可达，六端完整键盘/可访问性与读屏证据分列」 | 六端分别证明默认入口简洁且全部功能实际可达，给出全部交互控件的名称、角色、真实键盘焦点顺序，并独立登记实际读屏输出（`docs/READER-PRODUCT-PLAN.md:157`、`:191`–`:193`）。 |
| F10 | `docs/reader-total-progress/catalog.json:1720`：「全链路隐私/凭据/文件稳定性/临时文件清理的真实安全出口」 | 六端实际宿主分别证明平台安全存储及不可用时仅会话回退、日志/库/载荷不含凭据、TLS/跨源隔离、稳定私有文件、原子发布及正常/失败/崩溃后的临时文件处置（`docs/READER-PRODUCT-PLAN.md:165`、`:168`、`:185`–`:187`）。 |

已读 `docs/reader-total-progress/README.md`、`SESSION-CONTRACT.md`、`LEDGER-AUTHORITY.md`、C02 handoff 中相关记录，以及前两轮 `evidence/dfinal-b-20261114/REPORT.md`、`evidence/dfinal-b-followup-20261114/REPORT.md`。本次用户明确授权本机测试、F08–F10实施、三项台账更新与main-base交付，按这一范围执行。

## 三项证据审计表

| 项 | 已有证据 / 最近真实结果 | 本轮补上的部分 | 仍缺什么 / 最终state |
| --- | --- | --- | --- |
| F08 | 旧Windows2202原件书架run40086319655 success、GTK run40086971620 cloud-verified，但无呈现帧预算；前轮三原书基准pg10整本展开EXR_LIMIT、整体exit1；C02原生Android采样失败按原记录保留。逐文件/测试名/运行结果见[F08.md](F08.md)。 | 固定三本原书和spine，基准改走生产有界EPUB入口；独立进程原始64样本、p50/p95/峰值和相对阈值；严格散列下载与路径校验。 | 缺六端固定规模完整产品书架呈现帧、首次可交互和冻结预算；当前是隐藏宿主渲染/同二进制重复性。**pending**。 |
| F09 | 前轮当前壳五面UIA有名/角色、键盘与语音缺；六端旧审计失败/缺口、较新Apple构建模式诊断均保留。逐平台原文件、测试及最近结果见[F09.md](F09.md)。 | 采集器名称/角色断言失败及异常子进程退出均使CLI失败；清点共享helper和绘制命中目标；扩展词典、生词本、WebDAV真实面板，逐节点列名/角色/实测焦点。 | 缺当前全部功能/控件完整键盘与独立读屏；本轮未测控件仍逐项列缺。iPhone/iPad/Android需真机。**pending**。 |
| F10 | 五平台独立凭据模块与前轮Windows私有DACL/原子失败清理、sync15场景通过；C02组件82cases/880assertions/38negatives不授予full_F10。见[F10.md](F10.md)。 | 显式TokenUser owner；固定私有凭据stage经独占句柄严格验证后回收；生产writer flush后真实强杀，再由生产同步初始化恢复，保留旧凭据和负例。 | 缺安全存储实际壳接入/会话回退、旧owner/ACL迁移、第二身份、普通`.tmp/.part`、稳定文件和六端全链路。**pending**。 |

三份分项报告包含六端各自的已有证据、对应测试名、最近一次存档/本轮运行结果、具体缺失产物及所需环境。旧运行与本轮重跑分开登记；未重新认证的历史ZIP明确按存档引用。

## 实现与测试范围

完整代码与测试patch见[implementation.diff](implementation.diff)，按本轮固定基线导出；下列摘要说明各处行为和验证范围。

- F08：`examples/windows/check_shell_budget.inc` 复用 `import_bounded_epub → exr_library_source → shell_epub_source → exr_publication_open_source → bounded_pager`；`render_budget.py` 校验冻结原书/spine和真实路径，保存baseline/candidate各3个独立进程、每进程8次预热和64次0/1页交替的原始数据。阈值仅为同机比值：p50/p95/setup-ready <2.5、peak <1.25；`accepted=false`、`product_budget_accepted=false`保留。前轮EXR_LIMIT没有从历史记录删除；新入口测的是不同加载路径，不与旧整本展开指标作回归比较。
- F09：`capture_shell.py`、`control_contract.py`、`inventory_controls.py` 加强失败传播、逐控件计数与源码位置清单；静态清点238个原生/helper/绘制位置和33个名称注册位置，包含可选产品源码，不能推定这些位置在当前binary均已启用。新增 `windows-a11y-shell-capture-gate`，其反例涵盖缺名、漏面板、额外面板、采集异常和子进程exit77。`shell_dictionary.inc`共用helper补语义名字，既有`windows-selection-dictionary-storage`增加10个原生IAccessible名字断言；完整键盘和语音均不能由采集成功推定。
- F10：`shell_sync.inc` 私有writer显式指定owner；`sy_cred_recover_temp`只处理固定`sync.cred.tmp`，验证当前owner、protected双ACE、非reparse/目录及单链接，使用同一句柄删除。`sy_init`是同步的惰性初始化，不能称为整个程序无条件启动清扫。`check_shell_privacy.inc`实际强杀写入子进程，并保留活writer/硬链接/目录/宽权限占位拒绝和测试目录最终为空的断言。
- `reader-final-b-audit.yml` 在Windows-2022编译、全量CTest、verbose加强检查后，严格散列获取原书并运行固定基准，上传原始日志和JSON。下载内容变化时直接失败，不替换样本。

三本英文Gutenberg原件已原样保存到[frozen-books/README.md](frozen-books/README.md)所列位置，共4350583 bytes，保留书内许可，逐份SHA匹配原manifest；本机最终基准直接读取归档，可离线重放。`.gitattributes`沿用前轮证据目录规则，仅为本轮证据关闭文本归一化，保留原始Windows CRLF/摘要身份，源码检查规则未变。

没有更改 `tests/check_reading_release.py`；没有加入固定字形轮廓或宿主字体尺寸断言。真实原书负载使用宿主 `segoeui.ttf`，英文结果不授予CJK性能；CJK继续按宿主字体分流。

## 本机与 Actions 真实输出

本节在最终测试结束后记录实数；完整命令、源码与退出码由同目录 `*-exit.json` 保存，完整逐测试输出交付为 `ctest.txt` / `ctest.xml`，加强检查为 `new-checks.txt`。`run-local.ps1`复用前轮完整MSVC profile与已缓存依赖，保留完整命令。全量仅排除 `sdk-release|sdk-doc-coverage`。

首个Actions run43676797110在配置阶段由本lane主动取消，以纳入扩展采样发现的可访问性命名修复，未编译、不计测试通过；原始作业结论见[actions-cancelled.json](actions-cancelled.json)。第二个run43677013165在checkout阶段取消，以把可选宿主scanner纳入最终受测源码；其中always-run new-checks在未完成checkout时失败，不计验收，见[actions-cancelled-scanner.json](actions-cancelled-scanner.json)。

最终实施commit=`d2b0be6b4e2059bdbb33f0c8f53b137a20189188`。本机真实MSVC编译在a977e003完成；随后唯一实施变化是Python源码scanner，C/C++文件与二进制无变化。`build-exit.json`保留实际构建source，`audit-scope.json`按Git文本过滤后核对最终实施文件（本机manifest为CRLF），另保存真实磁盘与二进制SHA-256。

### 扩展 UIA 实际输出与逐控件清单

完整逐节点证据：[F09-controls.csv](F09-controls.csv)、[F09-control-summary.json](F09-control-summary.json)、[F09-current-uia-named/all-controls.json](F09-current-uia-named/all-controls.json)。采集跨八面共193行，重复控件按界面重复出现，**不是193个独立产品控件**。

```text
closed: controls=12 name_role_passed=True observed_keyboard_controls=0
search: controls=21 name_role_passed=True observed_keyboard_controls=0
settings: controls=48 name_role_passed=True observed_keyboard_controls=0
toc: controls=30 name_role_passed=True observed_keyboard_controls=0
dictionary-settings: controls=23 name_role_passed=True observed_keyboard_controls=0
vocabulary: controls=23 name_role_passed=False observed_keyboard_controls=0
webdav-account: controls=28 name_role_passed=True observed_keyboard_controls=0
shelf: controls=8 name_role_passed=True observed_keyboard_controls=0
audit_completed=true; name_role_passed=false; child_exit_code=0
complete_keyboard_verified=false; screen_reader_verified=false
exit=1
```

原文见[F09-current-uia-named.txt](F09-current-uia-named.txt)，命令/exit见`F09-current-uia-named-exit.json`。192行有名、193行角色有效、0行具有本轮实测键盘轨迹。剩余缺名是生词本Combo内部无HWND的Text节点，role50020、ValuePattern、focusable=true，仍由严格断言报失败。修复前各有HWND的缺名与采集路由错误产物保留，见F09分项报告。采集profile保留本机并由`.gitignore`排除；不授予F10清理证据。

原生命名断言已单独实际通过：

```text
516: DICTIONARY accessibility: 10 native list/combo/query/status/WebDAV/dynamic-body names read through IAccessible PASS
1/1 Test #516: windows-selection-dictionary-storage ... Passed 0.15 sec
100% tests passed out of 1
Total Test time (real) = 0.17 sec
```

完整原文与退出码：`F09-dictionary-test.txt`、`F09-dictionary-test-exit.json`。

### 私有凭据中断恢复实际输出

```text
500: PRIVACY credential forced termination=77 after production flush: sync initialization removed protected stage; old credential loaded; subsequent save succeeded
500: PRIVACY sync initialization recovery refused live writer, hard link, directory and nonprivate DACL; no unrelated temp scan
500: PRIVACY atomic publish failure: original preserved; .tmp absent
500: PRIVACY abrupt exit=77: original preserved; .tmp remains (startup scavenger MISSING)
500: PRIVACY isolated test directory empty and removed
1/1 Test #500: windows-privacy-cleanup .......... Passed 0.22 sec
100% tests passed out of 1
Total Test time (real) = 0.32 sec
```

完整原文与命令：[F10-tests.txt](F10-tests.txt)、`F10-tests-exit.json`。第一行是本轮凭据私有stage的生产恢复，第四行是保留的普通state临时文件缺口，两种文件不混用。

### Actions 同源编译、全量和加强检查

run [43677041326 / attempt1](https://github.com/NoGod3524/EXReader/actions/runs/43677041326)，受测源码`d2b0be6b4e2059bdbb33f0c8f53b137a20189188`，job132699372900，Windows-2022。配置、编译、全量CTest、加强检查、冻结原书获取与基准全部success。

```text
600/600 Test #515: windows-selection-render-budget .................... Passed 0.08 sec
100% tests passed, 0 tests failed out of 600
Total Test time (real) = 123.20 sec

100% tests passed, 0 tests failed out of 9
Total Test time (real) = 18.98 sec
```

完整逐测试输出：[actions/ctest.txt](actions/ctest.txt)、[actions/ctest.xml](actions/ctest.xml)、[actions/new-checks.txt](actions/new-checks.txt)，真实构建输出`actions/configure.txt`、`actions/build.txt`。仅排除`sdk-release|sdk-doc-coverage`。9项为：

```text
windows-selection-sync
windows-privacy-cleanup
windows-render-budget-report-contract
windows-a11y-control-contract
windows-a11y-shell-capture-gate
windows-a11y-control-inventory
windows-selection-keyboard
windows-selection-dictionary-storage
windows-selection-render-budget
```

新增/加强的Actions真实输出摘录（完整原文保留在上述文件）：

```text
500: PRIVACY credential forced termination=77 after production flush: sync initialization removed protected stage; old credential loaded; subsequent save succeeded
504: PASS shell audit gate: unnamed controls, missing/extra surfaces, collection errors and abnormal child exits fail; keyboard/speech remain missing
505: PASS inventory: 238 constructor/helper/painted-target sites, 33 name registration sites; unnamed/dynamic sites retained
516: DICTIONARY accessibility: 10 native list/combo/query/status/WebDAV/dynamic-body names read through IAccessible PASS
```

原ZIP：[actions.zip](actions.zip)，artifact14146926486，94523 bytes。下载后实算SHA-256与GitHub API digest匹配：`e8311fc1ce6346d920d9fd4e4720f2b6d6048fec7c2f914ba0831117e0ff2496`；source/run/job/artifact绑定见[actions-identity.json](actions-identity.json)。原书原始逐次数据见`actions/f08-realbooks.txt`及`actions/f08-realbooks.json`，同机比值和p50/p95/峰值附表见F08分项报告；不是本机与Actions之间相除。

### 本机首轮失败及隔离复核（原样保留）

首轮本机全量为**599/600、exit1**，完整输出/JUnit/命令为`ctest-first-failed.txt`、`ctest-first-failed.xml`、`ctest-first-failed-exit.json`；原始matrix为`pptx-matrix-first-failed.json`。唯一失败是既有`native-pptx-real-matrix`：100次渲染的单次最大314.9653ms超过原200ms上限，median16.2541ms（相对原baseline比值0.7928829），所有内容/颜色/覆盖检查通过。该测试和SDK核心未改，原绝对门槛没有放宽。

独立只读复算见[pptx-first-failure-analysis.md](pptx-first-failure-analysis.md)及JSON。测试本已RUN_SERIAL；没有每样本调度/CPU频率/后台活动遥测，**根因未知**，不推断是CTest并行或已修复的生产退化。

相同源码、相同原断言隔离复核一次，真实输出为：

```text
88: MATRIX files=15 passed=15 failed=0
1/1 Test #88: native-pptx-real-matrix .......... Passed 34.58 sec
100% tests passed out of 1
Total Test time (real) = 34.66 sec
```

命令/exit0和原始结果见`pptx-isolated-exit.json`、`pptx-isolated.txt`、`pptx-matrix-isolated.json`。隔离通过与Actions600/600不会覆盖首轮失败；第二次完整运行结果单独登记。

### 本机最终完整运行及加强检查

最终源码`d2b0be6b4e2059bdbb33f0c8f53b137a20189188`，完整CTest第二轮保留全部原测试及原断言，未额外排除失败项：

```text
598/600 Test #506: windows-selection-copy ............................. Passed 0.04 sec
599/600 Test #508: windows-selection-raster ........................... Passed 0.05 sec
600/600 Test #507: windows-selection-keyboard ......................... Passed 0.05 sec
100% tests passed out of 600
Total Test time (real) = 241.16 sec

100% tests passed out of 9
Total Test time (real) = 20.39 sec
```

完整全量原文：[ctest.txt](ctest.txt)、[ctest.xml](ctest.xml)；完整加强原文：[new-checks.txt](new-checks.txt)。命令与exit0见`ctest-exit.json`、`new-checks-exit.json`。仅排除`sdk-release|sdk-doc-coverage`，JUnit600、failures0、skipped0。9项名称与上节Actions清单相同；新增反例自检通过不等于真实UIA probe通过。

F10早期定向输出绑定4b2c863d，本机及Actions最终`new-checks.txt`再次实跑最终源码的同一恢复断言，完整输出同时保留。原PPTX测试的第二轮通过并未建立首轮计时尖峰根因。

prepush实际输出（命令、source、exit0见`prepush-exit.json`，完整[prepush.txt](prepush.txt)）：

```text
ok    无冲突标记残留
ok    code/docs 结构扫描
ok    check_sdk_docs.py
全部通过 —— 可以推
```

CI hygiene实际输出为`PASS: CI hygiene; violations=0; existing debt={'failfast': 242, 'negative': 9, 'diagnostic': 4, 'packaging': 4}`，原文与退出码见`ci-hygiene.txt`、`ci-hygiene-exit.json`；未更改既有debt基线。

### 本机固定原书基准实际输出

在本机完整CTest与verbose检查全部结束后，`2026-11-15T04:45:17–04:45:20Z`一次性采集18个独立进程，全部exit0，命令自身exit0。命令及时间：[F08-realbooks-exit.json](F08-realbooks-exit.json)；完整stdout：[F08-realbooks.txt](F08-realbooks.txt)；所有原始样本/书/font/EXE/manifest身份：[F08-realbooks.json](F08-realbooks.json)。每书候选侧3×64=192样本合并复算p50/p95，peak取候选三个进程最高值；相对判定按每进程统计量中位数相除。

| 固定原书及正文 | render p50 / p95 (ms) | peak working set (bytes) | 真实结果 |
| --- | --- | ---: | --- |
| pg1 Declaration h0 | 0.809150 / 0.971800 | 24125440 | 6进程exit0、同机相对检查通过 |
| pg10 Genesis h2 | 0.759150 / 0.991200 | 34287616 | 6进程exit0、同机相对检查通过 |
| pg11 Chapter I h1 | 0.836300 / 0.957000 | 17391616 | 6进程exit0、同机相对检查通过 |

完整四项相对比值及Actions独立附表见[F08.md](F08.md)。两机器字体/CPU不同，不跨机器相除。两份报告均`passed=true / advisory=true / accepted=false / product_budget_accepted=false`；`first_interactive=missing / display_present_frame=missing`保持，不能把render耗时当作真实显示帧。

## 台账约束与最终判定

仅F08/F09/F10允许变化，三项state保持pending。`evidence`是顶层已登记run键数组（`tools/reader_composition/total_progress.py:631`–`:633`），不能填任意路径/“缺”文字；F08/F09缺有效完整产品键仍为[]，F10保留原credentials/sideload/batch/sync有限组件引用。本轮报告及具体缺口更新在各项note，未扩展schema或注册未经核对的run。

[catalog.diff](catalog.diff)交付完整实际差异；[audit-scope.json](audit-scope.json)核对108、12/84/12、其他105条目及顶层不变、禁改文件字节不变，并将最终受测实现和二进制散列绑定。审计不把本轮组件绿灯转换成完整产品加分。

本机无法完成的验证：Windows第二身份和真实呈现/交互桌面采集需专用runner；Linux需GTK/AT-SPI/Orca及私有D-Bus/Secret Service；macOS需Apple桌面/Keychain/VoiceOver环境；iPhone、iPad、Android的性能、完整键盘/焦点、读屏语音、安全存储锁定和系统文件生命周期均**需真机**，模拟器产物独立登记。
