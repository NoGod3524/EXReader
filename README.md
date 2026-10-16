# EXReader — native C ebook engine

主项目已从 JavaScript 阅读框架重建为 **C11 原生阅读引擎**，当前版本 **0.8.0，开发中**。GPL-3.0-only。直接编译成 DLL / SO / dylib，以 C 接口供宿主调用。

文本解码、格式解析、文档模型、CSS 子集、换行、分页、文字位置、命中测试、页面像素合成和书库都在本项目 C 代码中。底层使用 FreeType、Expat、miniz、SQLite 和 stb_image 五个 C 组件，分别处理字体、XML、ZIP、数据库和 PNG/JPEG 解码。

框架面向通用宿主：宿主可以直接构造文档树和资源，将自己的解析结果交给引擎；文档树、资源、字形、行、图片和单元格坐标均可读取。宿主可以覆盖样式、关闭书内 CSS、替换图片解码器，或直接使用布局数据自行绘制。文档构造、解析和排版可独立于 SQLite 书库使用，UI、账号、同步和平台事件由宿主决定。

## 当前实现

| 模块 | 当前能力 |
| --- | --- |
| 文档输入 | TXT（UTF-8、带 BOM 的 UTF-16）、HTML、FB2、EPUB spine、DOCX 正文、RTF 正文、基础 MOBI / PalmDOC |
| 宿主文档构造 | `exr_document_create()` 接收通用节点、章节和资源字节，复制输入并生成规范化正文；宿主解析器无需注册，可直接接入现有搜索、布局、渲染和正文导出 |
| 分段按需加载 | 通用 publication / loader 接口；内置 EPUB 打开时只索引，访问某章时才解析和排版；session 以 LRU 保留 1–64 个分段 |
| EPUB 文档结构 | XHTML 文档树保留章节、标题、内联元素、嵌套列表、图片、表格、脚注、全部属性与原始解码文本；保留 EPUB 3 导航树、非线性章节和辅助 XHTML |
| EPUB 资源与链接 | manifest 资源清单、图片 / CSS / 字体等资源按需解压；支持章节相对路径、Unicode / 百分号转义与片段 ID 定位 |
| 自有排版 | 字体实际 advance / kerning、段落、标题字号、自动换行、基础中文标点规则、分页；页面宽高、字号、行距、段间距、页边距可调 |
| CSS 子集 | 章节样式表、内嵌和内联样式；元素 / 类 / ID / 后代 / 子选择器，优先级和继承；混合字号、粗斜体、颜色、对齐、缩进、边距、背景、实线边框和强制分页 |
| 图片与表格 | PNG/JPEG 解码、透明合成和等比缩放；等宽表格、单元格换行、colspan / rowspan、按行组跨页 |
| 原生渲染 | FreeType 字形栅格化，C 合成灰度或 RGBA 像素；BMP / PNG 输出，无图形界面依赖 |
| 文字定位 | UTF-8 字节位置、全文查找、坐标命中测试、按位置查页；改变页宽和字号后可重新定位 |
| 稳定文本锚点 | 保存选文、前后文和可选章节路径；正文前方增删后可重新查找范围，重复或失配明确报告；支持点书签，可独立于书库使用 |
| 原生书库 | SQLite 单文件保存原书、书名、作者、标签、收藏、已读状态、阅读位置、封面和笔记；删除书籍时级联删除标注；事务备份 |
| 文字转换 | C 输出 TXT、HTML、FB2、RTF、EPUB、DOCX；覆盖 Unicode 与文本转义往返，不保留复杂排版和图片 |

当前流式排版支持基础横排拉丁文字和中日韩文字。EPUB 和宿主构造的文档使用文档树进行样式、图片和表格布局；其他内置格式目前提供段落与标题。图片按块排版，表格采用等宽列，超过一页高度的行或 rowspan 行组返回 `EXR_LIMIT`。完整 CSS、浮动绕排、字体族选择、双向文字、复杂文字 shaping、UAX #14 / #29 的完整规则、竖排、连字符、EPUB CFI / 跨引擎标注迁移均待实现。PDF 固定版面引擎、KF8 / Huffman MOBI、CBZ、音频播放和 OCR 也尚未完成；PDF 文件当前返回不支持。具体 CSS 支持范围见 [接口文档](docs/NATIVE_API.md)。

0.7 提供稳定标注的文本锚点基础：精确选文至少需要一侧完整上下文或文档 / 章节边界佐证，同分候选返回歧义，不猜测旧偏移附近的位置。不提供模糊改字匹配、Unicode 规范化、grapheme 边界或文档指纹；旧书库标注保留为仅偏移的 legacy 记录，不自动认定已迁移。宿主可自行持久化选择器字段，正文格式转换不携带标注。

0.8 新增分段加载和逐段排版。宿主可提供任意格式的独立分段文档；EPUB 内置 loader 共享一份压缩书籍，按需解析 XHTML。缓存容量按分段数量计算，单章仍完整解析和排版，临时加载可多占一个分段；尚无页级续排和内存字节硬上限。页号、节点索引和正文偏移均为分段局部值，整书页数需逐段排版后才能确定；现有 SQLite 书库仍使用全书文档模型。

