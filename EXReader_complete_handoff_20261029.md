# EXReader 完整交接 — 2026-10-29

这份文件供新对话接手执行。请读完整份文件，先复核会变化的 GitHub 状态，再继续实际修复和主线任务。不要停在计划，也不要把准备好的任务描述为已启动的 Claude 任务。

最后核对时间：2026-10-29 15:54 美东。本文的运行状态是这一时点的快照，不是未来状态保证。

## 1. 用户目标与当前请求

项目：NoGod3524/EXReader，跨平台原生阅读器，自有 C11 PDF/阅读 SDK，Windows/macOS/Linux/Android/iPhone/iPad，无 WebView，主线包括导入、书架、阅读进度、批注、搜索、排版、跨端同步、迁移安全与冲突恢复。主线 P0 最高优先。

原交接链接：https://chatgpt.com/share/6ae394f4-0a3c-83e9-9b61-37de2c9609ef 。本文已提取必要内容，不需要把读取分享链接作为开始工作的前提。

用户明确要求：
1. 启动 3 个子代理修复问题，然后推进剩余主线。
2. 可把独立主线任务交给后台 Claude Sonnet 5.5 Medium。
3. 明确说“不要用 cpuse，用后台连”：不要通过电脑/浏览器 UI 操作 Claude 创建任务。
4. 后来要求解决 Claude 后台连接问题。当前尚未解决。
5. 最新要求：把完整状态 handoff 给另一个对话。本文就是该交接。

用户偏好中文、直接行动，不要反复问已授权的权限，不要频繁复述相同状态，不给无依据 ETA。完成一个有价值的工作包后继续下一个。诚实区分源码改好、构建通过、用例通过、独立证据核验、正式目录登记。

## 2. 必须保留的执行约束

- 本地/云工作区仅用于源码、Git、文档、轻量状态查看。
- 所有构建、语法检查、测试、fixture 生成、benchmark、原始工件解析均只能在 GitHub Actions 执行。
- 已授权创建独立分支、提交/push 这些分支、触发 Actions。
- 未授权默认分支合并/推送、创建 PR、tag、Release、正式发布。
- 保留冻结断言、原用例、预算、历史失败记录；不要改分母、延长预算或放宽断言来变绿。
- 不将不同源码的通过结果拼成同一最终产品的共同源码验收。
- 不重试未解释清楚的 D13 阻塞实验。
- 不用真实用户书库、密钥或凭据作测试；不要读取/导出 Claude OAuth 令牌。
- 独立分支隔离工作；不要覆盖当前旧的 dirty checkout。
- 用户授权不能解除平台沙箱限制。只能走正式配置流程，不能删网络限制环境变量、改路由、绕代理、关闭 TLS 或通过其他执行器逃逸现有限制。
- 仓库存在 AGENTS.md 时，新接手者应先读取适用规则；本文件不替代新发现的有效规则。

## 3. 工作环境与工具状态

最近恢复的本地环境：
C:\Users\Oscar\OneDrive\文档\ChatGPT\EXReader
PowerShell。用户时区 America/New_York。

最初本地分支为 codex/reliability-convert-memory，HEAD 9dfb155a，带许多旧的未提交修改。不要 reset/clean/stash 或切换后覆盖它。新会话先 git status，所有实际整合应在独立分支/工作区。

已知：
- rg 不可用时用适当替代；不要在这一点上卡住。
- gh CLI 的登录 token 先前无效；GitHub MCP 连接器正常可读写独立分支。
- Windows 本地已安装官方 Claude CLI：
  C:\Users\Oscar\.local\bin\claude.exe
  版本 2.1.310；不在 PATH。
- Python 3.14.7 可用，文件操作/交接包保存可用；不要借此在本地跑项目测试。
- 本轮一度原 Windows 环境断开，状态 unavailable；后来已恢复，15:54 可执行 Get-Location / python --version。
- 环境恢复不等于 Anthropic 网络权限恢复。最近实际检查仍存在 CODEX_SANDBOX_NETWORK_DISABLED；未见正式网络配置已改变的证据。
- 当前没有用于重连/配置该宿主环境的管理工具，也没有 Claude 专用后台任务连接器。

