# 并行交付集成验收

本分支 `codex/parallel-integration` 从 `feda26381a7b05c6a1ce3db91a440ca0094e06c5` 开始，保留各交付分支的原始历史。集成源码 `9e4b595ed7e10dcb2d78f5547e4e6a11a04ba3a1` 已通过八组同源云端验收及严格汇总；下列已接受结果只绑定该 SHA。

## 预集成 SDK 候选（阶段一，已云端通过）

预集成源码 `4729f7fc7d908d249704d96ee61cc74ee778a27f` 由三个已独立通过的交付按
`wp9-acroform` → `wp5-border-spacing` → `wp13-apple-review` 顺序合入本分支的合并提交组成，
保留原提交历史；兼容语料首次登记 `00a8838cf6089e67a730ca6fd4956cb45d09c27d` 仍是其祖先。
Android 失败候选与 OPDS facets 未纳入本候选。

同一源码的三组云端运行全部成功：

| 组 | run | 作业 | 覆盖 |
| --- | --- | --- | --- |
| native | `39821205425` | 7/7 | 三平台全量 ctest（含 `native-pdf-form`、`native-table-spacing`）、ASan/UBSan、可移植安装与裁剪安装、安装后组件与公开消费者、JNI/Swift、层依赖、Android arm64 与 iOS/iPadOS 库 |
| acroform | `39821209875` | 3/3 | AcroForm 专用用例、干净构建与 sanitizer |
| spacing | `39821213939` | 2/2 | 专用间距用例与全量回归 |

候选 K 登记在 `docs/validation/sdk-baseline.json`：SDK 3.40.0、ABI 1，受保护树逐项固定。
`tools/check_parallel_integration.py` 的严格汇总现在要求 K 与最终源码的受保护树一致、K 是最终源码祖先、
K 的三组证据运行同源成功、版本/ABI 与头文件一致，并额外要求 `acroform`、`spacing` 两个同源运行；
十组共 28 个上游作业的门槛保持原样，没有删除任何保护检查。OPDS 与 Android 的固定 SDK 常量必须指向 K；
Android 的常量在合入前登记为 pending，文件一旦出现而仍未登记就会被拒绝。

门禁本身已在云端验证：push 触发的协议 run `39823812435` 成功；以 `82f88966c0ca2bbca93837861270b8cb57ebb184`
为受检源码的 dispatch run `39823842117` 通过 protocol 与 baseline 两个作业，逐项核对祖先关系、受保护树、
OPDS 常量、pending Android 守卫、K 的三组证据运行及版本/ABI。两次运行都不授予任何包或能力通过。

未满足项：A 的 Android 新交付（45+10 用例/49 页/48 项门禁）、B 的至少 30 份独立文档与声明范围、
B 之后可能的 K 重冻结、所有权祖先 H、十组同源联合验收。本候选只验收上述声明范围，
`complete_product=false`、`wp16_accepted=false`，冻结 SDK 长测不转移到新源码。

## 交付合并与 SDK 候选重冻结（阶段三，已云端通过）

A（Android）与 B（AcroForm 独立文档语料）按原历史合入本分支，未 rebase 受测历史：

| 包 | 受测源码 | 交付 HEAD | 独立 run | 结果 |
| --- | --- | --- | --- | --- |
| A Android | `8a6636ed8ac6db06ab84e174f5a01c49d12511dc` | `31b36f305085cb8b1468b1d9b9b1ea2d67ee1656` | `39831715741` | 45/45 与 10/10 零失败零跳过、49 页、48 项门禁 `accepted=true`；唯一工件 `12449232819`（149127088 B、digest 有效） |
| B AcroForm 语料 | `a326fd38bbbb481da74657d682f649b1f45f7e2c` | `97e33452a96f1c042dcc98510b51f3e4af7253ef` | `39833769030` | 5/5 作业、四份工件同源；三平台各 75/75 文档、严格汇总 `problems=[]` |

B 改动了受保护集合中的顶层 `CMakeLists.txt`，原候选 K 因此不能沿用。在合并后源码
`d46ff370cb3c5ce9a0ceb4dc1f8b099209149280` 上重跑三组同源验证：native 7/7（`39837151097`）、
acroform 5/5（`39837165548`）、spacing 2/2（`39837179303`），据此重冻结候选 K = `d46ff37…`。
SDK 仍为 3.40.0、ABI 1；`src`、`include`、`cmake`、`tests/fixtures`、`bindings` 与两条受保护工作流未变，
只有 `CMakeLists.txt` 更新。OPDS 的 `BASELINE` 与 Android 的 `SDK_BASE` 都指向 K；
Android 的 `ANDROID_OWNERSHIP_HEAD` 固定到 A 的受测源码，只作为宿主变更审计终点，不替代 SDK 口径。

联合门禁同步更新：`acroform` 期望 5 个作业并核验四份能力工件（`EXReader-acroform-corpus`、
`EXReader-acroform-Linux`、`-Windows`、`-sanitizer`）的 run/source/大小/过期/digest；`spacing` 仍为 2 个作业。
十二组共 35 个上游作业（28 + 5 + 2），十组门槛未变。

