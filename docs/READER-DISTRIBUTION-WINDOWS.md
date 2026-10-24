# Windows 无构建路径的分发准备（J25）

本页记录 `codex/reader-distribution-windows` 分支上 Windows 归档分发准备的实际实现、实测结论、硬上限与未覆盖范围。固定实现起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，SDK 冻结 `9854061be331fe603a1822d9b2b36ee357154927`（3.40.0 / ABI 1）。本包只新增 `tools/reader_distribution_windows/**`、`tests/reader_distribution_windows/**`、`.github/workflows/reader-distribution-windows.yml`、本文件与 `docs/validation/reader-distribution-windows.json`；不改 `src/`、`include/`、`cmake/`、顶层 `CMakeLists.txt`、`tests/fixtures/`、`bindings/`、原生/可靠性工作流、产品 schema1 与既有 wire/anchor。

## 实测结论（不是设计假设）

发行构建**实际存在**构建机路径：安装前缀 262 个文件中，首轮扫描命中 **20 条**（12 条文本、8 条二进制），涉及 **27 个静态归档、919 个 `.debug$*` 段**。追查后定位到三个互不相同的面：

| 面 | 实例 | 载体 | 处置 |
| --- | --- | --- | --- |
| COFF 调试路径 | `lib/exreader/exr_vendor_aom.lib` 等 27 个归档中的 `.debug$S` 记录 `D:\a\EXReader\EXReader\build\...` | 编译器把命令行上的绝对源路径写进调试信息 | 外置编译参数 `/experimental:deterministic /pathmap:D:\a\EXReader\EXReader=exreader-src`（见下） |
| Windows 资源对象 | `exr_vendor_freetype.lib`、`exr_vendor_tiff.lib` 各 4 条命中 | freetype/libtiff 的 `.rc` 经 `CVTRES` 生成的对象自带 `.cwd D:\a\...` 与 `.res` 路径；**没有编译器开关能触及它** | 分发时按结构识别该成员并用真实 `lib.exe` 重建归档（见“结构化削减”） |
| 纯文本元数据 | `lib/pkgconfig/*.pc` 6 个文件 | 第三方 `install()` 把 `prefix=` 写成绝对构建路径 | 可逆、幂等、行数不变的重写为 `<path:键>` 并留审计 |

首轮（未处置）的原始阻断记录保留在 run `40129620869` 之前的多轮失败里；处置后同一源码的安装前缀扫描为 **0 命中**。

## 外置编译参数：先证明能力，再采用

`cl.exe` 对本参数有硬要求，工作流不猜：先用 4 组候选真实编译同一份控制源，再用扫描器判定哪个候选真的消除了构建根（`tools/reader_distribution_windows/probe_compile_flags.py`）：

| 候选 | 结果 |
| --- | --- |
| `/utf-8 /experimental:deterministic /pathmap:D:\a\EXReader\EXReader=exreader-src` | **0 命中（采用）** |
| `/utf-8 /experimental:deterministic /pathmap:D:/a/EXReader/EXReader=exreader-src` | 2 命中（正斜杠拼写不匹配命令行实际拼写） |
| `/utf-8 /experimental:deterministic /pathmap:D:\a\EXReader\EXReader=-` | 0 命中（备用形态） |
| `/utf-8`（无映射） | 8 命中 |

编译器自己给出前提：不加 `/experimental:deterministic` 时 `cl` 报 `D9007: '/pathmap:' requires '/experimental:deterministic'`（run 40128415245 日志）。采用后 27 个归档的调试路径变为 `exreader-src/build/...`，构建根消失。

**逐面证明**（`tools/reader_distribution_windows/build_path_controls.py` + `check_surfaces.py`，真实 MSVC 产物）：