子代理：
之前实际启动过 apple_mobile_annotations、apple_sdk342_integration、remaining_mainline。环境上下文仍可能列这些名称；但最后 collaboration.list_agents 实际只返回 /root。新对话不要假设它们仍在后台运行，更不要等待不存在的代理。其分支/源码/Actions 成果已全部在下文。若要重启 3 个代理，用户已有明确授权，按这些职责重新隔离任务即可。内置子代理只支持已列出的 GPT 模型，不能把它们冒称 Claude。

## 4. 正式进度：95/108，不是 91/108

已核验的冻结目录结果：
https://github.com/NoGod3524/EXReader/actions/runs/40928834086/attempts/2
attempt 2，source 5d4ec0ebd94fa3fabbf19af016073aef2877ac20，success。

Foundation 12/12；host 82/84；final 1/12；总计 95/108（88.0%）。
这只是固定验收条目进度，不是开发工时百分比，也不是全部最终产品已完成 88%。

剩余 host 2 项：iPhone/iPad 的 annotation_exchange。
剩余 final 11 项：F01–F05、F07–F12；F06 已验收。
新的 Windows 67/67 和启动保护 10/10 不自动增加固定目录计数。

冻结目录与审计源码：
分支 codex/apple-four-evidence-audit-20261029，最后已知 HEAD 6f7dc3bf71926c7c68de8781da31989fd2a537b6。
- docs/reader-total-progress/catalog.json
- tools/reader_composition/total_progress.py
- .github/workflows/reader-total-progress.yml
- docs/reader-total-progress/apple-continuation-20261029.md
- docs/reader-total-progress/apple-annotation-macos-audited.md
- docs/reader-total-progress/apple-sync-details-audited.md

固定 108 项定义源自 1adeabf…；以目录里的 scope_document/blob 为准，禁止改身份和分母。

最终 12 项：
| ID | 当前状态 | 验收范围 |
| --- | --- | --- |
| F01 | pending | 六目标同一最终产品源码完整功能 |
| F02 | pending | 六目标原书传输，至少两端真实应用上传/下载/打开闭环 |
| F03 | pending | 共享书架、子书架、分类、系列、删除和恢复一致 |
| F04 | pending | 进度/书签/批注及原始锚点双向互通、不误定位 |
| F05 | pending | 完整客户端离线重连、多头/墓碑、取消/崩溃恢复 |
| F06 | verified | 同一源码六份开发程序/包及解包/入口身份 |
| F07 | pending | 最终宿主实际单 SDK/产品 SQLite 提供者、模块无私有入口 |
| F08 | pending | 固定书库/平台真实产品帧时间、内存、交互预算 |
| F09 | pending | 简洁默认界面且完整功能可达，键盘/可访问性/读屏 |
| F10 | pending | 全链路隐私/凭据/文件稳定性/临时文件清理 |
| F11 | pending | 移动部署架构、真机能力、交付缺口 |
| F12 | pending | 升级/旧库兼容、许可/依赖、安装/导入/同步说明 |

F06 来自较早 source 8f8acf3234cba747165f001c0c96efe1b911e6ad，run 40678657371。Android/iPhone/iPad 是模拟器，不授予 F01/F07/F11 或正式发布。

## 5. 本次 handoff 前刚刷新的运行状态

| 运行 | 精确 source | 最新快照 |
| --- | --- | --- |
| 40935165396 | 55ec49020383ef5073f47502b300ab0b5d0a7cae | 整体 in_progress；macOS success；iPhone failure；iPad 尚 in_progress 但原生测试步骤已 failure |
| 40937262016 | 82f0bc538024dbd7bedfead76724d307eb683719 | in_progress，独立审计的 producer 等待 job 尚运行；不能计分 |
| 40937013878 | 6be10b3de1e7f9e98bab72db586a66e571199034 | in_progress；两个 SDK success；macOS 原生 success；iPhone/iPad in_progress |
| 40937997549 | bd28d4946f17a184dd3cd47a584cf49fce34e973 | completed failure；两个 SDK 构建 failure，原生及 supplemental skipped |
| 40938221167 | 7c769dc1b80cd70cbddd0240dcb5de57729104d0 | completed success，Windows 67/67 |
| 40939979816 | 2fff53ff6734ec2b495c841e6669aef562e170d7 | completed success，Windows 实际产品启动保护 10/10 |