### 首次联合尝试的 Apple 失败与修复

首次十二组同源尝试（源码 `6a0806beec03b6de6e9302c3eea957bb5c670d49`，已用标签
`s1-2026-10-22-attempt` 保留）中，三平台 UI 各 12 用例全部通过，但证据收集步骤失败：
`Rejected: SDK file identity mismatch`。

原因在交付形状而非阅读逻辑：SDK 安装规则会安装整个 `examples/`，Android 交付新增的
`examples/android/.gitignore` 随之进入安装树；`actions/upload-artifact@v4` 默认不包含隐藏文件
（`include-hidden-files: false`），sdk 工件往返后少了这个文件，本地登记的整树 SHA-256 清单因此对不上。

最小修复只改 Apple 工作流的 sdk 上传步骤，显式保留隐藏文件，不修改安装规则、不弱化身份校验。
由于这是非 OPDS 路径，按所有权契约重新冻结：先回退 OPDS 合并、把修复放入新的前置祖先 H，
再重新合入 OPDS。

## 下一轮 Apple/Android 集成（原候选，已被本轮取代）

> 本节保留历史候选与失败记录；当前交付身份以 `docs/handoffs/2026-10-22-parallel-index.md`、`docs/handoffs/2026-10-22-A-android.md`、`2026-10-22-B-acroform-corpus.md` 与上面阶段一记录为准。


Apple 审计候选 `e0f162af1fad68353b91f5f595867c4bccd2da81` 的 run `39801977033` 未通过，尚未合入本分支。macOS/iPhone 各 12 个 UI 用例/61 步、SDK 21 项、会话 18 项及三平台原 21 项自检通过；iPad 有三项 UI 失败，严格汇总拒绝验收。固定完整门槛仍为各平台 12 个 UI 用例/61 步/46 份附件、各 21 项原自检、21 项 SDK 及 18 项会话回归。保留本轮与前轮失败证据，后续候选不得拼接通过项。

第七轮 Apple 候选 `de0c1ada17a5488b78154e85ca8bd1beb46cc3ea` 已启动 run `39808190435`。
只读云端诊断确认原选文失败前页面上下文失效；本轮改用只读原生文字控件，并补齐等待失败
现场及失败原件采集。首次导入的原操作后状态缺失，下一轮保留观测继续验证；本轮尚未验收。

Android 原始交付 `9b57cc64094a9c5fc0474ec87ca660d2dc935b74` 的原受测源码为 `6f6bfb77e946d145245d90c7165188566b300e50`，run `39723075163` 已核验同源成功。审计修复候选 `c19854a2aeaefaa5a0c70b6865c17597c7caf21f` 已启动云端 run `39806252140`，尚未验收或合入。原 45 个具名用例保留并加强行为断言，另加独立 10 项回归、真实 49 页计量及 48 项证据门禁正反例；包含普通分页取消入口及跨 Activity 进度提交顺序回归。

联合门禁已加入 Apple 和 Android：Apple 固定八个作业/八份必需工件，Android 固定一个作业/一份完整验收工件。新协议的 21 项正反例已在 run `39802485518` 通过，仅检验门禁本身；下一轮必须在同一新集成源码上重跑十组共 28 个上游作业。九组旧协议的 18 项检查保留 run `39722560085`；既有八组验收不授予新候选通过。

## 已纳入的原始交付

| 包 | 原始交付 HEAD | 独立验收源码 | 当前集成状态 |
| --- | --- | --- | --- |
| 可选 OCR 适配器 | `bbe7139862e1705e7e8954b97c0b9dfbb639287e` | `09c4a54913e5c4211ca44de813ea54a30e241abb` | 同源云端验收通过 |
| 兼容语料协议 | `c8292c885d6b3ac1c27eec646eba3bd3d14ef712` | `5af959aa1b19991f9b8b56528058cfc921adf961` | 保留首次登记祖先；协议通过，真实语料验收未通过 |
| Windows 宿主 | `2d99fcd3a912eb05ad6df8257a13a6c929c860a8` | `40c45799131b3e7f2927d5cdb09a1bf72d9452db` | 原始交付及两组审计修复同源验收通过 |
| Linux 宿主 | `8ae82da506f4c7a1616f25a4544fe3ba77e90f08` | `44e546296862e3258ad885a3706652319c266a56` | 原始交付及审计修复同源验收通过 |
| 旧数据迁移 | `6515640` | `c2d23c29a3b2096c2236fdb414dcd1e66d3243b4`（审计修复） | 原始交付及审计修复同源验收通过 |
| OPDS | `45cff9e4853229a2affe6b8c5ddcfe55f8ac2b4a` | `ce5bfc75b20a0cb4faa22c3ca01ae5fbc910f88c`（审计修复） | 原始交付及审计修复同源验收通过 |

语料首次登记提交 `00a8838cf6089e67a730ca6fd4956cb45d09c27d` 必须保持为集成源码的祖先，不能用重写后的提交冒充原登记。