| 具名结果 | 证明内容 |
| --- | --- |
| `coff-debug-control-records-absolute-path` | 绝对源路径 + `/Z7` 的目标文件确实在 `.debug$*` 里记录构建根 |
| `pathmap-parameter-clears-coff-surface` | 被采用的参数使同一控制源的目标文件 0 命中 |
| `file-macro-control-is-absolute` | 运行时 `__FILE__` 打印绝对源路径 |
| `file-macro-relative-spelling-preserved` | 裸文件名拼写时 `__FILE__` 就是 `path_surface.c` |
| `archive-member-names-audited` | 真实归档的成员名审计（含相对目录名），绝对/越界名一律记为阻断 |
| `archive-drective-absolute-detected` | `#pragma comment(lib, "<绝对路径>")` 在 `.drective` 中保留绝对路径，扫描器必须报出 |
| `control-surfaces-would-block-shipping` | 控制组整体被门判定为不可发布 |

**观察项**（不当作通过项）：把源文件写成裸文件名后，`/Z7` 目标文件**仍然**记录编译器工作目录（构建根），因此“相对拼写”不足以清除 COFF 面，只有路径映射可以；该观察以 `observations.relative_spelling_object_hits` 记录在 `surfaces.json`。

## 结构化削减（vendor 资源对象）

`reduce_archives.py` 只做“保留或移除”，不改字节：

1. 逐成员解析归档；成员若含 `.rsrc$01` 且没有 `.text` 段，判定为 Windows 资源对象；
2. 其余成员按原 **相对成员名** 落盘，从提取目录用真实 `lib.exe` 重建（参数超长时走 `@response`），链接成员与符号索引由工具重生成；
3. 审计：保留成员名 + 内容摘要与原件逐条相等；`dumpbin /symbols` 定义符号只允许少掉 `$R*`；重建结果重扫必须 0 命中；任一不符即整体失败；
4. 结果：2 个库、2 个成员被移除（freetype、libtiff 各一），调试段从 919 降到 917，`lib/exreader` 其余字节不变。

建议给 root 的源码级替代（本包不越界修改）：在 `cmake/deps.cmake` 里对 freetype/libtiff 目标剔除 `.rc` 源，或在 vendor 目标上把资源编译关掉；这样连削减步骤都不需要。

## 纯文本面

6 个 `.pc` 文件的绝对前缀被替换为 `<path:键>`；每个替换都记录原始字节（`occurrences`），因此可以用“token→原始字节”精确还原全文（`sha256_before` 必须复原一致），并同时证明幂等、行数不变。未识别后缀的文本面不会被偷偷改写，而是记为 `refused` 并阻断。

## 归档成员名不是“只有 basename”

真实 MSVC 归档会保存**相对目录**成员名（如 `_deps\freetype-build\CMakeFiles\freetype.dir\src\base\ftbase.c.obj`）：183 个成员名带分隔符。它们不含盘符、不以分隔符开头、不含 `..`，因此不构成构建机路径；门只把**绝对/越界**成员名当作阻断面（`member_names_escaping`），并把带相对目录的数量作为观测记录。

## 可重定位消费

封好的归档被解包到 **工作区之外** 的 `D:/relocated/exreader-<run>-<attempt>/prefix`，然后只用该前缀：

- C 消费者（`distribution-consumer-c.exe`）：读安装的示例字体与示例 EPUB，分页、渲染 720×1040、取文本，页数上限 3；
- C++ 消费者（`distribution-consumer-cpp.exe`）：只用安装头编译 C++17 翻译单元并调用 C ABI；
- 原生 probe（`relocation-probe.exe`，**从 `<prefix>/bin` 运行**）：`GetModuleFileNameW/EnumProcessModules/GetModuleFileNameExW` 报出自身模块路径并分类全部已加载模块，前缀外且非 `%SystemRoot%` 的模块即失败；同时用公开 ABI 打开示例出版物；
- 既有安装消费者 `tests/reading_core` 的 `reading-document`：跑原九格式 smoke（9/9 `passed`）、`tests/reading_release` 的身份消费者（版本/ABI 与安装头一致）；
- 导入闭包：4 个消费者 PE 共 16 个导入 DLL，全部是系统/API-set/CRT，无路径型导入；导出的 vendor 闭包 13 声明 = 13 安装，无缺项。

## 具名结果（run 40135232301，同源同 attempt）

