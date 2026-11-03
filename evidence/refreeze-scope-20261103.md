# SDK candidate refreeze 最小改动面 · 2026-11-03

状态：**只读盘点与待批执行单，未实施**。取证对象为 `95100501`、framework `8ca964fc` 与预演合并树 `769e509566204f53c0020ddbdb94d568bb571efe`；下表散列描述已有对象，不指定它们为已接受的新候选。

**T1：B 待 refreeze。** Ubuntu run `41691589828` 的五项 protocol 全通过；性能 job `126111282946` 在采样前拒绝 `SDK protected tree changed`，`measurement_valid=false`、`results=null`。这没有测出性能退化，也不证明 Git/PR 路径不可行。方案 A 若整合同一产品树也须 refreeze，**分支选择不能绕过基线登记**。

## 1. 两个现有固定 SDK 身份

| 链条 | 当前固定对象 | 作用 |
|---|---|---|
| 集成候选登记 | `docs/validation/sdk-baseline.json.sdk_baseline = d46ff370cb3c5ce9a0ceb4dc1f8b099209149280` | check_parallel_integration 的注册候选、八项 protected_trees、native/acroform/spacing 证据 |
| 性能候选 | `tools/measure_reading_real.py:20 SDK = 9854061be331fe603a1822d9b2b36ee357154927` | R3 采样、baseline ZIP 重审、预算导出和后继严格验收 |

两条身份不能混称为同一个当前 candidate。只改 sdk-baseline.json 不会改变性能脚本的 SDK 身份拒绝。

登记表的 refreeze_trigger 原文：

> Any later change to a protected tree, including package B final corpus or engine work and the accepted Android delivery, requires a new candidate and new evidence

## 2. sdk-baseline.json 字段改动面

文件没有名为 `candidate` 的顶层字段；候选身份实际由 `sdk_baseline` 登记，`candidate` 是验证报告的输出字段。

| 字段 | 当前值/含义 | 批准执行后所需来源 |
|---|---|---|
| sdk_baseline | d46ff370… | 已独立验收的新候选完整 commit `C`，不得使用可移动分支名 |
| protected_trees | 八项 Git object ID | `git rev-parse C:<path>`，保留完整八项集合 |
| evidence.native / acroform / spacing | 39837151097 / 39837165548 / 39837179303 | 新 C 上三次独立的同源成功 run，原 ID 不能转授 |
| sdk_version / sdk_abi | 3.40.0 / 1 | 从 C 的 include/exr/base.h 读取；当前预演头文件为 3.41.0 / 1 |
| status / declared_change | 旧候选 K 及其交付范围 | 新候选真实范围、实际树变化与证据，不预写通过 |
| previous_baseline / superseded_candidate / history_note | 历史关系 | 保留旧候选与旧证据，将新旧替代关系准确登记 |
| consumer_contract / package_rule | 旧 SDK 版本与 K 一致性要求 | 按真实版本与契约更新说明，继续逐树验证 |
| refreeze_trigger / schema / contracts 的字段集合 | 基线变更触发与守卫说明 | 继续保留触发规则；contracts 所记活跃守卫须与新候选对应 |

相对**登记 K=d46ff370**，预演当前有五项不同（其中 native.yml 不同）；它不是“相对性能 SDK=9854061b 的四项差异”那张表。

| protected_trees key | 登记 K 值 | 预演 769e5095 值 | 盘点 |
|---|---|---|---|
| `src` | `5f34c5b7538f478c638fb98cd187b14ffff1eebc` | `e6bb1079cd50675a21ffe19cd99a6c08590eb3cf` | 需新登记 |
| `include` | `b3e88897939967688e607054fa524ec11669b9b4` | `775b4205dc86452d20e5744c73a3f1ae0a61d877` | 需新登记 |
| `cmake` | `31298d7a58a15b99694b7c8710d838fde7baf7b9` | `9ec9a577bc6b37c5527e12cbf5d600d5f199b483` | 需新登记 |
| `CMakeLists.txt` | `962dcfa741f0c3af5a8d0c25c33efa521cc1e032` | `15de1378caa992782fe18bf296cdaa638e607012` | 需新登记 |
| `tests/fixtures` | `2a1fd5e58347f6ed8692996ba855c703f3c2da46` | `2a1fd5e58347f6ed8692996ba855c703f3c2da46` | 仍须复核，当前相同 |
| `.github/workflows/native.yml` | `be39352acf9313ab596030efa6ecea9d5a4a4540` | `2df429e50fa80532026d0de46ee7fc5470b5274c` | 需新登记 |
| `.github/workflows/reliability.yml` | `a27c1d1ca5a7aae1d590ceed356fdd5cd81abdb9` | `a27c1d1ca5a7aae1d590ceed356fdd5cd81abdb9` | 仍须复核，当前相同 |
| `bindings` | `54c12f70a1a63cae6574984a388b66bf6248c38e` | `54c12f70a1a63cae6574984a388b66bf6248c38e` | 仍须复核，当前相同 |

