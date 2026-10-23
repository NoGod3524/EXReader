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

**架构约束：不依赖 WebView 或浏览器运行时。** HTML/EPUB 的解析、CSS 子集、排版和绘制由 C 核完成，
PDF 保留自有原生渲染核心；参考宿主使用原生控件及系统绘图接口显示引擎结果。
发布运行依赖不包含 WebView2、WKWebView、Android WebView、Chromium 或 Electron。
浏览器可用于开发期差分参考，不进入交付运行依赖。

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

具体执行分为 R1 标准阅读构建、R2 实际故障、R3 性能基线、R4 热点优化、R5 宿主有界接入、
R6 核心发布门槛，详见 [六个工作包](CORE-ROADMAP.md)。已完成能力的调整与现有 A/B/C 收口在同文登记。

总 SDK 当前为 3.40.0 开发版，ABI epoch 1、书库 schema 7。核心自有代码采用 MIT；第三方组件、字体和
可选解码器分别遵守各自许可。默认关闭 FAAD2，启用它的组合二进制需遵守 GPL。
版本字段以公开头文件为准，规则见 [VERSIONING.md](VERSIONING.md)。

## 原生阅读核心当前进展

R1分支 `codex/r1-reading-core` 从 S=`686ce2fe` 追加阅读 preset、安装后消费者与测量工具，
该阶段不修改引擎、公开头或原默认构建。后续集成分支 `codex/reading-package-integration`
已纳入R5的SDK有界存储契约、许可修补、平台门禁及四宿主接入。以下分列历史结果与当前状态：

