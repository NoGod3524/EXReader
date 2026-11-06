# R candidate protected-tree changes

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
