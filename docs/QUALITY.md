## 编译器诊断与覆盖测量 · 2026-11-08

本轮采用 **路线 C**，被测源码为 `db9bab668ac725a75f3f92919edec3625879c7a8`。**这是静态分析结果，不等同于运行时检查的结论。** 产品源码未修改。

**路线证据。** 本机是 Windows x64、MinGW GCC 16.2.0。使用包含 `int x = 0x7fffffff; x += 1;` 的[探针](../tools/quality/overflow_probe.c)执行：

```text
gcc -fsanitize=undefined -fno-sanitize-recover=all -g -O1 tools/quality/overflow_probe.c -o evidence/quality-20261108/local/overflow_probe.exe
ld.exe: cannot find -lubsan: No such file or directory
collect2.exe: error: ld returned 1 exit status
compile_exit=1

wsl -l -v
The Windows Subsystem for Linux is not installed.
wsl_exit=1
```

探针未能链接，因此未运行，也未得到 `signed integer overflow` 运行时输出；WSL 未安装，按任务分支转静态分析。[完整命令与原始输出](../evidence/quality-20261108/route.txt)。UBSan 执行数为 0，UBSan 诊断数为 **N/A**。

**静态诊断。** [分析器脚本](../tools/quality/analyze.py)从本轮 CMake `compile_commands.json` 取真实宏、头文件路径及标准，逐个执行 `gcc … -O0 -fanalyzer -Wno-error -fdiagnostics-format=sarif-stderr -c`。覆盖全部 **111/111 个 `src/*.c`**，并额外分析 FreeType **43**、Expat **5**、miniz **4** 个 C 编译单元；163 次 C 编译均成功。GCC 16 不支持旧 `-fdiagnostics-format=json`，故使用 SARIF；Expat 的 `.rc` 资源编译不计入 C 分析规模。

统计口径为最终 SARIF 发出的告警记录，同一位置的不同分析路径分别计数：**79 条、63 个源位置**。其中项目来源原始 34 条，4 条移入疑似误报；第三方 45 条中 FreeType 28、Expat 10、miniz 7。

| 类别 | 项目代码（待核查） | 第三方库（待核查） | 疑似误报 | 合计 | 样例（文件:行号） |
|---|---:|---:|---:|---:|---|
| 未初始化值 `-Wanalyzer-use-of-uninitialized-value` | 20 | 15 | 1 | 36 | `src/bidi.c:341`；Expat `siphash.h:220` |
| 空指针解引用 `-Wanalyzer-null-dereference` | 6 | 28 | 2 | 36 | `src/font_svg.c:1043`；FreeType `ftstream.c:787` |
| 内存泄漏 `-Wanalyzer-malloc-leak` | 3 | 0 | 1 | 4 | `src/fonts.c:74` |
| 空参数 `-Wanalyzer-null-argument` | 1 | 1 | 0 | 2 | `src/cfi.c:5`；FreeType `ftrfork.c:887` |
| 无限循环 `-Wanalyzer-infinite-loop` | 0 | 1 | 0 | 1 | miniz `miniz_tinfl.c:398` |
| **总计** | **30** | **45** | **4** | **79** | |

四条疑似误报仍保留原始告警：`construct.c:198` 的两条路径先假设资源数不大于 1、跳过初始化，再进入要求资源数大于 1 的遍历；`chapter_window.c:534` 的路径在预算失败设置非零错误后又假设错误为零；`toc_page.c:179` 的路径同时假设 `realloc` 成功搬迁与新指针为空。理由和定位见[逐条分类](../evidence/quality-20261108/diagnostics.json)。

每条诊断记录文件、行号、消息、静态路径涉及的函数、触发编译单元和原始 SARIF 索引；完整事件顺序与嵌套层级保存在 `analyzer-NNN.json.gz`。例如 `cfi.c:5` 的路径涉及 `exr_document_cfi_create_quoted → exr_cfi_create_for_part → exr_document_cfi_path_create_quoted → put`。这里的触发来源是编译命令，没有对应的运行时触发用例或运行时调用栈。复核入口：[实际命令](../evidence/quality-20261108/analyzer-commands.json)、[逐编译单元结果](../evidence/quality-20261108/analyzer-results.json.gz)。

**覆盖率构建。** 使用 `-g -O1 --coverage -fprofile-update=atomic`，链接也带 `--coverage`；没有启用 UBSan。沿用真书基线的功能组合，所有 SDK 层、测试及工具均构建；ICC、WebP/TIFF/AVIF、MP3/AAC、PDF crypto、JNI 和 fuzz 目标关闭，PDF JPX 开启。[完整构建配置](../evidence/quality-20261108/build-config.txt)、[初始配置命令](../evidence/quality-20261108/configure-command.json)、[最终构建输出](../evidence/quality-20261108/build-final.txt)。

`-O1` 构建另发出两条普通编译警告，**不计入上述 79 条 `-fanalyzer` 记录**：

| 类别 | 计数 | 样例 | 分类理由 |
|---|---:|---|---|
| `-Wformat-truncation` | 1 | `src/cbz.c:231` | 疑似误报：帧数上限为 4096，`#` 加帧号及结尾零小于额外分配的 24 字节。 |
| `-Wmaybe-uninitialized` | 1 | `src/flac.c:128` | 疑似误报：`coded_number` 返回成功的分支都写入 `n`，失败即返回；`bad` 返回 0。 |

初次构建因项目 `-Werror` 失败。仅在本轮构建参数加 `-Wno-error=format-truncation -Wno-error=maybe-uninitialized`，保留警告后完成构建；失败尝试与重试均保留。连同普通构建警告，总记录为 **81 条：项目待核查 30、第三方待核查 45、疑似误报 6**。

