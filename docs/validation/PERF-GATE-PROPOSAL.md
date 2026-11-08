# 性能门禁自归一化提案 · 2026-11-08

**现在不能恢复 required。** 本次实现、原始数据、冻结阈值和恢复条件如下。E3 仍为 `advisory=true, accepted=false`；本 PR 不应用 workflow 或规则集变更。

## 为什么改掉绝对毫秒门禁

旧提案独立候选的八项最大离散度为 **9.471% / 6.516% / 22.080%**，原始数据保留在 [perf-gate-20261107](../../evidence/perf-gate-20261107/)。当机器频率或可用 CPU 时间变化时，绝对毫秒会把机器变慢算成产品回退。给每台机器单独冻结绝对基线也不能消除同一机器的运行时漂移。

新方案在**同一原生进程、同一逻辑核**上，每次先做固定参照，再做一次目标翻页：

```text
page_ratio = target_ms / reference_ms
run_ratio = nearest_rank_p95(target_ms) / nearest_rank_p95(reference_ms)
```

门禁采用第二个公式；逐页比值及其 p95 另存。两个 p95 的比值通常不等于逐页比值的 p95，报告不混用。比值只有在两种操作受到相近程度的放慢时才能抵消噪声，受压实验直接验证这一点。

## 参照与操作计划

[reference.c](../../tools/perf/reference.c) 固定执行 **120,000,000 次**有数据依赖的无符号 FNV 风格混合步骤。只有整数运算和计时，无文件、SDK 调用、分配或机器相关的工作量标定。无符号回绕有定义，结果写入 volatile sink；[反汇编](../../evidence/perf-gate2-20261108/reference-disassembly.txt) 验证固定循环仍在，循环上限为 0x7270e00。同一源文件分别编进校准程序和目标探针，使用相同 Release 选项。

工作量不随产品优化或本机速度改变，实测离散度仍须通过下表。MinGW 链接参照时关闭 PE 墙钟时间戳；两次重建 SHA-256 同为 `7174d85e82a39ba878d90271642f73ebe8ffcb804874d814b7f383fda5383b0b`，避免候选重建仅因时间戳而被拒绝。

| 项目 | 固定口径 |
|---|---|
| 源码 | `93f9d8bb1ab5ed700bc8dbad47eef650eeb5bca9`；产品树未改 |
| 构建 | GCC 16.2.0，Release `-O3 -DNDEBUG`，SDK 默认功能；构建/重链接命令与日志保留 |
| 环境 | Lenovo / Core Ultra 7 256V，Windows 11 build 26200；机器信息和逐核遥测见 preflight |
| 亲和性 | CPU 3，探针与参照均 HIGH priority；串行采集 |
| 电源 | AC min=max=100、boost=0；每个 session 的 finally 恢复并读回核对 |
| 校准 | 每轮一个独立原生进程，1 次声明的 warmup + 31 次全部保留的参照测量；取 nearest-rank p95 |
| 目标 | 清单的 **17 EPUB + 1 PDF + 1 MOBI**；每本首屏 + 16 次顺序翻页，首屏不计入门禁 |
| 视口 | 重排 720×1040、margin 48、字号 24；PDF 沿用 R3 原生 1.0 render scale |
| 目标计时 | layout + RGBA render；打开、签名和释放在目标计时之外；暖 OS 文件缓存 |
| 每轮汇总 | 每本权重相同，共 **304** 个顺序配对样本；另留每本书自己的 p95 比值 |
| 重复 | 正常 5 轮，然后冻结预算，再受压 5 轮；没有删除异常点或选择五次 |
| 离散度 | 统一为 `100×(max-min)/nearest-rank p50`；不以 CV 替代 |

`ratio-probe` 生成测量副本，复用 R3 的分页、RGBA/文本/位置签名；MOBI 使用公开文档分页 API 和文档文本范围。输入先核对原清单 SHA-256，再复制到 ignored build 目录下的 ASCII 哈希文件名，避免 Windows 原生 argv 丢失中文路径；副本再次验散列。每个原始记录输出 `reference_ms`、`target_ms`、`ratio`。