每个运行链接为 https://github.com/NoGod3524/EXReader/actions/runs/上表运行号 。
接手先刷新尚运行项；不要根据整篇文件较早段落里的“等待”继续无限等。

## 6. 工作包 A：Apple 移动批注修复

负责人旧任务名 apple_mobile_annotations。

原候选：
source 622b9558f79eda07211e15c51bffcd728da6c553，run 40923468266。
macOS 39/39 原生用例通过，已独立验收。
iPhone/iPad 仅批注功能测试超过 240 秒；其他 34 个用例通过。
真实文件导出、有效/无效 JSONL 文件准备后，系统 picker 仍停在本地根目录：EXReaderAnnotations, Folder / 3 items。
问题在测试 helper 的 StaticText 点击、精确带扩展名文件匹配、ancestor loop，而非已证实产品数据错误。

原失败工件保留：
- iPhone ID 12922397214，455384151 bytes，sha256 8f710068c9d663d9e3c76822ca902c1618883da112304765a2fb243b6ad4a034
- iPad ID 12923187029，498934965 bytes，sha256 320a7c0f6d819a1e18439f2eb705d225105602416685b9e70f80cafe32845773

修复候选：
分支 codex/apple-mobile-annotations-handoff-20261029
source 55ec49020383ef5073f47502b300ab0b5d0a7cae
run 40935165396。

仅改 tests/reader_team24_apple/ui/FeaturesUITests.swift 的 helpers：
- 文件 Cell 支持系统隐藏扩展名；
- 直接导航文件夹 Cell，避开 ancestor loop；
- 缓存 tap frame / query。
所有 5 个 feature 测试正文都与 622b9558 字节一致；根代理已独立核对从 func testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot() 起的正文后缀。
原 run_ui.py、其他 34 测试不变。24 次滚动 / 90 秒等待 / 240 秒单用例预算不变。
新 Features blob 3aaa8003c61fd523b5286a9ea2c06f328e68f6a0。

job：
- macOS 123666094876：success 39/39，artifact 12924854400，315961256 bytes，
  sha256 f534f0ca6359aaeb3f6ee4a167bad1c8f3c893edfd98e1bf7de71f466dadcf39
- iPhone 123666094860：最新已 failure。
  新原始失败 artifact 12928097306，436248547 bytes，
  sha256 b7f3125fb508ecc417e59ca083f7ba89aa9e5308971c2aa483a1aab30adad7bb
- iPad 123666094857：最新仍上传/收尾中，但 Actual native features… 步骤已 failure。

新 iPhone 日志证明原 driver 最终触发：
AssertionError: Team24 Apple scoped acceptance incomplete; retain original evidence
具体失败用例/系统 picker 当时状态尚未重新从 xcresult/截图解析。下一步必须在 Actions 内读取这个新原始失败 ZIP，定位，再改 helpers；不要假定第一次 picker 修复已经成功，也不要直接加超时。

## 7. 工作包 B：真实 Apple SDK 3.42 与公共模块整合

负责人旧任务名 apple_sdk342_integration。

先前 Team24 build.py 实际硬编码 3.41 和较旧 SDK。新增 tests/apple_sdk342_host/build.py、run_ui.py，明确使用真实 3.42 输入，原 Team24 driver/tests 保留。

阶段分支：
codex/apple-sdk342-host-continuation-stage-20261029
source 4a68d80fbaa524fc28f899d209d795248627080b
base 80da967f5411e0c76d25e8bb21ec23c5f2b22385。

第一真实 3.42 候选：
codex/apple-sdk342-integrated-handoff-20261029
source 148a5b11f9e65e87520eddff98e5365e83e98c30
run 40935524467：SDK 成功，所有 native 在 admission 前失败，installed-file-set mismatch。
独立短检查 run 40936609291：应有 444 个 SDK 文件、传入 443 个；唯一缺失 examples/android/.gitignore，其他文件 hash 完全相同，raw 135/135。不能删清单断言。

