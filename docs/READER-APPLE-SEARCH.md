# Apple 原生书内查找

Mac、iPhone 与 iPad 的 SwiftUI 阅读页通过安装后的 `EXReaderSearch 0.1.0` 查找本书文字。搜索采用 F1 的 UTF-8 字面匹配，区分大小写；输入为 1–4096 字节，不接受 NUL。没有正则、OCR 或持久化全文索引。

## 所有权与批次

- F1 固定为已加固的模块树 `2e09cb2945564f25085074a816b95472392df205`；SDK 固定为 `9854061be331fe603a1822d9b2b36ee357154927`（3.40.0 / ABI 1），产品 schema 仍为 1。
- 每次串行 owner 队列调用在同一个实际 OS 线程上完成 `open → next(32) → 复制捕获 → result_free → close`。GCD 队列可能换线程，所以 F1 句柄不会跨批保留。
- UI 只保留当前 32 项；非空下一批替换当前列表。完成由 F1 `complete` 决定。恰好满批时，下一次空尾批保留最后 32 项并显示完成，命中仍可选择；首次零命中显示空列表。
- 跨批只传 F1 纯值游标与 Swift 值。游标绑定原件格式、SHA-256、字节数、SDK/文本投影版本、查询、模式和单元数。产品索引查询提供已验证的原件身份，不为每批重算全书哈希。
- 每批重新创建 pager，可能重复解析章节；此设计不授予线性分页或性能结论。

## 取消与定位

查询变化、取消、关闭或换书递增搜索代数，迟到结果被丢弃。F1 失败或取消不推进已成功批次的游标。扫描不调用渲染或进度写入接口。

阅读页不因弹出窗口内的键盘改变版面；键盘输入不触发底层阅读页重新分页。定位 UI 的判断依据是新位置上实际绘制的命中文字，而非会被后续页面尺寸更新覆盖的短暂状态文案。

点击结果后，宿主重新打开独立的 SDK library/文档实例，重新流式核对原件身份，再用复制的公开选择器解析。EPUB 校验精确 spine 序号和 part path；固定页要求精确且唯一的 page ID。只有公开解析结果为 `FOUND` 才分页、绘制并提交进度。丢失、歧义、身份变化或取消保留原阅读页面，不回退到旧字节偏移或页码提示。

重排选择器保存所有可空字段；固定页选择器按显式字节长度复制，保留 NUL。捕获属于 Swift 值，不接管 F1 的内存。进程重启只恢复查询文字与正常阅读进度，结果重新计算，游标和 SDK 指针不落盘。

## 单一 SDK 提供者

构建只显式链接安装后的 `libreader_search.a` 与现有动态 `libexreader.dylib`。它不跟随 F1 CMake 的传递依赖嵌入静态 SDK。原有产品 SQLite 唯一提供者检查保留，新增搜索对象、动态 SDK 依赖、未定义解析符号和禁止 SDK 实现符号检查。原生消费者还通过 `dladdr` 核对四个 SDK 符号来自同一动态映像。

## 云端检查

工作流为 [`reader-apple-search.yml`](../.github/workflows/reader-apple-search.yml)。本地只读写源码和 Git；构建、夹具生成、运行、语法检查和工件解包均在 Actions。

原生 11 项检查包括 32/32/6 批次、独立实例续查、查询/原件游标拒绝、取消重试、无命中且无状态写入、独立 FOUND、未解析保留进度、重复 EPUB spine、PDF 精确 page ID、真实 32 命中的空尾批/首次零命中以及单一 SDK 映像。保留原 catalog 8 项及实际 SDK mapping 16 项。

真实 UI 检查包括单结果选择、实际进程终止和重新计算、首次零命中保留页面、在真实 F1 取消轮询点取消，以及恰满 32 项后取空尾批、保留最后窗口并再次独立 FOUND 定位。32 次字面命中由云端夹具生成器预先写入实际 EPUB，预期文件在 SDK 读取前落成；应用通过正常导入和 F1 查找取得结果。三个目标均保留原始 xcresult、命名步骤和截图，严格收集器核对身份与精确附件集合。

## 实际受测源码与回归

