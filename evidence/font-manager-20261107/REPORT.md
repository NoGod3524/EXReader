# Font manager — 2026-11-07

发现、索引、选择、引擎接入四项实现完成。沿用中断时的 22 项工作树改动，本次补充回归、实测和交付证据，并合入 main 的 #69；同时给 Android 不使用的 env_copy 辅助函数加两行平台条件，避免未使用函数警告。原实现快照位于本地 `build/font-manager-original/`；三份实现、内部头、公开头共保留该快照约 94.2% 的最终行，见 [REUSE.json](REUSE.json)。

## API 与实现

公开 API 在 [font_manager.h](../../include/exr/font_manager.h)，共 213 行、12 个新符号：

- `create(options)` / `open(config)` / `free`：目录和单文件发现、创建后只读、UTF-8 路径；配置相对路径以配置文件目录为基准。
- `summary_get` / `skip` / `face_count` / `face` / `has_family` / `face_covers`：族、样式、脚本、逐文件原因及 cmap 覆盖可查询。
- `chain` / `pick`：请求族 → 同族其他样式 → 配置回退族 → 衬线默认 → 无衬线默认。`pick` 返回实际 face、步骤、链位置；无覆盖为 `SIZE_MAX` / `EXR_FONT_STEP_NONE`。
- `create_font`：把同一条链装载为 `exr_font`，返回引擎 face 到 manager face 的映射。layout/pager 的缺字标志为 `EXR_GLYPH_MISSING`。

头文件说明借用字符串、所有权、释放函数、失败返回和清空输出行为。管理器可并发查询；生成的 `exr_font` 遵守现有每个布局 worker 独立使用的规则。字体文件在索引后变更/删除时装载会省略它，返回映射仅包含成功装载的 face；全部不可用时明确返回 `EXR_FONT`。

| 实现 | 行数 | 职责 |
|---|---:|---|
| [src/font_manager.c](../../src/font_manager.c) | 559 | 配置、索引汇总、缓存复用、统一回退链、pick、装载 |
| [src/font_scan.c](../../src/font_scan.c) | 485 | 平台目录、递归发现、FreeType 元数据/Unicode cmap |
| [src/font_cache.c](../../src/font_cache.c) | 169 | 版本/FreeType 版本/校验和、大小+mtime 失效、原子替换 |
| [src/font_manager_internal.h](../../src/font_manager_internal.h) | 67 | 内部索引记录与平台接口 |

示例配置在 [fonts.conf](../../tests/fixtures/font_manager/fonts.conf)，宿主调用和限制见 [FONT_MANAGER.md](../../docs/FONT_MANAGER.md)。宿主通过 `open` + `create_font("serif", ...)` 把字体交给现有布局/分页接口。嵌入字体保持 CSS 优先级；宿主链在嵌入字体合并后仍保持顺序。未修改宿主。

ABI 仅增加符号，既有公开结构及 `exr_font_open` 语义不变；改变的是私有 opaque `exr_font` 的内部顺序标志。ABI epoch 仍为 1，现有 `native-abi` 通过。Windows `.def` 含全部 12 个新导出；共享库和静态组件均实际链接并执行新 API。使用现有 FreeType 和平台文件 API，没有新增第三方运行时依赖。

## 本地测试

MinGW-W64 x86_64 UCRT POSIX GCC **16.2.0**，Release。强制更新时间戳重编 `font_manager.c`、`font_scan.c`、`font_cache.c`、`fonts.c`、`layout.c` 和探针；实际命令均含 **`-Wall -Wextra -Wpedantic -Werror`**，退出 0。初次强制重编见 [BUILD-MinGW.log](BUILD-MinGW.log)、[BUILD-probe.log](BUILD-probe.log)、[BUILD-tests.log](BUILD-tests.log)；合并上游后重编见 [BUILD-merged.log](BUILD-merged.log)，最终平台条件修正重编见 [BUILD-final.log](BUILD-final.log)。