已纳入的审计修复：Linux `175adc9155836209b6a951b2a46c59fee88a1298`（独立验收源码 `af0fef29c5c61caf3607012965173db1e540330a`），Windows 证据检查器 `70868f85ff195b5a544c4fa40a10006e3671412d`（独立验收源码 `53890584cf67e3c92c63cf5d7bcc8537283e7c1e`）。两者独立复验及本次同源联合验收均通过。

Windows 任务修复 `f24fad18ed2dae30038afa4bf26f1e1cb35c29bd` 已合入，独立验收源码 `32f4f77cd69be5dcd2a66ed31701c5812997a78a`：原 26/158/8 保持通过，新增候选 11/11、旧基线 11/11 反向拒绝。

迁移审计代码随 `a17b277` 纳入受测源码；其独立最终两平台汇总已通过，验收后的文档提交 `b048e5a094253d2625254bc098bbe24daaf9a0b9` 另行合入。OPDS 修复交付为 `9a98f3256f4b1af457521ad188759812266cf0a2`。两包同源联合验收均通过。OPDS 的声明范围不含 HTTPS 实现、DRM 与宿主接入；迁移范围不含高保真格式转换，未定位内容保留于账本。

## 修复与验收门槛

- Windows 任务修复已通过独立及同源联合复验：串行任务取消、候选会话提交、失败恢复、书籍身份、标注操作和持久化错误传播；候选 11/11、旧基线 11/11 反向拒绝。
- Windows 证据修复已通过独立及同源联合复验：50 项证据回归、原 26 项检查、158 步 UI、8 张截图。
- Linux 修复已通过独立及同源联合复验：原 20 步 UI 及标注读取故障、退出码、非默认字号恢复负向回归。
- 联合云端验证：同一集成提交上的原生 CI、安装后的默认示例、修复后的 Windows/Linux UI、可选 OCR 安装消费者、语料协议与登记历史。
- 所有构建、测试、UI、语料生成及证据汇总只在 GitHub Actions 执行。原失败记录和交付证据保留；新增结果另存。

八组同源工作流及结果：

| 组 | 云端 run | 作业结果 |
| --- | --- | --- |
| native | `39716695522` | 7/7；含 Linux ASan/UBSan、安装消费及 iPhone/iPad 各 21 项自检 |
| ocr | `39716697514` | 3/3；release、sanitizers、audit |
| corpus | `39716699709` | 1/1；46 项协议检查，`corpus_accepted=false` |
| linux | `39716702306` | 1/1 |
| windows_evidence | `39716704453` | 1/1 |
| windows_worker | `39716706879` | 1/1 |
| migration | `39716710104` | 3/3；双平台各 65 场景/135 检查、31 项回归、17 项浏览器检查；29 项汇总门禁正反例 |
| opds | `39716712439` | 2/2；各平台 65 场景、8 条消费者链、38 项门禁 |

严格汇总 run `39718130711` 的 protocol、summarize 两作业均成功。`tools/check_parallel_integration.py` 与 `.github/workflows/parallel-integration.yml` 在云端核对完整分页、19 个上游作业、源码、运行状态、必需工件与散列元数据；协议 15 项正反例通过，汇总输出 `accepted=true`。云端工件 `parallel-integration-summary` 保存完整结果，身份见 `docs/validation/parallel-integration.json`。本地只登记云端结论，未下载工件或重新汇总。

OPDS 在最后合入前冻结集成基线；其工作流用该已审计祖先检查本次 OPDS 差异仅属于约定路径。原始包相对 handoff 的独立所有权记录保留；SDK 保护树仍逐项与固定 `a2552d7feb786cd2345d2b0b3eb894777b3254db` 对照。

## 能力范围

OCR 交付仅覆盖识别与坐标适配；PDF 文字层写回、原生文字去重、搜索/选文/标注联合验收和真实扫描件准确率仍待完成。高精度字符框定位未通过独立阈值验收。

语料协议工具完成不代表真实语料验收完成；本次新增登记的真实语料仍为 `0/1710`，保真与保存需独立能力证据。

Linux 宿主声明为不超过 8 MiB 的重排原书。Windows 宿主尚未接入有界大章入口；完整屏幕阅读器验收单独跟踪。各包的完整范围见其交付文档。

## 与可靠性长测的关系

冻结源码 `635225fe6ceb7759a948a1d8cede0ab18ea1cee9` 的云端长测 run `39666440519` 已通过 98 作业及严格汇总，99 份同源工件齐全，冻结 SDK 候选的 WP16 五项登记出口已闭合，记录见 `docs/validation/2026-10-22-reliability-cloud.json`。该文档历史已合入；应用和可选工具不转移这份 CPU 时长。既有包汇总中的 `complete_product=false`、`wp16_accepted=false`、`wp16_cpu_credit_seconds=0` 保持原意：它们仅验收各包声明范围，不另行授予引擎长测或项目整体完成。

依据：`docs/RELIABILITY-HANDOFF.md` 第 6 节、`docs/validation/2026-10-21-png-reliability.json`、`.github/workflows/reliability.yml`。