修复：
同分支 source 6be10b3de1e7f9e98bab72db586a66e571199034
run 40937013878。
SDK 上传 include-hidden-files:true，保留完整文件集校验、早期失败 receipt；合入 55ec helpers。
两个 SDK 已 success。macOS job 123672422146 success；
iPhone 123672422033 / iPad 123672421831 最新仍运行。
必须等其自身原始结果，不能转授其他源码成功。

共同源码公共模块候选：
公共边界 base e6b899284744b95dc832db92ed16324711ff5362。
prep 分支 codex/apple-sdk342-public-full-prep-20261029
source 81a67f7dc2c423306b10addf44b63e66dfb26316（skip ci）。
激活分支 codex/apple-sdk342-full-handoff-20261029
source bd28d4946f17a184dd3cd47a584cf49fce34e973
run 40937997549。

保留 e6 的 apps/reader 与 extras 公共模块 blobs，按上下文应用 Apple production/UI/tests + 旧记录 admission + 55ec helpers + 真实 3.42 driver。
81a→bd28 只有说明 commit，代码相同。
原 SDK core pin 8357eafa28423a7ab93ba08b823af80f01ad1505；src/include/cmake/CMakeLists/bindings 必须保持冻结身份。

最新重要失败：
40937997549 已 completed failure，非仍排队！
SDK iOS job 123673558077 与 macOS 123673558474 失败于：
CMakeLists.txt:91:
Set READER_ORIGINAL_HASH_PREFIX or EXREADER_ORIGINAL_HASH_PREFIX to the installed OPDSHash prefix
发生于 tools/build_apple_product.py 调用 apps/reader/store/native 的 CMake 配置。
iOS 配置只有 CMAKE_PREFIX_PATH=SDK、EXR_SDK、READER_PRODUCT_PREFIX 等，未传真正已安装的独立 OPDSHash prefix。
随后原生和 supplemental jobs skipped；authentication 123693968975 与 full-host-summary 123694058620 也 failure。
下一步修复独立 OPDSHash 构建/安装/传递，保持 public boundary，无私有 fallback。不要以删除依赖或 provider 检查修好表面构建。
失败的 iOS SDK artifact 12926949686，19320688 bytes，
sha256 699ada16e133eafa159d3c380247961aade3d392105f21f1d0eef795b49a8c58。

完整候选 CI：
.github/workflows/apple-sdk342-full-handoff-20261029.yml
2 同源码 SDK builds + 3×39 原生 + 12 supplemental（fonts/original/organization/sync ×3 平台）+ 原 Team24 authentication + full-host-summary（18 producer gates）。
tests/apple_sdk342_host/supplemental.py：
- 重 hash 同 run SDK 完整文件集；
- 原字体 1case；
- 原系统保存 1case + byte readback；
- 组织 6cases incl members；
- 真 TLS account 3cases + 401/retry 1case；
- 保留全部原预算和原报告/app 包，排除 key/derived。
full_summary.py：
18 producer 全 success、同 source、12 原 ZIP 重 hash、App Info EXRSourceSHA/SDKVersion/字节身份。
显式 complete_product=false、physical=false。

整合时必须保留：
- 80da 的 HostReadingRecords 允许录制于 3.40/3.41 的记录在实际 3.42 admission；e6 不含这条。
- e6 的 tools/build_apple_host.py 已接受 3.42 page-theme，别覆盖。
- e6 约 28 个公共模块改变：
  annotation-import/export 用 reader_revision_selector_encode_v1 / reader_selector_bytes_v1.h；
  reading_commands 用 reader_rs_encode_retained_raw_v1 / reader_reading_state_retained_raw_v1.h；
  Android Sync 独立 OPDSHash。
- 旧 Apple bridge/public headers 可保持同 blob；不需要恢复私有入口。
说明 docs/reader-total-progress/apple-sdk342-public-composition-prep.md。

## 8. 工作包 C：Windows 迁移前置验收与实际启动保护

负责人旧任务名 remaining_mainline。

### 8.1 迁移资格测试 67/67 已通过

