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
（至少一个，UTF-8，≤4096 字节，互不相同，不得以分隔符结尾）、`max_output_bytes`（每个文件；0＝64 MiB，上限 1 GiB）、
`cancel` 回调。状态：`OK/ARGUMENT/MEMORY/REVISION/DECODE/IO/LIMIT/CANCELLED`，错误含 `revision_code`、`rs_code`、`os_error`。

## 流式与内存

按 `annotations_page`（升序 keyset，每页 100，每页一个读快照）取小行，不复制 wire；每个实体再按需
`get` 单个修订。内存只有一页小行、一个实体的头列表和一个修订（≤1 MiB，JSON 转义后至多约 6 MiB），
不持有整本书的标注。无安全唯一头的实体（待父、并发、阻止的隐式复活）用 `heads` 取全部头，逐个 `get`。

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

## 限制

- 导出看到的是各页快照和各实体取头时的状态；导出期间有写入时，不同实体可能来自不同时刻（单个实体内一致）。
- 不核对书是否在书库、不解析 `FOUND`；偏移只是提示。
- 原子性按单个文件；跨两个文件没有事务。目标须与临时文件在同一文件系统（同目录保证）。
- Windows 超过 `MAX_PATH` 的路径取决于系统长路径设置；4096 字节是模块预算，不保证系统接受。
- 不提供导入、合并、冲突解决或 UI。

## 云端验收

工作流 `.github/workflows/reader-annotation-export.yml` 在 Ubuntu 22.04、Windows 2022、macOS 15 上从已安装的产品 SQLite、
修订库、阅读状态、SDK 和导出包构建 C11／C++ 消费者，并用 `tests/reader_annotation_export/` 的语料与独立读取器判定：
JSONL 由 Python `json` 和一个只依据上文编码规则手写的反转义器分别还原，每个头的 wire 必须与语料原字节逐字相同；
Markdown 由结构解析器读回并核对每个围栏内容、状态、位置字段，且证明围栏外没有可渲染标记；导出前后数据库转储和进度不变。
覆盖：中文、emoji、组合字符、换行、引号、Markdown／HTML 样本、控制字符、非规范 wire（`\uXXXX` 代理对、空格、键序、`display_time`）、
空导出、1234 条分页、anchor v1/v2、三种位置模式、冲突／墓碑／缺父／外来父／阻止复活、取消、预算边界、发布失败与写入失败。
Windows 无 `RLIMIT_FSIZE`，其写入类失败由被占用目标的发布失败代表；POSIX 则用 `RLIMIT_FSIZE` 触发中途写失败。

结果、工件和未授予的范围见 [validation/reader-annotation-export.json](validation/reader-annotation-export.json)；
本包不授予宿主 UI、六端、真机、性能、导入或冲突解决能力。
