# R6：轻量阅读核心发布门槛

目标：保留多格式解析与自有 PDF 渲染，用原生 C 路径提供可裁剪的阅读 SDK，不依赖 WebView 或浏览器运行时。R6 复用现有 GitHub Actions、安装消费者和证据检查，不增加发布框架。

## 当前状态（2026-10-23）

后续产品分包的 `reading-required` PR 入口只匹配目标默认分支 `codex/framework`；
stacked feature PR 保留各自同源专项，以及未改动的 native/reading-core 通用检查，
不再为每个堆叠层重复启动嵌套的十七作业。最终集成 PR、默认分支 push 和发布准备
仍须实际通过完整十七作业、必需工件、source/run/attempt 和冻结预算严格汇总。
规则25700819、发布者15368、无 bypass 及所有校验代码均不改变。旧分支要有序纳入
该事件配置后才适用；已有运行不自动取消，专项结果不能替代默认或发布门禁。

源码`fa540271ea8ad2d9af4cd31467699db2e50c640a`的[run39902467216](https://github.com/NoGod3524/EXReader/actions/runs/39902467216)
已17/17作业成功，最终`reading-required`严格`accepted=true`、`problems=[]`。
三平台六份SDK候选、固定八份真实语料、40进程/12参考页及冻结预算同次通过；
28份工件与完整身份见[验收JSON](validation/reading-required-fa54027.json)和[R6记录](R6-READING-RELEASE.md)。

PR #2已合入，默认分支规则25700819已active并云端读回。
[reading-required-ruleset.json](reading-required-ruleset.json)绑定GitHub Actions integration15368的
`reading-required`，严格检查且无bypass；仓库About已更新为原生C11/自有PDF/无WebView、MIT核心与可选依赖各自许可。
真实发布准备已在修复候选run39908781291核验并原样导出六包；正式tag/Release尚未执行，见[R6记录](R6-READING-RELEASE.md)。

## 初始设置快照（2026-10-22，历史保留）

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

首轮 Linux 运行已完成：受测 `54d8c592`，run `39853356309`，两个实际 check 为
`reading (reading-core)`、`reading (reading-library)`，均成功。范围与工件见 [启动记录](READING-CORE-START.md)。
后继完整SDK门禁已改为稳定的`reading-required`，其18份必需工件覆盖两profile、平台、真实语料、严格性能及原生证据。
最初两个reading检查不再单独作为默认分支统一门槛。

1. 已完成：共同源码运行17作业门禁，六包、native/sanitizer、R2原始证据及R3固定预算全部严格接受；旧缺Pillow汇总失败保留。
2. 已完成：PR #2接纳到默认分支，规则25700819已active。`reading-required.yml`覆盖PR和默认分支push，没有路径过滤。
3. 已验证：真实prepare核默认分支祖先、17作业、工件、版本/ABI/schema及已有tag后，原样导出六包和SHA256SUMS；首次404失败及修复候选58项回归保留。
4. 待执行：审阅发布准备结果后创建不可变版本。旧tag、失败与原工件保留；产品和宿主声明外范围另行验收。

## 检查映射

| 交付或变更 | 所需证据 | 当前落地边界 |
| --- | --- | --- |
| 两个阅读 profile | Release 构建、安装、安装后组件消费者、九格式合成smoke、组成与许可、候选封装 | Linux/Windows/macOS三平台六包已纳入同次17作业严格验收 |
| 阅读核心 / 自有 PDF 源码、公开头或依赖改变 | 上述 profile + `native.yml` 三平台 CTest、ASan/UBSan、可移植及裁剪安装消费、layers | 复用现有工作流；Linux profile 不能替代三平台证据 |
| EPUB/PDF 实际故障修复 | R2 固定文件散列、原故障、公开 API 的修复结果与回归 | 合成 smoke 不代表真实语料通过 |
| 性能承诺 | R3固定环境、五进程×八份、首屏/翻页/随机定位/峰值内存/体积、实际12页审阅及冻结预算 | Linux reading-core固定语料已严格通过；跨平台性能与任意文档性能不在本次授予范围 |
| 原生宿主接入有界入口 | 对应平台宿主 workflow 的阅读、恢复、取消与资源释放证据 | R5 分平台交付；宿主不依赖 WebView |
| PDF 编辑、OCR、OPDS、迁移、音频、全文索引等可选包 | 现有组件专属工作流与安装消费 | 可独立发包；交付组合含该组件时须验收，不向核心包虚增能力 |
| 包含 A/B/C 范围的联合交付 | `parallel-integration.yml` 及其 12 组 / 35 个上游作业、严格汇总 | 保留现有门槛；新 profile 不删除或绕过旧基线与所有权检查 |

## 一份交付记录即可

复用 workflow 日志、上传工件和现有 JSON；每次交付记录完整 source SHA、workflow 路径、run ID、attempt、作业结论、profile/编译器/依赖配置，以及工件的 ID、大小、SHA-256 digest 和有效期。安装后的头文件、运行库版本/ABI、CMake package 版本须对应同一产物。

所有必需作业须在同源码、所登记 attempt 成功；保留旧失败，不能从不同 attempt 或旧源码拼出通过结果。缺必需证据、取消、跳过、空工件、过期或身份不符均拒绝。初轮报告只有明确通过的构建与 smoke 范围，性能阈值和真实语料状态另列。

现有严格汇总的拒绝回归继续运行。新 profile 发布判定接线时，仅补覆盖新增条件的最小负例：缺一个 profile、源码不符、失败或跳过、工件缺失/为空/身份不符；R3 预算启用时补超预算拒绝。负例通过也不能替代正例运行。

## 许可证与版本收口

沿用 [SDK_COMPATIBILITY.md](SDK_COMPATIBILITY.md)、[VERSIONING.md](VERSIONING.md)、根目录 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`。发布包须含实际启用依赖的 notices 和许可证；音频关闭的阅读 profile 不链接 FAAD2，显式启用 AAC/FAAD2 的组合产物仍按其 GPL 条款分发。

发布前核对SDK/组件版本、ABI epoch、书库schema、安装消费者报告与更新日志。GitHub About已修正并云端读回；候选包按实际启用组件严格核完整许可材料。

## 基线与未完成项

A/B/C 联合验收绑定 `S=686ce2fe6c3463ef1b917569677ee9933e22faa9`，严格汇总 run `39850404743`，SDK 基线 K2 为 `d46ff370cb3c5ce9a0ceb4dc1f8b099209149280`。后续 profile/CMake 改动产生新源码，不能直接继承 S 的验收；触及既有受保护树时按 [PARALLEL-INTEGRATION.md](PARALLEL-INTEGRATION.md) 重新验证、冻结基线与更新契约。

冻结 SDK 的历史长测 CPU 信用只属于其原始源码。R1 首轮不授予 WP16、新源码长测、真实语料整体通过或产品完成。

R6的check名、封装/许可/版本判定、R3预算与候选17作业门禁已经验收；默认分支接纳、规则启用及实际六包准备已执行。
后继源码仍必须通过各自门禁，正式tag/Release另行批准。