## 五轮与慢机实测

<!-- MEASURED-RESULTS -->
| 状态 / 轮次 | 独立参照 p95 ms | 配对参照 p95 ms | 翻页 p95 ms | ratio |
|---|---:|---:|---:|---:|
| 正常 1 | 237.249000 | 238.211500 | 83.803000 | 0.351800816 |
| 正常 2 | 237.626900 | 238.260400 | 83.927800 | 0.352252410 |
| 正常 3 | 237.664500 | 237.424600 | 84.067200 | 0.354079569 |
| 正常 4 | 236.724800 | 237.785400 | 82.961800 | 0.348893582 |
| 正常 5 | 237.168100 | 237.878200 | 83.907500 | 0.352733037 |
| 受压 1 | 494.157900 | 492.442200 | 161.348300 | 0.327649214 |
| 受压 2 | 470.119000 | 489.465900 | 135.428000 | 0.276685260 |
| 受压 3 | 480.783900 | 486.629800 | 139.855700 | 0.287396497 |
| 受压 4 | 497.383300 | 493.122600 | 144.176300 | 0.292374148 |
| 受压 5 | 473.530500 | 497.210900 | 147.326100 | 0.296305049 |

| 五轮离散度 | 正常 | 受压 | 验收 |
|---|---:|---:|---|
| 独立参照 p95 | 0.396082% | 5.670801% | 通过（正常要求 <3%） |
| 翻页 p95 / 参照 p95 | 1.472236% | 17.431074% | 通过（正常要求 <5%） |
| 绝对翻页 p95 | 1.317403% | 17.978198% | 仅诊断 |

正常→受压：翻页 p95 中位数 **83.907500→144.176300 ms**，**1.7183× / +71.8277%**；配对参照 **2.0701× / +107.0144%**；ratio 中位数 **0.352252410→0.292374148**，漂移 **-16.9987%**，<10% 验收 **失败**。

| 整体冻结参照 R0 | 受压候选 p95 ratio | 警告 | 门禁 | 硬上限 |
|---:|---:|---:|---:|---:|
| 0.354079569 | 0.327649214 | 0.389487526 | 0.442599461 | 0.531119353 |

19 本各自的冻结阈值与受压候选（每列 p95 均对五轮取 nearest-rank）：