原资格分支 codex/migration-windows-native-qualification-20261029
5db9c2c0b574b0e63675a38b0653f3a9bdd2cb1c / run 40888673546：
64/67（43 frozen +21/24 native），g10/g15/g17 的 Path.rename 被保留的祖先 pin 拒绝。

修复分支 codex/migration-mainline-handoff-20261029：
测试专用 rename_sibling，通过原生 NULL RootDirectory + simple leaf + no-replace；
验证 direct parent 的 volume GUID/root、源文件完整 24byte FileID，无 reparse/hardlink/deletepending；
不释放/扩大原 pin，不加 fallback。
原 g09/g12/g14/g15 active-output-pin 拒绝保持。
g15 第二个 pre-I/O/pre-pin 子场景允许实际输出消失，但 anchored restart 仍须拒绝。

历史：
- ecbe0123e4a… /40936057156：cp1252 解码报错，未跑资格组，改显式 UTF-8。
- ed734a879c933b78006ce9e78e89921d3c44fe69 /40936421939：66/67。
- 40937534551 原失败保留检查：g10 子进程在 fixture rename/recreate 间看到请求短暂不存在，regular-open error2，target_sdk_open_attempted=false；确有安全拒绝，但不是期望的 anchored identity replacement 边界，不能放宽原断言。
- 测试专用新增 child-envelope-checked ready marker，在首次 envelope/targetID 验证后、GO ReadFile/SDK/output pin 前；g10 等到该真实边界再替换，原 postGO identity refusal 不变。

最终通过：
source 7c769dc1b80cd70cbddd0240dcb5de57729104d0
run 40938221167，job 123674334804，67/67（43/43+24/24），30min 固定预算。
artifact 12925153535，3799299 bytes，
sha256 7d2706741ffacbb0d0c7b62954ca4d2d28ded029d49a6b89d900fcb5eb514b32。
docs-only 后续 HEAD 0c0a24bf53b1efecb515ac5e6a8dfcf1a8f8e101；不要把该 SHA 当成已测试源码。
product_admission=false；full P0=false。这一成功本质是 Windows 移植资格/前置，不是实际产品恢复已完工。

### 8.2 实际 Windows 产品启动保护 10/10 已通过

分支 codex/windows-startup-migration-gate-handoff-20261029。
base Windows 3.42 e97b197fa62f3602f0179804b45f7546af2f155e。
只改 3 个产品文件：
1. 新增 windows_migration_gate.h（具体目录请读分支 diff，不凭猜测路径编辑）。
2. apps/reader/desktop/windows_catalog.inc 加 include。
3. examples/reader.c 在 InitializeCriticalSection 后、原 exr_library_open 前加 16 行 gate。

检查 library_path 的标记：
.migration-recovery
.migration-pending.json
.migrate-lock
任一存在/状态不确定则拒绝普通打开；.legacy-map.json 单独存在允许正常升级。
实际 GUI 显示中文 MessageBox，drive 输出 stderr，清理后 return2；
不解析/接管未知 journal，不启用未实现恢复。
这是 cooperative startup protection，不声称消灭所有 race。

第一候选 86d817824c41e72508a0a0d44d7e34fc6e562978 /40938965113：
同源实际 3.42 产品+旧 3.40 fixture 构建、标记与正常场景均通过；末尾 GUI 驱动 GetDlgItem(dialog,1) 写死控件失败。保留失败。
仅改测试驱动，通过真实 PID/#32770/按钮枚举关闭弹窗，产品 3 文件字节不变。

最终：
source 2fff53ff6734ec2b495c841e6669aef562e170d7
run 40939979816，job 123680473398，实际 10/10 success。
artifact 12926312358，4194330 bytes，
sha256 dca517038d2a92e0da834fd2870f516e861f061817b0fbbda023f6e35645f850。
6 个 marker file/dir 拒绝、pending 不创建缺失 DB、clean/legacy-only 实际 schema6→7、真实可见中文弹窗关闭后旧库不变。
没有 fake callback；不将中间 partial reports 当完整通过。

