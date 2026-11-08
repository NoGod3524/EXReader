# 书架增强：元数据编辑 / 系列 / 标签 / 阅读统计

> 前置：`codex/host-shelf-flow-20261108` 尚未合入 main（main=db9bab66 时仍未合入）。
> 本分支在 `examples/windows/shell_shelfmeta.inc` 中实现了**最小书架**（网格/列表 + 点击打开）。
> **与 shelf-flow 分支会冲突，合并时以 shelf-flow 的书架为准**；本层只贡献覆盖元数据、系列、标签与统计。

## 代码

| 文件 | 作用 |
|---|---|
| `examples/windows/shell_shelfmeta.inc` | 书架覆盖层、编辑信息对话框、统计页、计时、`shelf.json` 读写 |
| `examples/windows/shell_shelfmeta_drive.inc` | 验收驱动动作（只注入时钟和前台标志；点击走生产命中表/对话框命令） |
| `examples/windows/check_shell_shelfmeta.inc` | ctest `windows-selection-shelfmeta`（宿主自检组） |
| `docs/ui/acceptance/check_shelfmeta.py` | 真实 HWND 验收 + DPI 感知截图（`ops/capture_window.py`） |
| `examples/windows/shell_annotations.inc` | `annot_identity` 抽成 `shell_content_identity(book_id)`：书架与标注共用同一个内容 SHA-256 |

## A) 元数据编辑
- 右键书 → 「打开 / 编辑信息」。对话框：标题、作者、系列名、系列序号、标签（逗号分隔，下方列表点选已有标签可增删）、更换封面…（图片文件）、移除封面。
- 显示优先级：`shelf.json` 覆盖 > 书库元数据（EPUB 取 OPF `dc:title`，否则导入时的文件名）> 「未命名 / 未知作者」。
  与书库值相同的字段存为 `null`（不复制、不冗余）。
- 封面：选中的图片被**复制**到 `%APPDATA%\EXReader\covers\<sha256>-<ms>.<ext>`，`shelf.json` 存相对路径；移除/替换后删除旧副本。**书籍文件从不改动**。
- 已知限制：当前书库导入不提取 OPF `dc:creator`（`books.author` 列为空），所以 19 本真书的作者回退显示为「未知作者」，直到用户编辑为止。这属于库层（`src/`），超出本任务的 `examples/` 范围。

## B) 系列与标签
- 同名系列聚合成一组，组内按 `series_index` 升序（序号相同时按标题），组间按系列名排序，无系列的书放在最后的「未分组」中。
- 顶部标签条：全部 N / 每个标签（带数量）/ 未分类 N。
- 视图切换：网格（封面墙，序号 · 标题 / 作者）与列表（缩略图、作者、进度条 + 进度%/已读页数/章节、标签）。所选视图存在 `shelf.json` 的 `view` 字段中。

## C) 阅读统计 — 计时规则
「在读」指以下条件**同时**满足：
1. 有书打开在阅读屏（`g.has_current && g.frame.valid`），并且书架/统计覆盖层是隐藏的；
2. 主窗口在前台（`WM_ACTIVATE` 跟踪；失焦立即结算并停止）；
3. 距离上一次**活动**不超过 **30 秒**（`SM_IDLE_MS`）。活动 = 打开书、翻页（`page_step`/页面落地）、滚轮。

计时由 1 秒 `WM_TIMER`（`sm_tick`）推进，每次只记 `min(now, last_activity+30s) - last_tick`。
因此静置时最多多记 30 s，之后计时停止；下一次翻页时恢复。打开书架、切换书、关闭窗口都会先结算再停止。
每 60 s、失焦、开书架和关闭时把脏数据写盘。

每册记录：`read_ms` 累计时长、`opens` 打开次数、`last_read_ms` 最后阅读时间、`page_turns` 已读页数（翻页次数）、
`page/page_count`（章内页/章内总页；流式 EPUB 的章节是惰性分页，总数未知时为 0）、`part/part_count` 章节、`progress` 进度。
统计页：累计时长、书架/已读本数、**连续阅读天数**（从今天往前数，连续每天都有 `read_ms>0` 的天数；今天还没读不打断连续天数）、今日阅读、单册排行（按时长）。

## D) 持久化
- `%APPDATA%\EXReader\shelf.json`（可以用环境变量 `EXREADER_SHELF_PATH` 重定向，验收和 ctest 用这个方式隔离）。
- 原子写入：写 `shelf.json.tmp` → `FlushFileBuffers` → `MoveFileExW(REPLACE_EXISTING|WRITE_THROUGH)`。
  失败时内存中的条目回滚到编辑前的副本，新复制的封面会被删除，对话框保持打开，原文件逐字节不变（ctest 与窗口验收都验证了这一点）。
- `version` 字段：读到比 `SM_VERSION`(=1) 新的版本或者无法解析的文件时，**不覆盖**，书架进入只读并给出提示。
- 书籍 id = 内容 SHA-256（与标注同一函数 `shell_content_identity`），不用路径。

