**Performance gate final — 2026-11-09**

**结论：现在不能把 `performance` 设为 required。** 最终采样器的同代码五次复验只有 **2/5 pass**；第 1、2、5 次误报。Ubuntu CI 冻结基线为 **0/19**，CI 误报复验为 **0/5**。本轮交付的是可执行门禁和不可上线的实测反证，未改变 GitHub required 设置。

实现选 A-1 + A-2：主门禁比较同一 CPU/编译器/计数器环境的逐书线程周期 p95，墙钟只设 3× 极端退化看门狗。直接比较周期避免分别取两个 p95 后相除；代价是周期仍受硬件执行状态影响，必须用真实复验决定能否冻结。本轮复验否定了共享桌面上的这组阈值。

**冻结数据与口径**

[`perf-baseline-ci.json`](perf-baseline-ci.json) 是明确的 `status: blocked` 拒绝记录，19 个 CI p95 均为 null；`gate.py` 读取后以 **exit 2** 拒绝。下面是本地冻结数据，不是 Ubuntu 数字。实际基线及原始样本在 [final/perf-baseline-local.json](../../evidence/perf-gate-final-20261109/final/perf-baseline-local.json) 和 [final/local-baseline](../../evidence/perf-gate-final-20261109/final/local-baseline/)。

环境：Intel Core Ultra 7 256V，8 逻辑核，固定逻辑核 3，16,693,911,552 字节 RAM；Windows 11 build 26200；GCC 16.2.0，Release `-O3 -DNDEBUG`；计数器 `QueryThreadCycleTime`。SDK 复用当前 main 的字节相同构建，SDK SHA256 `c72d233b9a7cb1e8c93dd4fbd9aa7b494b73318326e3d58f62be7352f6569d3a`。完整编译开关、编译器哈希和源树对应关系均入档。

每本 3 个新进程，每个保留首屏但只计入 16 个顺序翻页；逐书将 48 个线程周期排序，取 nearest-rank 第 46 个作为 p95。包含 EOF 和跨章节创建 pager、排版、RGBA 渲染；不包含签名哈希、释放、打开文件或首屏延迟。19 本全页回归是单独的完整检查。无重试、无删点、无候选依赖的重设基线。

| 书籍 ID | 线程周期 p95（本地） | 墙钟 p95 ms | 全页回归页数 |
|---|---:|---:|---:|
| a-raisin-in-the-sun | 137,122,483 | 42.3588 | 356 |
| between-the-world-and-me | 46,685,987 | 14.4918 | 232 |
| black-boy | 91,359,405 | 28.1162 | 1,037 |
| born-a-crime | 44,512,938 | 13.7761 | 512 |
| crying-in-h-mart | 62,122,509 | 19.4360 | 535 |
| how-does-it-feel-to-be-a-problem-being-young-and-arab-in-america | 74,963,655 | 23.1455 | 503 |
| i-know-why-the-caged-bird-sings | 135,155,153 | 41.2806 | 625 |
| pachinko | 85,976,154 | 26.6129 | 1,266 |
| the-absolutely-true-diary-of-a-part-time-indian | 28,985,947 | 8.7887 | 566 |
| the-autobiography-of-malcolm-x. | 156,152,241 | 47.4452 | 279 |
| the-distance-between-us-a-memoir | 74,928,326 | 23.2403 | 714 |
| the-fire-next-time | 135,046,517 | 41.5247 | 189 |
| the-fire-this-time-a-new-generation-speaks-about-race | 99,422,556 | 30.8516 | 333 |
| the-house-on-mango-street | 39,650,741 | 12.3229 | 185 |
| zami-a-new-spelling-of-my-name---a-biomythography | 31,619,622 | 9.5850 | 659 |
| hongloumeng-24264 | 55,927,302 | 17.5624 | 1,684 |
| xingshihengyan-24239 | 54,282,239 | 16.8388 | 1,203 |
| tangshi300-52323 | 54,077,844 | 16.7056 | 84 |
| kusamakura-japanese-vertical-writing | 90,454,656 | 27.8937 | 464 |

**三档阈值与依据**

| 档位 | 周期 / 基线 | 行为 | 相对于 #97 +4.40% 残差 |
|---|---:|---|---:|
| warning | ≥1.10 | 列出警告，仍可 pass | 2.27 倍 |
| gate | ≥1.20 | fail，exit 1 | 4.55 倍 |
| hard | ≥1.35 | 标记 hard 并 fail | 7.95 倍 |