整合机会：
此前已比较 bd28 的 examples/reader.c / windows_catalog.inc 与 e97 baseline 字节相同，
可将上述 3 产品文件的最小 patch 按上下文接入新的公共源码整合分支。
不要 cherry-pick 整个 Windows 分支覆盖 SDK/public modules。
共同源码接入后仍需新 source 的实际产品验证，不能直接复用 10/10 为新源码打勾。

### 8.3 Windows P0 仍缺什么

docs/MIGRATION-WINDOWS-PRODUCT-NEXT-20261029.md
source 52908e5de15643c2bab9ae84876c13d48719a117。

已确认实质缺口：
- Windows lr_* 仍有 stubs；
- recovery worker 未 WIN32 build/install；
- 持久化 file identity：POSIX 33bytes / Windows 49bytes，需要明确版本格式，不能截断迁就；
- public sidecar/private custody 跨域发布流程未有；
- 必须保留既有 lifecycle、source/font lease cleanup、profile locks。
启动 gate 只是防止误开，不能把这些缺口写成完成。

POSIX 新目标恢复参考：
source acf892d4fe852dda4ed668589af53f7b3694f679
run 40864739308，270/270 success；历史 262/270 failure 仍保留。

## 9. 根代理独立验收准备

分支 codex/handoff-independent-acceptance-20261029。
最后远端 HEAD（本次重新读 ref 已确认）：
8867f522a108815fa5b9f6a7a7392485cb20a046。
base audit 6f7dc3bf…，不是公共产品整合分支。

提交：
- c943162c2d93bbfe1a41d1d344ef49b0f96e3bf2：mobile independent script +checkpoint doc。
- 82f0bc538024dbd7bedfead76724d307eb683719：dependent CI。
- 498793614c59e8503720e920c52d1bb72db123b5：checkpoint doc。
- 8867f522…：Claude 三份交接+launcher+README。

源码：
tools/reader_composition/apple_annotation_handoff_independent.py
.github/workflows/apple-mobile-annotation-handoff-independent-20261029.yml
docs/reader-total-progress/handoff-acceptance-20261029.md
注意旧 checkpoint 仍写 66/67、bd28 queued，本文件第5/7/8节是更新状态。

脚本显式参数：
--platform iphone|ipad
--producer-run
--producer-source 完整40hex
--producer-job
--artifact-id
--artifact-bytes
--artifact-sha256 完整64hex

独立验收要求：
- 原 run attempt1 /source/host job completed success；
- 原 ZIP 精确 ID/bytes/hash +安全解压；
- 与622 baseline 的5 feature bodies及完整原 driver字节一致；
- 原始 xcresult 39（5+13+13+4+4）；
- 旧测试5个源 hash；
- 5份保留程序二进制+Info source 独立 hash；
- 14原图与真实 OS dark/light command proof；
- SDK3.41 /emulator 范围明确；
- whole_run_accepted=false /physical=false，不扩大范围。
输出 build/apple-annotation-handoff-independent/<platform>/{inputs.json,result.json}。

独立运行40937262016/source82f，Ubuntu等待既有40935165396/source55ec/attempt1/固定分支，
50min上限+60s状态检查，不重新 dispatch原生生产测试。
然后macOS矩阵审计固定iPhone job123666094860、iPad123666094857。
即使整体producer因另一host失败，也可审计成功host，但不能接受失败host。
当前移动host已有失败，不能把这个等待运行当作即将成功。

尚未完成的目录适配：
此前有 verify_apple_mobile_annotation_handoff /adapter apple_mobile_annotation_handoff_v1 设计草案，但只在旧对话临时状态，未承诺已提交。
新对话必须从已保存源码继续，不依赖旧 JS store。
仅在新producer和独立audit都成功后：
将具体auditjob/artifact/name/hash/result、原source/run/job/artifact/bytes/hash、baseline622、测试正文身份、39/5/14/程序hash全部pin到总审计；
只更新两项mobilehost，固定108不变；
为根验收分支加 total-progress workflow trigger，然后实际跑完整目录审计。
在此之前不报97/108。

## 10. 已有可复用但不能扩权的其他证据