| 书籍 ID | 正常 p95 ratio | 受压 p95 ratio | 警告 | 门禁 | 硬上限 | 受压结果 |
|---|---:|---:|---:|---:|---:|---|
| a-raisin-in-the-sun | 0.383575779 | 0.386075447 | 0.421933357 | 0.479469724 | 0.575363669 | 三线以下 |
| between-the-world-and-me | 0.139538179 | 0.127038534 | 0.153491997 | 0.174422724 | 0.209307269 | 三线以下 |
| black-boy | 0.255126773 | 0.187563524 | 0.280639450 | 0.318908466 | 0.382690159 | 三线以下 |
| born-a-crime | 0.109303117 | 0.123668905 | 0.120233428 | 0.136628896 | 0.163954675 | warning |
| crying-in-h-mart | 0.175235191 | 0.217644589 | 0.192758710 | 0.219043988 | 0.262852786 | warning |
| how-does-it-feel-to-be-a-problem-being-young-and-arab-in-america | 0.212277987 | 0.239421507 | 0.233505786 | 0.265347484 | 0.318416980 | warning |
| i-know-why-the-caged-bird-sings | 0.346336705 | 0.352852542 | 0.380970375 | 0.432920881 | 0.519505057 | 三线以下 |
| pachinko | 0.239594780 | 0.181214621 | 0.263554257 | 0.299493474 | 0.359392169 | 三线以下 |
| the-absolutely-true-diary-of-a-part-time-indian | 0.071897985 | 0.103558756 | 0.079087784 | 0.089872481 | 0.107846978 | warning/gate |
| the-autobiography-of-malcolm-x. | 0.416668174 | 0.404132412 | 0.458334992 | 0.520835218 | 0.625002261 | 三线以下 |
| the-distance-between-us-a-memoir | 0.214683062 | 0.243301905 | 0.236151369 | 0.268353828 | 0.322024593 | warning |
| the-fire-next-time | 0.363993684 | 0.331712782 | 0.400393052 | 0.454992104 | 0.545990525 | 三线以下 |
| the-fire-this-time-a-new-generation-speaks-about-race | 0.275036046 | 0.226261332 | 0.302539651 | 0.343795058 | 0.412554069 | 三线以下 |
| the-house-on-mango-street | 0.110177612 | 0.123475313 | 0.121195374 | 0.137722015 | 0.165266419 | warning |
| zami-a-new-spelling-of-my-name---a-biomythography | 0.054003222 | 0.062989081 | 0.059403544 | 0.067504028 | 0.081004833 | warning |
| hongloumeng-24264 | 0.123187103 | 0.158171758 | 0.135505814 | 0.153983879 | 0.184780655 | warning/gate |
| xingshihengyan-24239 | 0.120122687 | 0.127168989 | 0.132134956 | 0.150153359 | 0.180184031 | 三线以下 |
| tangshi300-52323 | 0.126419566 | 0.164541780 | 0.139061523 | 0.158024457 | 0.189629349 | warning/gate |
| kusamakura-japanese-vertical-writing | 0.207385976 | 0.171123080 | 0.228124574 | 0.259232470 | 0.311078964 | 三线以下 |

单书正常 ratio 离散度最差为 **8.8196%**（between-the-world-and-me）；受压单书 ratio 中位数漂移最差为 **-38.2738%**（black-boy）。整体统计达标不能代替逐书稳定性。

独立未变更候选：整体三档超限次数（共 5 轮）为 **{'warning': 0, 'gate': 0, 'hard': 0}**；任一单书超过门禁的轮次 **1/5**；基线 eligible=True，候选 eligible=False。

逐页 RGBA/文本/位置签名在所有正常与受压轮之间一致：**True**。

<!-- /MEASURED-RESULTS -->

机器可读结果见 [experiment.json](../../evidence/perf-gate2-20261108/final/experiment.json)，逐次与逐书指标见 [normal/summary.json](../../evidence/perf-gate2-20261108/final/normal/summary.json) 和 [loaded/summary.json](../../evidence/perf-gate2-20261108/final/loaded/summary.json)。capture.json 记录每份 stdout 的散列；报告从 raw 重算，不信任缓存汇总。

慢机模拟启动 **1 个相同 HIGH priority 的忙循环**，与探针固定在 CPU 3 上竞争，其他设置不变；原始 PID 和 finally 停止记录见 loaded/capture.json。用正常与受压各五轮的 p50 比较实际放慢倍数及 ratio 漂移。该实验模拟 CPU 时间份额降低，没有等比例改变不同 CPU 的指令吞吐、内存带宽或磁盘性能；跨 CPU 型号仍需独立验证。

本轮正常绝对翻页 p95 的离散度也只有 **1.3174%**，ratio 为 **1.4722%**；不能把新工作负载的稳定性直接归功于归一化。受压时分子只放慢 1.7183×、分母放慢 2.0701×，证明二者未等比例变化，当前公式不足以消除这种争用。逐页 ratio 的 p95 中位数漂移为 **−1.0189%**，但它是另一种统计量，本轮没有用它替换指定的 p95 之比来改变验收结果。

限频诊断另试 AC min=max **50% / 25%**（boost=0）。31 次参照观测的 p95 分别为 **235.6523 / 235.2888 ms**，与正常 **237.249 ms** 接近，没有制造实际减速，因此不计作慢机通过证据，也未启动无效的五轮目标采集。两次设置均在 finally 恢复并读回一致；AC 接通状态已记录于 [power-status.json](../../evidence/perf-gate2-20261108/final/power-status.json)。