必需 18 项：`source-identity-bound`、`archive-matches-stage`、`archive-tamper-evident`、`archive-content-scanned-clean`、`stage-scanned-clean`、`headers-config-licenses-hashed`、`sanitization-audited`、`resource-objects-removed`、`relocation-prefix-distinct`、`relocated-consumers-pass`、`nine-format-smoke-complete`、`installed-identity-matches-headers`、`dependency-closure-system-only`、`probe-prefix-bound`、`debug-sections-carry-no-build-root`、`no-absolute-drective`、`archive-member-names-relative`、`deterministic-seal` —— 全部 pass。

具名负例 4 项，全部 pass（都要求命令**失败**）：`negative-probe-rejects-foreign-prefix`、`negative-consumer-rejects-missing-book`、`negative-scan-blocks-leaking-control`、`negative-scan-blocks-absolute-drective`。

## 工件与身份

- 发行归档：`EXReader-reading-core-3.40.0-Windows-X64.zip`，8,766,490 字节，`sha256 e2a17ce585b5e6a7b906441df1a53d1ea3c6d7e887f5feb03c07f66bfae5e67e`，262 条目，stage digest `966c0d1aac93df5f4e2c059be181bb8b3fcba605376bffb539617ddab7cb0c9a`；同一 stage 二次封装摘要相同（`deterministic-seal`）。
- 分类摘要：header 30/314,066；config 13/43,653；license 25/142,790；library 33/22,163,445；doc 21/1,052,830；example 133/1,706,749；other 7/162,239。
- 上传工件：`reader-distribution-windows-40135232301-1` id 12576243461、15,278,092 字节、`sha256:3c1eaa93…04a7`、到期 2027-01-22T21:40:09Z；汇总工件 id 12575809265、1,376 字节、`sha256:c87367cc…aef1`。
- `aggregate` 作业用 `gh api` 重算工件 ZIP 摘要、解包后重算内层发行摘要与条目数，并核对 `source_sha`/run/attempt/全部具名结果；跨源、跨 attempt、过期或篡改一律失败。

## 硬上限

| 项 | 值 |
| --- | --- |
| 单文件扫描 | 256 MiB |
| 单文件命中 | 4096 条 |
| 可重写文本文件 | 8 MiB |
| 树内文件数 | 20000 |
| 归档解包总量 | 1 GiB |
| 归档条目 | 20000 |
| 归档成员 | 20000 |
| 封装时间戳 | 2000-01-01T00:00:00Z（`--epoch` 可改） |
| 消费者渲染页数 | 3 |
| lib.exe 参数长度 | 6,144 字符后转 `@response` |

## 操作教训（写进本文件，避免下次重踩）

- git-bash 会把 `/utf-8`、`/Fo…`、`/pathmap:…` 当成 POSIX 路径改写成 `C:/Program Files/Git/…`，并且 `link` 会解析到 coreutils 的 `link`。因此所有原生工具调用都放在 Python 里用参数列表执行（`build_path_controls.py`、`probe_compile_flags.py`、`reduce_archives.py`），只有 `cmake` 直接由 shell 调用。
- `/pathmap` 与 `/experimental:deterministic` 必须同时给。
- 归档成员名可能是相对目录名；判定“泄漏”要看是否绝对/越界，而不是看有没有分隔符。

## 未覆盖与边界

- 只准备 `reading-core` 发行形态；`reading-library`、共享兼容 DLL、音频/文本索引组件不在本包范围。
- 未给 Windows 生产宿主接线（root 负责）；未做正式签名、tag、Release、PR 合并。
- 九格式 smoke 不含 TIFF 专用夹具；TIFF 路径由“削减后重建 + 消费者链接 + 逐成员/符号审计”间接覆盖，未单独跑 TIFF 图像用例。
- 引擎源码不含 `__FILE__`/`assert`，因此这两条源码级泄漏路径只由控制组证明“可检出”，未在发行物中出现。
- 发行物仍保留 917 个调试段（路径为 `exreader-src/…`）；本包的要求是“无构建机路径”，不是“无调试信息”。
