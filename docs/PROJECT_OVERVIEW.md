# EXReader 项目概述

更新日期：2026-10-22。本文按已登记的源码与云端证据描述开发状态；后续候选的验收单独记录。

## 项目定位与优先级

EXReader 是面向桌面和移动阅读应用的 C11 原生阅读引擎与可嵌入 SDK，提供文档解析、文字分析与塑形、
排版分页、像素绘制、搜索选择、稳定位置和可选的书库/音频/PDF 编辑能力。
宿主通过 C/C++、Swift 或 JNI 接入，可以使用引擎绘制，也可以读取布局与几何数据自行绘制。
UI、系统事件、账户、同步和平台服务由宿主负责。

2026-10-22 调整目标：**保留底层多格式解析与自有 PDF 渲染核心，把轻量、可靠与高性能作为主线。**
撤销“全面领先 MuPDF、CREngine、Readium、foliate-js”的总目标。这些项目继续作为质量和性能参照，
差分用于找出用户可见的缺陷和性能瓶颈。

| 优先级 | 工作范围 | 取舍原则 |
| --- | --- | --- |
| 核心必做 | 现有多格式入口、常用 EPUB/PDF 的打开与绘制、文字/定位正确性、首屏/翻页、取消和资源限界 | 先修真实阅读故障及热点；保持 C11 核心和可嵌入公开接口 |
| 轻量与性能必做 | 裁剪构建、按需加载、缓存预算、长章节窗口、二进制体积和峰值内存 | 可选组件关闭后不引入其运行依赖；速度、内存和显示质量一起计量 |
| 按需求推进 | PDF 编辑/表单、高级色彩与罕见特性、OCR、复杂转换、TTS、OPDS/LCP、完整平台应用 | 保留已有能力；新增范围须有真实使用需求、独立成本和验收出口 |

“绝对性能”落实为指定设备上的绝对耗时、内存与体积预算。每种构建 profile 先建立云端基线，
再冻结数值门槛；当前尚未建立统一预算，不能填写未经测量的 MB 或毫秒承诺。
记录打开、首屏、连续翻页、随机跳页 p50/p95、峰值 RSS、缓存/解析载荷和发布二进制大小；
同时固定字体、页尺寸、渲染质量、线程数与冷/热缓存条件。优化须保留正文、分页定位和显示正确性，
不得用漏绘、跳页或降低测量质量取得性能提升。度量口径见 [参考引擎与性能度量](COMPETITIVE.md)。

下一轮主线依次是：冻结最小核心构建与代表性语料 → 建立体积/延迟/内存基线 →
修复常用 EPUB 超时及 PDF 打开/绘制故障 → 按实测热点优化并接入必需回归 → 发布可追溯 SDK。
新增格式子特性按真实影响评估；当前核心版本无需等所有可选扩展实现完毕。

总 SDK 当前为 3.40.0 开发版，ABI epoch 1、书库 schema 6。核心自有代码采用 MIT；第三方组件、字体和
可选解码器分别遵守各自许可。默认关闭 FAAD2，启用它的组合二进制需遵守 GPL。
版本字段以公开头文件为准，规则见 [VERSIONING.md](VERSIONING.md)。

## 交付形态与能力

| 交付层 | 当前范围 | 主要边界 |
| --- | --- | --- |
| 原生引擎与 SDK | TXT/HTML/FB2/EPUB/DOCX/RTF/MOBI/KF8 重排输入，PDF/CBZ 固定页，Unicode 文字分析、OpenType、分页和绘制 | 各格式结构、CSS、脚本、图像与 PDF 子特性按支持矩阵声明 |
| 有界阅读与存储 | EPUB 章索引/窗口/恢复点；SQLite 原书、进度、标注、精确去重、备份；CBZ/PDF 分块或映射原书路径 | 旧完整快照 API 语义保留；宿主尚未全部接入有界入口，其他格式不能据此宣称大文件全流式 |
| 字体与图文 | 八个新增声明脚本、竖排/ruby/float/表格；COLR v1 与 SVG 字体子集；扩展 CBZ 图像 | 字体、脚本、颜色和组合模式存在明确支持边界，不能外推到全规范 |
| 原生参考宿主 | Windows、Linux GTK、macOS/iPhone/iPad；Android 另有独立交付分支 | 各宿主单独验收；大小限制、格式、后台/取消、真机及无障碍范围不同 |
| 工具与独立模块 | 轻量转换、EPUB/HTML 资源包 preserve、旧 UI 迁移、OPDS1/2、可选 Tesseract 适配器 | 高保真全格式往返、OCR PDF 文字层与搜索/标注闭环、HTTPS/LCP 和新宿主服务接入仍有缺口 |

