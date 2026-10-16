# Native C API 0.9

公开入口为 `include/exreader.h`；API 仍为实验性，尚未承诺二进制兼容。0.9 新增独立文字边界分析入口，并在 `exr_glyph` 末尾添加 `cluster_start/end` 和 `boundaries`；0.8 新增 publication / session 分段加载接口；0.7 新增稳定文本锚点接口，并在 `exr_note` 末尾添加 `anchor`；0.6 新增通用文档构造入口及 `EXR_CUSTOM = 0`；0.5 扩展了 glyph、line、page、bitmap 结构。宿主需要使用匹配版本的头文件重新编译。所有路径和字符串使用 UTF-8。所有 `exr_status` 函数返回 `EXR_OK` 表示成功；可选 `exr_error*` 接收错误详情。

## 所有权与并发

- `exr_document`、`exr_font`、`exr_layout`、`exr_library`、`exr_publication`、`exr_session` 为不透明句柄，使用各自析构函数释放。
- document 的 text / title / blocks / nodes / chapters / resources 和 layout 的 pages / lines / glyphs / boxes / image 为只读借用视图，所属对象释放后失效。树节点属性和文本也属于 document。借用的图片像素不可修改或释放。
- 布局拥有位置、样式和已解码图片，不保留文档指针。文档释放后仍可绘制；需要源节点内容或资源名称时保留文档。渲染时需传入生成该布局时使用的字体；字号变化由库设置。相同字体、布局或书库句柄的调用由宿主串行处理；不共享对象的独立句柄可独立使用。共享 publication、session 或压缩 archive 的文档，其调用及生命周期变更也由宿主串行处理；引擎没有全局状态或内部线程锁。
- `exr_books_free()` / `exr_notes_free()` 释放数组和其中字符串；后者也释放每条笔记的锚点字符串。修改元数据时复制结构并用自己的字符串设置输入字段，不替换结果数组中的库拥有指针。
- `exr_anchor_create()` 输出独立拥有的选文、前后文和章节路径字符串，由 `exr_anchor_free()` 释放；输入文档随后可释放。宿主也可直接提供选择器字段供只读解析，但不能用库的释放函数释放宿主借用的字符串。
- `exr_bitmap_free()` 释放像素。`exr_document_export()` / `exr_document_resource()` / `exr_library_blob()` 返回的字节，以及 `exr_text_analyze()` 返回的边界表，用 `exr_free()` 释放。这些字节独立于原对象或输入的生命周期。跨 DLL 调用时不要使用宿主 `free()` 释放库内存。
- 输出参数需为空或已先释放。对输入的任意无效 C 指针不提供运行时保护。
- `exr_document_create()` 在调用期间复制输入数组中的字符串、属性和资源字节；返回后可释放所有输入。失败时不交出部分文档，`*out` 为 NULL。
- `exr_publication_create()` 复制标题和分段元数据，不复制 loader context。若提供 release 回调，创建成功后由 publication 在最后一个 publication / session 引用释放时恰好回调一次；创建失败时仍由宿主清理 context。release 为 NULL 时不自动释放 context，宿主必须使其在全部 publication / session 生命周期内有效。
- `exr_publication_load()` 返回宿主拥有的独立文档，用 `exr_document_free()` 释放。`exr_session_get()` 返回借用文档和布局，契约有效期至下次 get / clear / free；宿主不得释放或长期保留这些指针。

## 文档与排版

`exr_document_open()` 根据扩展名选择解析器；内存入口显式指定 `exr_format`。文本模型使用规范化 UTF-8；进度和标注范围使用规范化文本的字节偏移，不使用页码作为永久位置。宿主通过 `exr_layout_page_at()` 在重新排版后查找该位置，通过 `exr_layout_hit_test()` 将坐标映射回文字。0.7 的文本锚点可以在正文投影变化后重新寻找选文；阅读进度仍为偏移。0.4 的 EPUB 正文投影会分隔表格单元格、排除 hidden 元素，偏移可能与 0.3 不同；旧标注只有偏移，迁移后仍明确标为 legacy，不能把当前正文中的同一数字偏移当作历史选文。旧 Foliate CFI 转换尚未实现。