阈值在最终采样前已固定。#97 的受压 +4.40% 是**归一化 ratio 的观测残差**，不能当作绝对周期噪声的上界或统计置信区间；#97 后续逐书最大漂移还达到 5.804235%。10/20/35% 是待实证检验的工程余量，本轮最大同代码周期增幅 **47.9538%** 已否定它在此环境中的可靠性。没有把 20% 改大以换取通过。

墙钟看门狗为 ≥3×（+200%）；#97 高压目标墙钟最大约 213.9031 ms / 无压中位数 82.7161 ms = 2.586×，因此选更宽的极端报警界线。此次仍观测到同代码 4.541×，所以共享环境里的墙钟看门狗也会误报。CPU 的 35% hard 不替代墙钟的 3× 看门狗。

**最终同代码五次误报测试**

| 次数 | 最差周期比 | 周期增幅 | 最差墙钟比 | 结果 | 最差周期书籍 |
|---|---:|---:|---:|---|---|
| repeat-1 | 1.479537676 | +47.9538% | 4.540956000 | **fail** | i-know-why-the-caged-bird-sings |
| repeat-2 | 1.393197363 | +39.3197% | 1.365710264 | **fail** | between-the-world-and-me |
| repeat-3 | 1.162792306 | +16.2792% | 1.159963760 | **pass** | i-know-why-the-caged-bird-sings |
| repeat-4 | 1.046193992 | +4.6194% | 1.053646681 | **pass** | the-house-on-mango-street |
| repeat-5 | 1.409418850 | +40.9419% | 1.414315884 | **fail** | the-autobiography-of-malcolm-x. |

每次均为 19 本 × 3 进程 × 16 页，没有追加第六次来替换失败轮次。SDK、探针二进制和产品源树相同，所有候选开始于冻结时间之后；见 [source-binary-audit.json](../../evidence/perf-gate-final-20261109/source-binary-audit.json)。第 1 次有 9 本 fail、第 2 次 2 本、第 5 次 2 本；逐书条目和原始数据见 [final/qualification](../../evidence/perf-gate-final-20261109/final/qualification/)。

初版采样器曾取得 5/5 pass，最差周期比为 0.988481522 / 1.035297434 / 1.049758481 / 1.071850052 / 1.075961961。其冻结采样与全页回归进程重叠；全部原始结果仍在 [initial qualification](../../evidence/perf-gate-final-20261109/qualification/)。代码审查修正 Linux CMake cache 路径，并去掉未使用的旧 ratio 字段后，重新冻结最终探针并完整复验，得到上表反证。两批使用相同 10/20/35% 与墙钟 3× 阈值。

**真阳性**

只给 `black-boy` 的进程设置 `PERF_GATE_FAULT_PERCENT=25`，在已计时的渲染窗口内执行忙循环，按该页原始线程周期增加约 25% 的实际执行工作；没有改 JSON 或乘大统计结果。产品源码和输出签名不变。

| 书籍 | 基线周期 p95 | 注入后周期 p95 | 比值 | 实测额外工作 | 结果 |
|---|---:|---:|---:|---:|---|
| black-boy | 91,359,405 | 113,268,185 | 1.239808698 | 25.006892% | fail（warning + gate），exit 1 |

其余 18 本未触发 fail。 [完整触发记录](../../evidence/perf-gate-final-20261109/final/qualification/positive-25-gate.json)。

**CI 阻塞的实查证据**

- 当前分支 256 个 workflow 中，调用 `tools/perf/` 和 `tools/regress/` 的入口均为 0；现有 `reading-real.yml` 使用 Ubuntu 22.04、另一套 8 本书。此任务禁止修改 `.github/`，因此没有执行新采样器的授权入口。
- 19 本书的清单是本地 Windows 路径，仓库为 public，未配置 CI 传输；没有把书籍原文推送到 GitHub。ZIP 供给工具已用 19 个输入做过哈希回环及非法归档拒绝测试。
- Linux 后端已实现 `perf_event_open(PERF_COUNT_HW_CPU_CYCLES)`、当前线程、user-only、pinned、拒绝 multiplex；当前环境无 WSL，未在 Linux 或 GitHub runner 上运行。没有把 CPU 纳秒或 TSC 当作线程周期。
- GitHub 规则集 25700819 仍只要求 `reading-required-core`（GitHub Actions app 15368）。未创建或改动 ruleset。

见 [ci-readiness.json](../../evidence/perf-gate-final-20261109/ci-readiness.json)、[实际规则集](../../evidence/perf-gate-final-20261109/github-ruleset-detail.json)、[CI 基线拒绝](../../evidence/perf-gate-final-20261109/final/ci-baseline-refusal.json)。