接口和所有权见 [NATIVE_API.md](NATIVE_API.md)，组件依赖见 [ARCHITECTURE.md](ARCHITECTURE.md)，
详细能力边界见 [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)。

## 已登记的验收与候选状态

单包结果只绑定其受测源码。功能合入集成候选后，需要在新的共同源码上重新验证。

| 范围 | 已登记结果 | 当前剩余事项 |
| --- | --- | --- |
| 冻结 SDK 可靠性 | 源码 `635225fe6ceb7759a948a1d8cede0ab18ea1cee9`，run `39666440519`：98/98 作业、99 同源工件、四目标各至少 24 实际进程 CPU 小时 | 后续核心改动不继承旧源码 CPU 额度；整项目发布状态另行收口 |
| WP6 有界 EPUB 章阅读 | 50/100 MiB 单章、10→100 MiB 索引/解析续排峰值增量 19.3 MiB、检查点及随机恢复固定出口已验收 | 新宿主接入仍单独推进 |
| 表格 border-spacing | 源码 `ee76f5b`，run `39816051738`，Windows/Linux 各 163/163；纳入 K 后专用 run `39821213939` 2/2 成功，native 全量回归通过 | 最终 S 仍须同源复验；完整 CSS 仍有缺口 |
| 基础 AcroForm | 源码 `7e44ae5`，run `39817023587`：Windows/Linux 各 4/4、ASan/UBSan 1/1，各 9394 次 CHECK；纳入 K 后专用 run `39821209875` 3/3 成功，native 全量回归通过 | 24 种进程内输入、0 份独立 PDF；至少 30 文件出口仍未满足，完整 WP9 未完成 |
| Apple 宿主审计 | 源码 `b3f28ca`，run `39813162880`：8/8 作业、8 工件，三平台各 12 用例/61 步/46 附件，严格汇总通过；已合入 K，native SDK/绑定构建通过 | K 上未重跑 Apple UI 专用验收，最终 S 仍须完整同源复验；真机/VoiceOver 仍独立跟踪 |
| Android 宿主审计 | 已登记候选 `ac7aecc` 的 run `39816104855` 最终失败 | 包 A 负责定位新一轮逐项失败并完整复验；旧源的 45/45 + 独立 4/10 不可拼接为新源通过 |
| OPDS facets | 独立分支源码 `757e2f3`，run `39815167314`：双平台各 65/65、facet 回归与 Linux sanitizer 通过 | 独立分支待最终集成；计数 profile、HTTPS、间接获取、借阅/支付/LCP 等边界保持 |
| SDK 预集成与基线 K | `4729f7fc7d908d249704d96ee61cc74ee778a27f`：native run `39821205425` 7/7、AcroForm 3/3、spacing 2/2；native 19 份工件同源、非空、未过期且具有 SHA-256 digest | C 阶段一/二完成；A/B 固定交付、必要的 K 重冻结、OPDS 合入及最终联合验收待完成 |

主要证据见 [冻结 SDK 记录](validation/2026-10-22-reliability-cloud.json)、
[表格间距](WP5_BORDER_SPACING.md)、[AcroForm](WP9_ACROFORM.md)、[Apple 审计](WP13-APPLE-REVIEW.md)，
Android/OPDS 独立候选的完整身份见 [总 handoff](handoffs/2026-10-22-after-deadline.md)。

