# 包 C：SDK 预集成、合法基线与同源联合验收

供独立 AI 执行的任务说明。用户把本文件交给你要求执行时，负责本包与最终汇合；A 修 Android，B 补 AcroForm 文档语料。
你现在就可以准备和预集成，最终源码冻结与完整验收等 A/B 的固定交付。此前限时轮次已结束，本文件编制时未恢复工程工作。

## 工作树与输入

仓库 `NoGod3524/EXReader`，只使用 `codex/parallel-integration` 的工作树：
`C:/Users/Oscar/.codex/worktrees/parallel-integration/EXReader`。
编制这组三份 handoff 前 HEAD 为 `041bf18477351f3499f336e65991cacfdbd22440`；当前 HEAD 可包含其后的交接文档提交。
先检查 Git 状态，保留已有改动，不重置或重建工作树。

| 输入分支 | 当前可用交付 HEAD | 实际受测源码 | 独立通过 run |
| --- | --- | --- | --- |
| `codex/wp9-acroform` | `4605dbf7524f8764b923e5c447e1a6988fe4f62f` | `7e44ae59d47a578dac3116154b0de5a67efb0163` | `39817023587`：Windows/Linux 各 4/4、ASan 1/1；B 后续会有新交付 |
| `codex/wp5-border-spacing` | `a0bb9d2d6988b74e62aa1592faed681cee1950d4` | `ee76f5b582ec92112bb294226d5b42758b1ad2ae` | `39816051738`：双平台各 163/163 |
| `codex/wp13-apple-review` | `535f6baff40234427d9d0584fee1432dfecf099b` | `b3f28ca19904f9a6f173113f6ed86e62928be875` | `39813162880`：8/8、严格汇总通过 |
| `codex/wp15-catalog-features` | `47d8fda0bea9aca6eb1f3f595344b31c0ec51d08` | `757e2f33271b358715ea8f83f44a3c779ad660e8` | `39815167314`：双平台各 65/65、facet 与 Linux sanitizer 通过 |
| `codex/wp13-android-review` | `05048cccd84532509e0d6039feb3b7769824ec1a` | `ac7aecc4d3c2e6e65a6797ab556cd31546ca3a5c` | `39816104855` 最终 failure；等待 A 的新通过交付 |

上述包尚未联合纳入本分支。文档 HEAD 与实际受测源码分开，不把独立旧运行当作共同源码验收。

## 阶段一：不用等待 A/B 即可开始

1. 读取 `docs/PARALLEL-INTEGRATION.md`、本次总 handoff 和各包 review/validation，核对 ancestry 与干净状态。
   优先保留原提交历史；兼容语料首次登记 `00a8838cf6089e67a730ca6fd4956cb45d09c27d` 必须仍为祖先。
2. 在本集成分支预合入已通过的 AcroForm 基础版、border-spacing、Apple，处理 CMake/API/文档冲突。
   不进 A/B 的工作树改文件；Android 当前失败版本不授予接受。OPDS 最后处理，见下面所有权规则。
3. 在云端跑新 SDK 的完整原生回归、Linux sanitizer、安装/裁剪安装/组件与公开消费者、导出和层依赖检查。
   保留 AcroForm 及 spacing 专用检查，核对实际配置没有关闭它们。根据真实失败做集成范围内的最小修复。
4. 准备工作流和门禁的基线迁移方案、十组运行映射及证据收口。预集成验证结果明确绑定阶段一源码。

本阶段可交付可复现的预集成 SDK 候选及通过/失败记录，不必等待 Android 修完才做这些工作。

## 阶段二：新的 SDK 基线必须有证据

多个可选包/宿主的旧 SDK 保护规则以 `a2552d7feb786cd2345d2b0b3eb894777b3254db` 为基线，
Android/OPDS 明确核对 `src/include/bindings/cmake/CMakeLists.txt` 等树。合入 AcroForm/CSS 后这些树会合法改变。
检查所有工作流的固定 SDK 基线，不能只处理这两个包，也不能删除保护检查来变绿。

先验证新 SDK，保留原 API/ABI/所有权和安装消费证据，再登记固定 SDK 候选 K；
让宿主/可选包验证其相对 K 没有额外修改 SDK。保留原基线的交付与历史结果。
不要把随意变化的当前 HEAD 当作基线来使检查自证通过；K 必须能追溯到单独接受的 SDK 证据。
B 的最终语料/引擎修复合入后，若改变受保护树，重新验证并冻结最终 K。

Android 的 `ANDROID_OWNERSHIP_HEAD` 只用于固定宿主变更审计终点，必须是受测源码祖先；
它不能替代运行的 source，也不能绕过 SDK 保护。所有权字段由你在集成分支维护，不抢写 A 的分支。