## 冻结阈值与拒绝规则

设 `R0` 为正常五轮 run_ratio 的 nearest-rank p95，即五轮最大值。三档为 **1.10×R0 / 1.25×R0 / 1.50×R0**，实际无量纲数字见实测段。每本书同样以该书五轮比值 p95 单独冻结三档，避免整体统计掩盖单本退化；实测段列出全部 19 本的当前值和阈值。

10% 警告余量是 <5% 离散度目标的两倍；25% 门禁延续既有延迟余量；50% 硬上限要求停止推进并复核。这些是政策余量，不是置信区间。警告只提示，任一整体或单书超过门禁/硬上限均非零退出。

除数值线之外，还拒绝：基线或候选不足五轮、参照校准离散度 ≥3%、整体 ratio 离散度 ≥5%、缺书/缺页、原始散列不符、RGBA/文本/位置签名变化、非正数/非有限参照、逐页比值算错，以及参照/编译器/flags/字体/采样工具/操作计划/输入散列不兼容。SDK 源码与 DLL 身份保留在溯源记录中，**不放进兼容键**，因此可比较产品代码候选。RSS 继续属于原有 E1 独立内存检查，不做速度归一化。

预算在受压候选开始前写入 [ratio-policy.json](../../evidence/perf-gate2-20261108/final/ratio-policy.json)，不因候选结果改写；`eligible=false` 时只能审议，不能用作 required 的批准基线。

## 误报评估

正常五轮参与定线，不能拿它们自己的过线率估计误报率。受压五轮在预算冻结后采集，使用同一 SDK，可作为独立的“产品未回退”候选。实测段分别列出整体三档超限数、任一单书门禁超限数和资格拒绝，不能只报数值通过而省略资格失败。

若五轮均未越整体门禁，观察值为 0/5，但单侧 95% 二项上界仍为 `1-0.05^(1/5)=45.1%`。连续五轮可能相关，因此这也不是生产误报率保证。恢复前需在实际 runner 上积累独立未变更对照和已知回退候选，检验整批资格与全部单书门禁的误报/漏报。19 本联合门禁的误报率应单独评估。

## 19 本全页回归

<!-- REGRESSION-RESULTS -->
同一源码 HEAD 的采集前/后全页回归均为 **19/19、11,296 页、8,648,640 glyph，像素哈希变化 0**。期间 CMake 重链接导致 SDK DLL 散列变化，因此另用最终 **同一 DLL** 重复全页比较，同样 **0 页变化**，比较退出 0。最终 DLL SHA-256 为 c965a690cbdc812ecfe9959e5f01edd05c49bf780abb35b513372daa74742ada；三次内容指纹均为 12b3b76f346ea736f218d8eb5e11af33673ceb31993c9c7ced98724e4689e732。

完整逐页数据：[before.json.gz](../../evidence/perf-gate2-20261108/realbooks-before.json.gz)、[after.json.gz](../../evidence/perf-gate2-20261108/realbooks-after.json.gz)、[repeat.json.gz](../../evidence/perf-gate2-20261108/realbooks-repeat.json.gz)；[同一 DLL 比较](../../evidence/perf-gate2-20261108/realbooks-repeat.diff.json)。
<!-- /REGRESSION-RESULTS -->

全页回归使用既有 `tools/regress/run_realbooks.py` 与 `tools/regress/layout.json`，与性能探针的早期页采样分别保留口径。证据只存页数、glyph 数和像素散列，不提交书籍内容。性能采集前后运行，避免四进程全页渲染干扰计时。

## workflow patch（仅提案，未应用）

完整 unified diff 见 [proposed-workflows.patch](../../evidence/perf-gate2-20261108/proposed-workflows.patch)，提交前执行 `git apply --check`。它新增 `performance-ratio` 检查，不修改既有 `.github/` 文件，不取消 run。关键片段：