输入上限 128 MiB、单文档正文上限 64 MiB、单布局上限约 400 万字形。文档树上限 262144 个节点、字符串累计 64 MiB、每个元素最多 256 个属性。ZIP 成员上限 32 MiB、条目上限 1 万、打开期间累计解压上限 128 MiB；后续每次资源读取单独应用 32 MiB 上限，由调用者释放返回的字节。XML 嵌套上限 256 层，不解析外部实体，拒绝实体声明；HTML 的脚本和样式不进入正文。单个文档仍完整解析并在内存中排版；0.8 可按需加载独立分段并缓存其布局，尚未实现页级续排和页缓存。

FreeType 提供真实字形 advance、kerning 和像素，不负责分页。EXReader 自己决定段落、换行、分页、基线和字形位置。0.9 按 Unicode 17.0.0 扩展字素簇保护换行与命中位置；换行机会使用下述 UAX #14 子集。字体仍按 Unicode 标量逐个取字形，尚未实现 OpenType shaping / GPOS、字体覆盖验证、字体回退或双向重排；阿拉伯文、印度文字和 emoji 序列的正确视觉塑形仍需后续工作。

正文查找为区分大小写的 UTF-8 子串查询。元数据搜索使用绑定参数的 SQLite LIKE，并转义 `%` / `_`，其大小写折叠规则为 SQLite 默认规则。

## 独立文字边界

`exr_text_analyze(text, size, &boundaries, &error)` 只分析宿主提供的 UTF-8 字节，不依赖 document、字体、布局或 SQLite。`size` 为明确的输入字节数，不包含额外的 C 字符串终止字节；不要求输入以 NUL 终止。成功时分配恰好 `size + 1` 字节的边界表，以源 UTF-8 字节偏移索引，宿主使用 `exr_free()` 释放。输入可以在函数返回后修改或释放。

| 标志 | 值 | 对应偏移前的边界含义 |
| --- | --- | --- |
| `EXR_BOUNDARY_GRAPHEME` | 1 | 扩展字素簇起点或文本末尾，可作为簇选择端点 |
| `EXR_BOUNDARY_LINE` | 2 | 当前换行规则允许在此断行 |
| `EXR_BOUNDARY_MANDATORY` | 4 | 必须在此断行，同时具有 `LINE` |
| `EXR_BOUNDARY_GLUE` | 8 | 此处禁止紧急换行，适用于不换行硬组与标点约束 |

`boundaries[0]` 与 `boundaries[size]` 均有 `GRAPHEME`；末尾恒为 `GRAPHEME | LINE | MANDATORY`。UTF-8 续字节和字素簇内部的标量起点全部为 0。没有 `LINE` 不等于 `GLUE`：布局可在普通长词的其他字素边界紧急换行；有 `GLUE` 时也不能这样拆开。

```c
const char text[] = "e\xCC\x81"; /* U+0065 + U+0301: one grapheme, three bytes. */
unsigned char *boundaries = NULL;
exr_error error = {0};
exr_status status = exr_text_analyze(text, sizeof(text) - 1, &boundaries, &error);
if (status == EXR_OK) {
    /* boundaries[0] is GRAPHEME; [1] and [2] are zero; [3] is the end boundary. */
}
exr_free(boundaries);
```

空字符串配合 `size = 0` 成功，返回一个末尾边界字节；`text = NULL`（包括 size 为 0）或缺失输出指针返回 `EXR_ARGUMENT`。有效输入上限为 64 MiB，超限返回 `EXR_LIMIT`；非法 UTF-8 返回 `EXR_ENCODING`。失败时只要输出指针有效，`*boundaries` 均为 NULL。此独立 API 按明确长度接受嵌入的 U+0000，并将它作为 Control 标量分析；文档模型仍拒绝嵌入 NUL。

扩展字素规则使用 Unicode 17.0.0 的 Grapheme_Cluster_Break、Extended_Pictographic 和 Indic_Conjunct_Break 属性，覆盖组合附标、Prepend / SpacingMark、Hangul、Indic 辅音连接边界、emoji ZWJ 与 Regional Indicator 配对。完整官方 `GraphemeBreakTest.txt` 的 766 个向量用于回归。

换行实现是明确的 UAX #14 子集：强制换行与 CRLF、普通空格、ZWSP、NBSP / NNBSP / WJ、ZWJ 之后的保护、不把开标点留在行末或闭标点留在行首的约束、中日韩文字间的机会，以及连字符、软连字符等类之后的机会。软连字符本身隐藏，当前未在断行处生成可见连字符。尚不包含字典断词、完整数字串和上下文引号规则。

