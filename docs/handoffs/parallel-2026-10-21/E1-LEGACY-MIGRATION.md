# E1：WP12 旧数据迁移独立子包

你负责从旧阅读器真实数据格式迁移到当前C SDK书库。请直接实现并完成云端验收，不停在设计、伪数据转换或“入口预留”。先读同目录`README.md`的基线、执行约定、文件归属和拒绝条件。

## 起点与范围

- 分支：`codex/wp12-legacy-migration`；实现基线`a2552d7feb786cd2345d2b0b3eb894777b3254db`。
- 旧应用参考ref：`codex/reader-app`，固定提交`24a3e04b6fc456fa3fa68fa7bd6d9cc3b5c4e383`。只作旧格式/行为参考，按现有MIT SDK独立实现迁移，不搬入旧应用/vendor运行时。
- 已核实旧IndexedDB名称默认`exreader`、版本1，store为`books`、`files`、`notes`；notes有`bookId`索引。不得虚构并不存在的旧版本。
- 旧字段包含书籍UUID、原文件、标题/作者、标签/收藏/状态、progress/cfi/page/seconds，以及quote/note/value/page/seconds/rects/bookmark等标注信息。启动时逐字段追到实际读写点再冻结映射。
- 当前目标为`include/exr/library.h`、`document.h`、`layout.h`、`audio.h`公开接口；原书、进度、重排/固定页标注和音频位置分开处理，schema6不改。

交付一条真实可用链路：浏览器旧IndexedDB只读导出→自描述迁移包→独立迁移工具→当前SDK书库→重开核对。若旧Tauri另有实际独立格式，也先查清并声明覆盖；不把同一IndexedDB复制当成两种格式。

## 实现要求

1. 导出器真实读取旧store，保存原文件字节、旧ID、版本、字段和散列，不修改源数据。文档说明同源浏览器如何运行及导出。
2. 明确定义可版本化迁移包与清单，区分缺字段、未知字段、未知版本、缺原书、散列不符和不支持格式。未转换的信息进入可回读的迁移报告，不能静默丢掉。
3. 使用公开SDK导入、元数据、进度和标注接口；不得直接写私有SQLite表。旧ID到新ID映射可由包内侧车清单管理，不改变schema。
4. 迁移采用阶段库与可验证发布；取消、读/写失败、目标占用或发布失败时原目标库和源数据保持不变。已有目标库先用公开备份接口构建阶段库，明确独占/关闭要求。
5. 重跑同一包和中断后重试不重复生成书籍、标注或书签；明确同原书不同旧ID与同旧ID内容变化的冲突规则。不得仅按文件名/大小去重。
6. CFI、文字引用、固定页和音频位置使用对应坐标；页码一基/零基显式转换。百分比不能伪装成精确字符锚点；歧义或无法定位的标注保留原内容并标为未定位。
7. 逐本处理并释放，不整包常驻；沿用SDK的输入、存储和取消边界，超限如实拒绝。CLI输出清晰的成功/拒绝/失败及逐项JSON，不在默认包引入浏览器或迁移运行时。

## 文件所有权

可新增/修改：`extras/migration/**`、`tests/migration/**`、`tools/check_legacy_migration.py`、`.github/workflows/wp12-migration.yml`、`docs/WP12-LEGACY-MIGRATION.md`、`docs/validation/wp12-migration*.json`。

只读参考：旧分支`src/store.js`、`src/library.js`、`src/app-library.js`及实际备份入口；当前公开头、`tests/test_library_unique.c`、`test_progress_library.c`、`test_reanchor_library.c`、`test_page_annotations.c`、`test_audio_library.c`。不修改其他包文件或旧分支。

## 云端量化出口

- 至少30个具名场景，覆盖元数据、标签/收藏/状态、原文件字节、重排进度、CFI/歧义引用、固定页/音频位置、标注/书签、重复与冲突、取消、损坏包、未知版本、目标占用和发布回滚。
- 至少一条在云端浏览器中真实创建版本1 IndexedDB→导出→SDK迁移→新进程重开验证的端到端链路，不能用手写JSON替代导出器验收。
- 二次迁移后书籍/标注数量和ID映射稳定；故障注入后原库逻辑内容及原书散列不变，临时文件和阶段库有明确处置。
- Linux与Windows云端消费；组件裁剪时给出明确依赖。产物附程序/SDK/导出器/输入散列、逐case结果、内存计量及原始云端日志。
- 实际执行与未执行分列；任一必做项失败或未知，不标完成。

## 最终交付

提交本分支并推送触发专用云端CI；保留失败证据，不合并。回复提交SHA、文档/代码/证据路径、云端run与结果、字段映射表、原子性和幂等规则、精确未满足项。不要把“迁移工具完成”写成“完整WP12高保真转换完成”。
