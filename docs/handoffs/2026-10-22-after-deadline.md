# EXReader 交接：2026-10-22 限时工作结束后

本文件供下一个 AI 接手。当前请求仅为整理 handoff，未恢复编码、测试或派工。
用户此前要求美东 12:55 停工，已执行；所有子代理已停止，截止提醒 `exreader-12-55` 已删除。
后续工程工作须由用户重新要求继续；不要据此文件自行恢复常驻监控。

## 1. 当前结论与执行约束

- 本轮五条线中，OPDS facets、表格间距、Apple 审计复验及 AcroForm 基础实现回归通过；Android 未验收。
- AcroForm 基础回归通过不等于完整 WP9：至少 30 份独立 PDF 的出口尚未满足。OPDS facets 通过也不等于完整 WP15。
- 编译、测试、语料生成、benchmark、模拟器、工件解析和证据汇总全部只在 GitHub Actions 云端执行。本地可读写源码/文档、操作 Git、提交云端工作流；不得本地运行测试、脚本语法检查、夹具生成或下载工件重汇总。
- 不推送 `codex/framework`，不合并 PR，不改用户主工作区的无关文件。各交付分支已推送，尚未联合合入。
- 失败、取消及诊断记录保留。验收必须同源码、同 run/attempt，完整作业与工件均满足门槛，不能拼接旧通过项。
- 写作偏好：删除只为防止被质疑、没有推进论证作用的话。只引用必要文件路径，不粘贴崩溃栈或样本细节。

仓库：`NoGod3524/EXReader`。主工作区：`C:/Users/Oscar/OneDrive/文档/ChatGPT/EXReader`。
所有下表分支均已有独立工作树，优先复用，勿重置或重建。

## 2. 精确交付身份

| 包/分支 | 工作树（均在 `C:/Users/Oscar/.codex/worktrees/` 下） | 受测实现源码 | 分支交付 HEAD | 云端 run / 结果 |
| --- | --- | --- | --- | --- |
| `codex/wp9-acroform` | `wp9-acroform/EXReader` | `7e44ae59d47a578dac3116154b0de5a67efb0163` | `4605dbf7524f8764b923e5c447e1a6988fe4f62f` | `39817023587`，3/3 success |
| `codex/wp5-border-spacing` | `wp5-border-spacing/EXReader` | `ee76f5b582ec92112bb294226d5b42758b1ad2ae` | `a0bb9d2d6988b74e62aa1592faed681cee1950d4` | `39816051738`，2/2 success |
| `codex/wp13-apple-review` | `wp13-apple-review/EXReader` | `b3f28ca19904f9a6f173113f6ed86e62928be875` | `535f6baff40234427d9d0584fee1432dfecf099b` | `39813162880`，8/8 success，严格 accepted |
| `codex/wp13-android-review` | `wp13-android-review/EXReader` | `ac7aecc4d3c2e6e65a6797ab556cd31546ca3a5c` | `05048cccd84532509e0d6039feb3b7769824ec1a` | `39816104855`，最终 failure |
| `codex/wp15-catalog-features` | `wp15-catalog-features/EXReader` | `757e2f33271b358715ea8f83f44a3c779ad660e8` | `47d8fda0bea9aca6eb1f3f595344b31c0ec51d08` | `39815167314`，2/2 success |

上述实现后 HEAD 保存文档与证据，不能用文档 HEAD 冒充实际受测源码。
`codex/parallel-integration` 工作树为 `parallel-integration/EXReader`；交接前 HEAD 为
`db3ea538c489ad7c03d29ce5149908963ee40f53`，本文件将由后续文档提交保存。
该分支尚未纳入本轮五条线的新交付。各工作树最近一次检查均干净。

### AcroForm：已实现与未满足项

新增公共表单 snapshot/read/free/write API，读取字段继承、值/默认值、选项、widget，
批量增量编辑文本、checkbox/radio/choice 的值与 AP/AS，处理预算、取消、失败原子输出。
Unicode 外观使用借用的轮廓字体；双向排版、缺 glyph/可见空轮廓明确拒绝。
multiline/password/comb/rich text/editable combo、旋转、动作/JS、XFA 等保持声明边界。

独立审查发现并已在最终源码修复：局部编辑错误清除整个表单的 NeedAppearances；
没有 RadiosInUnison 时重复 radio 导出值会同时选中。现在保留原 NeedAppearances，
重复 radio 值无明确 widget 选择能力时拒绝；设置 RadiosInUnison 时支持并逐 widget 检查 AS。

最终 Windows/Linux 各 4/4、ASan/UBSan 1/1，各 9394 次 CHECK；Linux 层检查 106 对象、
1162 符号引用、0 逆向，954 头依赖、0 逆向 include。
只有 1 个主表单（36 字段、39 widget、2 页）、24 种进程内输入，独立 PDF 文件数为 0。
这些检查数不能替代至少 30 份独立文档的工作包出口。

