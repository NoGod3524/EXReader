# Windows 无构建路径的分发准备（J25）

本页记录 `codex/reader-distribution-windows` 上 Windows 归档分发准备的实际实现与实测结论。固定实现起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，SDK 冻结 `9854061be331fe603a1822d9b2b36ee357154927`（3.40.0 / ABI 1）。本包只改 `tools/reader_distribution_windows/**`、`tests/reader_distribution_windows/**`、`.github/workflows/reader-distribution-windows.yml`、本文件与 `docs/validation/reader-distribution-windows.json`；SDK 保护树、产品 schema1、wire v1、anchor v1/v2 均未改。

第三版（root 复审返修，受测源 `e41c29ab0e33db0a61bc82560db7d0a08c7fee3f`，run `40140884244`）修复了复审指出的三个真实缺口，前一版（`db7f13a` / run `40135232301`）的全绿记录与其之前各轮失败原样保留，作为历史证据。

## 复审缺口一：pkg-config 元数据必须是可重定位配置，而不是占位符

上一版把 6 份 `.pc` 的绝对 prefix 换成 `<path:键>`：字节层面干净，但搬迁后指向不存在的路径，属于“抹掉”而非“修好”。现在按文件自身位置计算相对表达式：

- `pc_metadata.expression_for()`：`lib/pkgconfig/x.pc` → `{pcfiledir}/../..`；
- 只替换**安装前缀本身**（正/反斜杠两种拼写、大小写不敏感、最长优先），库名、依赖、`Libs`/`Cflags`、安装布局一律不动；
- 每次替换记录原始字节（`occurrences[].matched`）与写入值（`replacement`），因此可**精确还原**原文并证明幂等、行数不变；
- 替换后立刻用完整模式集重扫该文件：只要还有构建机路径残留（例如指向安装树之外的 `_deps` 目录）就**拒绝**，不做静默改写；
- 审计项：`mode: "pcfiledir"`、`expression`、`prefix_variable`、逐 occurrence 的 `replacement` 必须一致。

实测（受测源 run `40140884244`）：6 份 `.pc` 全部 `pcfiledir` 模式、6 次替换、残留 0、拒绝 0。

## 复审缺口一：用真实 pkg-config 查询并真的编译链接一个组件

`check_pkgconfig.py` 在**解包后的搬迁前缀**上运行真实 `pkg-config`（choco `pkgconfiglite` 0.28，`C:\ProgramData\Chocolatey\bin\pkg-config.EXE`）：

1. 枚举搬迁前缀下全部 `.pc`（本次 6 份，要求数量 ≥ 净化阶段记录的数量，防漏项）；
2. 每份跑 `--exists`、`--variable=prefix`、`--cflags`、`--libs`（`--validate` 在 0.28 上不被支持，按 `unsupported` 记录而非当作失败）；
3. 结构断言：`prefix` 必须是**搬迁前缀内已存在**的目录；`-I`/`-L` 每个目录必须存在且位于搬迁前缀内；越界路径进 `outside_paths` 并整体失败；
4. 组件消费者：先用 `--cflags` 里的头目录编译**真实 API 调用**（`#include <webp/decode.h>` + `WebPGetDecoderVersion()`），再用 `--libs` 转换出的 `/LIBPATH:` + `libwebp.lib` 链接并运行；没有头文件时退回“从库归档里取真实外部符号 + `/INCLUDE:<symbol>` 强制引用”的方式。

实测：`packages 6、outside 0、failed 0、consumer libwebp:webp-api、library lib\libwebp.lib、libs -L<relocated>/prefix/lib -llibwebp、linked true、ran true、accepted true`。具名结果：`pkgconfig-metadata-relocatable`、`pkgconfig-consumer-links-installed-library`。

## 复审缺口二：解包上限必须在分配之前

旧 `read_zip()` 先 `archive.read(info)` 再累计总量，单项超额时分配已经发生。现在的顺序是：

1. **声明阶段（不读内容）**：条目数 ≤ 20000、单项声明大小 ≤ min(`limit`, `max_entry`)、累计声明大小 ≤ `limit`、容器文件本身 ≤ 2×`limit`；名称禁止反斜杠/绝对/`..`/目录项/加密位；大小写折叠后禁止重复或别名成员；
2. **流式阶段**：按 1 MiB 块读，边读边算 sha256 与 CRC32，实际字节不得超过声明；结束时实际长度必须等于声明长度、CRC 必须等于中央目录值；
3. 容器损坏（截断、缺中央目录）由 `BadZipFile` 统一转成拒绝。

