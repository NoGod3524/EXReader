# 标注 Markdown／JSONL 导出（EXReaderAnnotationExport 0.1.0）

可选包，C ABI，只读。把一本书的产品标注导出为：

- **JSONL**：无损、可机读；保留实体身份、选择状态和每个头的**原 wire 精确字节**。
- **Markdown**：纯文本分享；保留书名、引文、批注和未定位／冲突状态。

它不是同步、导入或冲突解决：不写产品目录、修订库、SDK 书库、笔记或阅读进度，不打开书、不解析锚点、不联网、不解释 HTML。
不依赖 G03/G04，不新增表或实体，不读 SDK 私有 SQL，不使用本机 SDK 行号。

## 接口

`include/reader_annotation_export.h`；唯一入口 `reader_annotation_export_run(options, stats, error)`。
依赖的已安装公共 API：`reader_revision_annotations_page`、`reader_revision_heads`、`reader_revision_get`、
`reader_revision_book_title`（仅标题）、`reader_revision_new_id`（临时文件名）和 `reader_rs_decode`（Markdown 文本）。

选项：已打开的产品 `reader_revisions*`（借用，须在创建它的工作线程调用，无回调重入）、`book_key`、可选 `book_title`
（UTF-8，≤16384 字节；缺省时取该书唯一安全 book 头的标题，没有则无书名）、`jsonl_path`／`markdown_path`
（至少一个，UTF-8，≤4096 字节，不得以分隔符结尾；两路输出必须解析到**不同的最终目标**）、`max_output_bytes`（每个文件；0＝64 MiB，上限 1 GiB）、
`cancel` 回调。状态：`OK/ARGUMENT/MEMORY/REVISION/DECODE/IO/LIMIT/CANCELLED`，错误含 `revision_code`、`rs_code`、`os_error`。

两个输出在**创建任何临时文件之前**比较最终目标身份：Windows 用卷序号＋文件索引（两者都存在时）或 `GetFullPathNameW` 归一化后按序数忽略大小写比较；
POSIX 用 `stat` 的 dev/ino（两者都存在时）或父目录 `realpath` ＋末段名比较。因此 `dir/out` 与 `dir/./out`、重复分隔符、
`..` 段、Windows 大小写变体、指向同目录的符号链接、以及两条路径指向同一个已存在文件，都返回 `ARGUMENT`，既不写临时文件也不改动既有导出。

重入：公开合同是“在创建它的工作线程调用、无重入”，而取消回调就在该线程内。从回调再次调用
`reader_annotation_export_run` 属于重入：在检查任何路径、库或预算之前返回 `ARGUMENT`，**不清零调用方的 `stats`**，
外层导出继续（或按回调自己的返回值正常取消），不会出现嵌套发布互相覆盖。

## 流式与内存

按 `annotations_page`（升序 keyset，每页 100，每页一个读快照）取小行，不复制 wire；每个实体再按需
`get` 单个修订。内存只有一页小行、一个实体的头列表和一个修订（≤1 MiB，JSON 转义后至多约 6 MiB），
不持有整本书的标注。无安全唯一头的实体（待父、并发、阻止的隐式复活）用 **一次** `heads` 取全部头与图，逐个 `get`。

**单实体一个快照**：安全页行本身带着该页快照里的不可变头和同一张图，整段沿用；其余实体只调用一次 `heads`，
并**按同一次返回的图**、用 `reader_projection.h` 的公开规则重新分类 `selection`，进而派生 `tombstone`、
统计桶和 Markdown 状态。页读取与取头之间若有并发写者补齐父修订、显式合并、删除合并或显式恢复，导出的这条实体整条来自更晚的那一个快照，
不会出现 `selection=concurrent` 却 `graph.projection_safe=true/heads=1`、或新 delete wire 配 `tombstone=false` 的混搭；
头列表与 `graph.heads` 不一致时直接以 `REVISION` 拒绝。不同实体之间仍可能来自不同时刻。

## JSONL 格式（format_version 1）

UTF-8，LF，每行一个 JSON 对象，三类：

```json
{"type":"header","format":"exreader-annotation-export","format_version":1,"module_version":"0.1.0","book_key":"txt:…","book_title":"…或null","order":"annotation_id_ascending","wire_encoding":"json_string_utf8"}
{"type":"annotation","annotation_id":"32hex","entity_key":"book_key:32hex","selection":"safe|pending_parents|concurrent|blocked_restore|missing","tombstone":false,"graph":{"revisions":1,"heads":1,"missing_parents":0,"foreign_parents":0,"projection_safe":true,"deleted":false,"requires_restore":false},"heads":[{"revision_id":"32hex","operation":"put|delete|restore","sha256":"64hex","bytes":123,"wire":"…"}]}
{"type":"footer","annotations":1,"current":1,"tombstones":0,"pending_parents":0,"concurrent":0,"blocked_restore":0,"head_wires":1,"complete":true}
```