入口：`docs/WP9_ACROFORM.md`、`docs/validation/wp9-acroform.json`、`tests/test_pdf_form.c`、
`src/pdf_write.c`、`include/exr/pdf_edit.h`、`.github/workflows/acroform.yml`。
验收 JSON 的 `current_candidate_*` 是最终源码；下方 `tested_implementation_source/run/jobs`
保留 `72ca373` 的历史结果，不要误读为最新候选。

### 表格 border-spacing：声明范围通过

支持一/两个非负 CSS 长度、继承/initial/unset、collapse 清零、横纵间距、跨列/跨行、
分页、重复表头、高行拆分、竖排及 checkpoint/随机恢复。
Ubuntu/Windows 均 163/163；专用用例覆盖 21 种调用场景及 19 次随机翻页。
曾有回归未真正生成 XHTML thead 的问题，已修构造命名空间，保留原 11px 精确间距断言。

入口：`docs/WP5_BORDER_SPACING.md`、`docs/validation/wp5-border-spacing-acceptance.json`、
`tests/test_table_spacing.c`、`.github/workflows/wp5-border-spacing.yml`。
该结论只授予 border-spacing 子包，不授予整个 WP5 剩余 CSS 能力。

### Apple：独立严格复验通过

同一 run 的 8 作业/8 工件通过；macOS/iPhone/iPad 各 12 用例、61 步、46 附件，
各 21 项旧自检，SDK 桥接 21 项、Model 会话 18 项、83 项证据拒绝回归与严格汇总通过。
最后修复为 raw xcresult 散列采集移到最后一次 xcresulttool 导出之后；程序和持久化原件仍前置保留。

验证工件 `12442212853`（56822 B），
`sha256:42ddc5e944c346c2b1fc9f558f451ef1cec47772d4ded5e375cd957dd3555a22`。
真机、VoiceOver 人工走查、系统文件选择器系统进程点选、大章入口及联合集成仍独立跟踪。
入口：`docs/WP13-APPLE-REVIEW.md`、`.github/workflows/wp13-apple.yml`。

### OPDS facets：声明子集通过

独立模块 0.2.0：`opds_feed_facets()` 暴露 OPDS1 facetGroup/activeFacet/thr:count，
OPDS2 facets/self/properties.numberOfItems，包含链接解析、分组/选择预算及失败清理。
既有公开 feed/link/entry 尺寸不变，数据借用至 feed_free。计数字面量仅支持十进制数字，
小数点/指数表示在当前 profile 中返回 format。
Linux/Windows 各 65/65 原场景、8 条消费者链及 facet 回归通过，Linux ASan/UBSan 通过。
Sanitizer 曾发现空 XML 文本的空指针零长度操作，已修复，失败运行保留。
独立只读审查未发现可确认的新增实质缺陷。

入口：`docs/WP15-OPDS.md`、`docs/validation/wp15-opds-facets.json`、`extras/opds/`、
`tests/opds/facet_test.c`、`.github/workflows/wp15-opds.yml`。
HTTPS 仍需宿主 transport；间接获取、借阅/支付/DRM/LCP 与宿主 UI 接入未完成。

## 3. 优先接手 Android 失败

截止时记录是运行中；停工后为回答用户估时，在 16:57 UTC 只读核对到最新 run 最终 failure。
失败作业 `119954971411`，最终步骤 `Final fail-closed acceptance` 失败。
最新工件 `12442877834`：`EXReader-WP13-Android`，149850865 B，未过期、同源码，
`sha256:05940079adbcf78f9335a385f4b346a066d77f0d60f8b3cd52591b1dc8e73e37`。
本次尚未重新解析该最新工件的逐项失败原因；不要把旧源的 4/10 写成最新源的实测数量。

旧源 `5a04a27bf518766e03f20f2679e31d77bb42d8ce` / run `39813713535` 的确切结果：
原 45/45，独立 review 4/10。六项失败涉及重复取消时陈旧 UI 对象、两项新副本取消的空源文件
观测、删除源后的打开失败提示，以及两项选择控件观测。49 页/49 native next/0 recovery
及跨 Activity 提交锁已在该旧源通过，不能拼入新候选授予验收。

最新 `ac7aecc` 只修复 per-case JSON 后缀 glob 混匹配：现在按 suite、顺序编号、完整 case ID
精确匹配，仍拒绝额外文件；它没有修复上述六项。旧驱动已修 Downloads 滚动、PDF 保存后
清除选择的断言、无界 am start -W 等待，900 秒预算与真实操作断言保留。

下一步先在云端读取最新固定工件/日志，逐项判断是宿主实现还是测试驱动问题。
重点核对 `sources()`/删除源的 shell 嵌套引号和 glob 是否真正执行；陈旧 UI 对象要重新获取
实际控件，选择相关等待必须核对真实页面就绪，不能降低非空/复制/持久化断言。

主要路径：`examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostReviewTest.java`、
`HostWalkthroughTest.java`、`examples/android/app/src/main/java/org/exreader/host/`、
`examples/android/app/src/main/cpp/exreader_host_jni.c`、`tools/android_host_evidence.py`、
`tools/check_android_host.py`、`tests/android_host/check_evidence_gate.py`、
`docs/WP13-ANDROID-REVIEW.md`、`.github/workflows/wp13-android.yml`。
已有 `.github/workflows/wp13-android-diagnostics.yml` 可用于云内只读固定工件诊断；诊断不授予验收。