属性表随 C 源码编译，普通构建不运行 Python 或下载 Unicode 数据。`python tools/generate_unicode.py --download --check` 使用固定官方来源和 SHA-256 重现验证；派生属性表与官方测试使用 Unicode-3.0 许可，全文随 SDK 安装。

SDK 的 `examples/text.c` 与其他宿主示例一同编译为 `exreader-text-example`。直接运行，无需字体或参数；它验证 25 个 UTF-8 字节中的 4 个字素簇，范围为 `[0,3)`、`[3,14)`、`[14,22)`、`[22,25)`，并用 `exr_free()` 释放边界表。

## 分段 publication 与 session

`exr_publication` 保存分段目录及 loader，不要求整书已解析为一个文档。每个 `exr_part` 提供用于定位的 `id/path`、显示标题 `title` 和 `in_reading_order`；分段可以是章节、固定页或宿主定义的独立排版单位。`exr_publication_title()` / `exr_publication_parts()` 返回属于 publication 的只读元数据，索引只在该 publication 内有效。

`exr_publication_create()` 接收 `exr_publication_input`，复制标题及 parts 数组中的字符串。`load(context, part, out, error)` 在成功时交出一个独立、由引擎接管的 `exr_document`；可使用任意内置格式解析器或 `exr_document_create()` 构造，不需要全局注册。每次成功加载都应返回可独立释放的文档，不能交出宿主正在复用的借用句柄。若提供 release 回调，context 仅在 create 成功后交由 publication 在最后一个引用释放时回调清理；release 为 NULL 时仍由宿主管理其生命周期，不会默认调用 free。

publication 必须提供 1–10000 个分段。标题、分段 ID 和分段标题的单字符串上限为 64 KiB，分段 path 上限为 2046 字节，元数据累计上限为 64 MiB（含字符串终止字节）；字符串必须为有效 UTF-8。可选字符串为 NULL 时复制为空串。ID 和 path 允许为空或重复，例如 EPUB spine 可以重复引用同一资源；它们不是唯一键。

内置 `exr_publication_open()` / `exr_publication_open_memory()` 目前只接受 EPUB。打开时读取 container、OPF、manifest 和 spine，既不解压也不解析任何 XHTML；parts 先按 spine 顺序排列（包括 `linear="no"`），再追加辅助 XHTML。`in_reading_order` 保留原书阅读顺序属性；独立请求非线性章节或导航章节时，也会将该章作为独立文档投影和排版。请求一个 part 才解析对应 XHTML，完整资源清单仍可访问，所有分段共享同一份压缩 archive。跨章链接可以解析到资源；目标章节未解析时，目标节点返回 `SIZE_MAX`。

直接调用 `exr_publication_load()` 得到宿主拥有的文档，不进入 session 缓存。需要自动管理逐段排版时，调用 `exr_session_create(publication, font, config, capacity, ...)`，capacity 为 1–64 个驻留分段。session 保留 publication，因此创建成功后可以先释放宿主的 publication 句柄。config 和 user CSS 被复制；user CSS 必须为有效 UTF-8，大小不超过 1 MiB。font、图片解码回调及其 context 仍由宿主提供，必须在 session 生命周期内保持有效。改变字体或版式时，应创建使用新配置的 session。

```c
exr_publication *publication = NULL;
exr_session *session = NULL;
const exr_document *part_doc = NULL;
const exr_layout *part_layout = NULL;
exr_error error = {0};
exr_status status = exr_publication_open("book.epub", &publication, &error);
/* font is an open exr_font that will outlive session. */
if (status == EXR_OK)
    status = exr_session_create(publication, font, NULL, 2, &session, &error);
exr_publication_free(publication);
if (status == EXR_OK)
    status = exr_session_get(session, 0, &part_doc, &part_layout, &error);
/* Use the borrowed document/layout before the next get/clear/free. */
exr_session_free(session);
```

`exr_session_get()` 仅加载并排版所请求的分段；缓存命中直接复用文档和布局。达到容量后按 LRU 淘汰最久未访问的分段，同时释放其文档和布局；加载或排版失败保留原缓存。`exr_session_cached()` 返回当前驻留数量，`exr_session_clear()` 清空缓存，后续 get 会重新加载。新分段加载期间可临时多驻留一个分段；容量按分段数计算，不是内存字节硬上限。

