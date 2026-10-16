# Native C API 0.3

公开入口为 `include/exreader.h`；API 仍为实验性，尚未承诺二进制兼容。所有路径和字符串使用 UTF-8。所有 `exr_status` 函数返回 `EXR_OK` 表示成功；可选 `exr_error*` 接收错误详情。

## 所有权与并发

- `exr_document`、`exr_font`、`exr_layout`、`exr_library` 为不透明句柄，使用各自析构函数释放。
- document 的 text / title / blocks 和 layout 的 pages / lines / glyphs 为只读借用视图，所属对象释放后失效。
- 布局保存数值和位置，不保留文档指针。渲染时需传入生成该布局时使用的字体；字号变化由库设置。相同字体、布局或书库句柄的调用由宿主串行处理；不同句柄可独立使用。
- `exr_books_free()` / `exr_notes_free()` 释放数组和其中字符串。修改元数据时复制结构并用自己的字符串设置输入字段，不替换结果数组中的库拥有指针。
- `exr_bitmap_free()` 释放像素。`exr_document_export()` / `exr_library_blob()` 返回的字节用 `exr_free()` 释放。跨 DLL 调用时不要使用宿主 `free()` 释放库内存。
- 输出参数需为空或已先释放。对输入的任意无效 C 指针不提供运行时保护。

## 文档与排版

`exr_document_open()` 根据扩展名选择解析器；内存入口显式指定 `exr_format`。文本模型使用规范化 UTF-8；进度和标注保存规范化文本的字节偏移，不使用页码作为永久位置。宿主通过 `exr_layout_page_at()` 在重新排版后查找该位置，通过 `exr_layout_hit_test()` 将坐标映射回文字。当前位置规范属于 0.3 文档模型，不兼容旧 Foliate CFI。

输入上限 128 MiB、正文上限 64 MiB、布局上限约 400 万字形。ZIP 成员上限 32 MiB、条目上限 1 万、累计解压上限 128 MiB。XML 不解析外部实体，拒绝实体声明；HTML 的脚本和样式不进入正文。所有排版在内存中完成，长书暂未实现按页懒排和页缓存。

FreeType 提供真实字形 advance、kerning 和像素，不负责分页。EXReader 自己决定段落、换行、分页、基线和字形位置。当前字体只按 Unicode 标量取字形，复杂 OpenType shaping、双向文字和完整 grapheme / line break 算法仍需扩展。

正文查找为区分大小写的 UTF-8 子串查询。元数据搜索使用绑定参数的 SQLite LIKE，并转义 `%` / `_`，其大小写折叠规则为 SQLite 默认规则。

## 书库

SQLite 数据库保存原文件 BLOB、封面 BLOB、元数据和 UTF-8 位置标注。书籍主键为库内整数。格式在导入时验证；正文大小用于检查进度和标注范围。书库使用 application_id 与 schema version 检查，拒绝不认识的现有数据库。单句修改使用 SQLite 事务语义，书籍删除通过外键清理笔记。

`exr_library_backup()` 使用 SQLite VACUUM INTO 生成可直接打开的完整备份；目标数据库不能已有非空内容。封面目前作为受大小限制的 BLOB 存储，框架尚不解析或缩放封面图片。媒体大文件的流式导入尚未实现。现有 ZIP / IndexedDB 备份需要未来的迁移工具。

## 嵌入平台

宿主负责文件选择、字体提供、页面纹理显示、触摸 / 鼠标 / 键盘事件和系统生命周期。像素输出为 8 位灰度，可转为纹理或原生绘图缓冲。Android 可经 JNI 调用 C，Apple 平台可经 Objective-C / Swift 导入 C 头文件；当前尚未提供这些宿主适配器。