Android 接受条件：同次 45+10 用例零失败零跳过、49 页/49 native next/0 recovery、48 项门禁
正反例及严格 accepted=true；唯一 android-host 作业成功，工件同 run/source、非空、未过期、digest 有效。
范围仅 API34 x86_64 模拟器，不含真机/签名/TalkBack/全格式逐项验收。

云端只读入口：

```text
https://api.github.com/repos/NoGod3524/EXReader/actions/runs/39816104855
https://api.github.com/repos/NoGod3524/EXReader/actions/runs/39816104855/jobs?per_page=100
https://api.github.com/repos/NoGod3524/EXReader/actions/runs/39816104855/artifacts?per_page=100
```

## 4. 集成顺序与现有门禁

先修 Android 并独立通过，再完成候选的同源集成；互不依赖的准备工作可并行。
公共布局/PDF 写入层的改动应在集成分支串行处理，不覆盖其他包的修改。

现有联合协议是十组、28 个上游作业：native(7)、ocr(3)、corpus(1)、linux(1)、
windows_evidence(1)、windows_worker(1)、migration(3)、opds(2)、apple(8)、android(1)。
同一新集成 SHA 全部成功、必需工件齐全后，才运行 `parallel-integration.yml` 严格汇总。
门禁协议自身通过不能代替真实联合验收。

注意新核心能力与旧可选包的 SDK 保护基线：Android/OPDS 现有规则仍以
`a2552d7feb786cd2345d2b0b3eb894777b3254db` 为 SDK 不变基线。直接合入 AcroForm/CSS
会改变 src/include/CMake，不能删保护检查来变绿。应先独立验证并冻结新的 SDK 候选，
明确登记新基线及保持的公开兼容契约，再验证可选模块/宿主相对该候选没有额外改变 SDK。
原固定基线的交付证据保留，不能通过把基线随意设成当前 HEAD 自证未改。

原集成策略仍需保持：非 OPDS 包先集成，冻结前置祖先 H，最后处理 OPDS 所有权 HANDOFF=H。
Android 的 ANDROID_OWNERSHIP_HEAD 只固定宿主变更审计祖先，不能替代当前受测源码或绕过 SDK 保护。
新增 AcroForm/spacing 的专用检查也必须保留在最终候选验证中，不能只跑旧联合组便授予新能力通过。

旧八组联合验收绑定 `9e4b595ed7e10dcb2d78f5547e4e6a11a04ba3a1`，严格汇总 run `39718130711`；
十组门禁 21 项协议检查 run `39802485518` 只验证协议。详情见 `docs/PARALLEL-INTEGRATION.md`。
该文档中的旧 Apple/Android 失败候选并非最新；本文件的精确身份表优先用于当前交接。

## 5. 已闭合历史与剩余队列

冻结 SDK `635225fe6ceb7759a948a1d8cede0ab18ea1cee9` 的 run `39666440519` 已通过
98 作业、严格汇总、99 同源工件，四目标各 24 实际进程 CPU 小时。该记录只绑定冻结源码，
不转移给新核心改动或宿主包。见 `docs/validation/2026-10-22-reliability-cloud.json`、
`docs/RELIABILITY-HANDOFF.md` 第 6 节。
WP6 有界 EPUB 章阅读已在此前完成；剩余是各宿主接入口，勿据早期包 B 的未完成摘要重做引擎。

二十项队列见 `docs/WORK-QUEUE-2026-10-22.md`。本轮只推进 1/8/14/15/18，其他十五项未启动：
PDF 安全 redaction、认证/加密写回、JPX/JBIG2、Pattern、OutputIntent/色彩、透明组合外部差异、
CSS 百分比/overflow、OCR 文字层闭环、高保真转换、迁移宿主入口、可嵌入视图/有界大章宿主入口、
TTS、屏幕阅读器/真机、LCP/授权流、真实语料/最终集成。真实语料仍为 0/1710。

## 6. 模型分工与时间估计

上一轮实际累计启动 5 个 `gpt-6.1-sol` / High 子代理，最多 3 个同时加主代理，未启动 20 个并发代理。
子代理名称中的历史状态不能当作当前仍在工作；所有已停止。

最近向用户提出的分工建议是：关键集成、疑难核心缺陷及独立审查用 High；范围清晰的实现用 Medium；
简单文档/脚本用 Low；CI 查询和等待交给自动化。该建议尚未改变任何模型配置或创建后续任务。

此前给用户的粗估：本轮声明范围收尾约 6–10 小时，Android 修复/复验 3–6 小时，集成及同源
复验 2–4 小时；若连 WP9 的 30 独立 PDF 门槛也补齐，另约 1–2 天。它们是工作量估计，
不是云端运行完成时刻，也不覆盖其余十五项。最终同源验收依赖 Android 先通过。