分段的页号、节点 / 资源索引和规范化 UTF-8 偏移都是局部值，不能当作旧接口的全书偏移。宿主保存位置时需结合 part 索引或宿主唯一标识、id/path，以及局部偏移或 `exr_anchor`；不能仅靠可能重复的 id/path 区分分段。锚点只在所加载分段的正文内解析。整书总页数在各段排版完成前未知，本接口不预先排完整本书。

loader 和图片解码回调不能销毁或重入当前正在执行的 publication / session。`exr_session_get()` 拒绝同一 session 的重入访问；这不替代宿主对共享 publication / source 对象及其生命周期的串行管理。

这一层提供分段增量加载和排版，不提供单章内部的页级续排。每次仍完整解析并排版一个分段，超长段落和大表格仍整体处理；EPUB 压缩输入仍受 128 MiB、单 ZIP 成员仍受 32 MiB 上限约束。需要更细粒度时，宿主 loader 可以提供更小的独立分段。现有 `exr_document_open()`、书库导入、`exr_library_document()`、全书搜索和导出继续使用原文档模型，不自动变为懒加载。

SDK 的 `examples/lazy.c` 可编译为 `exreader-lazy-example`，用法为 `font.ttf output.png [book.epub part-index]`。不传书籍参数时，创建三个由宿主 loader 构造的分段，仅加载索引 1；传入 EPUB 和从 0 开始的 part 索引时，使用内置索引并只渲染该分段的第一页。两种路径均设置一个驻留分段，输出用于检查实际加载数量。

## 稳定文本锚点

`exr_anchor` 由半开范围 `start/end`、精确选文 `exact`、前后文 `prefix/suffix` 和可选章节路径 `chapter` 组成。位置均为规范化正文的 UTF-8 字节偏移。`exr_anchor_create()` 从当前文档捕获最多 64 KiB 的选文，以及两侧各最多 32 个 Unicode 标量的上下文；输入范围必须位于 UTF-8 字符边界。`start == end` 捕获点书签，其 `exact` 是空字符串；`exact == NULL` 则表示没有文本选择器的旧偏移记录。

```c
exr_anchor anchor = {0};
exr_anchor_match match;
exr_error error = {0};
if (exr_anchor_create(doc, selection_start, selection_end, &anchor, &error) == EXR_OK) {
    /* Persist the fields; later resolve against a newly opened/constructed document. */
    if (exr_anchor_resolve(updated_doc, &anchor, &match, &error) == EXR_OK &&
        match.state == EXR_ANCHOR_FOUND) {
        /* match.start/end are the usable UTF-8 range in updated_doc. */
    }
}
exr_anchor_free(&anchor);
```

`exr_anchor_resolve()` 只读取文档和选择器，不修改原锚点。`EXR_OK` 表示完成匹配过程，宿主还必须检查 `match.state`：

| 状态 | 含义 |
| --- | --- |
| `EXR_ANCHOR_FOUND` | 唯一最佳候选；`match.start/end` 为当前正文中的范围 |
| `EXR_ANCHOR_MISSING` | 找不到有足够上下文佐证的候选，或指定章节路径已消失 |
| `EXR_ANCHOR_AMBIGUOUS` | 多个候选取得相同最高匹配等级，拒绝按旧偏移猜测 |
| `EXR_ANCHOR_LEGACY` | `exact == NULL`，只有旧偏移，无法验证原选文 |

除 `FOUND` 外，输出 `start/end` 均为 `SIZE_MAX`，不能直接交给定位或排版接口。精确选文必须至少有一侧完整前后文匹配，或有文档 / 章节边界作为佐证；两侧都匹配的候选优先。点书签使用同样的上下文和边界规则。原偏移不是解决重复内容歧义的依据。

捕获的范围完全位于同一章节时记录其路径，解析限制在对应章节范围内；跨章节范围不记录章节路径。路径消失时返回 `MISSING`，不自动搜索其他章节。宿主明确去掉 `chapter` 限制后可尝试全篇或跨格式匹配；这只是精确文本选择器的复用，不包含文档身份验证或格式标准间的映射。

这些接口独立于 SQLite，适用于内置格式和 `exr_document_create()` 构造的文档；宿主可在自己的存储中保存全部字段。锚点捕获继续验证 Unicode 标量边界，不自动将选区扩展到字素簇；需要整簇选择时，宿主可先对规范化正文使用 `exr_text_analyze()` 选择端点。不支持模糊改字匹配、Unicode 规范化、文档指纹和 EPUB CFI；引文或上下文发生变化可能返回 `MISSING`。正文导出接口不序列化锚点。0.9 不改变文档归一化投影和 ASCII 空白处理。

