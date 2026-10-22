# R6：轻量阅读核心发布门槛

目标：保留多格式解析与自有 PDF 渲染，用原生 C 路径提供可裁剪的阅读 SDK，不依赖 WebView 或浏览器运行时。R6 复用现有 GitHub Actions、安装消费者和证据检查，不增加发布框架。

## 当前状态（2026-10-22）

本轮只读核对 `NoGod3524/EXReader`：

| 对象 | 云端实际状态 |
| --- | --- |
| 默认分支 | `codex/framework` |
| 分支 metadata | `protected=false`、`protection.enabled=false` |
| 必需状态检查 | `checks=[]`、`contexts=[]`、`enforcement_level=off` |
| protection API | HTTP 404，`Branch not protected` |
| repository rulesets | `[]` |
| GitHub About | 仍写 `GPLv3 native C ebook engine...` |
| GitHub license metadata / 仓库 `LICENSE` | MIT / MIT |

来源：`GET /repos/NoGod3524/EXReader`、`/rulesets`、`/branches/codex%2Fframework` 及其 `/protection`。GitHub 连接工具拒绝该编码分支路径，因此分支两项通过只读 `gh api` 取得；仓库与 rulesets 通过 GitHub 连接读取。**现在有 CI，没有已强制执行的默认分支合并门槛。** 本轮未修改仓库设置或 About。

## 最小落地顺序

1. 在共同源码上运行 `.github/workflows/reading-core.yml`，验证 `reading-core` 与 `reading-library` 两个 profile。前者保留多格式和 PDF，后者增加 SQLite 书库。
2. 首轮云端完成后登记实际生成的 check 名称、workflow 路径和工件名。完成的检查才加入 GitHub 必需检查，名称不依据文档猜测；必需 workflow 应覆盖目标分支的 PR，避免路径过滤导致检查缺席。
3. 核心发布复用同源码的现有 native 回归、安装消费、sanitizer 和层检查；按下表附加变更涉及的组件验收。GitHub required checks 配置与发布流程接线是后续执行项。
4. R3 冻结设备、语料、测量方法及阈值后，再把性能预算升级为阻断条件。首轮测量不授予“满足性能预算”。

## 检查映射

| 交付或变更 | 所需证据 | 当前落地边界 |
| --- | --- | --- |
| 两个阅读 profile | Release 构建、安装、现有安装后组件消费者、九格式合成 smoke、包体积与初始耗时/内存报告 | 新 `reading-core.yml` 首轮验证；Linux 范围，实际成功以云端结果为准 |
| 阅读核心 / 自有 PDF 源码、公开头或依赖改变 | 上述 profile + `native.yml` 三平台 CTest、ASan/UBSan、可移植及裁剪安装消费、layers | 复用现有工作流；Linux profile 不能替代三平台证据 |
| EPUB/PDF 实际故障修复 | R2 固定文件散列、原故障、公开 API 的修复结果与回归 | 合成 smoke 不代表真实语料通过 |
| 性能承诺 | R3 固定测量环境、重复次数、首屏/翻页/随机定位/峰值内存/体积及冻结预算 | 先出数，后定预算；R4 优化须保持正确性 |
| 原生宿主接入有界入口 | 对应平台宿主 workflow 的阅读、恢复、取消与资源释放证据 | R5 分平台交付；宿主不依赖 WebView |
| PDF 编辑、OCR、OPDS、迁移、音频、全文索引等可选包 | 现有组件专属工作流与安装消费 | 可独立发包；交付组合含该组件时须验收，不向核心包虚增能力 |
| 包含 A/B/C 范围的联合交付 | `parallel-integration.yml` 及其 12 组 / 35 个上游作业、严格汇总 | 保留现有门槛；新 profile 不删除或绕过旧基线与所有权检查 |

## 一份交付记录即可

复用 workflow 日志、上传工件和现有 JSON；每次交付记录完整 source SHA、workflow 路径、run ID、attempt、作业结论、profile/编译器/依赖配置，以及工件的 ID、大小、SHA-256 digest 和有效期。安装后的头文件、运行库版本/ABI、CMake package 版本须对应同一产物。

所有必需作业须在同源码、所登记 attempt 成功；保留旧失败，不能从不同 attempt 或旧源码拼出通过结果。缺必需证据、取消、跳过、空工件、过期或身份不符均拒绝。初轮报告只有明确通过的构建与 smoke 范围，性能阈值和真实语料状态另列。

现有严格汇总的拒绝回归继续运行。新 profile 发布判定接线时，仅补覆盖新增条件的最小负例：缺一个 profile、源码不符、失败或跳过、工件缺失/为空/身份不符；R3 预算启用时补超预算拒绝。负例通过也不能替代正例运行。

## 许可证与版本收口

沿用 [SDK_COMPATIBILITY.md](SDK_COMPATIBILITY.md)、[VERSIONING.md](VERSIONING.md)、根目录 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`。发布包须含实际启用依赖的 notices 和许可证；音频关闭的阅读 profile 不链接 FAAD2，显式启用 AAC/FAAD2 的组合产物仍按其 GPL 条款分发。

发布前核对 SDK/组件版本、ABI epoch、书库 schema、安装消费者报告与更新日志，不要求独立组件版本号相同。GitHub About 的 GPLv3 描述需要单独修正为当前 MIT 核心与可选依赖说明；本轮只登记差异。

## 基线与未完成项

A/B/C 联合验收绑定 `S=686ce2fe6c3463ef1b917569677ee9933e22faa9`，严格汇总 run `39850404743`，SDK 基线 K2 为 `d46ff370cb3c5ce9a0ceb4dc1f8b099209149280`。后续 profile/CMake 改动产生新源码，不能直接继承 S 的验收；触及既有受保护树时按 [PARALLEL-INTEGRATION.md](PARALLEL-INTEGRATION.md) 重新验证、冻结基线与更新契约。

冻结 SDK 的历史长测 CPU 信用只属于其原始源码。R1 首轮不授予 WP16、新源码长测、真实语料整体通过或产品完成。

R6 尚待：首轮云端结果与 check 名冻结、默认分支必需检查实际启用、发布工件/许可证/版本判定接线、R3 性能阈值落地。该文档是门禁映射与现状记录，未启用 GitHub 保护。