K 的登记及最新阶段记录见集成分支固定提交 `b81f138` 中的
[SDK 基线](https://github.com/NoGod3524/EXReader/blob/b81f13869bb49b1138e4862faf64daae01d5fd01/docs/validation/sdk-baseline.json)、
[预集成证据](https://github.com/NoGod3524/EXReader/blob/b81f13869bb49b1138e4862faf64daae01d5fd01/docs/validation/2026-10-22-preintegration.json) 与
[联合验收说明](https://github.com/NoGod3524/EXReader/blob/b81f13869bb49b1138e4862faf64daae01d5fd01/docs/PARALLEL-INTEGRATION.md)。

## 五项工程质量目标

这五项是轻量阅读核心的质量保障。差分与专项覆盖围绕声明范围及真实使用风险选择；
全规范覆盖和所有可选模块完成不再作为核心发布的统一前提。

| 目标 | 已有工作 | 尚未闭合的出口 |
| --- | --- | --- |
| 默认分支必须通过的 CI 与可信构建基线 | `native.yml` 在默认分支 `codex/framework` push 和 PR 上运行；已有默认/裁剪 SDK 安装消费、ABI/分层检查；K 已同源验证并固定八条受保护树，12 组联合协议及基线门禁自验通过 | 2026-10-22 只读核对时默认分支 `protected=false`、required checks 为空、rulesets 为空。仍需配置必需检查与合并/发布门槛，并完成最终 S 的联合验收 |
| EPUB 超时、PDF 打开/渲染失败闭环 | 整本文档探针、逐进程超时/失败保留、独立分类与回归工具；已有针对性引擎修复 | 历史 EPUB 500 本仅 483 完成，另有 11 超时、5 限制、1 参数状态；PDF 122 份中 49 完成，其余 73 留有分类，不能全部视作同一故障。原批未整体验收；新协议可复现真实语料登记仍为 0/1710 |
| 成熟引擎差分、像素与性能回归 | WP7 有 HarfBuzz 对照，彩色字体有 Chrome 对照，PDF 部分颜色/绘制有 MuPDF 独立参考；已有像素、页面 hash、分页与转换基准 | 统一固定工具/字体/采样口径、语料、容差及资源阈值，覆盖真实 EPUB/PDF 故障，并接入必需 CI；专项对照不替代全格式差分验收 |
| 内存峰值、长章节和恶意输入专项 | WP6 有界章出口、1 GiB CBZ 原书导入、1 GiB WAV 随机读取、取消/限界/sanitizer 与四目标可靠性长测 | 每次核心变更绑定新源码复验；其他格式大文件、其他音频 1 GiB 实测和全部宿主有界接入仍未覆盖 |
| 许可证、版本与发布流程统一 | MIT 主许可证、第三方通知、版本规则、ABI/schema 区分，以及冻结 SDK 的多平台许可/产物/基准归档 | GitHub About 仍含旧“GPLv3”描述，与当前 MIT LICENSE 不一致；需统一说明、tag/版本/产物身份、许可清单与发布阻断规则，新集成候选尚未完成整条发布闭环 |

相关入口：[兼容语料清单与缺口](COMPAT-CORPUS-PARALLEL.md)、[整本文档检查](CORPUS_VALIDATION.md)、
[色彩差分](COLOR_MATRIX.md)、[性能记录](PERFORMANCE.md)、[可靠性交付](RELIABILITY-HANDOFF.md)、
[第三方许可](../THIRD_PARTY_NOTICES.md)。历史失败、取消和原预期保留，不能删除困难样本或用事后预期提高通过率。

## 当前并行工作包

| 包 | 独立职责 | 汇合依赖 |
| --- | --- | --- |
| [A：Android 修复](handoffs/2026-10-22-A-android.md) | 修复失败行为/驱动，完成同一新源码的 45+10、分页计量和严格证据门禁 | 交付固定源码与完整云端验收 |
| [B：AcroForm 语料](handoffs/2026-10-22-B-acroform-corpus.md) | 补至少 30 份独立 PDF、保存重开和外观验证；必要时修复表单缺陷 | 交付固定源码、逐文件证据与回归 |
| [C：SDK 集成](handoffs/2026-10-22-C-integration.md) | 阶段一/二完成：合入 AcroForm、spacing、Apple 修复，云端验证 K 并登记基线与严格门禁 | 阶段三/四等 A/B 固定交付；最终 S 跑原十组 28 作业，加 AcroForm 3 作业和 spacing 2 作业，共 12 组 33 个上游作业及严格汇总 |

C 的 protocol 自验 run `39823812435` 成功；dispatch run `39823842117` 的 protocol、baseline 成功，
受检源码为 `82f88966c0ca2bbca93837861270b8cb57ebb184`，summarize 按设计跳过。当前门禁核对 K 的祖先关系、
八条受保护树、基线证据及版本/ABI，并要求 OPDS `BASELINE` 和合入后的 Android `SDK_BASE` 指向 K。
Android 守卫尚登记为 pending；文件合入时必须转为有效契约。

后续顺序：A/B 交付 → 若受保护树改变则重验并冻结新 K → 登记 Android 基线与所有权源码 →
冻结非 OPDS 祖先 H → 最后合入 OPDS facets 并登记 `HANDOFF=H` → 冻结 S →
在 S 上重跑 12 组并提交 12 个 run ID，严格汇总 `accepted=true` 后授予联合验收。
33 个上游作业之外，联合门禁自身另有 protocol、baseline 和 summarize 作业。

三包是当前功能与集成子任务，不替代上述五项质量目标。C 直接覆盖 SDK 基线与联合验证，B 覆盖表单专项输入；
EPUB/PDF 历史失败闭环、通用差分门禁和完整发布制度尚未成为这三包中可独立验收的完整任务。
其余十五项能力见 [历史工作清单](WORK-QUEUE-2026-10-22.md)，现作为候选积压，按上述优先级重新选择，
不全部列入下一核心版本。A/B/C 已冻结的交付及 12 组联合验收契约继续单独收口；
本次定位调整不修改其脚本或将未通过项改记为通过。

所有构建、测试、生成、模拟器、工件解析与证据汇总均在 GitHub Actions 执行。独立用例通过、
多平台构建通过、共同源码验收和最终发布门槛分开记录；未满足项继续保留。