SDK 的 `examples/anchor.c` 提供无需字体的完整示例；与构造文档示例使用同一个 examples CMake 工程，生成 `exreader-anchor-example`。它在保存选文后释放原文档，再打开插入前言的版本并检查重新定位的结果。

## 通用文档构造

`exr_document_create()` 接收宿主生成的 `exr_document_input`，不经过文件解码器。自定义格式的解析器可以直接调用此函数，得到供现有搜索、CSS、布局、渲染和正文导出使用的 `exr_document`。构造后的 `exr_document_format()` 返回 `EXR_CUSTOM`。此版本不引入全局状态或解析器注册表，也不提供已创建文档的原地修改接口。

```c
exr_attribute attrs[] = {{"id", "intro"}, {"class", "body"}};
exr_node_input nodes[] = {
    {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
    {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
    {EXR_NODE_PARAGRAPH, 1, "p", NULL, attrs, 2},
    {EXR_NODE_TEXT, 2, NULL, "Hello from a host parser.", NULL, 0}
};
exr_chapter_input chapter = {"main", "chapters/main.unit", 1, 1};
exr_document_input input = {"Host document", nodes, 4, &chapter, 1, NULL, 0};
exr_document *doc = NULL;
exr_error error = {0};
exr_status status = exr_document_create(&input, &doc, &error);
if (status == EXR_OK) {
    /* Arrays and strings above may now be released or changed. */
    /* Use doc with exr_document_find(), exr_layout_create_ex(), etc. */
}
exr_document_free(doc);
```

`nodes` 必须按前序排列：索引 0 为唯一 `EXR_NODE_DOCUMENT`，其 parent 为 `SIZE_MAX`；每个后续节点的 parent 必须是仍处于当前祖先链上的较早索引。文档根的直接子节点必须为 `EXR_NODE_CHAPTER`，且每个章节在 `chapters` 数组中恰好列出一次。章节不得嵌套。`TEXT` 必须提供非 NULL 的 text，其余节点的 text 必须为 NULL；文本、图片和换行节点不能包含子节点。引擎计算 child/sibling、章节归属和正文范围，输入无需提供这些派生数据。name 可省略，节点 kind 提供段落、标题、表格等语义；name 和 attributes 可保留宿主的元素名称及扩展信息。

自建文档中的普通名称只用于保留来源信息及匹配 CSS 标签选择器，不会因名为 `head`、`script`、`strong` 等而自动启用 HTML 行为。需要 HTML 标签行为时使用明确的 XHTML 展开名，例如 `http://www.w3.org/1999/xhtml|link` 引用书内样式表。无名称的段落、标题、图片等语义节点仍可通过 class、ID、通配选择器和内联 style 设置样式；文本节点和无名称的文档/章节包装节点不直接匹配选择器。class、id、style、hidden，以及图片的 src/width/height、单元格的 colspan/rowspan 是引擎识别的通用属性，其余属性按原值保留。

`exr_chapter_input` 提供 id、path、root 和 `in_reading_order`。正文按章节数组顺序投影，只有 `in_reading_order != 0` 的章节进入正文及布局；输出章节的 `in_spine` 与 `linear` 均取此布尔值。辅助章节仍保留树和链接目标，其节点范围为 `SIZE_MAX`。章节资源按 path 自动匹配；没有同路径资源时，输出 `resource = SIZE_MAX`，章节仍可解析链接。

`exr_resource_input` 提供资源元数据及编码字节。引擎复制字节，不要求章节同时提供源文件资源。`data = NULL, size = 0` 声明只有元数据的资源，之后读取返回 `EXR_FORMAT`；非 NULL 的 data 配合 size 为 0 表示有效空资源，读取成功并返回可用 `exr_free()` 释放的零长度缓冲区。NULL data 配合非零 size 无效。

path 是原始虚拟文件名，不是 URI：必须为非空、规范化的相对路径，使用 `/`，不能包含空路径段、`.` / `..`、反斜杠、冒号或控制字符。路径最长 2046 字节、最多 256 段。字面的 `%`、`#` 和 `?` 可用于路径；链接引用它们时分别编码为 `%25`、`%23` 和 `%3F`。资源路径在资源数组内唯一，章节路径在章节数组内唯一；两组中同路径表示对应资源。每组内非空 ID 不能重复，同一节点内不能有重名属性。