具名负例（合成、**不使用巨型夹具**，声明超额的样本 < 4 KiB）：`zip-refuses-declared-oversize-before-reading`、`zip-refuses-declared-per-entry-oversize`、`zip-refuses-truncated-container`、`zip-refuses-tampered-content`、`zip-refuses-duplicate-members`、`zip-refuses-case-aliased-members`、`zip-accepts-honest-archive`，加上原有的越界/反斜杠/绝对/目录项拒绝。真实发行归档 262 条目仍完整通过（`archive-matches-stage`、`archive-tamper-evident`）。

## 复审缺口三：汇总必须要求全部具名结果

旧 `aggregate_artifacts.py` 只要求 `results` 非空且全 pass，删掉若干项仍可接受。现在复用单一契约：`verify_distribution.REQUIRED_RESULTS`（20 项）与 `verify_distribution.REQUIRED_NEGATIVES`（4 项）由校验器与汇总器共同引用：

- 缺项、重复、未知/替代名称、状态非 pass、`negative_cases` 列表与固定名单不一致 → 一律拒绝；
- 同源/run/attempt 绑定与真实 ZIP 摘要重算保持；
- 新增协议负例 `tests/reader_distribution_windows/check_aggregate.py`：删一项、重复一项、改名替换、置 fail、删负例、缩短负例名单、加未知负例、空列表、跨源、跨 attempt、改写 pkgconfig 结果名，共 12 个具名用例全部要求拒绝。

## 实测结论（不是设计假设）

安装前缀 262 个文件的首轮扫描命中 **20 条**（12 文本、8 二进制），27 个静态归档、919 个调试段，三个不同面：

| 面 | 实例 | 载体 | 处置 |
| --- | --- | --- | --- |
| COFF 调试路径 | 27 个归档的 `.debug$S` 记录 `D:\a\EXReader\EXReader\build\...` | 编译器把命令行上的绝对源路径写进调试信息 | 外置参数 `/experimental:deterministic /pathmap:D:\a\EXReader\EXReader=exreader-src` |
| Windows 资源对象 | `exr_vendor_freetype.lib`、`exr_vendor_tiff.lib` 各 4 条 | freetype/libtiff 的 `.rc` 经 `CVTRES` 生成的对象自带 `.cwd` 与 `.res` 路径，无编译器开关可及 | 按结构识别该成员、用真实 `lib.exe` 从相对成员名重建，逐成员/逐符号审计 |
| 纯文本元数据 | 6 份 `lib/pkgconfig/*.pc` | 第三方 `install()` 写入绝对 prefix | `pcfiledir` 相对表达式（本版修复，见上） |

外置参数先证明能力再采用：4 组候选真实编译同一控制源并扫描结果——`deterministic+pathmap（反斜杠拼写）` 0 命中（采用）、正斜杠拼写 2 命中、映射为 `-` 0 命中（备用）、无映射 8 命中；`cl` 自己报 `D9007: '/pathmap:' requires '/experimental:deterministic'`。

逐面具名证明：`coff-debug-control-records-absolute-path`、`pathmap-parameter-clears-coff-surface`、`file-macro-control-is-absolute`、`file-macro-relative-spelling-preserved`、`archive-member-names-audited`、`archive-drective-absolute-detected`、`control-surfaces-would-block-shipping`；观察项（不当作通过项）`relative_spelling_object_hits` 记录“裸文件名仍记录工作目录”。

## 结构化削减（vendor 资源对象）

`reduce_archives.py` 只做“保留或移除”，不改字节：成员含 `.rsrc$01` 且无 `.text` 段即判定为 Windows 资源对象；其余成员按原**相对成员名**落盘，从提取目录用真实 `lib.exe` 重建（参数超长走 `@response`），链接成员与符号索引由工具重生成；审计要求保留成员名与内容摘要逐条相等、`dumpbin /symbols` 定义符号只允许少掉 `$R*`、重建结果重扫 0 命中。本次 2 个库、2 个成员被移除，调试段 919→917。建议 root 在 `cmake/deps.cmake` 对这两个目标剔除 `.rc` 源，即可免去削减步骤（本包未越界修改）。

## 归档成员名不是“只有 basename”

真实 MSVC 归档保存**相对目录**成员名（`_deps\freetype-build\CMakeFiles\...\ftbase.c.obj`）：183 个成员名带分隔符。判定看是否**绝对/越界**（`member_names_escaping`=0 才放行），带相对目录只作观测记录。

## 可重定位消费

