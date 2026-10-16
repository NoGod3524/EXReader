# Native C API 0.4

公开入口为 `include/exreader.h`；API 仍为实验性，尚未承诺二进制兼容。所有路径和字符串使用 UTF-8。所有 `exr_status` 函数返回 `EXR_OK` 表示成功；可选 `exr_error*` 接收错误详情。

## 所有权与并发

- `exr_document`、`exr_font`、`exr_layout`、`exr_library` 为不透明句柄，使用各自析构函数释放。
- document 的 text / title / blocks / nodes / chapters / resources 和 layout 的 pages / lines / glyphs 为只读借用视图，所属对象释放后失效。树节点属性和文本也属于 document。
- 布局保存数值和位置，不保留文档指针。渲染时需传入生成该布局时使用的字体；字号变化由库设置。相同字体、布局或书库句柄的调用由宿主串行处理；不同句柄可独立使用。
- `exr_books_free()` / `exr_notes_free()` 释放数组和其中字符串。修改元数据时复制结构并用自己的字符串设置输入字段，不替换结果数组中的库拥有指针。
- `exr_bitmap_free()` 释放像素。`exr_document_export()` / `exr_document_resource()` / `exr_library_blob()` 返回的字节用 `exr_free()` 释放。这些字节独立于原对象的生命周期。跨 DLL 调用时不要使用宿主 `free()` 释放库内存。
- 输出参数需为空或已先释放。对输入的任意无效 C 指针不提供运行时保护。

## 文档与排版

`exr_document_open()` 根据扩展名选择解析器；内存入口显式指定 `exr_format`。文本模型使用规范化 UTF-8；进度和标注保存规范化文本的字节偏移，不使用页码作为永久位置。宿主通过 `exr_layout_page_at()` 在重新排版后查找该位置，通过 `exr_layout_hit_test()` 将坐标映射回文字。0.4 的 EPUB 正文投影会分隔表格单元格、排除 hidden 元素，偏移可能与 0.3 不同；旧偏移未提供自动迁移，书库现有标注仍只有偏移。跨版本稳定标注和旧 Foliate CFI 转换是后续工作。

输入上限 128 MiB、正文上限 64 MiB、布局上限约 400 万字形。文档树上限 262144 个节点、字符串累计 64 MiB、每个元素最多 256 个属性。ZIP 成员上限 32 MiB、条目上限 1 万、打开期间累计解压上限 128 MiB；后续每次资源读取单独应用 32 MiB 上限，由调用者释放返回的字节。XML 嵌套上限 256 层，不解析外部实体，拒绝实体声明；HTML 的脚本和样式不进入正文。所有正文排版仍在内存中完成，长书暂未实现按页懒排和页缓存。

FreeType 提供真实字形 advance、kerning 和像素，不负责分页。EXReader 自己决定段落、换行、分页、基线和字形位置。当前字体只按 Unicode 标量取字形，复杂 OpenType shaping、双向文字和完整 grapheme / line break 算法仍需扩展。

正文查找为区分大小写的 UTF-8 子串查询。元数据搜索使用绑定参数的 SQLite LIKE，并转义 `%` / `_`，其大小写折叠规则为 SQLite 默认规则。

## EPUB 文档树与资源

`exr_document_nodes()` 返回前序排列的节点数组；0 为文档根。通过 `parent`、`first_child`、`next_sibling` 遍历。缺失索引为 `SIZE_MAX`。节点的 `chapter` 指向章节数组；文档根没有章节。节点索引只在当前 document 生命周期内有效，不能用作持久书签。

`exr_document_chapters()` 先按 spine 顺序返回章节，包括 `linear="no"`；再按 manifest 顺序追加尚未在 spine 中出现的 XHTML（例如 EPUB 3 nav）。`in_spine` 和 `linear` 标明阅读顺序属性。章节记录 manifest ID、规范化 ZIP 路径、根节点与资源索引。

文本节点的 `text` 保存 XML 解码后的原始空白和内容；元素的 `name` 与属性名采用 Expat 展开名 `namespace-URI|local-name`，无命名空间时为原名。`exr_node_attribute()` 精确匹配名称，例如 `class`、`style`、`href`、`src`、`id`、`colspan`、`http://www.idpf.org/2007/ops|type`。元素名、内联样式、内嵌 style 文本、未知元素及其属性均保留。

节点 `start/end` 是规范化正文的半开 UTF-8 字节区间，与原始 XHTML 字节位置和 `strlen(node.text)` 不同。当前正文只包括线性 spine 章节；head、script、style、hidden 子树和辅助章节的范围均为 `SIZE_MAX`。没有文字的可见元素可以有零长度范围。辅助脚注和目录的树仍可访问，链接仍可指向它们。图片书可以成功打开并检查结构，但当前文字排版接口对没有正文的书返回 `EXR_FORMAT`。

EPUB 3 目录通过 nav 子树表达，层级由其中的 ol/li 保留。可用 `exr_node_attribute(node, "http://www.idpf.org/2007/ops|type")` 查找包含 `toc` 的标记。EPUB 2 NCX 暂只保留为原始资源。其他格式的树目前只提供原解析器已有的标题和段落，没有新增其结构解析。

`exr_document_resources()` 返回 manifest 清单，包含 ID、规范化路径、媒体类型和 properties（如 nav、cover-image）。document 保留一份压缩 EPUB；XHTML 在打开时解析，其他资源通过 `exr_document_resource()` 按需解压，不写临时文件、不请求网络。清单中的资源可能缺失或损坏，读取时返回错误。

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

CSS 目前保存供后续排版使用，正文投影尚不计算样式继承或 display。表格当前按单元格提取正文，图片尚未解码和绘制。现有导出接口仍为文本转换，会丢失图片、链接和样式。

## 书库

SQLite 数据库保存原文件 BLOB、封面 BLOB、元数据和 UTF-8 位置标注。书籍主键为库内整数。格式在导入时验证；正文大小用于检查进度和标注范围。书库使用 application_id 与 schema version 检查，拒绝不认识的现有数据库。单句修改使用 SQLite 事务语义，书籍删除通过外键清理笔记。

`exr_library_backup()` 使用 SQLite VACUUM INTO 生成可直接打开的完整备份；目标数据库不能已有非空内容。封面目前作为受大小限制的 BLOB 存储，框架尚不解析或缩放封面图片。媒体大文件的流式导入尚未实现。现有 ZIP / IndexedDB 备份需要未来的迁移工具。

## 嵌入平台

宿主负责文件选择、字体提供、页面纹理显示、触摸 / 鼠标 / 键盘事件和系统生命周期。像素输出为 8 位灰度，可转为纹理或原生绘图缓冲。Android 可经 JNI 调用 C，Apple 平台可经 Objective-C / Swift 导入 C 头文件；当前尚未提供这些宿主适配器。