**执行规模。** 以下均为本轮新构建的实际执行结果，合并统计见 [measurements.json](../evidence/quality-20261108/measurements.json)。

| 工作负载 | 执行规模 | 结果与证据 |
|---|---|---|
| 全部注册 ctest | **205/205**；串行 1,094.75 秒 | **0 失败、0 跳过**；[控制台](../evidence/quality-20261108/ctest.txt)、[JUnit](../evidence/quality-20261108/ctest.xml)、[完整用例清单](../evidence/quality-20261108/ctest-inventory.json) |
| 真书逐页分页、渲染、哈希 | **19 本、11,484 页、8,648,640 字形计数**；373.22 秒 | 19/19 成功；页数、字形数、每页 RGBA 像素哈希均 **0 变化**；[逐页结果](../evidence/quality-20261108/realbooks.json.gz)、[差异报告](../evidence/quality-20261108/realbooks.diff.json) |
| 既有样本 | **1,884 文件清单；1,742 个输入直接执行；渲染 4,720 页** | 文档 1,583、图像 93、字体 61、数据库 2、音频 1、音频元数据 1、字体配置 1；[逐文件记录](../evidence/quality-20261108/fixtures.jsonl)、[补充类型记录](../evidence/quality-20261108/fixtures-extra.json) |

本轮根 CMake 注册 205 个测试；此前 211 用例证据另有六个 `windows-selection-*` 条目，当前根 CMake 未注册这些条目。未通过筛选排除任何已注册测试。样本结果为：1,191 个文档完整完成、44 个图像成功解码、59 个字体成功打开、3 个音频/配置输入成功处理、445 个输入由 SDK 拒绝；拒绝状态逐条登记，没有把拒绝等同于成功。驱动无崩溃、无 60 秒超时、无页数上限。另 142 个 oracle、原始像素、说明和测试数据仅登记身份，不计作独立执行输入。全部原件 SHA-256 校验不变。

真书沿用 `docs/ui/evidence/annotations/books-after.json` 的字体、布局和主机字体辅助函数，新编译桥接库链接本轮覆盖率 DLL；比较器判定条件可比，原基线未改。内容指纹为 `dcceb19c8ea43ba4db5ac57a7ea2b3bbbc127a105f3451490f2ffe2eff7f44fa`。普通测试输出**未发现** `runtime error:` 行；UBSan 诊断数仍为 N/A。

**覆盖率。** `gcov --json-format --stdout` 读取 **1,728 份对象/进程计数记录**，按源码文件与行号合并执行并集，避免同一源码在多个目标中被重复计入分母。覆盖统计包含 `src/*.c` 的 GCC 可执行行，不含第三方、头文件、测试代码和被配置关闭的宏分支。

- **总体行覆盖：31,737 / 33,840 = 93.79%。**
- **源文件执行：111 / 111。函数执行：2,281 / 2,354 = 96.90%，73 个函数未执行。**
- `exr_document_open`、`exr_publication_load`、`exr_pager_next`、`exr_render_page_color`、`exr_fixed_render` 和 `exr_font_open` 均有真实计数。逐个源文件、已执行/未执行行号、全部函数名称及执行状态见 [coverage.json](../evidence/quality-20261108/coverage.json)；[原始 gcov JSON](../evidence/quality-20261108/gcov-raw.jsonl.gz)与[每次命令/标准错误](../evidence/quality-20261108/gcov-commands.json)可复核数字。

| 关键文件 | 已执行 / 可执行行 | 行覆盖率 | 已执行 / 已编译函数 |
|---|---:|---:|---:|
| `src/pager.c` | 1,546 / 1,606 | **96.26%** | 73 / 74 |
| `src/layout.c` | 263 / 275 | **95.64%** | 25 / 25 |
| `src/raster.c` | 312 / 354 | **88.14%** | 16 / 18 |
| `src/fonts.c` | 228 / 240 | **95.00%** | 22 / 22 |
| `src/pdf_content.c` | 528 / 535 | **98.69%** | 35 / 35 |
| `src/formats.c` | 1,092 / 1,476 | **73.98%** | 63 / 86 |
| `src/chapter_reader.c` | 323 / 517 | **62.48%** | 30 / 45 |
| `src/audio_output.c` | 22 / 76 | **28.95%** | 7 / 9 |

`chapter_reader.c` 中 `exr_txt_pager_create`、`exr_txt_pager_create_private` 及其 TXT 回调共 15 个函数未执行，是本次覆盖的明确缺口。Windows 长路径限制使真书每个工作进程的两个 OpenJPEG 第三方 gcda 写入失败；补充样本的四个同类失败已缩短路径重跑成功。所有进程组的 **111 份项目源码 gcda 均齐全**，上述项目覆盖率不包含 OpenJPEG。原始采集错误保留，后续运行已采用更短的目录名。

[证据自检](../evidence/quality-20261108/verification.txt)通过，核验了源文件身份、诊断计数、全部 ctest、原样本哈希、19 本逐页哈希、覆盖分母和变更边界。[复跑命令](../evidence/quality-20261108/commands.txt)要求新的构建/计数目录，防止累积旧 gcda。

**边界与复核。** 只新增 `tools/quality/`、`evidence/quality-20261108/` 和本节。[源码及产物身份](../evidence/quality-20261108/provenance.json)记录 111 个 C 文件 SHA-256、四个受保护目录 Git tree、被测 DLL、字体和桥接库哈希。每步追加到 [QUAL-OUT.txt](../evidence/quality-20261108/QUAL-OUT.txt)。原书、二进制、字体副本、图片和 gcda/gcno 不入库。