构造要求有效 UTF-8 字符串；资源字节为任意二进制。标题省略时为空字符串。上限为 262144 个节点、10000 个章节、10000 个资源、每节点 256 个属性、树深 256 层（包含文档根）、模型字符串累计 64 MiB、单资源 32 MiB、资源字节累计 128 MiB；正文仍有 64 MiB 上限。参数错误返回 `EXR_ARGUMENT`，非法 UTF-8 返回 `EXR_ENCODING`，超限返回 `EXR_LIMIT`。函数会复制输入并完成验证及正文投影后才返回文档。

导出仍为六种格式的正文转换，不序列化完整文档树和资源。`EXR_CUSTOM` 不作为 `exr_document_open_memory()` 的输入文件格式，也不支持通过 `exr_library_import()` 直接保存；SQLite 书库当前持久化的是已有文件格式的原始字节。

## 文档树与 EPUB 资源

`exr_document_nodes()` 返回前序排列的节点数组；0 为文档根。通过 `parent`、`first_child`、`next_sibling` 遍历。缺失索引为 `SIZE_MAX`。节点的 `chapter` 指向章节数组；文档根没有章节。节点索引只在当前 document 生命周期内有效，不能用作持久书签。

对于 EPUB，`exr_document_chapters()` 先按 spine 顺序返回章节，包括 `linear="no"`；再按 manifest 顺序追加尚未在 spine 中出现的 XHTML（例如 EPUB 3 nav）。`in_spine` 和 `linear` 标明阅读顺序属性。章节记录 manifest ID、规范化 ZIP 路径、根节点与资源索引。宿主构造文档保留输入的章节顺序与虚拟路径。

文本节点的 `text` 保存 XML 解码后的原始空白和内容；元素的 `name` 与属性名采用 Expat 展开名 `namespace-URI|local-name`，无命名空间时为原名。`exr_node_attribute()` 精确匹配名称，例如 `class`、`style`、`href`、`src`、`id`、`colspan`、`http://www.idpf.org/2007/ops|type`。元素名、内联样式、内嵌 style 文本、未知元素及其属性均保留。

节点 `start/end` 是规范化正文的半开 UTF-8 字节区间，与原始 XHTML 字节位置和 `strlen(node.text)` 不同。正文只包括阅读顺序中的章节；HTML head/script/style、hidden 子树和辅助章节的范围均为 `SIZE_MAX`。自建文档的 HTML 标签规则需要显式 XHTML 命名空间。没有文字的可见元素可以有零长度范围。辅助脚注和目录的树仍可访问，链接仍可指向它们。图片书可以打开、排版和绘制，图片本身的文字范围可以为零；纯图片书的文本位置不足以唯一标识页面。

EPUB 3 目录通过 nav 子树表达，层级由其中的 ol/li 保留。可用 `exr_node_attribute(node, "http://www.idpf.org/2007/ops|type")` 查找包含 `toc` 的标记。EPUB 2 NCX 暂只保留为原始资源。其他内置格式的树目前只提供原解析器已有的标题和段落，没有新增其结构解析；宿主构造入口可以提供更完整的结构。

`exr_document_resources()` 返回 manifest 清单，包含 ID、规范化路径、媒体类型和 properties（如 nav、cover-image）。全书 document 保留一份压缩 EPUB；XHTML 在打开时解析，其他资源通过 `exr_document_resource()` 按需解压，不写临时文件、不请求网络。publication 分段文档则只解析所请求章节，并共享压缩 archive。清单中的资源可能缺失或损坏，读取时返回错误。

```c
size_t count, resource, target, size;
void *bytes = NULL;
exr_document_chapters(doc, &count);
if (count && exr_document_resolve(doc, 0, "../images/cover.png",
                                &resource, &target, &error) == EXR_OK &&
    resource != SIZE_MAX) {
    if (exr_document_resource(doc, resource, &bytes, &size, &error) == EXR_OK) {
        /* Host decodes bytes using the resource media type. */
        exr_free(bytes);
    }
}
```

`exr_document_resolve()` 以指定章节路径为基准，处理 `..`、UTF-8 和百分号转义，包括仅有 `#fragment` 的地址。成功返回资源索引；若目标 XHTML 已解析，还返回章节根或对应 id / xml:id 节点。找不到资源或片段时相应索引为 `SIZE_MAX`；外部 URI、越过 ZIP 根、非法编码等返回 `EXR_ARGUMENT`。解析基准是章节路径，尚不应用 HTML base 或 xml:base。

