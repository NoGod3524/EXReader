# 阅读状态：冻结SDK真实锚点与产品修订 v1 兼容性

本包回答一个前置问题：冻结SDK `9854061be331fe603a1822d9b2b36ee357154927`
真实捕获的阅读位置、书签和标注，能否用现有产品修订 wire v1 表达，并在另一独立
SDK书库安全恢复。起点 `210403d121d6484a8fff4ea7ffd911efa3163535`，分支
`codex/reader-reading-state`。

**结论：不能授予阅读状态同步完成。** v1 只能无损承载“非空引文”的高亮标注。
SDK 的每一种阅读进度、每一种书签和无文本固定页都是点选择器（`exact` 为空），
v1 一律拒绝；带章节作用域的重排选择器也没有 v1 字段。这需要 root 决定的
版本化扩展（下文最小方案），本包没有修改 wire 规则、revisions 模块或 schema1。

## 受测身份与云端结果

受测源码 `a403fee5f0cdb120840cd6fe0ef24e5fc2c0ce96` 的
[run 40055313938](https://github.com/NoGod3524/EXReader/actions/runs/40055313938)，
attempt 1，**3/3 成功**：

| 作业 | ID | 结果 |
| --- | --- | --- |
| ubuntu-22.04 | `120756903673` | 探针检查 121/121，24 个真实案例，接收端 FOUND 19、误定位 0、无 FOUND 写入 0，交换修订 14 |
| windows-2022 | `120756903961` | 同上；24 个案例与全部生命周期步骤逐字段与 Linux 相同 |
| 同 run 工件核对 | `120757666509` | 在 Actions 下载两份 ZIP，实际字节与 SHA-256 等于 API 记录，工件 head SHA、summary 身份、report 散列均绑定本源码／run／attempt |

| 工件 | ID | 字节 | digest |
| --- | --- | --- | --- |
| `reader-reading-state-Linux-40055313938-1` | `12545052072` | 10092312 | `sha256:08dc00185ca1ac055cd235fb0bcd672e59e2c83e6c87dd0234ae174bb932fef1` |
| `reader-reading-state-Windows-40055313938-1` | `12544859098` | 8168739 | `sha256:853a8c8a00d9467d9758af4f16cef7b5dd31cf28b299cc68697f1ad65e466a18` |
| `reader-reading-state-evidence-40055313938-1` | `12545440405` | 1659 | `sha256:4d99ea93e03e7703ca18419d31980686c5b30923e87236c460b93e3393fb2a1b` |

门禁：HEAD 等于 `GITHUB_SHA`；固定起点为祖先；SDK 八条冻结路径、schema1、
`apps/reader/{store,revisions,sync,commands}` 与 `READER-REVISION-WIRE.md` 自起点未变。
产品 catalog、revisions、SDK、适配层依次安装后，独立 C 与 C++ 消费者只用已安装包编译。
SQLite 3.54.0（source id `2026-10-09 15:46:58 be8d059e…`）由唯一产品 provider 提供：
Linux 链接图为 `libreader_catalog_sqlite.a(sqlite3.c.o)`，Windows 为
`reader_catalog_sqlite:sqlite3.c.obj`，同时满足 SDK 与产品调用，无系统 SQLite。
本机未构建、未测试、未下载工件；摘要取自作业日志与云端核对作业。
完整身份、散列与逐案字段见 [reader-reading-state.json](validation/reader-reading-state.json)。

### 同源原件与两个独立书库

原件全部在作业内由 `make_fixtures.py` 生成（只用标准库、ZIP 存储项），两平台字节相同：

| 角色 | 字节 | SHA-256 | A 库 ID | B 库 ID |
| --- | --- | --- | --- | --- |
| `book.txt` | 636 | `fcc117171436330ec0a2fa7ba24437593d77b30e96ba25cb2b9d8649ed0ac604` | 1 | 2 |
| `book-edited.txt` | 663 | `a3fd2777a0091020bd583a5e5c7bf8063f5bae2d43fba2114f8eb0fabf570ad8` | 2 | 3 |
| `book.epub` | 1913 | `99a21d3a73924d5b2efe4596076348b1eb7b00715ebc727737edd91f2f3bf50b` | 3 | 4 |
| `pages.pdf` | 1560 | `23f9dff3bc6bd85a19a9e24c6cb0390e17d7907af8c6b98c55273295386431ed` | 4 | 5 |
| `pages.cbz` | 43936 | `1fc44de12a387e0ff1df9fb10aa1a5cb17aca32ee6ee9aa85d0db848adc4b0f3` | 5 | 6 |

B 库先导入一本无关书，所以同一原件在两端的 SDK 本机 ID 不同。两端都用
`exr_library_blob` 读回并逐字节比较原件；两份 schema1 产品库各自以
`reader_catalog_attach` 把全局 `format:sha256` 映射到本机 ID，ID 从不进入 wire。
EPUB spine 为 `a.xhtml, b.xhtml, a.xhtml`；PDF 页 ID 为 `page-1..3`（第 3 页无文本，
提取 0 字节）；CBZ 页 ID 为 `001.png..003.png`。

### 逐案：SDK 捕获、v1 原样验证、接收端公开解析

“v1 原样”把真实捕获逐字段写入 v1（不做适配）交给未修改的验证器；
“v2 研究”是上文方案的字节，先被未修改的 v1 验证器以 `Unsupported anchor version`
拒收，再从字节解析后在 B 库解析。偏移为 UTF-8 字节。

| 案例 | 真实捕获 | 发送端 | v1 原样 | 适配层 | 接收端 | B 库 SDK 写入 |
| --- | --- | --- | --- | --- | --- | --- |
| TXT 开头高亮 | `0–27` 多字节 | FOUND | 通过 | OK | v1 FOUND `0–27` | `exr_library_note` |
| TXT 跨 4 字节表情 | `42–55` | FOUND | 通过 | OK | v1 FOUND `42–55` | note |
| TXT 结尾高亮 | `629–636`（文末） | FOUND | 通过 | OK | v1 FOUND | note |
| TXT 重复文字、上下文唯一 | `151–184` | FOUND | 通过 | OK | v1 FOUND | note |
| TXT 完全重复块 | `482–498` | AMBIGUOUS | 通过 | OK | AMBIGUOUS | 无 |
| TXT 字节中间偏移 | 捕获 `EXR_ARGUMENT` | — | — | — | — | 不取整，不捕获 |
| TXT 进度（多字节处） | 点 `48` | FOUND | `Empty revision field` | point | v2 研究 FOUND `48` | 活动阅读时不写；关闭后 `exr_library_progress` |
| TXT 进度文首／文末 | 点 `0`／`636` | FOUND | `Empty revision field` | point | v2 研究 FOUND | `exr_library_progress` |
| TXT 书签 | 点 `118` | FOUND | `Empty revision field` | point | v2 研究 FOUND | 空范围 note |
| 改版原件的真实引文 | `179–210` 取自 `book-edited.txt` | — | 通过 | OK | 强行放入原书：MISSING | 无；产品先按 `book_key` 拒绝路由 |
| EPUB 全文存储章节引文 | `172–196`，`chapter=b.xhtml`，prefix 0 | FOUND | **通过（静默丢失 chapter）** | chapter_scope | v2 研究 FOUND；去掉 chapter 本样本也 FOUND | 无 |
| EPUB 章内高亮 | part 1 `27–39` | FOUND | 通过 | OK | v1 FOUND | `exr_library_epub_note` |
| EPUB 章末高亮 | `159–169`（章末） | FOUND | 通过 | OK | v1 FOUND | epub note |
| EPUB 进度 | 点 `27` | FOUND | `Empty revision field` | point | v2 研究 FOUND | `exr_library_epub_progress` |
| EPUB 章首书签 | 点 `0` | FOUND | `Empty revision field` | point | v2 研究 FOUND | 无 SDK 点笔记 API，仅产品记录 |
| EPUB 重复 spine 路径 | `a.xhtml` `0–22` | FOUND | 通过 | OK | 路由拒绝（不解析） | 无 |
| PDF 页内高亮 | `page-1` `16–42` | FOUND | 通过 | OK | v1 FOUND | `exr_library_fixed_note` |
| PDF 重复行 | `page-2` `56–72` | AMBIGUOUS | 通过 | OK | AMBIGUOUS | 无 |
| PDF 书签 | `page-1` 点 `16` | FOUND | `Empty revision field` | point | v2 研究 FOUND | 空范围 fixed note |
| PDF 无文本页书签 | `page-3` `(0,0)`，全空 | FOUND | `Empty revision field` | textless_page | v2 研究 FOUND `(0,0)` | 空范围 fixed note |
| PDF 进度 | `page-2` 页首点 | FOUND | `Empty revision field` | point | v2 研究 FOUND | `exr_library_update` position=1 |
| CBZ 无文本页书签／进度 | `002.png` `(0,0)` | FOUND | `Empty revision field` | textless_page | v2 研究 FOUND | fixed note／position=1 |

v1 路径下，每个高亮还在发送端把解码后的记录重新解析，与原捕获的解析结果逐字段相同；
有界 EPUB 的 pager 捕获与 `exr_publication_load` 章文档捕获一致。所有 FOUND 都等于
发送端捕获范围；非 FOUND 时 SDK 笔记数不变。

### v1 高亮的产品修订生命周期（两端各一个产品库）

同一全局 `annotation_id` 的记录在 A/B 产品库间按原字节与 SHA-256 交换（共 14 份）：

| 步骤 | 产品选择 | SDK 动作（A／B） |
| --- | --- | --- |
| 新建；失败重试记固定 token；ack 后再投递同字节 | SAFE | 两端各建 1 条笔记；重投 `created=false`，不重入队 |
| 编辑 | SAFE | 两端更新为新文字 |
| 两端并发编辑并互换 | CONCURRENT | 两端都不写 SDK，各保留自己最后安全文字 |
| 合并 | SAFE | 两端更新为合并文字 |
| 删除墓碑 | SAFE(delete) | 两端删除各自笔记 |
| 删除后直接 put | BLOCKED_RESTORE | 不写 |
| restore 直接命名墓碑 | SAFE | 两端重建 |
| 离线三连改，最新先到 | PENDING_PARENTS ×2，最后 SAFE | 缺父期间不写；补齐后只应用最终头 |
| SDK 与产品都已提交后重启 | SAFE | 内存映射丢失，按范围+文字收养，再次收养不重复 |
| 向不存在的 SDK 书写入失败 | SAFE 不变 | 产品历史与 outbox 不受影响 |
| 产品已提交、SDK 步骤中断、重启后到达新文字 | SAFE | **新建第二条，旧笔记残留（已知缺口）** |

接收端 B 在全过程中的已存进度保持 `636`，远端注释不改变阅读位置。

## SDK 公开 API 的实际语义

以下取自冻结源码的公开实现，并由 Actions 中的真实捕获逐项复核（见结果表）。

| 公开 API | 捕获／解析语义 |
| --- | --- |
| `exr_anchor_create(doc,start,end)` | 两端须在 UTF-8 边界，否则 `EXR_ARGUMENT`，不取整；`exact` 为原文 `[start,end)`（≤64 KiB）；`prefix/suffix` 各 ≤32 标量／128 字节，截断在所在章节范围内；所在章节路径非空时填 `chapter`。空范围产生点：`exact=""`。 |
| `exr_anchor_resolve_ex` | `exact==NULL` 为 LEGACY；按 prefix/suffix 计分，平局为 AMBIGUOUS；永不使用旧偏移打破平局；只有 FOUND 给出范围。`chapter` 改变搜索作用域。 |
| `exr_pager_anchor_create/resolve` | 有界 EPUB 章内同一匹配器，偏移为章内规范化 UTF-8。 |
| `exr_fixed_anchor_create(page_id,text,start,end)` | `page_id` 必填；无文本页的快照为空串，只能捕获 `(0,0)`，`exact/prefix/suffix` 全空；字节长度保留内嵌 NUL。 |
| `exr_fixed_anchor_resolve` | `page_id` 不同即 MISSING，不跨页猜测；空文本页上的全空选择器为 FOUND `(0,0)`。 |
| `exr_library_progress` | 只接受点：`exact` 非 NULL 且为空、`start==end`。 |
| `exr_library_epub_progress` | 只接受点，另需 `part` 与包内 `path` 一致。 |
| `exr_library_epub_note` | 新建／改范围必须是非空引文，**有界 EPUB 没有点书签的 SDK 存储**。 |
| `exr_library_note` / `exr_library_fixed_note` | 允许空范围（点书签）；选择器由 SDK 从库内原件重新捕获。 |
| 固定页进度 | `exr_book.position` 为零基页号，经 `exr_library_update` 保存，没有选择器。 |

## wire v1 的相关条件（未改）

`progress/annotation` 的 `location` 为 `reflow_global`（selector）、`epub_chapter`
（`part_path`+selector）或 `fixed_page`（`page_id`+`page`+selector）。
selector 固定为 `exact/prefix/suffix/start/end`，`exact` 必须非空，未知字段拒绝，
`anchor_version` 必须为 1，字符串不得含 NUL。`start/end` 只是提示，不能代替引文解析。

## 兼容性决定

| SDK 捕获 | v1 | 原因 |
| --- | --- | --- |
| 重排非空引文，无 `chapter` | 可表达 | 字段一一对应，接收端以 `exr_anchor_resolve_ex` 解析 |
| EPUB 章内非空引文，`part_path` 在 spine 中唯一 | 可表达 | `chapter` 为空或等于 `part_path` |
| 固定页非空引文，无 NUL | 可表达 | `page_id` 为权威，页号提示不一致即拒绝 |
| 任一点（进度、书签） | **不可** | `exact` 为空，v1 拒绝 |
| 无文本固定页（CBZ、空 PDF 页） | **不可** | 只存在点 |
| 重排引文带 `chapter`（EPUB 全文存储） | **不可** | v1 `reflow_global` 无该字段；丢弃会改变解析作用域，可能把章首引文解析到别处 |
| EPUB `part_path` 在 spine 重复 | 发送可表达，接收**拒绝路由** | v1 只有路径，无法确定是哪一个 part |
| 固定页选择器含 NUL | **不可** | v1 拒绝 NUL |

被否决的绕行：

- 把点改成“相邻一个标量”的引文：位置是 `start` 还是 `end` 在文首／文末无法区分，
  空文档和无文本页根本没有标量，并且是对 v1 字段语义的暗中放宽。
- 只传 `start/end`：v1 明确它们不能代替引文；跨书库位置只能由 FOUND 授权。
- 丢弃 `chapter`：章首引文的空 prefix 在章节作用域得分，在全文作用域只在文首得分，
  另一处同 suffix 的文字可能因此变成唯一 FOUND，属于误定位。

## 最小版本化方案（待 root 协调，未实施）

1. 封装 `version` 保持 1，只在 `location.anchor_version` 引入 **2**。现有验证器对
   非 1 一律 `FORMAT "Unsupported anchor version"`，因此旧客户端整份拒收，不入库；
   之后引用它的 v1 子修订在旧端表现为缺父，`PENDING_PARENTS`，不会投影或定位。
2. v2 selector：`exact` 允许为空**当且仅当** `start==end`；并强制 `end-start` 等于
   `exact` 字节数（SDK 本身的条件）。无文本固定页为 `exact=prefix=suffix=""`、
   `start=end=0`，以 `page_id` 定位。
3. v2 `reflow_global` selector 增加必填 `chapter`（字符串或 null），原样承载 SDK 作用域。
4. v2 `epub_chapter` 增加必填 `part`（spine 序号），与 `part_path` 同时匹配才路由，
   对应 SDK `exr_epub_location` 的 part+path 要求，解决重复 spine。
5. 书签的产品表示：**annotation 实体，selector 为点**；`text` 为书签标签。
   高亮为非空引文。不新增实体类型或 SQL 表。进度在 v2 必须是点。
6. 旧记录：v1 原字节永不重写、升级或重新序列化；v2 验证器对所有 v1 正例保持接受、
   语义不变，对 `anchor_version:1` 下的空 `exact` 等全部 v1 反例保持拒绝。
7. 同步注释与 SDK 本机笔记的持久映射在 schema1 中不存在（见下文已知缺口），
   需要 root 另行决定 schema 或 SDK 侧外部 ID，本方案不包含。

探针对每个 v1 不可表达的真实捕获都生成方案中的 v2 字节，交给**未修改**的 v1
验证器，记录其拒绝；再从这些字节（而非内存中的捕获）解析并在另一书库解析定位，
仅在 FOUND 后调用公开 SDK 持久化。这只是协议可行性研究，不经过产品修订库。

## 适配层（可消费的固定接口）

`apps/reader/reading-state` 安装为 `EXReaderReadingState 0.1.0`，公开 C 头
`reader_reading_state.h`，C++17 实现，依赖已安装的 SDK `EXReader 3.40.0`、
`EXReaderRevisions 0.3.0` 与唯一产品 SQLite provider：

- `reader_rs_classify/encode`：只对无损捕获输出 v1 原字节并以
  `reader_revision_validate` 复验；否则 `NOT_REPRESENTABLE` 加缺口码，不输出字节。
- `reader_rs_decode`：复验后解析出记录，不重新序列化。
- `reader_rs_resolve_reflow/epub/fixed`、`reader_rs_epub_part`、`reader_rs_fixed_page`：
  只用公开 resolve；`page_id` 与 `part_path` 唯一匹配才路由，不按页码猜测。
- `reader_rs_store_reflow/epub/fixed_note`：只在 FOUND 后调用公开 SDK 笔记 API。

适配层不读写 SDK 表，不写产品目录，不开跨库事务。UI 由 root 与各平台接入者消费。

## 已知缺口

- **注释持久映射**：schema1 只有 `reader_local_books`（书→SDK 本机 ID），没有
  全局 annotation_id→接收端 SDK 笔记 ID。探针只能在内存中保持映射，重启后按
  “范围+文字完全相同”收养。若产品已提交新修订而 SDK 步骤中断、随后重启，
  新文字无法认领旧笔记，旧笔记残留。探针把这一情形记录为缺口，不算通过。
- 有界 EPUB 书签即使 wire 扩展后，SDK 也没有点笔记 API，只能保留在产品修订。

## 保留的失败

失败 run 与其工件原样保留，不作为验收证据：

| run | 源码 | 原因与处理 |
| --- | --- | --- |
| `40053371857` | `4526b905…` | 探针缺 `reader_projection.h`，两平台消费者编译失败；适配层本身已在 `/W4 /WX` 与 `-Werror` 下通过 |
| `40053631455` | `346ac31a…` | 两平台探针以 2 退出，致命信息只在工件内；改为把日志打进作业 |
| `40054043109` | `960df668…` | 探针用 `(text,length)` 构造字符串，参数求值顺序未定义，长度读成 0 |
| `40054400770` | `045ba7ff…` | Linux 全通过；Windows 探针检查全通过，但检查器不认 MSVC 链接图格式，且 deflate 使两平台原件不同；改为存储项 ZIP |
| `40054857963` | `922b4e9c…` | 工作流成功，但书签案例用了非 hex 的注释 ID，v1 因 ID 而非空引文拒绝；不采用，改 ID 并要求精确拒绝原因 |

## 逐项未覆盖

- 进度与书签经产品修订跨设备同步：需 root 先决定上文 v2 方案；本包只有 SDK 字节往返研究。
- 无文本固定页、带章节作用域的重排选择器：同上。
- 含 NUL 的固定页选择器：探针原件没有产生真实 NUL 文本，只有分类规则，没有真实捕获。
- 注释全局 ID→接收端 SDK 笔记的持久映射（schema 决策）。
- 有界 EPUB 书签的 SDK 存储（SDK 无点笔记 API）。
- 重复 spine 路径的 EPUB 注释（需 v2 `part`）。
- macOS、iOS、Android 构建；宿主 UI；WebDAV 实际传输；六平台互通；性能预算。

默认分支与 PR 未合并，未建 tag 或 Release。文档提交 `[skip ci]`，不改变受测源码。