恢复所缺的条件是：合法的 19 本书 CI 访问方式、允许部署执行入口、runner 暴露并允许读取真实 PMU、明确的同构 runner/编译器环境，以及该环境的 19/19 冻结基线、同代码 5/5 pass 和 +25% 真阳性 fail。当前单环境基线拒绝未知 CPU/image/compiler；`ubuntu-latest` 标签本身不固定 CPU 型号，不能把别的环境自动当作通过。若仍在共享 runner 上观察到这里的噪声，需采用可控 runner 或重新验证逐样本周期归一化；不能用本轮数据承诺成功。

GitHub 的 [runner 规格文档](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) 说明 hosted runner 与标签口径；[Linux perf_event_open 文档](https://man7.org/linux/man-pages/man2/perf_event_open.2.html) 说明计数器、权限和 enabled/running 计数。本轮没有据此推断目标 runner 的 PMU 可用性。

**可直接应用的 patch、恢复与回滚**

[`performance-required.patch`](performance-required.patch) 新增独立 `performance` 上下文；不更改五组非性能门禁。无 `continue-on-error`、无路径过滤，PR 使用 base SHA 中的已审查基线；冻结/资格测试用不同上下文 `performance-qualification`，不能以基线导出成功满足 required。`git apply --check` 和 actionlint 1.7.12 均通过。
.github/、src/、include/、examples/ 未改。该 patch 还没有运行验证，当前拒绝基线会让它失败。

恢复顺序：

1. 在获准的 CI 变更中执行 `git apply --check docs/validation/performance-required.patch`、`git apply docs/validation/performance-required.patch` 并合入 main；暂不增加 required context。配置 `PERF_CORPUS_URL` repository secret，内容必须是 19 个 `<sha256>.<epub|pdf|mobi>` 根目录条目的 HTTPS ZIP。外部 fork PR 拿不到 secret；未解决其供给方式前，也不能对这些 PR 开 required。
2. `gh workflow run performance.yml --ref main -f mode=freeze`。下载该 run 的 `perf-gate-<run>-<attempt>` artifact，把实际生成的 `perf-baseline-ci.json` 和 `baseline-raw/` 一起审查入库，替换当前 blocked 记录。保留 runner/image、CPU、编译器、源码、run/attempt 和样本摘要。
3. `gh workflow run performance.yml --ref main -f mode=qualify`，必须得到 5 次正常 pass、1 次真实注入 fail，并核对相同 SDK/探针、19 本内容签名和完整页回归。还需确认独立新 runner 不会换到未注册的 CPU/image；否则单环境基线不能上线。
4. 在实际 PR 上确认 `performance` 正常执行与通过后，给规则集 25700819 的 required status checks 添加 `performance` / app 15368；保留现有 `reading-required-core`、strict、bypass 和其余规则。只有到这一步才开启 required。

换 runner 的重新冻结命令（新路径，不覆盖旧基线）：

```bash
python3 tools/perf/refresh_baseline.py \
  --build build/perf --font build/perf-input/font/Reader.otf \
  --manifest build/perf-input/books/manifest.json --cpu 0 \
  --output evidence/perf-gate-ci-new/baseline-raw \
  --baseline evidence/perf-gate-ci-new/perf-baseline-ci.json
```

随后重新跑资格测试并审查替换。日常 `gate.py BASELINE CAPTURE --output RESULT` 只读基线，0=pass，1=性能退化，2=证据/环境无效；生产 CI 不传 `--local`。

回滚：先从规则集移除新增的 `performance` required context，保留 `reading-required-core`；再 `git revert <引入-workflow-patch-的提交>`。若只是在未提交工作树应用 patch，可先 `git apply -R --check docs/validation/performance-required.patch` 再 `git apply -R docs/validation/performance-required.patch`。保留旧基线与失败证据，不能在失败时自动刷新预算。

**验证与范围**

19 本全页回归：**11,426 页、8,648,571 字形，页数/字形/逐页哈希变化均为 0**。内容指纹 `f133272deccc097ee10bbdcf18cdb60c95bf3035ddde529e8dbea24a1d5ce488`。本次测量代码没有链接回 SDK，注入只存在于探针。

构建、门禁边界/NaN/缺失/篡改/签名/CI 冒充拒绝测试、归档验证、patch 应用检查均通过；性能资格测试本身明确失败。证据索引见 [verification.json](../../evidence/perf-gate-final-20261109/verification.json)，逐步记录见 [PERFGATE-FINAL-OUT.txt](../../evidence/perf-gate-final-20261109/PERFGATE-FINAL-OUT.txt)。