最终 C 如果再修改受保护 workflow，上表须从 C 重新计算，不能复制预演散列。

## 3. check_parallel_integration.py：受影响断言，保留而非放宽

| 位置 | 断言 | refreeze 要满足的条件 |
|---|---|---|
| baseline_problems，约 178–194 行 | 完整 immutable SHA；baseline != 汇总 source | 候选 C 与后继登记/汇总源码 S 分开提交，C 是 S 的前置候选 |
| 同函数 | protected_trees 恰好为 PROTECTED_TREES；evidence 恰好 native/acroform/spacing | 保持八条保护路径与三类证据，不删检查 |
| 同函数 protected loop | 汇总源码的每个保护对象等于注册候选对象 | S 与 C 在保护集相同；发生新保护改动则再次 refreeze |
| 同函数 contracts loop | OPDS BASELINE 与 Android SDK_BASE 均等于注册 sdk_baseline | `.github/workflows/wp15-opds.yml` 当前 d46ff370；`tools/android_host_evidence.py` 当前 9854061b，二者需同步新 C |
| verify_baseline:338–340 | compare 的 merge_base 是 C，source 在其后/相同 | 维持祖先关系；baseline_problems 仍拒绝 C==S |
| verify_baseline:343–352 | 活跃 contract 存在、可解析，不得仍标 pending | 保留活跃 Android 守卫，不以 pending 绕过 |
| verify_baseline:354–362 | 三个不同正整数 run ID；head_sha==C；对应 workflow；completed/success | 新 native.yml / acroform.yml / wp5-border-spacing.yml 各自成功；不是 reading-required 父 run 三次复用 |
| verify_baseline:363–368 | 注册 version/ABI 等于 C 的公开头 | 按 C 真实版本登记，不把新版头标成旧版 |
| selftest:295–327 | 拒绝保护集变化、证据集漂移、旧 pin、同源假基线等 | 继续通过现有正反例；目前没有仅因正常 refreeze 就必须改写这些断言的证据 |

因此本项的核心是**更新输入登记、候选证据与守卫常量**，不是将 assert 改成允许差异。

## 4. 性能证据：需要哪次 run 的哪些数据

现有流程把“独立 seed 测量”“预算/图像审阅导出”“后继严格验收”分成不同运行，不可从失败 T1 补造测量值。

| 角色 | 本次所需新 run | 必需数据 |
|---|---|---|
| R_seed(E) | 新 C 的后继采样源码 P 上，reading-real.yml 单 job、baseline_only=true、require_budgets=false；每个实际环境 E 单独取证 | run ID/attempt/job ID、P 完整 SHA、SDK=C、completed/success；唯一 reading-real-<run>-<attempt> artifact 的 ID/digest/bytes/过期与 source 身份；summary 原始字节 SHA |
| 同一 R_seed(E) 原始测量 | 不能用 41691589828，它 measurement_valid=false | 八份真实输入各五次，共 40 新进程原输出/命令/stderr/exit 0；12 对参考页原图、摘要、像素差值；全部 route RGBA/UTF-8/位置签名；source_clean、before==after、受保护对象、编译/消费者/安装 SDK identity |
| 同一 R_seed(E) 指标 | 从完整有效 summary 导出，不手填 | 每项 p95、延时/内存/回退计数、consumer/installed SDK bytes；contract/corpus/font SHA；CPU、编译器、参考版本、OS/arch/image；measurement_valid=true、accepted=false、render_parity_granted=false |
| R_review / R_export(E) | reading-pixel-diagnostic.yml 绑定新 R_seed(E) 的 source/run/artifact/digest | 12 对原图的实际 finding、图像 SHA、reviewed；已提交 review JSON 的路径/SHA；export_reading_real_budgets.py 核原 ZIP/报告后按现有公式导出 budgets |
| R_strict(E) | 预算已提交后的另一轮、相同环境完整验收 | 40 进程/12 页重跑；accepted=true、measurement_valid=true、problems=[]、拒绝回归通过；预算选择、签名、参考图与来源链重新核实 |
| R_required | 新预算与 SDK 登记落源后的完整 reading-required | 所有上游同源通过，最终 accepted=true；protocol 子项通过不等于总 gate 通过 |

