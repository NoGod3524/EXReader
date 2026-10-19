# 模块与稳定核心

2026-10-19，C11 SDK3.33.1，MIT，ABI1，schema6。

## 核心与可选组件

`exr_core`是CMake组合目标，选择以下七个静态库；它自身不引入运行时包装层。宿主可直接链接其中更小的库。

| 目标 | 所有权与职责 | 允许依赖 |
| --- | --- | --- |
| `exr_base` | 错误/取消、源、内存、UTF/URI/CSS词法、坐标/视口、基本位图生命周期与输出 | 无项目内上层 |
| `exr_graphics` | 路径/描边、像素合成、画布、图片解码、可选ICC | base |
| `exr_text` | 字素/断行、双向、字体/字形、OpenType、断词、可变轴 | base、graphics |
| `exr_doc` | 开放文档树/构造、固定页provider、文本位置/锚点/CFI、文本标注交换 | text及其下层 |
| `exr_formats` | TXT/HTML/EPUB/FB2/DOCX/RTF/MOBI适配、资源、导航、转换与EPUB元数据 | doc及其下层 |
| `exr_layout` | 样式、行/表格/浮动/分页、显示文字投影、书内字体、publication/session | formats及其下层 |
| `exr_render` | 将排版结果适配到原生像素绘制 | layout及其下层 |

`exr_core`目前还组合内置重排格式适配，因为现有排版读取资源/书内字体、publication提供EPUB按章加载。只需模型与文本分析时直接选`exr_doc`/`exr_text`，无需音频、SQLite或PDF。后续若将格式适配再裁细，需先把这些资源访问归还通用文档provider，不能引入反向调用。

| 可选目标 | 内容与开关 | 依赖边界 |
| --- | --- | --- |
| `exr_pdf` | PDF/CBZ读取，`EXR_ENABLE_PDF` | formats；私有PDF密码库只挂在这里 |
| `exr_pdf_edit` | PDF批注与元数据写入，`EXR_ENABLE_PDF_EDIT` | pdf；核心/PDF读取不依赖编辑器 |
| `exr_audio` | 时间线、WAV/FLAC/MP3/AAC/M4B、PCM/WSOLA、设备输出，`EXR_ENABLE_AUDIO` | base；不依赖文档、字体或SQLite |
| `exr_library` | SQLite书库、笔记、进度和宿主音频续播数据，`EXR_ENABLE_LIBRARY` | formats；启用PDF时再链接pdf；无音频播放依赖 |
| `exr_textindex` | 独立SQLite全文索引，`EXR_BUILD_TEXT_INDEX` | base；不依赖书库或文档 |

SQLite仅在书库或索引存在时获取/构建。FAAD2默认关闭；`EXR_ENABLE_AAC=ON`只链接音频目标。核心自有代码保持MIT，包含FAAD2的最终组合二进制仍须遵守GPL，静态归档的分名不会改变该要求。

## 公开接口与版本

`include/exr/`有13个独立头，`core.h`包含阅读核心，`audio.h`、`library.h`、`pdf.h`、`pdf_edit.h`、`textindex.h`各自提供可选接口。原`exreader.h`保留为总入口。

默认`exreader`共享总库直接复用组件对象，Windows显式导出原304个函数；各静态目标自动传递`EXR_STATIC`。应用选择共享总库或静态组件一种接入方式，避免同一对象跨两个运行库实例释放。

版本在`cmake/versions.cmake`、对应头的版本宏和安装CMake目标的`EXR_COMPONENT_VERSION`中给出。核心/PDF读取当前为3.33.1，其余组件为3.33.0，之后可独立发布；本次分层按中等更新归入3.33.0，完整历史见[更新日志](../CHANGELOG.md)。现有核心签名、记录布局和所有权按ABI1保持兼容。显式关闭整个组件会省略其库和符号；关闭组件内部的编解码功能仍保留原有不可用查询接口。

```cmake
find_package(EXReader CONFIG REQUIRED COMPONENTS core)
target_link_libraries(reader PRIVATE EXReader::exr_core)
# 按需添加：EXReader::exr_audio / exr_library / exr_pdf / exr_pdf_edit / exr_textindex
```

安装包包含自包含的组件静态归档和必要的第三方私有归档；消费方无需源码目录或第三方头。`tests/sdk_components`以C/C++分别编译头文件并调用安装后的静态组件。`examples`依据已安装组件选择可构建的示例。JNI目前需要音频和PDF组件；纯核心SDK关闭`EXR_BUILD_JNI`。

## 内部头与依赖检查

基础、文档、字体、样式、图形和格式分别拥有私有头，原`src/internal.h`总头已移除。字体对象不再包含布局结构，正文转换也不再藏在基础输出文件。

`display_bidi.c`的调用者均为排版模块，函数处理生成字形、原文映射、文档字段和分页计划，因此归layout；Unicode双向分析本身仍在text。CBZ与固定格式打开分发归pdf组件。这两项是根据类型/职责修正归类，不作为运行时缺陷修复计数。

```sh
cmake --build build/native --parallel 4
python3 tools/check_layers.py build/native
```

检查器读取CMake记录的活动组件/源归属，只扫描实际对应的GNU/LLVM对象，忽略旧构建遗留的其他对象。新增未分类源、错误目标归属、循环、逆向符号调用或本地头包含都会失败。例外清单为空。源与本地头包含图会递归检查引号include的所有分支；第三方及构建生成的头由编译验证。该检查没有推导结构体成员的语义所有权，不能代替代码审查。

当前完整配置为99个对象、1021条跨文件符号引用、898条源/头依赖，两个方向的逆向计数都为0。纯核心配置为59个对象、586条符号引用、505条源/头依赖，逆向计数同为0。

## 验证范围

拆分前后304项函数声明，以及703项公开类型大小、对齐与成员偏移相同。13个头分别通过C/C++编译。原有131项完整回归加上核心、音频、书库、PDF编辑和文本索引的5项独立链接回归，合计136项；裁剪配置另跑相应组件检查。

完整构建、纯核心和无音频/PDF书库组合分别验收；跨平台CI还包括安装消费、sanitizer、fuzz与移动库交叉构建。逐次结果记录在[NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)。代码审计未关闭的PDF色彩/透明度、解析器/字体/媒体等逐路径问题见[审计记录](AUDIT-2026-10-19.md)。

分层代码`716235e`的[CI39328976671](https://github.com/NoGod3524/EXReader/actions/runs/39328976671)已7/7通过：三桌面各136/136，安装/裁剪组合全部通过；sanitizer133/133、20万次fuzz以及Android/Apple移动库构建通过。完整审计仍按未关闭项继续推进。

3.33.1组语义修复代码`d0a0b8d`的[CI39334889967](https://github.com/NoGod3524/EXReader/actions/runs/39334889967)同样7/7通过，三桌面各136/136、安装/裁剪/绑定及移动交叉编译均通过；结果见[本批原始记录](validation/2026-10-19-group-spaces-ci.json)。