- 批注行按 `annotation_id` 逐字节升序，每个全局 ID 一行；`heads` 按修订 ID 升序。**footer 存在才表示导出完整。**
- `selection=safe` 且 `tombstone=true`：唯一安全头是 delete（墓碑）。`pending_parents`：缺父或外来父，不能假装唯一当前批注。
  `concurrent`：多个并发头，全部列出，不挑选。`blocked_restore`：删除后未经显式 restore 的 put。
  `missing`：仅用于存储在读页与取头之间消失的极端情形，计入 `pending_parents`。
- **`wire` 字符串编码**（定义明确）：把 wire 的 UTF-8 字节写成 JSON 字符串；只转义 `"`→`\"`、`\`→`\\`、
  `\b \f \n \r \t`，其余小于 U+0020 的控制字符写成 `\u00xx`（小写十六进制），其他所有字节（含 `/`、U+007F、
  U+2028、非 BMP 字符）按原 UTF-8 字节写出，不用代理对。任何 JSON 读取器还原的字符串，按 UTF-8 编码即是原 wire 逐字节。
  wire 经修订库验证为无 NUL 的良构 UTF-8，导出前再校验一次。读取器可用 `sha256` 和 `bytes` 自检。
- 导出不含输出路径、数据库路径、账号凭据或 SDK 行号；`graph` 只是修订图的计数。

## Markdown 格式

固定中文标签。标题行为 `# 书名`（无书名时为书籍标识），所有 ASCII 标点前加反斜杠，换行和控制字符变空格，
因此标题里的 `<`、`*`、`[ ]()`、`&` 都是字面文字。每个实体 `## 批注 N`，状态为：
当前批注（唯一的安全头）／已删除（墓碑）／冲突（并发头或被阻止的隐式复活，逐头列出）／未定位（缺少父修订）。
每个头 `### 头 i/n：修订 …（操作）`，列出位置模式、锚点版本、书内部分路径（EPUB）、页面标识与页索引（固定页）、
章节范围（reflow v2）和**偏移提示（仅供参考，未用于定位）**，随后引文、前文、后文、批注。
引文、前文、后文和批注一律放在 ` ```text ` 围栏中，围栏反引号数比内容里最长反引号串多一，因此其中的 Markdown、HTML、
链接和图片只是文字。Markdown 中 CR／CRLF 变 LF，其他 C0 控制符和 DEL 变为 U+2400 控制图形；JSONL 不做此变换。
围栏之外只有本模块的固定标签、十六进制 ID 代码片段和上述转义文本。

## 发布与失败

每个输出写入同目录下独占创建的临时文件（`.exr-export-<随机>.tmp`），缓冲写、`flush`＋`fsync`（macOS 用 `F_FULLFSYNC`，
Windows 用 `FlushFileBuffers`）后，POSIX `rename`、Windows `MoveFileExW(REPLACE_EXISTING|WRITE_THROUGH)` 原子替换目标。
任何失败、取消或预算超限都删除临时文件，既有的有效导出保持不变。同时要两个输出时，两个临时文件都完整后才开始发布；
若发布第二个时失败，第一个已发布，`stats.jsonl_published／markdown_published` 如实标出。
取消回调在每页、每个实体、每个头和每次缓冲刷写时轮询。输出预算按字节精确计，超出返回 `LIMIT`。
最终目标身份在临时文件创建之前判定，别名直接 `ARGUMENT`；从取消回调重入同一入口同样在创建任何东西之前被拒（见“接口”）。

## 限制

- 导出期间有写入时，不同实体可能来自不同时刻；**同一实体**的 selection／tombstone／graph／heads／统计／Markdown 来自同一个有效公开快照
  （安全页行用该页快照，其余用同一次 `heads` 的图分类）。这一条由云端“第二进程窗口”验收，不是文档承诺。
- 快照窗口用取消回调作为唯一阻塞点；模块与修订库都没有为它新增钩子。
- 重入拒绝按线程判定；回调另起线程并使用另一个受测库不属于本合同的 no-reentry 范围，仍受修订库 owner 规则约束。
- 路径身份只比较平台可给出的文件身份（卷/文件索引，或父目录 realpath＋末段名）；尚未存在、只能通过 reparse point 才等价的别名不做枚举。
- 不核对书是否在书库、不解析 `FOUND`；偏移只是提示。
- 原子性按单个文件；跨两个文件没有事务。目标须与临时文件在同一文件系统（同目录保证）。
- Windows 超过 `MAX_PATH` 的路径取决于系统长路径设置；4096 字节是模块预算，不保证系统接受。
- 不提供导入、合并、冲突解决或 UI。

## 云端验收

工作流 `.github/workflows/reader-annotation-export.yml` 在 Ubuntu 22.04、Windows 2022、macOS 15 上从已安装的产品 SQLite、
修订库、阅读状态、SDK 和导出包构建 C11／C++ 消费者，并用 `tests/reader_annotation_export/` 的语料与独立读取器判定：
JSONL 由 Python `json` 和一个只依据上文编码规则手写的反转义器分别还原，每个头的 wire 必须与语料原字节逐字相同；
Markdown 由结构解析器读回并核对每个围栏内容、状态、位置字段，且证明围栏外没有可渲染标记；导出前后数据库转储和进度不变
（四个快照窗口的那 4 条推进修订由夹具的第二进程写入，窗口段之后重新基线；其余每次导出仍逐字比对转储）。
覆盖：中文、emoji、组合字符、换行、引号、Markdown／HTML 样本、控制字符、非规范 wire（`\uXXXX` 代理对、空格、键序、`display_time`）、
空导出、1234 条分页、anchor v1/v2、三种位置模式、冲突／墓碑／缺父／外来父／阻止复活、取消、预算边界、发布失败与写入失败。
另外三类（本轮新增）：**单实体快照窗口**——四个窗口书各只有一条标注，导出在取消回调里阻塞于“页已读完、实体还没取头”的确定性握手上，
由**第二进程**在同一产品库提交一条推进修订（父到达／显式合并／并发删除合并／显式恢复），再让导出继续；导出的 selection、tombstone、graph、heads、
统计和 Markdown 必须全部来自那一个更晚的快照，且该头的 wire 逐字等于语料原字节。
**路径别名**：点段、重复分隔符、`..` 段、Windows 大小写、POSIX 符号链接目录，全部在写临时文件之前被拒，既有导出不变、目标文件不产生；
同目录两个真正不同的目标仍然正常发布（防过度拒绝）。
**重入**：取消回调里嵌套调用同入口（含共享外层 stats、以及嵌套目标就是外层目标）一律被拒，外层照常完成或取消，不留临时文件。
Windows 无 `RLIMIT_FSIZE`，其写入类失败由被占用目标的发布失败代表；POSIX 则用 `RLIMIT_FSIZE` 触发中途写失败。

结果、工件和未授予的范围见 [validation/reader-annotation-export.json](validation/reader-annotation-export.json)；
本包不授予宿主 UI、六端、真机、性能、导入或冲突解决能力。

## 已验收结果

受测源码 `0b79307a41fc5152cf10f7c34e30573d2481aa08` 的
[run 40085969696](https://github.com/NoGod3524/EXReader/actions/runs/40085969696)（attempt 1）：
Ubuntu 22.04、Windows 2022、macOS 15 三个消费者作业和严格汇总作业均成功，每个平台 **25 项**具名检查通过
（原 19 项含写入失败项：Linux／macOS 为 `RLIMIT_FSIZE` 中途写失败，Windows 为被占用目标的发布失败，另一项在对应平台声明跳过）。
语料 1346 份 wire（批次 1342 ＋ 窗口推进 4），其中一本书 1234 条标注；18 个导出文件（10 个原有 ＋ 8 个窗口）的 SHA-256 在三个平台逐字相同。
工件 ID、字节数、摘要、有效期和作业 ID 见 [validation/reader-annotation-export.json](validation/reader-annotation-export.json)。

保留的原失败与新增失败（均已修，断言未删、工件未删）：

- `40078772023`：Windows MSVC C4310 常量截断，在实现中修复。
- `40079424539`：严格汇总器错误地要求各平台检查名完全一致，修的是汇总器，实现字节未变。
- `40083679976`（**修复前**，新回归先证明缺口）：三平台同时报出
  `selection=pending_parents` 配 `graph{heads:1, projection_safe:true}`；点段别名一次导出同时报 `jsonl_published=1` 与 `markdown_published=1`（写进同一个文件）；
  取消回调里的嵌套导出返回 OK 且 `jsonl_published=1`。
- `40083884769`：实现已修，窗口检查拿“推进 wire”去比“头 wire”（父到达时头仍是原 child），测试修正。
- `40085105713`：恢复窗口把保留修订数写成 5（实为 4），夹具修正。
- `40085507969`：25 项全过，但 4 条推进修订使运行前的库基线失效；改为窗口段之后重新基线，未删除任何断言。

未授予：宿主 UI、真机、读屏、性能、六端、导入与冲突解决。