未来 run ID 尚未产生，本步不得以旧 ID 占位冒充新证据。历史流程可追溯的 seed：

| 环境 | 旧 seed run / source | 旧预算与审阅 |
|---|---|---|
| EPYC 7763 | 39899829270 / 887e1bb59ef6f28c15824cb7593654f3610f3cef | tests/reading_real/budgets.json；docs/validation/reading-real-pixel-review.json |
| EPYC 9V45 | 40010390609 / 9442e84d60469de5551de7ce7e62191a0059d9d1 | tests/reading_real/environments/amd-epyc-9v45/budgets.json；对应 reading-real-amd-epyc-9v45-pixel-review.json |
| Xeon 8573C | 40010395155 / 同上 | tests/reading_real/environments/intel-xeon-8573c/budgets.json；对应 reading-real-intel-xeon-8573c-pixel-review.json |

旧数据继续绑定旧 SDK/环境。可复用逐页 finding 的条件见 READING-CPU-BASELINES.md：原图字节及全路由签名完全一致并登记等价来源；新源码仍要自己的运行。

### 与新证据直接联动的文件

- `tools/measure_reading_real.py:20, 538–545`：将性能 SDK pin 对齐已接受 C，保留祖先、语料登记与逐保护对象相等校验。
- `tools/export_reading_real_budgets.py:76–103`：导入上述 SDK/PROTECTED；核 R_seed 原报告、40 次输出和 SDK identity。更换 pin 不能省略重新测量。
- `.github/workflows/reading-real.yml:63–65`：将预算/契约/主 review 与旧 `f32bb8aa…` 比较的冻结锚点需要经批准的版本化更新，否则新预算/主 review 会先被拒绝；继续保留身份锁，不删除 diff 检查。
- `tests/reading_real/environments.json`、对应预算 JSON、对应 review JSON：记录新 seed/attempt/artifact/digest/summary SHA、精确环境与新文件 SHA；`docs/validation/reading-real-performance.json`、READING-REAL-PERFORMANCE.md、READING-CPU-BASELINES.md 记录新结果并保留旧身份。
- `tools/reading_real_environments.py:62–102`：目前 schema=1、环境键唯一、原 7763 legacy 预算字节固定且必须登记恰好一次；不能直接覆盖 legacy 文件或给同一环境再加一条来容纳新版 SDK。**新 candidate 的预算路径/登记版本隔离方式是待批设计点**；若需更改 selector/schema，应保留旧证据并补拒绝回归，不能临时删除 legacy/精确环境约束。
- `tests/reading_real/contract.json` 和语料 real-v1.json：沿用现有测量公式、40/12 计划与固定输入；如目标另要求变更，它将扩大为新的测量契约，本清单不自行实施。
- 本次 Apple native 版本失败另有显式安装 SDK 选择问题：`tools/build_apple_host.py` 默认 3.40.0，预演头为 3.41.0。新 native 证据前须核实明确的版本选择；若调整受保护 native.yml，必须先纳入候选 C 再采证。不能宣称仅改 registry 就已消除全部平台失败。

## 5. 既有流程是否可照用

已执行 `rg -n -i 'refreeze' docs`，命中 sdk-baseline.json 的 refreeze_trigger 和 docs/validation/2026-10-22-preintegration.json:302 的待重冻条目。继续查中文“SDK 候选重冻结”，存在实际交付流程与成功历史：