| 状态 | 工作包 | 内容 |
| --- | --- | --- |
| 已完成 | R1（Linux） | 受测源码 `54d8c592ed4f48e2f5ddb7811de213c95e41243c`，run [39853356309](https://github.com/NoGod3524/EXReader/actions/runs/39853356309) attempt 1：`reading (reading-core)`、`reading (reading-library)` 均成功；安装消费者 3/3、4/4，九格式合成 smoke 均 9/9，组件/依赖判定与拒绝自验通过 |
| 已完成 | R3 初始采样（Linux） | 同一 run 两 profile 各三次独立进程的 1 MiB TXT 首屏/32 次翻页采样，汇总 accepted |
| 已完成（失败保留） | R1/R3 首轮 | 源码 `61aa183`，run `39852907619`：构建、安装、消费者与 smoke 成功，测量自验因 mock 误拦截失败、实际采样未执行；修复后在新源码重验 |
| 已完成 | R1 跨平台（H1） | 受测源码 `9b968a16fc47596725e849e56ee98e4c4c210b74`，run [39854485070](https://github.com/NoGod3524/EXReader/actions/runs/39854485070) attempt 1：Windows/macOS × 两 preset 4/4 作业成功，构建、安装、安装消费者 3/3 或 4/4、九格式合成 smoke 9/9 与依赖/配置判定 accepted，见 [H1 记录](https://github.com/NoGod3524/EXReader/blob/2e8e981b6dd44d855a23931480fe5e0d5c791762/docs/READING-PLATFORMS.md)；未做性能或体积预算。程序集合、依赖解析与链接器身份的门禁加固由 [H6](https://github.com/NoGod3524/EXReader/blob/62ab38e8223e42f1562fda7137cd41b4d87620f1/docs/handoffs/reading-H6-platform-gate.md) 另行跟踪 |
| 已完成 | R3 初始 PDF/CBZ 测量（Linux，合成） | 源码 `3cd7bdf14d4ee961a9cdda98bd7410d34c04161b`，run [39855093753](https://github.com/NoGod3524/EXReader/actions/runs/39855093753)：655 字节 1 页 PDF 与 908 字节 4 页 CBZ 各三进程；可区分页面候选 `4b6f562c29181d509f470feda0e5f1226fd466bb`，run [39856195765](https://github.com/NoGod3524/EXReader/actions/runs/39856195765) 增加 3 页 PDF/4 页 CBZ 的 32×32 合成文档，12 进程/240 次绘制、60 项拒绝自验，2026-10-22 只读核对为 success。见 [R3 记录](https://github.com/NoGod3524/EXReader/blob/ea3d4d1a24c0febd8d14f110594b7226e2527c82/docs/READING-PDF-PERFORMANCE.md) |
| 已完成 | R5 宿主H8–H11 | 共同源码`e25959e`，四组11作业/11必需工件同源、attempt1通过；各平台严格汇总接受，见[共同验收记录](R5-SDK-FREEZE.md) |
| 已验证 | R5 SDK 契约 | 固定`9c69bc4`，窗口单元递归已修复，六组18执行作业/30工件同源通过；旧冻结撤回与失败记录保留，见[SDK冻结记录](R5-SDK-FREEZE.md) |
| 未执行 | R2 | 九格式原创 fixture 清单已冻结，仅作小型回归；真实 EPUB/PDF 语料仍为 0/1710，实际故障尚未逐份登记修复 |
| 未执行 | R3 正式基线 | 真实多页 PDF、嵌入/回退字体与复杂图像、真实语料、跨平台性能、峰值内存预算与冻结的硬性能预算 |
| 未完成 | R4 / 设备与读屏 | R4等待可复现热点；真机、VoiceOver/TalkBack及宿主声明外能力另行验收 |
| 未执行 | R6 启用 | 门禁映射已写入，两个 check 尚未设为默认分支必需检查；默认分支 `protected=false`、rulesets 为空 |

两个 preset 只做组件裁剪：`reading-core` 关闭音频（含 MP3/AAC）、书库、全文索引、PDF 编辑、旧共享总库、工具和 JNI，
保留 PDF、PDF 密码认证、ICC 与全部现有图像开关；`reading-library` 仅再打开 SQLite 书库。
裁剪不增强 PDF 或图像能力；初始 1 MiB TXT 与极小 PDF/CBZ 采样均为合成工作负载，不是成熟性能基线，
也不替代真实语料或硬预算。R3 表中 RSS 基线与峰值相同只表示未超过进程先前高水位，不能推断没有分配。
新配置结果只绑定其受测源码，不继承 S 的联合验收或旧源码长测额度。命令与前置条件见
[README 阅读 SDK preset](../README.md#阅读-sdk-preset)，记录见 [首轮启动](READING-CORE-START.md)、[门禁映射](READING-CORE-GATE.md)、
[语料准备](READING-CORPUS.md) 与 [测量口径](READING-PERFORMANCE.md)。

## 交付形态与能力

| 交付层 | 当前范围 | 主要边界 |
| --- | --- | --- |
| 原生引擎与 SDK | TXT/HTML/FB2/EPUB/DOCX/RTF/MOBI/KF8 重排输入，PDF/CBZ 固定页，Unicode 文字分析、OpenType、分页和绘制 | 各格式结构、CSS、脚本、图像与 PDF 子特性按支持矩阵声明 |
| 有界阅读与存储 | EPUB 章索引/窗口/恢复点；SQLite 原书、进度、标注、精确去重、备份；CBZ/PDF 分块或映射原书路径 | 四宿主已在声明范围接入有界EPUB及章内持久化；旧完整快照API保留，其他格式仍有明确上限 |
| 字体与图文 | 八个新增声明脚本、竖排/ruby/float/表格；COLR v1 与 SVG 字体子集；扩展 CBZ 图像 | 字体、脚本、颜色和组合模式存在明确支持边界，不能外推到全规范 |
| 原生参考宿主 | Windows、Linux GTK、macOS/iPhone/iPad、Android已纳入共同R5源码 | 各宿主按声明范围验收；大小限制、格式、后台/取消、真机及无障碍范围不同 |
| 工具与独立模块 | 轻量转换、EPUB/HTML 资源包 preserve、旧 UI 迁移、OPDS1/2、可选 Tesseract 适配器 | 高保真全格式往返、OCR PDF 文字层与搜索/标注闭环、HTTPS/LCP 和新宿主服务接入仍有缺口 |

接口和所有权见 [NATIVE_API.md](NATIVE_API.md)，组件依赖见 [ARCHITECTURE.md](ARCHITECTURE.md)，
详细能力边界见 [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)。

## 已登记的验收与候选状态

单包结果只绑定其受测源码。功能合入集成候选后，需要在新的共同源码上重新验证。

| 范围 | 已登记结果 | 当前剩余事项 |
| --- | --- | --- |
| 冻结 SDK 可靠性 | 源码 `635225fe6ceb7759a948a1d8cede0ab18ea1cee9`，run `39666440519`：98/98 作业、99 同源工件、四目标各至少 24 实际进程 CPU 小时 | 后续核心改动不继承旧源码 CPU 额度；整项目发布状态另行收口 |
| WP6 有界 EPUB 章阅读 | 50/100 MiB 单章、10→100 MiB 索引/解析续排峰值增量 19.3 MiB、检查点及随机恢复固定出口已验收 | 新宿主接入仍单独推进 |
| 表格 border-spacing | 独立验收后纳入 S，run `39844627315` 2/2 成功，并纳入 S 的 native 回归 | 声明范围联合验收通过；完整 CSS 仍有缺口 |
| 基础 AcroForm 与独立文件语料 | 独立 75 文件出口通过；在 S 的 run `39844617258` 5/5 成功，并纳入严格联合汇总 | 至少 30 文件出口已满足；75 份含写拒绝/取消/不可读树。安装消费者各覆盖 31、跳过 2；高级表单范围未完成 |
| Apple 宿主审计 | 独立审计通过后在 S 重验，run `39844598529` 8/8 作业、8 工件成功，严格联合汇总接受 | 声明范围联合验收通过；真机/VoiceOver 仍独立跟踪 |
| Android 宿主审计 | 独立审计通过后在 S 重验，run `39844608350` 成功，完整证据由严格联合汇总接受 | API34 x86_64 模拟器范围联合验收通过；真机/签名/TalkBack 等另列；旧失败继续保留 |
| OPDS facets | 独立审计通过，冻结 H 后纳入 S，run `39844589166` 双平台 2/2 作业成功并获严格汇总接受 | 声明范围联合验收通过；计数 profile、HTTPS、间接获取、借阅/支付/LCP 等边界保持 |
| SDK 预集成与原基线 K（历史） | `4729f7fc7d908d249704d96ee61cc74ee778a27f`：native run `39821205425` 7/7、AcroForm 3/3、spacing 2/2；native 19 份工件有效 | 阶段一/二结果保留，已由最终 K2 接续 |
| 最终 SDK 基线 K2 与共同源码 S | K2=`d46ff370`；S=`686ce2fe6c3463ef1b917569677ee9933e22faa9`；12 组/35 上游作业与严格汇总 [39850404743](https://github.com/NoGod3524/EXReader/actions/runs/39850404743) 通过，44 上游工件有效 | A/B/C 已收口；产品整体、S 的 WP16 长测、真实语料和新性能预算尚未完成 |

主要证据见 [冻结 SDK 记录](validation/2026-10-22-reliability-cloud.json)、
[表格间距](WP5_BORDER_SPACING.md)、[AcroForm](WP9_ACROFORM.md)、[Apple 审计](WP13-APPLE-REVIEW.md)，
Android/OPDS 独立候选的完整身份见 [总 handoff](handoffs/2026-10-22-after-deadline.md)。

最新 A/B 固定交付、云端核对和 C 接续要求见 [A/B 到齐登记](https://github.com/NoGod3524/EXReader/blob/8c25d2f67c5846b548a2aafa0060f06036c1d364/docs/handoffs/2026-10-22-AB-delivered.md)。

原A/B/C阶段以 [联合验收登记](https://github.com/NoGod3524/EXReader/blob/8c25d2f67c5846b548a2aafa0060f06036c1d364/docs/handoffs/2026-10-22-ABC-accepted.md) 为准；
后续R5的当前SDK与宿主源码另见[冻结及共同源码记录](R5-SDK-FREEZE.md)。

原 K 的阶段一/二历史记录见集成分支固定提交 `b81f138` 中的
[SDK 基线](https://github.com/NoGod3524/EXReader/blob/b81f13869bb49b1138e4862faf64daae01d5fd01/docs/validation/sdk-baseline.json)、
[预集成证据](https://github.com/NoGod3524/EXReader/blob/b81f13869bb49b1138e4862faf64daae01d5fd01/docs/validation/2026-10-22-preintegration.json) 与
[联合验收说明](https://github.com/NoGod3524/EXReader/blob/b81f13869bb49b1138e4862faf64daae01d5fd01/docs/PARALLEL-INTEGRATION.md)。

## 五项工程质量目标

这五项是轻量阅读核心的质量保障。差分与专项覆盖围绕声明范围及真实使用风险选择；
全规范覆盖和所有可选模块完成不再作为核心发布的统一前提。

| 目标 | 已有工作 | 尚未闭合的出口 |
| --- | --- | --- |
| 默认分支必须通过的 CI 与可信构建基线 | `native.yml` 在默认分支 `codex/framework` push 和 PR 上运行；已有默认/裁剪 SDK 安装消费、ABI/分层检查；K2 固定八条受保护树，S 的 12 组联合验收与严格汇总通过 | 2026-10-22 只读核对时默认分支 `protected=false`、required checks 为空、rulesets 为空。仍需配置必需检查与合并/发布门槛 |
| EPUB 超时、PDF 打开/渲染失败闭环 | 整本文档探针、逐进程超时/失败保留、独立分类与回归工具；已有针对性引擎修复 | 历史 EPUB 500 本仅 483 完成，另有 11 超时、5 限制、1 参数状态；PDF 122 份中 49 完成，其余 73 留有分类，不能全部视作同一故障。原批未整体验收；新协议可复现真实语料登记仍为 0/1710 |
| 成熟引擎差分、像素与性能回归 | WP7 有 HarfBuzz 对照，彩色字体有 Chrome 对照，PDF 部分颜色/绘制有 MuPDF 独立参考；已有像素、页面 hash、分页与转换基准 | 统一固定工具/字体/采样口径、语料、容差及资源阈值，覆盖真实 EPUB/PDF 故障，并接入必需 CI；专项对照不替代全格式差分验收 |
| 内存峰值、长章节和恶意输入专项 | WP6 有界章出口、1 GiB CBZ 原书导入、1 GiB WAV 随机读取、取消/限界/sanitizer 与四目标可靠性长测 | 每次核心变更绑定新源码复验；其他格式大文件、其他音频 1 GiB 实测和全部宿主有界接入仍未覆盖 |
| 许可证、版本与发布流程统一 | MIT 主许可证、第三方通知、版本规则、ABI/schema 区分；R6已更新并云端读回About，候选封装与严格门禁在云端复验 | 默认分支必需检查尚未启用；tag/版本/产物身份及发布阻断规则仍待最终共同源码闭环，见[R6记录](R6-READING-RELEASE.md) |

相关入口：[兼容语料清单与缺口](COMPAT-CORPUS-PARALLEL.md)、[整本文档检查](CORPUS_VALIDATION.md)、
[色彩差分](COLOR_MATRIX.md)、[性能记录](PERFORMANCE.md)、[可靠性交付](RELIABILITY-HANDOFF.md)、
[第三方许可](../THIRD_PARTY_NOTICES.md)。历史失败、取消和原预期保留，不能删除困难样本或用事后预期提高通过率。

### GitHub About（已更新）

原About为 `GPLv3 native C ebook engine with custom pagination, raster rendering and a SQLite bookshelf`，
与MIT元数据不一致。本轮R6已更新仓库说明并通过GitHub连接读回：

> Lightweight native C11 reading engine and SDK: multi-format parsing, in-house PDF rendering, no WebView. MIT core; optional dependencies retain their own licenses (FAAD2/AAC-enabled binaries require GPL compliance).

中文说明可用：“轻量原生 C11 阅读引擎与 SDK：多格式解析、自有 PDF 渲染、不依赖 WebView。核心为 MIT；
可选依赖保留各自许可，启用 FAAD2/AAC 构建的组合二进制须遵守 GPL。”
FAAD2 默认关闭，阅读 preset 也不链接它；只有显式 `EXR_ENABLE_AAC=ON` 并链接音频组件的产物须按 GPL 分发
（提供对应源码与许可文本）。许可证原文、版本和tag保持；本次About更新不构成新版本发布。

## 既有 A/B/C 交付收口

| 包 | 独立职责 | 汇合依赖 |
| --- | --- | --- |
| [A：Android 修复](handoffs/2026-10-22-A-android.md) | 声明范围独立验收通过，交付 `31b36f30`；已纳入 S 并复验 | 已收口，支持边界保留 |
| [B：AcroForm 语料](handoffs/2026-10-22-B-acroform-corpus.md) | 独立文件出口通过，交付 `97e33452`；已纳入 S 并复验 | 已收口，可选编辑支持边界保留 |
| [C：SDK 集成](handoffs/2026-10-22-C-integration.md) | 阶段一至四完成；K2、H、S 及 12 组/35 作业严格汇总均已登记 | 联合验收通过；完整发布制度和性能路线另行推进 |

C 已合入固定交付，重验并冻结 K2=`d46ff370`，冻结非 OPDS 祖先 H=`d10fa590` 后完成 OPDS 合入。
最终 S 的 12 组/35 上游作业全部成功，汇总 run `39850404743` 的 protocol、baseline、summarize 也全部成功。
完成日志明确 `accepted=true`；OPDS 与 Android 的 SDK 契约均为 K2，`pending_contracts=[]`。
早期 protocol 自验、原 K 和 33 作业协议继续作为历史保留，原A/B/C验收以该最终 S 为准。

三包是当前功能与集成子任务，不替代上述五项质量目标。C 直接覆盖 SDK 基线与联合验证，B 覆盖表单专项输入；
EPUB/PDF 历史失败闭环、通用差分门禁和完整发布制度尚未成为这三包中可独立验收的完整任务。
下一版执行 [原生阅读核心路线](CORE-ROADMAP.md)；其余十五项能力见 [历史工作清单](WORK-QUEUE-2026-10-22.md)，
按需积压，不全部列入下一核心版本。A/B/C 等待条件已满足，R1–R6 已在 `codex/r1-reading-core` 启动，
实际进展见 [原生阅读核心当前进展](#原生阅读核心当前进展)。

所有构建、测试、生成、模拟器、工件解析与证据汇总均在 GitHub Actions 执行。独立用例通过、
多平台构建通过、共同源码验收和最终发布门槛分开记录；未满足项继续保留。