## 阶段三：A/B 交付后完成最终冻结

1. 核对 A 的新 Android 同次 45+10/49页/48门禁/严格 accepted 交付；B 的至少 30 文件与完整声明范围证据。
   固定准确 SHA 后合入本分支，解决冲突并在云端验证必要回归，不使用跨源拼接。
2. 完成全部非 OPDS 路径更改，包括集成工具、门禁协议、基线配置及必要集成文档，冻结前置祖先 H。
3. 最后合入 OPDS facets 并在 OPDS 约定路径登记 `HANDOFF=H`、合法 SDK 基线 K。
   `tools/check_opds.py` 所有权差异终点目前为 HEAD；H 之后新增非 OPDS 路径会被拒绝。
   后续若需要非 OPDS 修复，应重新整理冻结顺序/所有权契约并保留原证据，不通过删白名单检查绕过。
4. 冻结最终共同源码 S。验证它包含 A/B 接受的变更及所有新回归。独立包旧源码通过只作输入证据。

## 阶段四：共同源码云端验收

现有 `tools/check_parallel_integration.py` 要求十组、28 个上游作业：

| key | workflow | jobs |
| --- | --- | ---: |
| native | `native.yml` | 7 |
| ocr | `wp11-ocr.yml` | 3 |
| corpus | `compat-corpus.yml` | 1 |
| linux | `wp13-linux.yml` | 1 |
| windows_evidence | `wp13-windows-evidence.yml` | 1 |
| windows_worker | `wp13-windows-worker.yml` | 1 |
| migration | `wp12-migration.yml` | 3 |
| opds | `wp15-opds.yml` | 2 |
| apple | `wp13-apple.yml` | 8 |
| android | `wp13-android.yml` | 1 |

这些工作流全部跑同一 S。确保 native 或补充的同源检查实际执行 AcroForm/spacing/B 新语料及所需 sanitizer，
不能让原十组形式成功却漏掉新能力验证。若增加专用同源工作流，单独登记它与 S 的身份，保留上述十组完整门槛。

所有生产者成功后，云端 dispatch `.github/workflows/parallel-integration.yml`，
`source_sha=S`，`runs_json` 为十个 key 对应的实际 run ID；不指定执行端本地汇总。
只运行 protocol/selftest 的成功不能授予联合验收。

严格条件：run 和每个 job 同源、完整计数、全部 success；工件同 run/source、非空、未过期且有有效 digest；
全分页收集 jobs/artifacts（每页 100，按 total_count 取全）；各包自己的严格汇总也通过；最终 summary accepted=true。
任意失败/取消/缺项/跳过/身份冲突均保留未通过。旧失败、原件与旧源码结果不覆盖、不拼接。

## 历史事实与范围

旧八组联合验收绑定 `9e4b595ed7e10dcb2d78f5547e4e6a11a04ba3a1`，严格汇总 run `39718130711`。
十组门禁 21 项协议自测 run `39802485518` 只验证协议，尚未授予十组实际共同源码通过。
旧 `PARALLEL-INTEGRATION.md` 中 Apple/Android 候选状态已过时，当前交付身份以本文件及 A/B 新交付为准。

冻结 SDK `635225fe6ceb7759a948a1d8cede0ab18ea1cee9` 的 run `39666440519` 已通过 98 作业、99 工件，
四目标各 24 实际进程 CPU 小时。此证据不转移到新核心源码；本包联合验收不自动授予新源码 WP16 长测。
AcroForm 语料、真实语料 0/1710、真机/VoiceOver/TalkBack、完整 WP15 和其他十五项不能混成产品整体完成。

## 文件范围、约束与交付

你只写本集成分支：合并提交、解决集成冲突、维护集成工具/工作流/基线契约及集成说明/验收 JSON。
不要直接改 A/B 工作树，也不要顺手实现 Android 功能、PDF 新模式或其他剩余包。
所有编译、测试、语料生成、模拟器、工件解析和证据汇总只在 GitHub Actions。
本地可读写源码/文档和 Git；不跑本地测试、语法执行、生成器或下载工件；不推 `codex/framework`，不合并 PR，
不启动本地常驻轮询。只引用必要路径，不输出崩溃栈或样本细节。

交付：预集成与最终 S 分开登记；输入包固定 SHA、SDK 基线 K、OPDS 所有权祖先 H、各 run/attempt/job/工件身份、
新能力检查覆盖、严格汇总和未满足项、交付 HEAD 与干净状态。通过仅授予实际声明范围，不写产品完成。
建议关键集成与保护契约判断用 High；常规脚本/文档工作降档，CI 等待不占用反复推理。