| 本地来源 | 可沿用步骤 |
|---|---|
| docs/PARALLEL-INTEGRATION.md:34–52，交付合并与 SDK 候选重冻结 | 先整合固定源码；在同一 C 重跑 native、acroform、spacing；再更新注册 K、受保护对象与两份 SDK pin；原长测不转授 |
| docs/READING-REAL-PERFORMANCE.md:32–70 | 独立有效 baseline → 12 页实际审阅 → 云端预算导出 → 预算落源 → 后继完整严格运行 |
| docs/READING-CPU-BASELINES.md:15–47 | baseline_only 采样；按精确 CPU/编译器/参考工具分开冻结；保留旧预算；原始 40/12 数据重审 |
| docs/READING-PIXEL-REVIEW.md，末节“新 SDK 与预算出口” | 新 SDK 完整测量与全部 12 页新证据，签名改变时明确审阅和新基线登记 |
| .github/workflows/reading-pixel-diagnostic.yml:9–38, 77–97 | 已有只读采证/模板/审阅预算 exporter 的 dispatch 输入与实现 |

结论：**有既有流程可沿用**；未发现一份可以不修改身份参数便直接执行的新 SDK 全链自动 refreeze 脚本。以下执行单按上述现有步骤编排，预算登记隔离方式待批。

## 6. 待批执行单（B 档，未执行）

记号：C=最终 SDK 产品候选，S=后继登记源码，P=含性能 pin 的采样源码，Q=预算/审阅落源，R_seed/R_strict 为不同运行。所有 SHA/run/digest 取实际结果，不提前造值。

1. **批准边界**：owner 确认新候选范围与版本、目标环境、旧证据保留方式、预算登记隔离方案。保持默认分支/Settings/ruleset 不变；不将 refreeze 混入 ledger PR #28。
2. **固定 C**：在独立分支保留已验语料三路径处理；把必要的 SDK 显式版本选择纳入最终树，列出相对旧 K 的保护集 diff。若之后再改任何保护对象，重新固定 C。
3. **接受 C 的新 SDK 证据**：按 PARALLEL-INTEGRATION 的三组运行，在同一完整 C 上运行 native / acroform / spacing，全部完成成功并核 jobs/artifacts。当前 T1 原生失败 run 不能登记为新 candidate 的成功证据。
4. **后继登记 S**：sdk_baseline=C；从 C 抽取八项 protected_trees 与头文件 version/ABI；登记三个新 run；同步 OPDS BASELINE / Android SDK_BASE；保留旧登记历史。C!=S，C 是 S 祖先；运行现有 baseline 与正反例门禁。
5. **性能采样 P**：性能 SDK pin 指向 C，保护对象与 C 一致，沿用测量契约。经批准调整冻结锚点与预算登记版本边界，保留所有旧证据锁。使用已有 reading-real.yml 的 baseline_only=true / require_budgets=false 对每个目标环境独立运行 R_seed(E)；要求 completed/success、40/12 完整、measurement_valid=true/accepted=false。
6. **审阅与导出**：把真实 R_seed 的 run/source/artifact/digest 传给 reading-pixel-diagnostic.yml；全部 12 页实际审阅并提交 review，再以 exporter 核原 ZIP/报告导出预算。按既有公式，不调整阈值使失败候选过关。
7. **冻结 Q**：提交新预算、review、精确环境登记与散列、相应冻结锚点和出处文档；旧候选与旧环境数据继续可追溯。未知环境不得套用近似 CPU 预算。
8. **独立严格复验**：预算提交后运行同环境 R_strict，要求完整 40/12、accepted=true、拒绝回归通过；再对完整新来源运行 reading-required，记录父 run、所有上游、最终 job 与 artifact 身份。未取得这些出口前只写“待 refreeze/待验收”，不提前改进度分。
9. **失败与回退**：任一步失败保留原报告、停止后续登记；未接受的候选不替换已接受身份。登记已落源需要撤销时用逆向提交与受保护 PR，不 force-push；不靠默认分支切换解决候选身份不匹配。

**refreeze 属基线变更，需 owner 一句“执行”（B 档），本步不得实施。** 本次只更新独立 RESULT.md 并生成本清单；未编辑 SDK 登记/代码/workflow/预算，未运行测试或触发云端，未提交/推送本清单，未修改 catalog、Settings、默认分支或 ruleset。
