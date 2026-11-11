# 宿主接入指南

SDK 提供同步的 C 调用；窗口、任务队列、设备像素比例、文件选择和持久化策略由宿主负责。完整可编译入口见 [分页示例](examples/pagination.c)、[渲染示例](examples/render.c)、[字体示例](examples/font.c) 和 [标注示例](examples/annotation.c)。逐函数契约见 [API.md](API.md)，格式边界见 [能力矩阵](CAPABILITY-MATRIX.md)。

## 1. 生命周期：create → open → layout → render → free

先用 `exr_font_manager_create` 或 `exr_font_manager_open` 建立字体目录，再用 `exr_font_manager_create_font` 为一个排版工作线程创建 `exr_font`。短文档可由 `exr_document_open` / `exr_document_open_memory` 读入，使用 `exr_layout_create_ex` 排完整文档；EPUB、MOBI/KF8、FB2 使用 `exr_publication_open`、`exr_publication_load` 或 `exr_session_create` 按分部读取。PDF/CBZ 走 `exr_fixed_open` → `exr_fixed_render`，没有可重排文档的分页步骤。

交互式重排通常选择 `exr_pager_create` → `exr_pager_next`，每次拿到一个独立的单页 `exr_layout`；渲染这个对象的页号始终是 0。若要随机访问和缓存，改用 `exr_pager_set_cache` → `exr_pager_get`，不要与 `next` 混用。大章节 EPUB 可用 `exr_publication_pager_create` 限制解析工作区；该适配器与完整文档快照的能力和限制不同。

| 资源 | 宿主释放方法 | 使用期间必须保活的对象 |
|---|---|---|
| 字体管理器 | `exr_font_manager_free` | 借用目录/家族/face 字符串的使用者结束后再释放 |
| `exr_font` | `exr_font_free` | pager/session 的字体必须活到其销毁；有效布局字体由 `exr_layout_font` 借出，不单独释放 |
| 文档 | `exr_document_free` | 普通 pager 借用的 document 必须活到 pager 销毁 |
| publication | `exr_publication_free` | session / publication pager 保留引用；provider context 等最后引用消失后才 release |
| `pager_next` / layout create 的布局 | `exr_layout_free` | 与同一 pager 产生的页面串行变更生命周期 |
| `pager_get` / `session_get` 的布局 | 不直接 free | 只借用；下一次缓存操作可能使旧视图失效，先完成渲染/复制 |
| `exr_bitmap.pixels` | `exr_bitmap_free(&bitmap)` | 异步上传纹理时，等上传消费结束再释放 |

退出时先取消并等待正在运行的 SDK 调用结束，停止使用借用视图，再释放位图、独立页面、pager/session、文档/publication、字体和管理器。所有带 `struct_size` / `size` 的配置先清零并填入对应 `sizeof`；有 `*_defaults` 的配置从默认值开始。输出对象先置零；重新赋值前释放旧输出，创建函数不会替宿主释放旧指针。

## 2. 事件循环：何时分页、何时渲染

SDK 不启动阅读工作线程，也不会主动请求窗口重绘。打开书籍后，将读取和第一页分页放到宿主串行 worker。`exr_pager_next` 返回 `EXR_OK` 且输出非 NULL 时，立即对该单页调用渲染，再把完成的位图移交 UI 线程。`EXR_OK` 且输出 NULL 表示 EOF；`next` 失败后要重建 pager。

翻页事件优先显示宿主缓存的位图；缓存未命中再请求 `get` 或顺序 `next`，可在 worker 空闲时预取相邻页。窗口尺寸、字号、字体链、行高或 CSS 改变时，先保存文本锚点，再取消旧任务、重建配置和 pager/session、解析锚点定位并重绘；旧页号不能作为新排版位置。仅背景颜色变化可对同一布局调用 `exr_render_page_background` 重新绘制。

`exr_control.cancelled` / `progress` 在当前调用线程同步执行。回调中只更新线程安全的取消标记、投递进度消息或复制需要的数据；不得重入或销毁正在执行的对象。`total == 0` 表示总量未知。UI 的取消信号需用宿主原子变量/锁传递，不能让另一线程在 SDK 调用未结束时 free。给每次排版请求一个宿主 generation；完成结果若不匹配当前 generation，释放而不显示。

同一 publication、pager、session、canvas、字典和索引句柄的调用/释放由宿主串行化。同一字体实例的排版、shaping、渲染也不能并发；即使参数标注 `const`，内部字体缓存仍可能变化。不可变的字体管理器允许多个线程并发查询，释放仍需等查询结束。[字体契约](../include/exr/font_manager.h)、[回调契约](../include/exr/base.h)。