```diff
+      - name: Measure five runs of the same 19 books
+        run: |
+          python -X utf8 tools/perf/ratio_capture.py capture --build build/perf-ratio-build --font $env:PERF_FONT --manifest $env:PERF_CORPUS --output build/perf-ratio/candidate --cpu 3 --runs 5
+          exit $LASTEXITCODE
+      - name: Recompute raw ratios and enforce frozen tiers
+        if: always()
+        run: |
+          python -X utf8 tools/perf/ratio_capture.py check $env:PERF_RATIO_POLICY build/perf-ratio/candidate build/perf-ratio/result.json
+          exit $LASTEXITCODE
+      - name: Retain all raw attempts
+        if: always()
+        uses: actions/upload-artifact@v4
+        with:
+          path: build/perf-ratio/
+          if-no-files-found: error
```

应用前需在 runner 上提供清单原件、固定字体、同编译器/flags/参照及已批准的合格冻结 policy，配置 `PERF_CORPUS`、`PERF_FONT`、`PERF_RATIO_POLICY`。本机依赖路径在 build-command.json；workflow 不能直接使用这些本机路径。runner 电源配置应与批准基线一致，并复验该 runner 的压力漂移。

## 能否恢复 required，以及还差什么

**不能恢复。** 整体 ratio 与单书结果必须分别判断：同一 SDK 在同核竞争下已经出现单书门禁误报，不能据整体统计达标推进 required。还缺实际 runner 的冻结基线和独立复验、已知产品回退的拒绝性验证，以及 E3 strict 报告生产者。

现有 `tools/measure_reading_real.py` 仍调用 `perf_policy.advisory()`，强制 `accepted=false`；`tools/reading_required.py` 则要求 `accepted=true`。本次允许范围内不能修改这两个实现，套 workflow patch 也不能使其进入严格验收。新 `ratio_capture.py check` 给出本地数值结果，仍输出 E3 advisory 身份。

恢复顺序：先解决受压单书误报，逐书复验离散度与慢机漂移，并在实际 runner 取得独立数据；再以另一个 PR 实现 strict 生产者并验证正反候选、完成 real-v1 来源与同 run/attempt 严格复验；owner 在 [#32](https://github.com/NoGod3524/EXReader/issues/32) 记录冻结预算和恢复决定后应用 workflow，手动运行和真实 PR 活验，最后注册 required context。既有 core 保护继续保留。E3 截止 **2026-12-15 00:00 America/New_York** 不变。

## 复现、失败记录与核验

```powershell
# 本机完整配置参数在 evidence/perf-gate2-20261108/build-command.json。
cmake -S tools/perf -B build/perf-ratio -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/perf-ratio --target ratio-probe perf-reference --parallel 4
New-Item -ItemType Directory evidence/perf-gate2-20261108/NEW
pwsh -NoProfile -File tools/perf/ratio_session.ps1 -Output evidence/perf-gate2-20261108/NEW -Build build/perf-ratio -Font C:/path/Reader.otf -Cpu 3
python tools/perf/ratio_report.py evidence/perf-gate2-20261108/NEW
python tools/perf/check_ratio.py evidence/perf-gate2-20261108/NEW/normal
git apply --check evidence/perf-gate2-20261108/proposed-workflows.patch
```

普通优先级探索中，参照单进程 p95=502.316 ms，范围 248.906–2064.147 ms；发现严重调度干扰后停止自己的探针，保留未完成批次。后续高优先级接入真书时，先后暴露 PDF 格式选择、MOBI 分页/文本签名适配缺口，均保留失败 stdout/日志，修复后先通过全部 19 本冒烟才开始 final 批次。未完成批次不用于凑五次或定阈值。各 session 电源恢复值和原因均保留。

详细进度见 [PERF2-OUT.txt](../../evidence/perf-gate2-20261108/PERF2-OUT.txt)。新增/修改都限于 `tools/perf/`、`docs/validation/`、`evidence/perf-gate2-20261108/`；产品目录与 `.github/` 未改。