解包到**工作区之外** `D:/relocated/exreader-<run>-<attempt>/prefix`，只用该前缀：C 消费者（安装字体 + 示例 EPUB，分页/渲染 720×1040/取文本，≤3 页）、C++17 消费者（仅安装头 + C ABI）、原生 probe（**从 `<prefix>/bin` 运行**，枚举全部已加载模块，前缀外且非 `%SystemRoot%` 即失败）、既有 `tests/reading_core` 的 `reading-document` 跑原九格式 smoke（9/9）、`tests/reading_release` 身份消费者。导入闭包 16 个 DLL 全为系统/API-set/CRT、0 路径型导入；vendor 闭包 13 声明 = 13 安装。

## 具名结果（run 40140884244，同源同 attempt，共 24 项全 pass）

必需 20：`source-identity-bound`、`archive-matches-stage`、`archive-tamper-evident`、`archive-content-scanned-clean`、`stage-scanned-clean`、`headers-config-licenses-hashed`、`sanitization-audited`、`resource-objects-removed`、`relocation-prefix-distinct`、`relocated-consumers-pass`、`nine-format-smoke-complete`、`installed-identity-matches-headers`、`dependency-closure-system-only`、`probe-prefix-bound`、`pkgconfig-metadata-relocatable`、`pkgconfig-consumer-links-installed-library`、`debug-sections-carry-no-build-root`、`no-absolute-drective`、`archive-member-names-relative`、`deterministic-seal`。

具名负例 4（均要求失败）：`negative-probe-rejects-foreign-prefix`、`negative-consumer-rejects-missing-book`、`negative-scan-blocks-leaking-control`、`negative-scan-blocks-absolute-drective`。

## 工件与身份

- 发行归档：`EXReader-reading-core-3.40.0-Windows-X64.zip`，8,766,461 字节，`sha256 7ffe053de224b8ec2ceebf5825cc559b0b0974e5ad037493266fb27e9ce1be05`，262 条目，stage digest `38ecb5c8c73d8ab6cefb38853f884efb42b06c2e2360ba4fb2e749862c7b3852`；同 stage 二次封装摘要相同。
- 分类摘要：header 30 / config 13 / license 25 / library 33 / doc 21 / example 133 / other 7（字节数见验收 JSON）。
- 上传工件：`reader-distribution-windows-40140884244-1` id 12579131103、15,279,596 字节、`sha256:53d3eb85…569b`、到期 2027-01-22T22:59:59Z；汇总工件 id 12578238426、1,411 字节、`sha256:3a2f215d…0e6`。
- `aggregate` 作业用 `gh api` 重算工件 ZIP 摘要、解包后重算内层发行摘要与条目数，并按固定契约核对全部具名结果；跨源/跨 attempt/过期/篡改一律失败。

## 硬上限

| 项 | 值 |
| --- | --- |
| 单文件扫描 | 256 MiB |
| 单文件命中 | 4096 条 |
| 可重写文本文件 | 8 MiB |
| 树内文件数 | 20000 |
| 归档解包总量（声明与实测双检） | 1 GiB |
| 容器文件本身 | ≤ 2×解包上限 |
| 归档条目 / 归档成员 | 20000 / 20000 |
| lib.exe 参数长度 | 6,144 字符后转 `@response` |
| 封装时间戳 | 2000-01-01T00:00:00Z（`--epoch` 可改） |
| 消费者渲染页数 | 3 |

## 操作教训

- git-bash 会把 `/utf-8`、`/Fo…`、`/pathmap:…` 当 POSIX 路径改写，且 `link` 会解析到 coreutils 的 `link`；所有原生工具调用改在 Python 里用参数列表执行。
- `/pathmap` 必须与 `/experimental:deterministic` 同时给。
- 归档成员名可能是相对目录名，判“泄漏”要看绝对/越界。
- MSVC 的 `/c` 默认把 `.obj` 写到**当前目录**，探针必须显式 `/Fo`，否则链接会报 `LNK1181`。

## 未覆盖与边界

- 只准备 `reading-core` 发行形态；`reading-library`、共享兼容 DLL、音频/文本索引组件不在本包范围。
- 未给 Windows 生产宿主接线（root 负责）；未做正式签名、tag、Release、PR 合并。
- 九格式 smoke 不含 TIFF 专用夹具；TIFF 路径由“削减后重建 + 消费者链接 + 逐成员/符号审计”间接覆盖。
- 引擎源码不含 `__FILE__`/`assert`，这两条源码级泄漏路径只由控制组证明“可检出”。
- 发行物仍保留 917 个调试段（路径为 `exreader-src/…`）；要求是“无构建机路径”，不是“无调试信息”。
- `pkg-config` 组件消费者用 `libwebp` 的真实 API（头文件已随安装布局提供）；其他 5 份 `.pc` 只做变量/目录/存在性校验，未逐个编译。