### `shelf.json` 实际片段（来自 `run/shelf-sample.json` 与 `run/restart/restarted.shelf.json`）
```json
{"version":1,"books":[
{"sha256":"5a3b11c8f3ee4dd1c41d264aaf27dd83bb82faa1ebf3c7370a7072a0711cb3df","title":"芒果街上的小屋","author":"桑德拉·希斯内罗丝","series":null,"series_index":null,"tags":["小说"],"cover":null,"stats":{"read_ms":120000,"opens":1,"last_read_ms":1794157560000,"page_turns":12,"page":4,"page_count":0,"part":3,"part_count":4,"progress":0.7500}},
{"sha256":"c22402e02baa5e9b7c88c895a9f232f2858f7c168122aaf084493b85e37f6d58","title":null,"author":null,"series":"成长三部曲","series_index":3,"tags":["回忆录"],"cover":null,"stats":{"read_ms":120000,"opens":1,"last_read_ms":1794071040000,"page_turns":12,"page":7,"page_count":0,"part":4,"part_count":43,"progress":0.0930}}
],"days":[{"date":"2026-11-06","read_ms":120000},{"date":"2026-11-07","read_ms":120000},{"date":"2026-11-08","read_ms":120000}],"view":"grid"}
```
带封面的条目（重启后、移除之前）：`"cover":"covers/7f8a2a6c…357033-1794167236943.png"`。

| 字段 | 含义 |
|---|---|
| `version` | 文件格式版本，目前是 1；以后迁移时据此分支处理 |
| `books[].sha256` | 书籍内容 SHA-256，也是主键 |
| `title` / `author` | 用户覆盖值；`null` = 使用书库/OPF 值 |
| `series` / `series_index` | 系列名 / 序号（允许小数，比如 1.5）；`null` = 不属于任何系列 |
| `tags` | 标签数组（多对多；去重后最多 32 个） |
| `cover` | 相对于 shelf.json 目录的封面副本路径；`null` = 默认封面 |
| `stats.read_ms` | 累计在读毫秒数（按上面的规则） |
| `stats.opens` | 打开次数 |
| `stats.last_read_ms` | 最后阅读时间（Unix 毫秒） |
| `stats.page_turns` | 已读页数（翻页计数） |
| `stats.page`/`page_count` | 当前章内页 / 章内总页（未知时为 0） |
| `stats.part`/`part_count` | 当前章节 / 总章节数 |
| `stats.progress` | 进度 0–1 |
| `days[]` | 每个本地日期的阅读毫秒数，用于今日阅读和连续天数 |
| `view` | 上次使用的书架视图 `grid`/`list` |

## 验收结果（`run/result.json`）
命令：`python docs/ui/acceptance/check_shelfmeta.py out/EXReader.exe C:/Windows/Fonts/NotoSerifSC-VF.ttf docs/ui/evidence/shelfmeta/run`
（窗口客户区 1280×800 @96 DPI，生产 HWND，用 `ops/capture_window.py` 截图）

| # | 项 | 结果 |
|---|---|---|
| 1 | 3 本书编辑标题/作者/系列/标签 → 重启 | **3/3** 保留（`edit/edited.shelf.json` 与 `restart/restarted.shelf.json` 字段相同） |
| 2 | 3 本书换封面 → 重启 | **3/3** 解码尺寸与原图一致（300×450、320×480、280×420）；移除封面后 **3/3** 回到默认，`covers/` 下剩余 0 个文件 |
| 3 | 2 个系列 × 3 本 | 成长三部曲：Crying in H Mart(1)、Black Boy(2)、Born a Crime(3)；火的系列：Between the World and Me(1)、The Fire Next Time(2)、The Fire This Time(3)——插入顺序是打乱的 |
| 4 | 4 个标签筛选 | 经典 3/3、种族 3/3、回忆录 4/4、小说 2/2（实际/期望）；未分类 1；全部 9 |
| 5 | 3 本书 × 2 分钟（虚拟时钟，连续 3 天） | 每本 120000 ms，总计 360000 ms，打开次数各 1；`days`=11-06/07/08 各 120000；**连续 3 天**。ctest 另外覆盖 1→2→3 天，以及跳过一天后归 0 |
| 6 | 静置判定 | 翻页后静置 5 分钟：+30000 ms（只记 30 s 宽限）；再静置 5 分钟：+0；再翻页 +10 s：+10000；失焦后翻页 +60 s：+0 |
| 7 | shelf.json 片段 | 见上文 |
| 8 | 19 本真书回归 | 19/19 本，11296 页，8648640 字形；和同源基线 `evidence/perf-gate-20261107/realbooks-repeat.json` 相比：页数变化 0、字形数变化 0、页哈希变化 **0**，`content_fingerprint` 都是 `12b3b76f…e732`（`books-after.json`、`books-after.diff.json`）。本任务没有改 `src/`/`include/`。注意：`annotations/books-before.json`（11484 页）出自更早的库源码 c665d1c，不能作为同源基线 |
| 9 | ctest / 宿主自检 | ctest **212/212**（基线 211 + 新增 `windows-selection-shelfmeta`）；`--self-test` **26/26**（`selftest.json`） |
| 10 | 截图 | 网格 `edit/grid.png`、列表 `stats/list-progress.png`、编辑信息 `edit/edit-dialog.png` / `restart/edit-dialog-tags.png`、统计页 `stats/stats.png`；另有筛选 `restart/filter-*.png`、重启 `restart/restarted-grid.png`、移除封面后 `restart2/removed-restarted.png` |

### 静置判定的验证方法（第 6 项）
`run/idle/` 使用独立的 `idle-shelf.json`：冻结虚拟时钟 → 前台 → 打开 Black Boy → 翻一页 → `sm_clock|advance|300000`
（按每步 1 s 推进，每一步都调用和 1 s `WM_TIMER` 相同的 `sm_tick`）→ dump。也可以手动验证：
真实运行时翻一页后不再操作 5 分钟，打开「统计」，该书时长只会增加约 30 s。
