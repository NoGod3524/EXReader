# Performance 门禁恢复提案 · 2026-11-08

**目前不能恢复 required。** 本 PR 只测量和提案；E3 仍是 `advisory: true, accepted: false`，issue [#32](https://github.com/NoGod3524/EXReader/issues/32) 的截止仍为 **2026-12-15 00:00 America/New_York**。

## 采集对象与前置检查

受测源码 `2f288e15066d616972d312e638b5d9dd04d6e786`（采集前 fetch 核对 main）。从本工作树重新构建原有 `tools/perf/CMakeLists.txt`，SDK 产品代码未改。沿用 E1 的四章确定性 EPUB、冻结 Noto Sans CJK 字体、Release 默认功能、720×1040 / 1280×800 / 2560×1440、margin 48、字号 24。每次新进程，首帧 + 32 顺序页 + 16 固定 seed 随机页，验证 RGBA/文本/位置签名，暖 OS 文件缓存；不裁剪异常、不平均多个进程、不删除失败批次。

采集前逐项确认：

- [ ] 暂停自己启动的构建、下载、索引和测试；关闭经用户同意的高负载应用。不要终止别人的任务。使用专用宿主或维护窗口，确保其他任务不会在采集中启动。
- [ ] AC 接通、节电关闭；记录电源计划及 CPU 最小/最大性能、boost 策略。保存原值；临时 AC min=max=100、boost=0，结束在 `finally` 恢复并读回核对。该设置是请求，不能当作有效频率锁定的证明。
- [ ] 记录 CPU/核数/RAM、OS/build、编译器/flags、依赖树、运行库、runner 标签、源码和工具/二进制/字体/输入散列；未知项填 unknown。
- [ ] 记录 SMBIOS 厂商/型号与 HypervisorPresent。HypervisorPresent=true 本身不证明运行于 VM；若是 VM，额外记录宿主争用和 vCPU 分配，未验证独占时仅诊断。
- [ ] 先采集至少 10 秒的逐核性能计数器、性能限制标志与进程 CPU 增量，再等待负载安静。正式专用 runner 预设整机忙碌度 ≤5%，等待最多 15 秒；任一次未满足则整批不合格。此轮探索用 ≤25%、3 秒，不能据此声称环境安静。
- [ ] 读取温度/热节流证据；温度不可读时登记 unknown。检查负载下有效性能是否漂移，不以系统报告的名义 MHz 代替有效频率。出现限频或无法排查热状态时先解决环境问题。
- [ ] 同一核心、高优先级、串行，无 GUI；预先声明每组至少 5 个进程、一次完整批次。所有八项指标均要求 `100×(max-min)/nearest-rank p50 <5%`。不以 CV、单个指标或挑出的五次代替整批极差。
- [ ] 先冻结预算，再在同环境采集独立候选；候选不通过时保留原阈值和失败证据。

本轮工具：`preflight.ps1` 记录环境和进程 CPU **增量**，`fixed_clock.ps1` 临时设置并恢复电源，`gate_capture.py` 复用 E1 原操作计划并将资格收紧到 ≥5 次、<5%、空闲目标必须满足。`gate_policy.py` 从全部原始 stdout 重算指标、校验散列/签名/环境，输出三档阈值与严格判定。旧 E1 的 <10% 规则没有修改。

[TYPOGRAPHY-BENCH.md](TYPOGRAPHY-BENCH.md) 的 18 组字体/行高测量使用宿主 input→present 端到端口径；其 100/200 ms 目标与这里的无窗口 SDK RGBA 计时不同。本提案重采 E1 的三种配置，不将两个数据集混合导出预算。

## 环境问题与因果边界

旧数据的直接证据在 [e1-load-analysis.json](../../evidence/perf-gate-20261107/e1-load-analysis.json)：普通轮采集前整机忙碌度 14.80%–100%，normalized 17.19%–34.11%，独立候选 9.96%–29.41%。旧采集器等待超时后仍会测量，旧 `summarize` 不把 `idle_target_met=false` 纳入资格判定。旧 normalized/candidate 使用的 35% 上限全部满足，因此**超时缺口并非已证实的旧 29.51% 直接原因**；高背景负载与短时测量竞争已被记录。

本轮 preflight 看到 `DeepSeek Harness` 持续使用 CPU；preflight 自身的 PowerShell/WMI 也有开销，因此遥测在原生计时前后执行。固定 CPU、禁用 boost 后仍有波动，说明这些设置尚不足以隔离噪声；不能把全部波动归因于某一个后台进程或 CPU 频率。

Lenovo 83JT，Core Ultra 7 256V，8 核/8 逻辑核，Windows 11 build 26200，约 16 GB RAM，MinGW GCC 16.2.0。SMBIOS 没有 VM 来宾签名，HypervisorPresent=true；温度接口返回 Access denied。性能限制计数器见逐次 pre/postflight，零标志不替代温度证据。有效频率漂移及热节流仍未完全排除。

## 重采实测

| 轮次 / 核心 | 配置 | 新进程数 | 八项中最大离散度 | 首屏离散度 | 未达空闲次数 |
|---|---|---:|---:|---:|---:|
| attempt-2 / CPU 6 | default-release | 5 | 15.615% | 6.638% | 1 |
| attempt-2 / CPU 6 | 1280x800 | 5 | 14.050% | 1.564% | 0 |
| attempt-2 / CPU 6 | 2560x1440 | 5 | 5.663% | 1.935% | 0 |
| attempt-3 / CPU 3 | default-release | 5 | 3.922% | 2.944% | 4 |
| attempt-3 / CPU 3 | 1280x800 | 5 | 20.593% | 4.203% | 0 |
| attempt-3 / CPU 3 | 2560x1440 | 5 | 6.254% | 6.254% | 0 |
| candidate / CPU 3 | default-release | 5 | 9.471% | 9.471% | 1 |
| candidate / CPU 3 | 1280x800 | 5 | 6.516% | 4.167% | 4 |
| candidate / CPU 3 | 2560x1440 | 5 | 22.080% | 5.327% | 5 |

三轮完整采集共 **45 个新进程**；另保留 attempt-1 的 1 个进程（5% 空闲目标持续无法满足后停止本地采集，电源已恢复）。完整三轮均无资格：attempt-3 默认组仅离散度达标，4/5 次未满足探索轮空闲条件。独立候选八项最大离散度为 **9.471% / 6.516% / 22.080%**，验收 1 未满足。

每轮 samples.json/raw/ 保留逐次指标与签名。attempt-2 的“>=10%”控制台提示继承自旧采集器；其 JSON stable 由新 <5% 规则计算，审计再次从 raw 重算。attempt-3/candidate 的提示已修正。

[strict-check.json](../../evidence/perf-gate-20261107/strict-check.json) 核对独立候选 15 个进程：环境/工作负载/签名一致，数值门禁无超限；基线资格与候选稳定性失败，返回 1，local_numeric_pass=false、e3_restoration_granted=false。

## 三档数字与依据

以**同环境、同配置、同指标**的合格冻结基线进程 p95 为分母，定义 `R=max(候选各延迟指标进程p95 / 对应基线进程p95)`。警告不会改变退出码，门禁/硬上限超出都会返回非零；资格、环境、签名失败也返回非零。所有输出继续保留 E3 advisory 身份。

| 档位 | 数字 | 导出与处置依据 |
|---|---:|---|
| 警告 | **1.10×** | 基线 p95 加 10%；当整批极差 <5% 时预留两倍该噪声目标，仅提示。这个倍数是政策选择，不是置信区间。 |
| 门禁 | **1.25×** | 基线 p95 加 25%；沿用 E1/R3 既有延迟余量，超过阻塞。 |
| 硬上限 | **1.50×** | 基线 p95 加 50%；建议同环境绝对拒绝并要求人工复核。现 E1 只规定 >1.5× 人工复核，升级为自动拒绝需 owner 批准。 |

nearest-rank，5 个进程的 p95 就是最大值；这是本轮有限样本上界，不是总体尾延迟估计。延迟毫秒阈值统一向上取整到 0.001 ms。RSS 不做机器速度归一化，另保留 E1 门禁 `ceil(基线RSS p95×1.05)+1MiB`，不放宽到 25%/50%。

**当前没有合格基线。** 下列绝对值由 attempt-3 的全部原始数据脚本导出，`three-tier-policy.json` 明确 `eligible=false`；用于审议和检验工具，尚未满足“基于干净数据定阈值”的验收。完整七项延迟×三组及内存值都在该 JSON，不手填或覆盖历史预算。

| 配置 | 指标 | 当前独立候选 p95 ms | 警告 ms | 门禁 ms | 硬上限 ms | 数值结果 |
|---|---|---:|---:|---:|---:|---|
| default-release | open_ms | 36.2745 | 38.775 | 44.063 | 52.875 | 三线以下 |
| default-release | first_visible_ms | 84.8422 | 85.882 | 97.593 | 117.111 | 三线以下 |
| default-release | turn_p95_ms | 18.8689 | 20.320 | 23.091 | 27.710 | 三线以下 |
| default-release | random_p95_ms | 161.7200 | 170.656 | 193.928 | 232.713 | 三线以下 |
| 1280x800 | open_ms | 35.3497 | 38.428 | 43.668 | 52.402 | 三线以下 |
| 1280x800 | first_visible_ms | 84.9704 | 91.857 | 104.383 | 125.259 | 三线以下 |
| 1280x800 | turn_p95_ms | 21.9385 | 24.331 | 27.649 | 33.179 | 三线以下 |
| 1280x800 | random_p95_ms | 188.3240 | 199.249 | 226.419 | 271.703 | 三线以下 |
| 2560x1440 | open_ms | 37.4109 | 39.089 | 44.420 | 53.304 | 三线以下 |
| 2560x1440 | first_visible_ms | 128.8714 | 138.294 | 157.152 | 188.583 | 三线以下 |
| 2560x1440 | turn_p95_ms | 64.3240 | 66.446 | 75.506 | 90.607 | 三线以下 |
| 2560x1440 | random_p95_ms | 563.9887 | 625.823 | 711.163 | 853.395 | 三线以下 |

最差延迟项为 2560×1440 turn_max_ms：基线 p95 61.1610 ms，独立候选 74.7641 ms；三线为 **67.278 / 76.452 / 91.742 ms**，比例 **1.2224×**，只越警告线。全部延迟低于门禁/硬上限；稳定性仍失败。

| 配置 | 当前 RSS p95 bytes | 独立 RSS 门禁 bytes |
|---|---:|---:|
| default-release | 38653952 | 41639527 |
| 1280x800 | 38653952 | 41630925 |
| 2560x1440 | 41713664 | 44908135 |

冻结预算原始样本 SHA-256：`7dec0f1b9988531437edbbca8ecbbcad8de94c10b29980d172699cf45b159ec6`；导出器：`ca749172f04248d97d8345dc0b68331667595dc11c87288e62e1d0afcda84e20`；预算文件：`fc2937e1c22041ab973d47abeecddca61f8f50cdfdb053102921f3d431f82c7f`。预算先于候选采集导出；审计拒绝候选早于冻结时间、预算重写、样本散列变动和环境不兼容。

## 慢机器与归一化

直接把本机毫秒预算用于慢机器会误报。当前可执行策略是每个 `comparison_key` 独立建基线，并用上面的 R 表示回归比例；CPU、OS、编译器/flags、依赖、运行库、电源和亲和性不匹配则拒绝比较，登记新环境。内存仍按字节约束。即使机器慢两倍，只要相对其自身合格基线不回退，就不会因沿用本机毫秒线而误报。

跨机器校准仅建议用于诊断：冻结一个与阅读 SDK 无关的固定次数整数计算操作及固定尺寸 RGBA 混合操作，各测 ≥5 次，取 p50；分别估计 CPU/内存和栅格速度系数，再考察 `阅读延迟/对应校准耗时`。在原生计时区间外前后测校准，漂移 ≥5% 时整批作废。不能用待测阅读操作自身作为分母，否则会抵消真实回归；不能用单一计算系数归一化 font I/O、PDF 解码和 RSS。需在慢机器实测验证后另提政策；本轮没有跨机器数据，不启用跨环境硬门禁。

## 可直接套用的 workflow 提案

以下完整 unified patch 与 [proposed-workflows.patch](../../evidence/perf-gate-20261107/proposed-workflows.patch) 一致，已用 `git apply --check` 检查。**本 PR 未应用。** 新文件 `.github/workflows/performance-gate.yml` 从第 1 行插入；`.github/workflows/reading-required.yml` 替换文件开头的注释与 push/pull_request 分支行。其余现有流程和五组 core 门禁保留。

新增 `performance-tier` 是专用 Windows runner 的补充数值检查，包含三档注解、稳定性、散列和签名审计；不是八份 real-v1 参考图/来源严格复验的替代品。runner 必须有 `exreader-perf` 标签、Python/CMake/Ninja/GCC，并事先在相同构建目录/依赖/编译器上取得合格基线，将 `PERF_BASELINE_DIR` 指向该已提交证据目录（含 `three-tier-policy.json`）。不能将本轮 ineligible 文件设为批准基线。新 runner 先手动观察；完成下述环境键与 strict 模式实现、取得合格基线并经严格复验后，再注册为必需检查。

```diff
--- /dev/null
+++ b/.github/workflows/performance-gate.yml
@@ -0,0 +1,64 @@
+name: Performance tier probe
+on:
+  pull_request:
+    branches: [main]
+  workflow_dispatch:
+permissions:
+  contents: read
+concurrency:
+  group: performance-tier-${{ github.repository }}
+  cancel-in-progress: false
+jobs:
+  tier-probe:
+    name: performance-tier
+    runs-on: [self-hosted, Windows, X64, exreader-perf]
+    timeout-minutes: 45
+    env:
+      PERF_BASELINE_DIR: ${{ vars.PERF_BASELINE_DIR }}
+      PERF_RUNNER_LABEL: exreader-perf
+    defaults:
+      run:
+        shell: pwsh
+    steps:
+      - uses: actions/checkout@v4
+      - name: Require an approved baseline before building
+        run: |
+          $ErrorActionPreference = 'Stop'
+          if (!$env:PERF_BASELINE_DIR) { throw 'PERF_BASELINE_DIR must identify the committed baseline for this exact runner' }
+          $policy = Get-Content "$env:PERF_BASELINE_DIR/three-tier-policy.json" -Raw | ConvertFrom-Json
+          if (!$policy.eligible) { throw 'Baseline is ineligible' }
+          New-Item -ItemType Directory -Force build/perf-gate | Out-Null
+      - name: Build the unchanged SDK and pinned E1 probe
+        run: |
+          $ErrorActionPreference = 'Stop'
+          cmake -S tools/perf -B build/perf-gate-build -G Ninja -DCMAKE_BUILD_TYPE=Release
+          if ($LASTEXITCODE) { exit $LASTEXITCODE }
+          cmake --build build/perf-gate-build --target e1-probe --parallel 4
+          if ($LASTEXITCODE) { exit $LASTEXITCODE }
+          python -c "import sys; sys.path.insert(0, 'tools'); from host_font import fetch; fetch('build/perf-gate-font')"
+          if ($LASTEXITCODE) { exit $LASTEXITCODE }
+      - name: Measure five fresh processes per viewport
+        run: |
+          pwsh -NoProfile -File tools/perf/fixed_clock.ps1 -Build build/perf-gate-build -Font build/perf-gate-font/Reader.otf -Output build/perf-gate/candidate -Cpu 3 -Runs 5 -IdleCpuMax 5 -IdleTimeout 15
+          exit $LASTEXITCODE
+      - name: Audit raw samples and enforce the frozen tiers
+        if: always()
+        run: |
+          python tools/perf/gate_policy.py check "$env:PERF_BASELINE_DIR/three-tier-policy.json" build/perf-gate/candidate build/perf-gate/tier-result.json
+          $auditExit = $LASTEXITCODE
+          if (Test-Path build/perf-gate/tier-result.json) {
+            $report = Get-Content build/perf-gate/tier-result.json -Raw | ConvertFrom-Json
+            foreach ($row in $report.comparisons) {
+              if ($row.exceeded -contains 'warning') { Write-Output "::warning::$($row.configuration)/$($row.metric) ratio=$($row.ratio)" }
+              if ($row.exceeded -contains 'gate') { Write-Output "::error::$($row.configuration)/$($row.metric) gate exceeded" }
+              if ($row.exceeded -contains 'hard') { Write-Output "::error::$($row.configuration)/$($row.metric) hard cap exceeded; owner review required" }
+            }
+          }
+          exit $auditExit
+      - name: Preserve all attempts and policy restoration evidence
+        if: always()
+        uses: actions/upload-artifact@v4
+        with:
+          name: performance-tier-${{ github.run_id }}-${{ github.run_attempt }}
+          path: build/perf-gate/
+          if-no-files-found: error
--- a/.github/workflows/reading-required.yml
+++ b/.github/workflows/reading-required.yml
@@ -1,11 +1,10 @@
-# E3: no longer the required check; retained performance evidence is advisory.
-# Required non-performance context: reading-required-core. Do not cite advisory results as acceptance.
+# Activation only after issue #32 owner restoration record and strict candidate verification.
 name: Required native reading SDK
 on:
   pull_request:
-    branches: [codex/framework]
+    branches: [codex/framework, main]
   push:
-    branches: [codex/framework]
+    branches: [codex/framework, main]
   workflow_dispatch:
 permissions:
   contents: read
```

## 恢复顺序与回滚

1. 取得专用/安静且热状态可验证的 runner，完整 ≥5 次/配置、所有八项离散度 <5%；从原始样本导出并冻结三档预算，登记环境/源码/导出器/字体/输入/二进制/样本散列。再做一次独立同环境严格复验，不按候选结果扩预算。
2. 在 P/F07 provider 之后的实际候选上，完成既有 real-v1 八原件、Poppler 参考图、RGBA/文本/位置签名、来源/run/attempt 和冻结预算的完整严格复验。合成 EPUB 与 19 本像素回归各自提供不同证据，不能替代此步骤。
3. 将本地原型推进到可验产品变更的实现：当前继承的 E1 comparison_key 包含被测 SDK DLL 散列，工具刻意只做同二进制重复采样审计；恢复前要把被测 SDK 身份保留在溯源记录、从环境兼容键中剥离，继续严格核对第三方运行库，并验证跨源码候选的签名/数值拒绝行为。同时补充并审阅性能报告生产者的显式 strict 模式：目前 `tools/measure_reading_real.py` 末尾调用 `perf_policy.advisory()`，它强制 `accepted=false`；旧 `tools/reading_required.py` 又要求 `accepted=true`。**仅改 workflow 或规则集无法恢复严格验收。** 该生产者改动和 Linux refreeze 不在本 PR 允许范围内，另提实现与拒绝性测试。
4. Owner 在 #32 记录以上证据与恢复决定；批准硬上限处置、冻结预算和 strict 模式后才应用 workflow patch。先 workflow_dispatch，确认同源同 attempt 严格汇总和失败样本确实拒绝，再用真实 PR 验证检查注册。
5. 保存规则集 JSON，在现有 `reading-required-core` 之外增加已验证的 `performance-tier` 和严格 `reading-required` 检查，绑定实际 GitHub Actions app；保留其余保护字段，不凭猜测填写上下文名。待真实 PR 活体验证后宣告 advisory → required。
6. 回滚时依据已保存规则集只移除新加的性能必需上下文，保留 core；撤回本 patch、恢复报告 advisory 身份，保留失败/run/原始样本，不取消 workflow run。Owner 将理由与下一次复验计划记入 #32。

E3 条件当前：环境与原始数据绑定已采集；稳定性不合格、热状态未排清；新真实候选完整严格复验、可接受的冻结预算、生产者 strict 模式、owner 决定均未完成。因此现在**不能恢复**。12 月 15 日仍未完成时，按原 E3 转为只读发布，不延长 advisory。

## 复现与核验

本机构建命令保存在 `evidence/perf-gate-20261107/build-command.json`（本机依赖路径需存在）。按数组运行 configure，再 `cmake --build evidence/perf-gate-20261107/build --target e1-probe --parallel 4`。字体为现有 host_font.py 固定散列资产；跨机先核依赖树，不挪用本机预算。

```powershell
# 每次 Output 必须是尚不存在的目录；该轮保持原样，不自动重试。
pwsh -NoProfile -File tools/perf/fixed_clock.ps1 -Output evidence/perf-gate-20261107/NEW-baseline -Cpu 3 -Runs 5 -IdleCpuMax 5 -IdleTimeout 15
python tools/perf/gate_policy.py derive evidence/perf-gate-20261107/NEW-baseline evidence/perf-gate-20261107/NEW-baseline/three-tier-policy.json
# 只有 eligible=true 才能推进正式恢复。独立候选用新目录，保持相同环境。
pwsh -NoProfile -File tools/perf/fixed_clock.ps1 -Output evidence/perf-gate-20261107/NEW-candidate -Cpu 3 -Runs 5 -IdleCpuMax 5 -IdleTimeout 15
python tools/perf/gate_policy.py check evidence/perf-gate-20261107/NEW-baseline/three-tier-policy.json evidence/perf-gate-20261107/NEW-candidate evidence/perf-gate-20261107/NEW-check.json
python tools/perf/check_gate_policy.py evidence/perf-gate-20261107/attempt-3
git apply --check evidence/perf-gate-20261107/proposed-workflows.patch
```

19 本在当前 HEAD 的新构建 SDK 上完整跑两轮，每轮 **19/19、11,296 页、8,648,640 glyph/文本区域计数**，两轮逐页像素差异 **0**，内容指纹一致，重复比较退出 0；没有修改产品代码。记录见 realbooks.json、realbooks-repeat.json 与 realbooks-repeat.diff.json。性能采集结束后才启动四进程真书回归。

与历史 c665d1c 基线比较有 **8,604 个共有页哈希变化**，结果返回 1，保留在 realbooks.diff.json。历史源码到本次 HEAD 已有 29 个 src/include 文件变更，构建功能配置也不同；历史差异尚未人工审阅，不能记为历史基线回归通过。本 PR 的“不影响产品”证据是产品树未改及相同 HEAD 两轮全页零差异。

本地核验：严格 5% 边界、少样本/未达空闲拒绝、raw 篡改拒绝、原始数据重算和 advisory 政策检查通过；workflow patch dry-run 与 YAML 结构检查通过；src/include/examples/.github 无改动。