CSS `display:none` 只影响布局，不删除规范化正文；重新排版时原有文字位置保持不变。HTML `hidden` 属性在文档投影阶段排除，其行为与 CSS 隐藏不同。现有导出接口仍为文本转换，会丢失图片、链接和样式。

## 宿主样式与布局输出

`exr_layout_create()` 保留默认入口。通过 `exr_layout_create_ex()` 配置宿主样式和图片解码器；配置及 CSS 字符串只在创建调用期间借用。

```c
exr_layout_config config = exr_layout_config_defaults();
config.page.width = 600;
config.document_css = 0; /* Disable linked, embedded and inline book CSS. */
config.user_css = "p {font-size:24px;line-height:1.6} img {max-width:100%}";
status = exr_layout_create_ex(doc, font, &config, &layout, &error);
```

书内 link/style 按文档顺序读取并限制在对应章节；内联 style 使用更高优先级。元素、`*`、`.class`、`#id`、组合、逗号列表、后代和 `>` 子选择器可用。支持 specificity、源码顺序、`!important` 和文字属性继承。宿主 `user_css` 的优先级高于全部书内规则（包括书内 `!important`），便于调用方控制阅读样式。关闭书内 CSS 后仍保留标题、粗体、斜体等语义默认值；宿主可以覆盖它们。

| 范围 | 已实现 |
| --- | --- |
| 文字 | font-size（4–256）、font-weight（合成粗体）、font-style（合成斜体）、color、line-height、text-align（left/start/center/right/end/justify）、text-indent |
| 盒模型 | width / max-width、margin / padding 及四边长属性、background-color（background 仅接受颜色）、统一 border-width / border-color / border-style（solid/none）和 border 简写 |
| 流布局 | display: none/block/inline/table/table-row/table-cell；break-before/after 和 page-break-before/after 的 page/always/auto |
| 尺寸 | px、pt、em、rem、百分比和零值；margin 可 auto；图片支持 height，普通块的 height 尚未应用 |
| 颜色 | #RGB、#RGBA、#RRGGBB、#RRGGBBAA；black/white/red/green/blue/gray/grey/transparent/navy/yellow/orange/purple |

`rem` 当前以宿主页默认字号为基准。`inherit` 支持文字属性；缩进和边框宽度不支持百分比。所有负尺寸均忽略，外边距不折叠。未知属性、选择器和 at-rule 会被跳过；尚不支持 @import、@media、变量、伪类、属性选择器、字体族/嵌入字体、flex/grid、浮动、定位、完整空白规则和浏览器式盒模型分片。属性值和单位使用小写。样式表合计上限 1 MiB、4096 条规则、131072 项展开声明、每规则 256 项声明、2000 万次匹配工作；达到上限返回 `EXR_LIMIT`。

`exr_layout_glyphs()` 输出字形编号、字号、颜色 `0xRRGGBBAA`、合成粗/斜体标志、基线、源节点和文字偏移。0.9 的 `cluster_start/end` 是当前可见内联串中该字形所属字素簇的源 UTF-8 半开范围；同一簇中的字形共享范围，可以跨文本节点和样式边界。原有 `start/end` 仍保留每个标量的源范围，`boundaries` 为该标量之前的 `EXR_BOUNDARY_*` 标志。分段和文档使用各自局部偏移，簇索引不是永久标识。

`EXR_GLYPH_HIDDEN = 4` 标记格式、换行控制、变体选择符等不应绘制的条目，内置栅格器跳过这些字形，自定义绘制也需跳过；它们仍保留源文本范围。普通字符的字体覆盖和标记定位取决于宿主字体及当前逐标量取字形方式，分组不会执行复杂塑形。布局不会拆开字素簇，也不会在 `GLUE` 边界紧急断行；不可拆的组超过内容宽度时保留整组，`clip_left/right` 指明水平裁切范围。

`exr_layout_hit_test()` 按命中的字素簇整体宽度返回其起点或终点，不返回簇内部偏移；当前坐标和簇顺序仍按逻辑 LTR 排布，没有 BiDi 视觉重排。`exr_layout_lines()` 输出行矩形与字形范围；表格一行可有多个并列文字行。`exr_layout_boxes()` 输出背景块、图片和单元格的页面坐标、边框与背景，按页及节点前序排列。page 的 line/box 范围可直接迭代。坐标单位为逻辑像素，原点在页面左上方。