| ctest 组 | 结果 | 断言 | 覆盖 |
|---|---|---:|---|
| discovery | 通过 | 54 | 临时目录三字体计数、UTF-8 子目录、族/样式/脚本/本地化别名、单文件、TTC 双 face、非字体/损坏文件记录、必需/可选缺目录、空目录 |
| selection | 通过 | 89 | Latin/CJK/无覆盖、同族其他样式、粗体/斜体、配置回退、默认衬线/无衬线、generic、40 份重复安装不挤占链 |
| cache | 通过 | 142 | 冷/热一致、mtime/size 变化、缓存截断/校验和/版本破坏、文件增删、不能写缓存仍返回可用管理器 |
| integration | 通过 | 96 | 4 线程 × 2000 查询、整文档与 pager/render、逐 glyph 映射与缺字标志、嵌入字体优先且宿主链不乱、文件变更/删除、错误配置 |

[FONT-TESTS.log](FONT-TESTS.log) 保留完整命令和断言数。共享库配置全量 **173/173**，由 169 增加 4，耗时 **109.26 秒**，见 [CTEST.log](CTEST.log)。关闭共享兼容库的静态 SDK 四组 **4/4**，见 [STATIC-TESTS.log](STATIC-TESTS.log)、[BUILD-static-final.log](BUILD-static-final.log)；合并重编见 [BUILD-static-merged.log](BUILD-static-merged.log)。

编译符号/头依赖检查：110 对象、1220 符号引用、0 新增逆向依赖、0 逆向 include，见 [LAYERS.txt](LAYERS.txt)。

## 500 文件冷/热实测

Windows 11 10.0.26200；Intel64 Family 6 Model 189，8 逻辑 CPU。500 个目录项循环使用真实 Arial TTF、SimSun TTC、Noto Sans CJK SC OTF，**667 faces / 4 families / 5,962,134,580 逻辑字节**。先复制三个源字体到工作目录，再为 500 项建本地硬链接，避免复制约 6 GB 数据；每个文件仍独立经过 FreeType 解析。Windows Fonts 内原始文件不允许直接建硬链接，首次准备错误保留在 [BENCHMARK-setup-attempt.txt](BENCHMARK-setup-attempt.txt)。

每轮删除索引缓存后启动新进程测冷，再启动新进程测热；共五轮。时间为管理器内部墙钟，包括目录枚举、解析/缓存读写，不包括进程启动与夹具准备。冷表示没有字体索引缓存，未清操作系统文件缓存。

| 轮次 | 冷 ms | 热 ms |
|---|---:|---:|
| 1 | 1137.157 | 13.015 |
| 2 | 1085.152 | 15.022 |
| 3 | 1198.712 | 15.076 |
| 4 | 1167.579 | 13.479 |
| 5 | 1180.800 | 13.550 |
| 中位数 | **1167.579** | **13.550** |
| 最大值 | **1198.712** | **15.076** |

五轮全部满足 **1500 / 150 ms** 预算；每轮冷 500 文件解析、热 **0 解析 / 500 缓存**。原始结果见 [BENCHMARK.json](BENCHMARK.json)。

本机 `C:/Windows/Fonts` 有 541 个文件；另实跑平台目录发现，得到 339 可用字体文件 / 362 faces / 190 族，205 条跳过记录（含非字体/不可用项/可选目录）。349 个字体候选文件冷解析 **1006.844 ms**；热恢复 349 文件、0 解析、**7.510 ms**，见 [PLATFORM-cold.jsonl](PLATFORM-cold.jsonl)、[PLATFORM-hot.jsonl](PLATFORM-hot.jsonl)。

## 真实书与破坏性用例

未改原《紅樓夢》EPUB，完整遍历 31 parts。正式配置正文 `serif = Noto Serif SC`，回退 `Noto Serif SC → Noto Sans CJK SC`；映射显示顺序为上述两族。使用本机已有的 Noto Serif SC 可变字体，默认 weight 200。两次实测都用同一探针、现有分页实现和 **612×624 / margin 0 / 18px / line 1.6 / paragraph 14.4**，关闭嵌入字体，横排、CSS `serif`。基线走既有 `exr_font_open(Reader.otf)`，新路径走管理器。