- Apple sync producer 40914421686，source 6c7d043d416c1ab1075016695ae510c7b23dd2e5；
  independent 40920468235，source 8404d9…，三端已独立验收。
  核验涉及真实401、失败时outbox保留、恢复后256分片扫描、原始XCTest。
- macOS annotations producer40923468266/source622、job123625260629；
  independent40928332937/sourcea24e…，39case/14marks/5binaryhash。
- iOS organization40911140164/sourceb259db…，6case包括membership。
- iOS original save40905868673/source127c…；
  independent40910291131，真实系统保存+byte readback。
- font producer40627627614，independent40904394809。

上面缩略 SHA 仅作检索线索；需要精确 pin 时读 API/既有catalog取完整值，不补造。

公共边界 e6b899284744b95dc832db92ed16324711ff5362：
run40871185232，7jobs成功，仍明确 F07=false：
installed_android_sync_runtime=false，
Android仅 adapter-source-runtime，
原Sync network_suites_run=false。
实际targets linux/windows/android/macos/iphone/ipad（iPad从同Applejob）。
各模块/各image私有入口和provider身份检查不等于最终宿主真实网络完整验收。

## 11. Claude 后台任务：实情、准备、阻碍

实际创建数量：0。没有session URL/ID。不能称为“已handoff给Claude”。

曾经在用户禁止前查看过 Claude UI，看到 Sonnet5.5 Medium、Cloud Default和连接repo。
UI里留有未发送C1草稿，选择base codex/apple-sdk342-full-handoff-20261029，
界面曾提示会直接push到base。未点击Send。
用户随后明确禁止电脑操作；不要再访问/发送这个草稿，尤其不要误推公共base。

官方 CLI诊断：
C:\Users\Oscar\.local\bin\claude.exe version2.1.310
auth status：loggedIn=true，claude.ai /firstParty /Pro。
不要读令牌文件、不要把登录凭据放GitHub或输出。
help明确：
- --cloud [description|session_id|url] 创建/附着云session；
- --cloud需要interactiveTTY；
- --model sonnet是别名，--effort medium；
- --bg/--background 是本地后台，不等于云task；
- agents --json可列本地session。
不要假定别名在远端一定等于Sonnet5.5；实际创建后核对模型。

尝试：
1. 非TTY --cloud直接拒绝，需要交互终端，没有任务。
2. 官方CLI+TTY+--model sonnet --effort medium --cloud任务：
   getaddrinfo ENOTFOUND api.anthropic.com，没有任务。
3. Resolve-DnsName api.anthropic.com：Access is denied。
4. 当前执行环境含CODEX_SANDBOX_NETWORK_DISABLED；代理变量存在，但未打印值。
5. 搜索Claude/Anthropic专用插件，返回空；内置GPT任务工具不能创建Claude。
6. 网络策略管理接口不可用；sandbox_approval等类别自动拒绝，不能靠重复确认解决。
7. 后来本地设备短暂unavailable，现在恢复；网络限制仍未获正式解除。

应采取的下一步：
- 检查新会话的实际网络policy/环境状态是否已通过正式设置改变；
- 有受支持的环境管理流程时配置Anthropic必要域名并按流程review；
- 没有该接口时明确需要环境所有者恢复/配置网络，不能假装可自修；
- 不删除guard、不绕代理、不关TLS、不导出OAuth、不换执行器逃逸已拒绝的网络；
- 网络正式可用后，先只创建C1并取得session ID/URL+模型/分支回执，再提交C2/C3，避免无回执重复提交；
- 仍不通时继续GitHub主线，不把等待当进展。

已准备3份独立任务和隔离分支，均从bd28建立，尚无Claude代码提交：
1. claude/handoff-c1-android-sync-20261029
   实际安装Android Sync/WebDAV API34运行：真实上传/下载/hash、401/故障恢复；不是adapterprobe。
   Scope：Android接入+tests/reader_android_installed_sync_handoff/、独立workflow、docs/reader-total-progress/claude-c1-android-installed-sync.md。
2. claude/handoff-c2-product-performance-20261029
   F08：Windows/Linux真实产品UI帧/交互与内存；保留固定书库/阈值，不拿SDK算法benchmark代替。
   Scope：tests/reader_product_performance_handoff/等独立新增；不改Apple或Windows迁移文件。