接下来的实现顺序：更完整的文字排版 → PDF 和有声书；新增能力继续使用开放的文档与资源接口。大书后续仍需页级续排、单个超长章节处理和更细的内存预算。EPUB 正文使用严格 XHTML 解析，未实现 HTML5 错误恢复、EPUB 2 NCX 目录解析、远程资源和元素级 base URI；原始 NCX 可通过资源接口读取。当前转换器仍输出正文，不保留文档树结构。

## 构建

需要 C11 编译器与 CMake 3.24+。首次配置联网下载五个固定版本的 C 组件，并验证 SHA-256；后续复用构建缓存。

```sh
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --config Release --parallel 4
ctest --test-dir build/native -C Release --output-on-failure
cmake --install build/native --config Release --prefix stage
```

Windows 推荐 Visual Studio C 工具链；MinGW 的部分 Ninja 发行版无法处理中文构建路径，需要通过 ASCII 路径的目录联接配置工程。MSVC 使用静态 CRT；所有库分配的内存由对应的 `exr_*_free()` 释放。

配置 `-DEXR_BUILD_TOOLS=OFF -DEXR_BUILD_TESTS=OFF` 只构建库。Linux 可用 `-DEXR_SANITIZE=ON` 启用 AddressSanitizer / UndefinedBehaviorSanitizer。Android、iOS 和 iPadOS 使用 CMake 对应工具链编译；该工程输出引擎库，不输出手机阅读器安装包。跨平台验证状态见 [验证记录](docs/NATIVE_VALIDATION.md)。

## 直接运行

```sh
exreader-render book.epub /path/to/font.ttf page.png 0 720 1040
```

Windows 的示例：

```powershell
.\stage\bin\exreader-render.exe tests/fixtures/sample.txt C:/Windows/Fonts/msyh.ttc page.png
```

字体由宿主或用户提供，系统字体文件不随项目分发。命令行可使用 UTF-8 / Unicode 路径；Windows 参数通过宽字符入口转换。

这是 C 引擎实际生成的页面：

![Native C styles, images and table rendering](docs/styled-page.png)

## C 接入

```c
#include <exreader.h>

exr_document *doc = NULL;
exr_font *font = NULL;
exr_layout *layout = NULL;
exr_bitmap image = {0};
exr_error error = {0};
exr_status status;

status = exr_document_open("book.epub", &doc, &error);
if (status == EXR_OK) status = exr_font_open("font.ttf", &font, &error);
if (status == EXR_OK) status = exr_layout_create(doc, font, NULL, &layout, &error);
if (status == EXR_OK) status = exr_render_page_color(layout, font, 0, &image, &error);
if (status == EXR_OK) status = exr_bitmap_write_png(&image, "page.png", &error);

exr_bitmap_free(&image);
exr_layout_free(layout);
exr_font_free(font);
exr_document_free(doc);
```

接入自己的解析器时，将解析结果写入前序节点数组，再调用构造入口：

```c
exr_node_input nodes[] = {
    {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
    {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
    {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
    {EXR_NODE_TEXT, 2, NULL, "Hello from a host parser.", NULL, 0}
};
exr_chapter_input chapter = {"main", "chapters/main", 1, 1};
exr_document_input input = {"Host document", nodes, 4, &chapter, 1, NULL, 0};
exr_document *doc = NULL;
exr_error error = {0};
exr_status status = exr_document_create(&input, &doc, &error);
/* On success, doc owns copies; pass it to the same layout/search/export APIs. */
exr_document_free(doc);
```

创建后的文档格式为 `EXR_CUSTOM`，输入数组、字符串和资源字节可在调用返回后释放。此入口不需要全局解析器注册表。自定义文档尚未提供结构化持久化；SQLite 书库仍按原文件字节导入。

SDK 附带完整宿主示例，可只使用安装后的头文件和库编译：

```sh
cmake -S stage/examples -B build/host -DEXR_SDK=/absolute/path/to/stage -DCMAKE_BUILD_TYPE=Release
cmake --build build/host --config Release
```

运行生成的 `exreader-construct-example`，传入字体文件和输出 PNG 路径，即可将自建文档排版为页面。`exreader-anchor-example` 无需字体和参数，演示保存选文并在正文插入内容后重新定位。构造接口的节点命名与 XHTML 行为约定见 [接口文档](docs/NATIVE_API.md)。

`exreader-lazy-example` 演示分段加载；默认创建三个宿主分段，只请求索引 1。提供 EPUB 和从 0 开始的分段索引时，改用内置 EPUB 索引：

```sh
exreader-lazy-example font.ttf host-part.png
exreader-lazy-example font.ttf epub-part.png book.epub 0
```

[公开头文件](include/exreader.h) · [接口与内存约定](docs/NATIVE_API.md) · [第三方许可](THIRD_PARTY_NOTICES.md)

## 版本保留

当前默认开发线直接使用 C 工程。此前的 [JavaScript 框架](https://github.com/NoGod3524/EXReader/commit/4533185)、[带 UI 的阅读器](https://github.com/NoGod3524/EXReader/tree/codex/reader-app) 和 [MIT 版 0.1.1](https://github.com/NoGod3524/EXReader/tree/codex/reader-0.1.1) 保留为历史版本。现有下载页仍是 0.1.1 阅读器；原生引擎目前与旧 UI、IndexedDB 书库和旧标注尚未接通。

Copyright (c) 2026 EXReader contributors. 自有代码为 GPL-3.0-only，第三方组件保留原许可；既有版本的 MIT 授权不撤回。