- 原 Noto Sans：**1073 页、0 缺字**；[BASELINE-book.jsonl](BASELINE-book.jsonl)、[截图](BASELINE-page.png)。
- 管理器 Noto Serif SC：**1092 页、0 缺字**；[NOTOSERIF-book.jsonl](NOTOSERIF-book.jsonl)、[截图](NOTOSERIF-page.png)。本书文字由首选衬线覆盖；第二回退族的实际出场由缺字夹具验证。
- **28/28 个有首行记录的分卷：首行文字、源范围及行盒均完全一致**。沿用既有排版验收参考页 **part 15 / page 0**，首行 31 个码点、源范围 **[0,93]**、行盒 **[27,27,576,27]** 一致，文字为“接著林之孝家的同著几個老婆子來，生恐有正事呼喚，二者恐丫鬟們年”。基线与衬线截图已目视核对，自动复核断言覆盖全部 28 个首行。
- **全书分页仍有变化：1073→1092 页**。没有修改布局参数；其他字形的度量与组合会影响后续分行，因此首行一致不能推广为全书每行、每页不变。完整比较见 [BOOK-COMPARISON.json](BOOK-COMPARISON.json)。
- 补充 SimSun 配置为 **1023 页、0 缺字**；28 个有记录的分卷中 18 个首行文字/源范围一致，参考首行行盒高 27→25.2 px。见 [SIMSUN-COMPARISON.json](SIMSUN-COMPARISON.json)、[SERIF-book.jsonl](SERIF-book.jsonl)、[截图](SERIF-page.png)。正式验收采用上述首行度量相同的 Noto Serif SC。

把必需目录设为不存在的 `absent-required-fonts`：**进程退出 1 / EXR_IO(3)**，错误原文包含路径，见 [MISSING-error.txt](MISSING-error.txt)、[MISSING-exit.txt](MISSING-exit.txt)。未静默使用随包字体。损坏 `.ttf` 不崩溃且可枚举原因；缓存破坏和索引后字体消失均有上述回归。

## 复现与树登记

最终验收基于合并 main #69 后的树；初次验收数字保存在提交 15843084 的历史中。所有输入、源文件和二进制 SHA-256、验收基准提交及 CMake 功能开关见 [PROVENANCE.json](PROVENANCE.json)。完整字体/书籍与构建输出留在本机，未入库。`REAL-BOOK.conf` 路径相对于本轮 acceptance 工作目录，实际调用配置为 `noto-serif.conf`；原创建字夹具的正常测试不依赖系统字体或 fontTools。

```powershell
$fontBuild = 'C:/Users/Oscar/Documents/Codex/fontmgr-20261107/build'
ctest --test-dir $fontBuild --output-on-failure -j 4
ctest --test-dir $fontBuild -R native-font-manager -V
python tools/check_layers.py $fontBuild
python tests/benchmark_font_manager.py "$fontBuild/exreader-font-manager-probe.exe" tests/fixtures/font_manager build/font-manager-new-benchmark --fonts build/font-manager-acceptance/sources/arial.ttf build/font-manager-acceptance/sources/simsun.ttc build/font-manager-acceptance/sources/Reader.otf --hardlinks
& "$fontBuild/exreader-font-manager-probe.exe" build/font-manager-acceptance/noto-serif.conf C:/Users/Oscar/Documents/Codex/exr-cjk-corpus/hongloumeng-24264.epub - build/font-manager-new-page.png
python evidence/font-manager-20261107/verify.py $fontBuild C:/Users/Oscar/Documents/Codex/exr-cjk-corpus/hongloumeng-24264.epub build/font-manager-acceptance
```

受保护源/头/测试夹具与必要构建清单变更已登记到 [R-PROTECTED-TREES.md](../ci-packaging-20261103/R-PROTECTED-TREES.md)。`examples/`、`.github/` 没有本分支改动。未手动触发 CI、未取消 workflow run。步骤记录逐步追加到 [FONT-OUT3.txt](../../FONT-OUT3.txt)。