3. claude/handoff-c3-delivery-licenses-20261029
   F12交付资料/真实依赖许可/六包内容清单；不把未实现恢复写成支持，不做正式Release。
   Scope：docs/reader-delivery-handoff/、tests/reader_delivery_manifest_handoff/，必要最小许可打包。

三份原始完整prompt+launcher+README在：
https://github.com/NoGod3524/EXReader/tree/codex/handoff-independent-acceptance-20261029/docs/claude-handoff-20261029
文件：
C1-android-installed-sync.txt
C2-product-performance.txt
C3-delivery-licenses.txt
Start-Claude-Handoff.ps1
README.md
本地前三prompt+launcher也在同相对路径；控制台默认编码可能显示中文问号，实际读取请用UTF-8，不用默认Get-Content判断损坏。
launcher检测CODEX_SANDBOX_NETWORK_DISABLED后主动拒绝提交；这一保护不可删掉冒充修复。
launcher只是准备，不代表任务已提交。

## 12. GitHub连接器实用说明

优先GitHub连接器，gh登录不可靠。通过工具发现查实际schema，不猜参数。
常用：
- github_fetch(url)可读取api.github.com/repos/NoGod3524/EXReader/actions/runs/ID、
  /jobs?per_page=100、/artifacts?per_page=100、git/ref/heads/分支、git/commits/SHA、git/trees/SHA?recursive=1。
- github_fetch_file(repository_full_name,path,ref)读源码。
- github_fetch_workflow_job_logs(repo_full_name,job_id)读已完成job的文本日志。
  job尚运行时404 BlobNotFound并不代表CI未开始；只在完成后读。
- github_create_branch /create_tree /create_commit /update_ref用于独立分支写入；
  update_ref用expected_sha防止覆盖他人提交，冲突时先读新HEAD。
- github_update_file需已有blob SHA，且显式branch；不要省略branch写默认分支。
- fetch类 structuredContent.content通常是JSON字符串；fetch_file的content是源码文本。
  mutation structuredContent可能直接给sha/commit_sha/content_sha。
  各次响应结构可不同，先辨识再解析，不把工具“Action completed”文本当源码。
- 二进制artifact不能通过github_fetch直接解析；所有下载/解包/xcresult解析在Actions。
- 不输出secret，不调用不支持的敏感API。

## 13. 新对话建议执行顺序

1. 读此文件与适用仓库规则；确认本地dirty状态，创建独立工作区，别覆盖旧改动。
2. 刷新第5节6个run和相关job状态；如有新原始失败，只在Actions里解析。
3. 重新启动3个隔离代理（如有可用工具）：
   A 只处理mobile批注新失败；
   B 修复bd28独立OPDSHash prefix及同源Apple全套；
   C 将最小Windows启动gate接入共同源码并补产品P0。
   主代理负责独立证据与整体整合，不让代理并改同文件。
4. Claude后台连接按第11节正式路径解决。有真实session回执再报已创建；保持“不用电脑操作”。
5. 保留67/67与10/10已通过成果，不无故重复跑；对新共同源码接入产生的新风险跑必要新检查。
6. 批注修复成功→独立原ZIP核验→固定目录适配→总审计，才可能95→97。
7. 推进真正final gates：Android installed Sync、跨端原书/锚点/组织/故障恢复；不能拿Apple scoped/UI模拟器通过替代六端共同产品。
8. 完成有实际结果时再给简短中文更新；不无限等待、不编造百分比、不保证完成时间。

## 14. 给新对话的可直接使用启动指令

“请完整读取这份EXReader交接，延续其中全部有效约束，先复核最新GitHub状态，然后实际修复移动批注失败、Apple3.42公共模块整合的OPDSHash构建接入，并推进Windows迁移P0。可启动3个隔离子代理；Claude任务必须通过后台连接创建，禁止电脑/浏览器UI操作，也禁止绕过网络沙箱。三份Claude任务已准备但尚未提交。固定验收目前95/108；只有真实结果和独立核验完成后才能登记。不要问我重复确认，也不要停在计划。”

