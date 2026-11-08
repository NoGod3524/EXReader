# R candidate protected-tree changes

2026-11-07 — `codex/engine-malformed-triage-20261107` 触及受保护树 **src/**、**include/**、**tests/** 及 **CMakeLists.txt**：`src/formats.c` / `include/exr/formats.h` 增加显式严格 EPUB 结构校验 API；`tools/check_document.c` 通过 `--strict` 调用；默认阅读入口保持宽容。新增 mimetype、目录与本地头不符、容器缺失三组本地回归，并复核内容重定向、空文件 CRC、CLI 与原始 1,024 项配方。R 后续候选须包含本轮修改；定性、逐项结论和本地验收见 [REPORT.md](../malformed-triage-20261107/REPORT.md)。

| 工作包 | 受保护项 |
|---|---|
| V (#29) | include、cmake、CMakeLists.txt |
| P (#30) | CMakeLists.txt、.github/workflows/native.yml |

去重后四项：**include、cmake、CMakeLists.txt、.github/workflows/native.yml**。CMakeLists.txt 在 P 中只增加 windows_accessibility.inc 的 install 条目，保留已有 install、目标及版本字段。

R 候选必须取 #30 合并之后 ledger/base-20261103 的提交，并包含 provider 最终变更；不得使用 0dba1b85 或此前提交，也不得把旧候选的证据授予新树。本步不 refreeze、不跑完整矩阵。

Windows 打包正例必须来自实际安装后的 SDK 和实际生成的 exe。缺失 staged include 的负例记录实际退出码与 EXPECTED 完整路径；另验证缺 exe 会在创建输出目录前失败。

## 2026-11-05 — CSS 竖排属性别名修复

本轮新增受保护项 **src/**，具体文件 `src/style.c:357`（别名表及规范名归一化入口）。原因：真实日文竖排 EPUB《草枕》使用 `-epub-writing-mode`，原属性识别忽略了它，导致全书横排。修复仅增加六项属性名别名，不改布局、分页或字形逻辑。

与 V/P 去重后的 R 候选受保护项现为五项：**src、include、cmake、CMakeLists.txt、.github/workflows/native.yml**。本轮 `tests/test_vertical.c:273` 仅新增回归断言，不属于 `tests/fixtures/` 受保护树；夹具、字号、视口及书籍原包均未变。

R 必须取包含本次 `src/style.c` 修复及此前 V/P/provider 变更的后续候选提交，不能沿用旧 src 树的证据。本步未 refreeze、未跑全矩阵。数字、逐页像素回归与边界见 [CSS-ALIASES.md](../real-books-20261105/CSS-ALIASES.md)。

明确未做：`text-combine-upright` 的实际合字排版；其前缀名归一化不表示已有该能力。

2026-11-06 — `codex/cjk-kinsoku-20261106` 触及受保护树 **src/**：仅 `src/inline.c`，为 SP + U+FF1A/U+FF1B 共用软断行过滤并设置 GLUE（feed/display_scan 两入口）；不改变默认 Unicode 分析或硬换行。R 后续候选须包含此修复；本轮仅本地验收、未跑 CI，数字与逐页像素证据见 [REPORT.md](../cjk-kinsoku-20261106/REPORT.md)。

2026-11-06 — `codex/cjk-punctuation-compression-20261106` 触及受保护树 **src/**（仅 `src/inline.c`）与 **tests/fixtures/**（新增 `fonts/cjk-punctuation.ttf`、`fonts/latin-punctuation.ttf` 两个原创矩形字体）。相邻全角中文标点每处通过 advance 减少 0.5em；预断行、最终行、intrinsic/pending 测宽共用判定，跨行不压缩。R 后续候选须包含本轮源代码及夹具；数字、逐页哈希和本地全量测试见 [REPORT.md](../cjk-punctuation-compression-20261106/REPORT.md)。未手动触发 CI。

2026-11-06 — `codex/cjk-host-open-fix-20261106` 触及受保护树 **src/**，仅 `src/flow.c`：当前分页页尚无正文行或图片时，图片适配高度取整页可用高度与 `exr_flow_bottom(f) - f->y` 的较小值，避免 CSS 前置 margin 产生空白封面页；已有正文／图片后的换页行为保持原逻辑。宿主 `examples/reader.c` 的分页缓存增至 32 MiB，失败时始终显示实际状态及错误原文。`tests/test_page_cache.c` 新增三种布局回归，不触及夹具树。R 后续候选须包含此修复；本地验收数字与逐页像素证据见 [REPORT.md](../cjk-host-open-fix-20261106/REPORT.md)。未手动运行 CI，未取消 workflow run。

2026-11-06 — `codex/cjk-space-collapse-20261106` 触及受保护树 **src/**：`src/document.c` 在投影时按左右 Unicode 字符类别丢弃 CJK 间折叠空格；`src/document_internal.h` 声明共用内部判定；`src/chapter_index.c` 同步流式章节索引偏移，避免索引与窗口投影不一致而打不开正文。连续 ASCII 空白仍先折叠，任一侧为非 CJK 时保留一个空格。新增投影与分块索引／窗口单测；既有禁则用例改用按新规则仍保留的混合文本空格与 NBSP，保留边界／advance 断言。不改夹具、UI 样式或工作流。R 后续候选须包含上述三文件；六项本地验收与逐页像素证据见 [REPORT.md](../cjk-space-collapse-20261106/REPORT.md)。未手动运行 CI，未取消 workflow run。

2026-11-06 — `codex/cjk-justify-20261106` 触及受保护树 **src/**：`src/document.c` 补全中文标点空白折叠集合；`src/inline.c` 共用半 em 标点压缩、行首／行末占位及有上限的排版择行；`src/flow.c` 对 CJK 段落做字间两端对齐，跳过段末、标题、居中及单行段；`src/flow_internal.h` 保存段落 CJK 标志和流式 intrinsic 测量状态。R 后续候选须包含本轮源代码；未改公共 ABI、工作流、颜色、圆角、行高或缩进。九项本地验收与逐页哈希见 [REPORT.md](../cjk-justify-20261106/REPORT.md)。本分支包含前置 #62 空格折叠提交，未手动触发 CI、未取消 workflow run。

2026-11-07 — `codex/font-manager-20261107` 触及受保护树 **src/**、**include/**、**tests/**、**cmake/** 与 **CMakeLists.txt**：新增 `src/font_manager.c`、`src/font_scan.c`、`src/font_cache.c`、`src/font_manager_internal.h` 和 `include/exr/font_manager.h`，由 `include/exreader.h` 暴露；`src/font_internal.h`、`src/fonts.c`、`src/layout.c` 保存并传播管理器的宿主回退顺序；`cmake/modules.cmake` 增加 Windows 公共符号导出；`CMakeLists.txt` 注册四组本地 ctest 与公开 API 验收探针；`tests/` 增加原创建字夹具、生成／临时目录／计时脚本及回归用例。`tools/layers.json` 登记新源文件和头文件归属。公开 ABI 只增符号，epoch 保持 1，未修改 `examples/` 或 `.github/`。R 后续候选须包含本轮完整树；不得沿用此前 src/include/夹具树证据。审查、编译、四组测试、冷热启动与真实书结果见 [REPORT.md](../font-manager-20261107/REPORT.md)。本轮未手动触发 CI、未取消 workflow run。

本轮中断后续验收已重新执行：MinGW `-Wall -Wextra -Wpedantic -Werror` 强制重编通过；本地 ctest 173/173、静态 SDK 字体四组 4/4；500 文件五轮冷/热最大 1198.712/15.076 ms。增补缓存增删、配置破坏与嵌入字体合并回归；为Android未使用的静态环境变量辅助函数加平台条件。验收已在合入main #69的树上重新执行。真实书正式配置Noto Serif SC→Noto Sans CJK SC，28/28个有记录分卷的首行文字、源范围、行盒全部一致，0缺字；全书分页1073→1092，完整数字及SimSun补充配置见上述报告。

2026-11-07 — `codex/cjk-u3000-20261107` 触及受保护树 **src/**：`src/document.c` 将 U+3000／U+00A0 与 ASCII 空白共用折叠判定，U+3000 移出 CJK 字符集合；`src/document_internal.h` 声明共用空白函数；`src/chapter_index.c` 同步流式章节索引的投影偏移。混合连续空白先折叠，再按左右 CJK 字符决定删除或保留 U+0020；块首尾空白丢弃，缩进仍由 CSS text-indent 负责。R 后续候选须包含以上三文件；本地统计、页数、逐页哈希、全量测试和 DPI 感知截图见 [REPORT.md](../cjk-u3000-20261107/REPORT.md)。未手动触发 CI，未取消 workflow run。

2026-11-07 — `codex/engine-chapter-layout-20261107` 触及 **src/**、**include/**、**tests/** 与 **CMakeLists.txt**：引擎恢复同一 XHTML 文本节点内的章节标题／全角空格段落边界，章节与标题强制分页，标题和装饰线禁用 justify；增加可由 CSS 覆盖的 CJK 段落默认缩进，以及独立的页面／块语义查询 API。既有 `exr_page`、`exr_line`、配置记录 ABI 不变。`tests/fixtures/pager-golden.txt` 仅将 `layout-epub` 的一个跨 spine 页改为两个独立页，其余 88 页金样不变；两个既有窄行几何测试显式设零缩进。新增三组章节布局测试及真书 CLI 探针。不改 `examples/` 或 workflow，不手动运行 CI，不取消 workflow run。R 后续候选须包含本轮源代码及公共头文件；本地数字、19 本页数及像素哈希见 [REPORT.md](../engine-chapter-layout-20261107/REPORT.md)。