宿主可先按 boxes 顺序绘制背景、图片和边框，再绘制文字。`exr_layout_image(layout, resource)` 返回对应资源的解码后 RGBA 借用视图；缺失时返回 NULL。这些输出可直接用于自定义渲染器，不需要创建内置页面位图。

## 图片、表格与像素

内置 `exr_image_decode()` 接受 PNG/JPEG 字节并返回独立 RGBA 像素，用 `exr_bitmap_free()` 释放。布局按资源缓存图片；图片保持纵横比，限制在内容宽度和可用页高之内。width/height 同时存在时按容纳方式缩放，图片当前独占块。缺失、外部、损坏或不支持的图片显示带标志的占位框；资源/解码限制错误会中止布局。解码尺寸上限 8192×8192 且总像素不超过 16 Mi，编码输入上限 32 MiB，stb 临时分配上限 128 MiB，布局图片缓存上限 64 MiB。

宿主设置 `decode_image`、`release_image` 和 `image_context` 可替换解码器。回调收到资源元数据及编码字节；返回 `channels=4`、非预乘 RGBA、有效 width/height/stride。引擎复制像素，然后无论成功或失败都调用配套 release 回调一次；不得在 release 中释放借用的编码输入。`EXR_FORMAT` 表示占位框，其余非成功状态中止布局。要保留内置 PNG/JPEG 支持，宿主回调可以调用 `exr_image_decode()` 并在 release 中使用 `exr_bitmap_free()`。回调及 context 只需在 layout create 调用期间有效，渲染不会再次调用它们。

表格采用等宽列，支持单元格换行、colspan 和 rowspan。具有跨行单元格的相连行组一起分页；高于一页的行组返回 `EXR_LIMIT`。上限为 64 列、4096 行/单元格、8 层嵌套。尚不支持按内容自动分配列宽、跨页拆分单元格、重复表头、垂直对齐和 border-collapse。单元格的可见边框、背景和内边距由样式控制。

`exr_render_page()` 输出 1 通道灰度；`exr_render_page_color()` 输出 4 通道 RGBA。内置渲染器使用白底、双线性图片缩放、透明合成和 FreeType 字形，整页位图不超过 64 MiB。`stride` 是每行字节数。PNG 支持两种通道并保留输入 alpha；BMP 写为 24 位并将 alpha 合成到白底。写入时 `channels=0` 兼容灰度输入。框架不提供窗口、GPU 或事件循环。

## 书库

SQLite 数据库保存原文件 BLOB、封面 BLOB、元数据和 UTF-8 位置标注。书籍主键为库内整数。格式在导入时验证；正文大小用于检查进度和标注范围。书库使用 application_id 与 schema version 检查，拒绝不认识的现有数据库。0.7 将 schema v1 事务迁移到 v2，原标注保留其偏移、备注和 ID，选择器保持 NULL，因此解析为 `LEGACY`；不从新版正文反推旧引文。单句修改使用 SQLite 事务语义，书籍删除通过外键清理笔记。

宿主应零初始化输入 `exr_note`。保存新标注时，`exr_library_note()` 为当前书籍正文捕获文本选择器；修改同范围标注的备注保留已有选择器。宿主可以显式提供 `note.anchor` 重新锚定，锚点的 `start/end` 必须与笔记范围一致。查询的 `exr_note.anchor` 由结果数组拥有，使用 `exr_notes_free()` 一次释放全部内容。稳定锚点保存历史文本证据，实际显示前应调用 `exr_anchor_resolve()` 并检查其状态。

`exr_library_backup()` 使用 SQLite VACUUM INTO 生成可直接打开的完整备份；目标数据库不能已有非空内容。封面作为受大小限制的 BLOB 存储；宿主可调用图片解码接口生成像素，封面不自动缩放。媒体大文件的流式导入尚未实现。现有 ZIP / IndexedDB 备份需要未来的迁移工具。

## 嵌入平台

宿主负责文件选择、字体提供、页面纹理显示、触摸 / 鼠标 / 键盘事件和系统生命周期。像素或布局数据可转为纹理或原生绘图命令。Android 可经 JNI 调用 C，Apple 平台可经 Objective-C / Swift 导入 C 头文件；当前尚未提供这些宿主适配器。