## 3. 渲染目标：通道、stride、DPI

`exr_render_page` 输出 8-bit 灰度，`exr_render_page_color` 输出每像素 4 字节的 RGBA；`exr_render_page_ex` / `exr_render_page_background` 的 channels 只能为 1 或 4。RGBA 是按地址 R、G、B、A 排列的 straight alpha，颜色值为 `0xRRGGBBAA`，不是平台整数 BGRA。前三个入口以不透明白底开始；background 入口允许指定初始背景，书籍自身颜色仍按绘制顺序覆盖。

这些 API **分配并返回** SDK 位图，没有传入现成像素缓冲区或 GPU framebuffer 的接口。不要把宿主目标指针塞进输出结构体。逐行从 `pixels + y * stride` 复制 `width * channels` 字节；UI API 要求 BGRA、预乘 alpha、不同 stride 或底向上扫描时由宿主转换。输出像素左上原点、y 向下。SDK 当前紧密排列 `stride = width * channels`，宿主消费时仍读取返回的 stride。宿主自制 `exr_bitmap` 的 writer 输入允许 `stride >= width * channels`。位图上传后归还 `exr_bitmap_free`，不要跨 DLL 边界用宿主 `free`。[实现](../src/raster.c)、[位图写出](../src/core.c)。

重排 API 没有独立 DPI 参数：页面宽高和字体尺寸进入布局坐标，输出宽高为其向上取整。宿主要在同一坐标体系中应用设备比例，不能只放大位图宽高而保持字号/边距不变。可用 `exr_reader_style_config` 从 CSS 像素偏好生成带 scale 的内容区配置；按 `(left, top) * scale` 放置结果，点击坐标减去该偏移后交给命中测试。渲染整页像素预算为 64 MiB。

固定版面使用 `exr_fixed_render(document, page, scale, ...)`：原生 PDF 页面以 1/72 英寸点为基础，普通 PDF 的 `scale = target_dpi / 72`；`unit_scale`（如 PDF UserUnit）和旋转由页面 geometry 处理。用 `exr_viewport_create` 返回的 matrix 绘制、inverse 做屏幕到页坐标的命中测试；自定义 fixed provider 的单位取决于其 geometry，不能一概套 PDF 点数。[坐标实现](../src/viewport.c)。

## 4. 字体管理器：目录、回退链、预算

`exr_font_manager_options` 的 `struct_size` 设为 `sizeof`；`locations` 按优先顺序给目录或单文件，目录递归深度上限 8，识别 `.ttf/.otf/.ttc/.otc`。必需路径缺失/不可读返回 `EXR_IO`；可选路径设置 `EXR_FONT_LOCATION_OPTIONAL`，由 skip/summary 查询原因。`EXR_FONT_MANAGER_PLATFORM_DIRECTORIES` 在显式位置之后追加平台目录；需要可复现字体结果时只提供固定字体目录。`cache_path` 可持久化索引；失效缓存自动重扫，缓存写入失败只记录在 summary，不能因此把一次成功的字体扫描判作失败。

回退顺序为请求家族最接近样式 → 请求家族其他样式 → `fallback_families` → serif → sans-serif → 其余已发现字体补充覆盖。末尾优先色彩字体，再按新增 Unicode scalar 覆盖选择；去掉重复或不增加覆盖的 face。链最多 32 face；`serif_families` 和 `sans_serif_families` 同时为空字符串可关闭最终 discovered tail。`exr_font_manager_pick` 只验证 scalar cmap 覆盖，不能证明整个 emoji/复杂脚本序列可正确塑形；无覆盖返回 `EXR_OK`、face `SIZE_MAX`、step NONE。

管理器创建字体的总输入预算为 256 MiB，普通 `exr_font_create` 是 128 MiB；它们不是任意可配置的 `byte_budget` 字段。嵌入字体与回退字体共用 32 face / 256 MiB 管理限制；配置 `embedded_fonts = 0` 可只使用宿主字体链。管理器最多索引 65536 face。`create_font` 重新读取字体文件，已丢失/变化或超预算的 face 可能被省略，检查返回映射和缺字标志。

