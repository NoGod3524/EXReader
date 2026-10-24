# 目录导航（F2）：`EXReaderNavigation 0.1.0`

独立可选安装包，公开 C ABI 头 `reader_navigation.h`，仅依赖冻结 SDK（3.40.0、ABI1）的 `core` 组件。
不自写 EPUB/PDF 解析器，不读 SDK 私有 SQL，不依赖产品目录、修订或阅读状态模块，默认 reading 构建不含它。
源码在 `apps/reader/navigation/`，测试在 `tests/reader_navigation/`，工作流为
`.github/workflows/reader-navigation.yml`。**验收状态见末节，当前未获云端授予。**

## 做什么

宿主直接展示书籍自带目录；用户点击后，模块把该行解析成可验证的原生导航目标，由 root 自己执行跳转。
模块不改阅读位置、进度、标注、书库或同步记录，不联网、不启动浏览器、不携带凭据，不解释或执行目录文字。

## 快照

| 来源 | 打开函数 | 行的 `part` 含义 | 使用的公开 SDK |
| --- | --- | --- | --- |
| EPUB 出版物 | `reader_navigation_open_publication` | spine 序号 | `exr_publication_navigation`、`exr_publication_parts` |
| 重排文档 | `reader_navigation_open_document` | 章节序号 | `exr_document_navigation`、`exr_document_chapters` |
| 固定页（PDF/CBZ） | `reader_navigation_open_pages` | 页序号 | `exr_fixed_pages` |

- 打开时一次复制全部行：原始顺序、parent、label、href、base、role、part 原样保留；不排序、不合并、
  不去重，重复标题仍是多行。label 作为纯文本，HTML 实体解码后的 `<script>` 仍是字面文字。
- SDK 把 `part` 留成 `SIZE_MAX` 的目标（未知路径、spine 中重复的路径、外部或空目标）保持
  `READER_NAVIGATION_NONE`，绝不猜成某章。
- 快照不含 SDK 指针：SDK 对象释放后仍可查询。查询返回的页（`reader_navigation_page`）也是独立副本，
  可在快照关闭后读取，并各自用 `reader_navigation_page_free` 释放。
- 没有自带目录的书得到空快照（`node_count == 0`，`author_outline == 0`）。
- **固定页**：冻结 SDK 没有 PDF 大纲能力，本包也不为此修改 SDK。`open_pages` 只给“按页入口”
  （角色 `page`，标签取页标签、缺省取页 ID），`info.kind == PAGES` 且 `author_outline` 恒为 0，
  不能称为作者大纲。测试 PDF 含 `/Outlines`，断言其标题从不出现。

## 分页、层级与限额

- `reader_navigation_rows(first, 1..100)` 与 `reader_navigation_children(parent, first, 1..100)`
  （`parent == NONE` 列根）。`count == 0` 仅当 `first == total`；`first > total` 为 `RANGE`；`next == NONE` 表示读完。
- 明确的受检上限：总行数 10000（同 SDK）、层级 64（根为深度 0）、总文字 4 MiB（含终止符）。
  选项只能调低。超限返回 `READER_NAVIGATION_LIMIT`，不静默截断；SDK 自身的 `EXR_LIMIT` 同样映射为 `LIMIT`。
- SDK 把损坏的目录（`EXR_FORMAT`/`EXR_ENCODING`）报告为 `CORRUPT`，不产出半个快照。

## 目标解析

`reader_navigation_resolve_publication|document|page|cfi` 在宿主传入的**同一本书的存活 SDK 句柄**上校验：
快照记录的整本书身份（各 part 的 path 与 id）必须与存活句柄一致，否则 `MISMATCH`。

| 行的情形 | 结果 |
| --- | --- |
| SDK 已解析 part，片段存在 | `OK`：spine 序号 + `exr_part.path` 原样 + `exr_part.id` + 片段节点 |
| 片段 id 不存在 | `PART_ONLY`：保留 part，无节点；宿主可显式打开章首，模块不猜 |
| URI scheme 或 `//` 开头 | `NEEDS_HOST`，不抓取、不打开 |
| 无 href，或没有任何同路径 part | `UNRESOLVED` |
| `..` 越过容器根、绝对路径、反斜杠、坏百分号转义 | `RANGE` |
| spine 中多个 part 共用该路径 | `AMBIGUOUS`，`candidates` 升序列出全部；绝不取第一个 |
| 宿主传 `explicit_part` | 必须在候选内且与行路径一致，否则 `MISMATCH`/`RANGE`；与 SDK 已给的 part 冲突亦 `MISMATCH` |
| 全 EPUB CFI | `exr_publication_cfi_resolve`；输出 spine 序号、path、CFI 点；非法或无 EPUB 提供者为 `CORRUPT` |

SDK 未解析而本模块又只找到一个同路径 part 时同样返回 `UNRESOLVED`：只有 SDK 的 part 或宿主显式身份才被接受。
路径折叠（`.`、`..`、百分号解码）只用于解释 SDK 未解析的目标与核对显式身份，规则与 SDK 的 `exr_resolve_path` 一致。
片段节点序号是 `exr_publication_load(part)` 返回文档内的节点下标，具有确定性，可在第二个独立打开的 SDK 对象上复核。

## 所有权、取消与重入

快照句柄及其调用、`close` 在创建它的 owner 上使用；传入的 SDK 句柄只在调用期间借用。模块不创建线程。
`exr_control` 回调内再调用同一快照的任何函数返回 `BUSY`，状态不变（SDK 句柄自身的禁止重入规则也适用）。
取消在每次 SDK 调用前后及每 256 行拷贝处轮询；`CANCELLED` 时无输出、无需释放。失败调用的输出一律为空。

## 云端验证（仅 GitHub Actions）

Windows/Linux 安装后的 C 与 C++ 消费者链接 `EXReaderNavigation`（及其 SDK `core`）；C++ 探针另链接已安装 `pdf` 组件以打开真实 PDF，不链接产品模块。覆盖：
EPUB3 nav、EPUB2 NCX、嵌套与空目录、重复标题、非 ASCII 标题、相对路径与片段、重复 spine、外部目标、
未解析 part、越界/损坏、分页、深度/节点/文字限额、取消（逐个轮询点）、重入、CFI，
以及快照在 SDK 释放后的寿命。期望来自夹具生成器手写的 TSV，而非模块自身；
真实可解析目标在**第二个独立打开**的 SDK 对象上复核 spine 序号、路径与片段节点 id；
源文件字节前后哈希相同。同源报告绑定完整 source/run/attempt，两平台结果须逐项一致。

## 验收状态

`docs/validation/reader-navigation.json` 仍为 `accepted: false`。
首轮 `e3ebed25` / run `40073175739` 两平台因缺少公开 `exr/formats.h` 声明编译失败，原运行保留。
第二轮 `3c0ffdd9` / run `40073375893` 两平台构建和 C 消费者通过，但 C++ 探针各 113 项中有一项失败：
自定义 publication 的加载器返回无 chapter 的 TXT，不能用于公开 fragment resolve。
探针现改为用 `exr_document_create` 构造带真实章节路径的文档，另先独立核对缺失片段的 SDK 返回值；
原 `PART_ONLY` 断言保留，模块生产源码与冻结 SDK 未变。后续结果仅按实际云端运行登记。
即便通过，也只授予本包接口：不含宿主 UI、产品性能、六平台互通、macOS，且 PDF/CBZ 无作者大纲。