最终 Search 受测源码为 `ae30466a4bd72b343b90f94008373b24d2086b6f`。搜索 run [40127300142](https://github.com/NoGod3524/EXReader/actions/runs/40127300142) attempt 1 的 7 个作业全部成功，严格汇总作业 `120973959131` 确认 `accepted=true`。三个目标各 4/4 用例、14 个命名步骤和 18 份原始附件；原生 search 11 项、原 catalog 8 项和 mapping 16 项全过。云端汇总实际下载六份生产者 ZIP，逐份核对 ID、字节数、SHA-256、有效期、源码、run/attempt 和报告，确认程序散列对应工件内真实可执行文件。

此前固定源 `b05498073d6e0a0189da60ae8481a8ee1aef26ab` 完成了 Search 原 3 场景及一次原回归。后续仅对 Search 空尾批作适用专项复验，两个源码分别记账：

| 源码 | 运行 | 状态 | 实际覆盖 |
| --- | --- | --- | --- |
| `ae30466a` | [Search 40127300142](https://github.com/NoGod3524/EXReader/actions/runs/40127300142) | 7/7 success | 原生 11+8+16；三个目标各 4 例 / 14 步骤 / 18 附件，包含真实 32 命中空尾批 |
| `b0549807` | [Search 40120637548](https://github.com/NoGod3524/EXReader/actions/runs/40120637548) | 7/7 success | 原生 10+8+16；三个目标各原 3 例 / 10 步骤 / 13 附件 |
| `b0549807` | [原 WP13 40121800002](https://github.com/NoGod3524/EXReader/actions/runs/40121800002) | 8/8 success | 三目标各原 13/13 / 67 步骤 / 50 附件；97 项门禁突变；package SDK 21 / model 18 / bounded 15 |
| `b0549807` | [原 shelf(full) 40121809402](https://github.com/NoGod3524/EXReader/actions/runs/40121809402) | 5 success / 1 failure / 1 skipped | native 8+16+22；Mac/iPhone 完成原书架、账户与生产语义；iPad 原 7 项执行过，但容器定位使收集失败，后两组未执行 |
| `b0549807` | [原 mapping 40121823546](https://github.com/NoGod3524/EXReader/actions/runs/40121823546) | 6/6 success | 三目标各原 5/5 / 22 步骤 / 14 附件；原生 catalog 8 与 mapping 16 |

每个运行保留自己的工件与身份，`b0549807` 的原回归不转移给 `ae30466a`。最终 root 共同源码仍需组合复验。完整 ID、散列和状态见 [`reader-apple-search.json`](validation/reader-apple-search.json)。

iPad 容器问题的只读诊断 [40126749435](https://github.com/NoGod3524/EXReader/actions/runs/40126749435) 在隔离分支 `codex/reader-apple-search-evidence` 上完成，始终 `diagnostic_only=true, accepted=false`。它认证原工件 `12573195290` 的 15,066,720 字节及 SHA-256 后，确认 always 布局 trace 步骤的后一次成功定位覆盖了 `container.json`：19:25:49 开始，Booted→Booted，四个 simctl 命令均 exit 0。首次失败的具体命令记录已丢失。后续共同工作流需为不同阶段保留独立报告；本包未修改或放宽原回归的证据门禁。

## 保留的失败与边界

- `9caa8820` / run `40118546762`：search 原生 10 项过，但独立 catalog 消费者因新的 SDK 类型返回值而编译失败；改为返回经过校验的身份字符串，保持独立构建。
- `a20738b4` / run `40119168327`：Mac/iPhone 各 3/3，iPad 在点中结果后等待短暂完成文案失败；后续使用实际新位置、命中文字与空错误验证定位，并让窗口内键盘不改变底层阅读版面。该轮取消 latch 可能停在 publication 打开阶段，不授予 `reader_search_next` 内取消。
- `d10a1c39` / run `40120046954`、`a166402a` / run `40120406632`：六个生产者作业全部过；严格汇总的自写 urllib 下载在重定向后收到 HTTP 401。最终源码复用现有 gh 下载助手，保留认证处理和明确的瞬时 HTTP 重试；断言、预算与期限未放宽。

`b0549807` 的空尾批显示问题已在 `ae30466a` 修复并通过三个目标的实际 UI 专项；没有反向翻批，仍只缓存最后一个 32 项窗口。

验收仍是声明的原生接口与三场景 UI；真机、性能预算、VoiceOver/焦点顺序和完整六平台阅读器由各自范围验收。