分页预算另设：`exr_pager_set_cache` 管页面数量/载荷；`exr_pager_set_checkpoints` 管回放检查点；`exr_chapter_options.workspace_budget` 管章节解析工作区；session 的 `exr_session_set_budget` 不包括共享字体、源数据、临时解析和渲染位图。宿主应分别计量，不能把页面缓存预算当整个进程内存上限。[字体管理器](../include/exr/font_manager.h)、[分页预算](../include/exr/layout.h)。

## 5. 标注：锚点、保存与恢复

`exr_anchor` 包含 `start/end`（规范化文档文本的 UTF-8 字节半开区间）、`exact`（选文）、`prefix/suffix`（前后语境）和可选 `chapter` 路径范围。`exr_anchor_create` 最多复制 64 KiB 选文和两侧各 32 个 Unicode scalar；空区间用于点书签。创建输出中的字符串归调用者，用 `exr_anchor_free`。不要将 C 结构体原样写磁盘：指针、`size_t` 宽度及地址不构成可移植存档。

持久化记录应包含宿主稳定 source ID、内容 revision/hash、稳定 part/path、锚点各字段、评论文本和记录版本；数字用足够宽的整数或十进制字符串保存，NULL 与空字符串区分。`exr_content_anchor` / `exr_text_range` 支持跨 part 范围；part 是目录索引而不是全书偏移。CFI 的 DOM 文本 offset 是原始节点 UTF-16 code units，与这些规范化 UTF-8 字节偏移不能互换。

恢复时先重新打开相同内容，再调用 `exr_anchor_resolve` / `exr_anchor_resolve_ex` 或 bounded pager 的 anchor resolve；只有 `match.state == EXR_ANCHOR_FOUND` 才能绘制高亮/跳转。`EXR_OK` 也可能是 MISSING、AMBIGUOUS 或 LEGACY，保留注释并标记待定位，不猜测附近旧 offset。得到范围后按当前布局重新求页号和矩形。

SDK 自带 SQLite library 可用 `exr_library_note/notes` 保存普通重排笔记；bounded EPUB 使用 `exr_library_epub_note/notes` 和 `exr_epub_location`（part/path/selector），不能把它当全书 offset 模式。两类 note ID 分属不同接口命名空间。固定版面用 `exr_fixed_anchor`（page_id、页内字节区间、quote context）及 fixed notes；扫描页没有文本层时不支持文字锚点，SDK 不执行 OCR。查询的 note 数组用各自 `*_notes_free`，不能仅释放数组首地址。

跨应用交换可用 `exr_text_annotation_export/import` 的 Web Annotation JSON：其紧凑 profile 保存 source、评论与 TextQuoteSelector，不携带 SDK offset/chapter，导入后必须在宿主选定文档/part 内重新 resolve。写文件时先写临时文件再原子替换，数据库写入完成后再通知 UI“已保存”。[锚点与交换](../include/exr/document.h)、[库持久化](../include/exr/library.h)。

## 文本时序图

```text
UI / 事件循环             宿主串行 worker            SDK                    宿主存储
    | 打开(source, generation)  |                     |                         |
    |-------------------------->| manager create/open |                         |
    |                           |-------------------->| 扫描/缓存字体           |
    |                           | create_font + open  |                         |
    |                           |-------------------->| doc/publication          |
    |                           | pager create        |                         |
    |                           |-------------------->| 保存配置，建立分页状态    |
    | 首屏/下一页请求           | next/get            |                         |
    |-------------------------->|-------------------->| 同步排版；回调进度/取消   |
    |                           |<--------------------| layout 或 EOF/错误        |
    |                           | render(page 0)      |                         |
    |                           |-------------------->| 分配灰度/RGBA bitmap      |
    |<--------------------------|<--------------------| bitmap + stride           |
    | 校验 generation / 上传纹理|                     |                         |
    | 纹理消费完成 → bitmap free|                     |                         |
    | 选择文本/保存笔记         | anchor create       |                         |
    |-------------------------->|-------------------->| quote + UTF-8 range       |
    |                           |---------------------------------------------->|
    |                           |                      事务保存/原子替换         |
    |<--------------------------|<----------------------------------------------|
    | 尺寸/字体变化             | 保存锚点、取消并等待旧调用完成                 |
    |-------------------------->| 重建 pager → resolve → layout → render        |
    | 关闭                      |                     |                         |
    |-------------------------->| 等待调用结束，释放 bitmap/layout/pager         |
    |                           | 释放 document/publication/font/manager         |
```

`get` 返回的是借用布局，图中的 `layout free` 仅适用于 `next` 或独立 create 所有的布局。UI 和 worker 交换结果时转移明确的所有权；进度/取消回调不是另一个 SDK 线程。
