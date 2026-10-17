# Native C API 0.27

公开入口为 `include/exreader.h`；API 仍为实验性，尚未承诺二进制兼容。0.12 新增独立双向分析与 OpenType 塑形接口，`exr_glyph` 末尾增加 `offset_x/offset_y/bidi_level`，`exr_layout_config` 末尾增加段落 `direction`，并增加 `EXR_GLYPH_SHAPED` 标志。宿主需使用匹配版本的头文件和库重新编译。所有路径和字符串使用 UTF-8。所有 `exr_status` 函数返回 `EXR_OK` 表示成功；可选 `exr_error*` 接收错误详情。

0.12.1 修复审计发现的长附标序列塑形开销、重复章节锚点、超限备注写入、XML 非法字符导出、跨行塑形上下文、RTF Unicode fallback 和 HTML script/style 原始文本处理；`exr_library_note()` 同时支持输出 ID 指向输入 `note.id`。回归覆盖见 [验证记录](NATIVE_VALIDATION.md#0121-audit-fixes)。

## 所有权与并发

### 取消和进度

0.16 提供 `exr_control`：可选 `cancelled(context)`、`progress(context,stage,completed,total)` 和借用的 context。回调同步运行在调用线程，引擎不创建后台线程，也不调度 UI；宿主负责选择工作线程。stage 区分随机读取、样式、分页、塑形和绘制，total 为 0 表示未知；嵌套塑形片段或新的资源操作会重新开始自己的局部计数。回调不能销毁或重入正在访问的对象。

通过 `exr_layout_config.control` 控制布局/分页，通过 `exr_shape_options.control` 控制独立塑形，通过 `exr_source.control` 控制读取。`exr_pager_set_control(pager,&control,error)` 可在非忙碌状态替换回调，传 NULL 关闭。取消是协作式的，在阶段边界、文本/lookup 工作批次和图片绘制行批次检查。分页的整段双向分析及依赖库调用会在其相邻检查点响应取消。

取消返回 `EXR_CANCELLED`，失败输出保持 NULL/0。借用分页模式保留之前的页缓存，命中缓存不运行取消回调；解除取消后，下次未命中可从检查点恢复。顺序 `next()` 在任何错误后仍需重建 pager。`exr_render_page_ex(layout,font,page,channels,&control,&bitmap,error)` 接受 channels 为 1 或 4，取消释放并清空部分位图。原来的绘制函数等价于不传 control；绘制调用的 context 只需在这次调用期间有效。

随机读取回调的 control 随源描述符复制，context 必须与保留的源同寿命；布局/分页的 control 随配置复制，context 必须维持到相应工作结束。返回的独立页面不持有布局时的控制回调，之后可用不同的 control 绘制。配置、塑形参数和源描述符在 0.16 扩展了字段，需重新编译宿主。

- `exr_document`、`exr_font`、`exr_layout`、`exr_library`、`exr_publication`、`exr_session`、`exr_pager`、`exr_bidi` 为不透明句柄，使用各自析构函数释放。
- document 的 text / title / blocks / nodes / chapters / resources 和 layout 的 pages / lines / glyphs / boxes / image 为只读借用视图，所属对象释放后失效。树节点属性和文本也属于 document。借用的图片像素不可修改或释放。
- 布局拥有输出数据及所引用的图片像素，不保留文档指针。文档释放后仍可绘制；需要源节点内容或资源名称时保留文档。渲染时需传入生成该布局时使用的同一个字体集句柄；字号变化由库设置。相同字体、布局或书库句柄的调用由宿主串行处理；不共享对象的独立句柄可独立使用。共享 publication、session、pager 或压缩 archive 的文档，其调用及生命周期变更也由宿主串行处理；引擎没有全局状态或内部线程锁。
- `exr_books_free()` / `exr_notes_free()` 释放数组和其中字符串；后者也释放每条笔记的锚点字符串。修改元数据时复制结构并用自己的字符串设置输入字段，不替换结果数组中的库拥有指针。
- `exr_anchor_create()` 输出独立拥有的选文、前后文和章节路径字符串，由 `exr_anchor_free()` 释放；输入文档随后可释放。宿主也可直接提供选择器字段供只读解析，但不能用库的释放函数释放宿主借用的字符串。
- `exr_bitmap_free()` 释放像素。`exr_document_export()` / `exr_document_resource()` / `exr_library_blob()` 返回的字节、`exr_text_analyze()` 的边界表、`exr_shape()` 的字形数组和 `exr_bidi_reorder()` 的视觉索引数组，用 `exr_free()` 释放。它们独立于原对象或输入的生命周期。`exr_bidi_scalars()` 则是属于分析句柄的借用视图。跨 DLL 调用时不要使用宿主 `free()` 释放库内存。
- 输出参数需为空或已先释放。对输入的任意无效 C 指针不提供运行时保护。
- 同一 pager 产生的独立页可以在 pager 和文档释放后使用；这些页会共享不可变图片，页的生命周期变更也由宿主串行处理。
- `exr_document_create()` 在调用期间复制输入数组中的字符串、属性和资源字节；返回后可释放所有输入。失败时不交出部分文档，`*out` 为 NULL。
- `exr_publication_create()` 复制标题和分段元数据，不复制 loader context。若提供 release 回调，创建成功后由 publication 在最后一个 publication / session 引用释放时恰好回调一次；创建失败时仍由宿主清理 context。release 为 NULL 时不自动释放 context，宿主必须使其在全部 publication / session 生命周期内有效。
- `exr_publication_load()` 返回宿主拥有的独立文档，用 `exr_document_free()` 释放。`exr_session_get()` 返回借用文档和布局，契约有效期至下次 get / set_budget / clear / free；宿主不得释放这些指针。
- `exr_pager_next()` 返回宿主拥有的独立单页布局，用 `exr_layout_free()` 释放；可在 pager 和 document 释放后继续绘制。`exr_pager_get()` 返回借用单页布局，有效期至下次 get / set_cache / free，不由宿主释放。一个 pager 只能选择其中一种访问模式。

## 文档与排版

`exr_document_open()` 根据扩展名选择解析器；内存入口显式指定 `exr_format`。文本模型使用规范化 UTF-8；进度和标注范围使用规范化文本的字节偏移，不使用页码作为永久位置。宿主通过 `exr_layout_page_at()` 在重新排版后查找该位置，通过 `exr_layout_hit_test()` 将坐标映射回文字。0.7 的文本锚点可以在正文投影变化后重新寻找选文；阅读进度仍为偏移。0.4 的 EPUB 正文投影会分隔表格单元格、排除 hidden 元素，偏移可能与 0.3 不同；旧标注只有偏移，迁移后仍明确标为 legacy，不能把当前正文中的同一数字偏移当作历史选文。旧 Foliate CFI 转换尚未实现。

输入上限 128 MiB、单文档正文上限 64 MiB、单次文档排版工作上限约 400 万字形。文档树上限 262144 个节点、字符串累计 64 MiB、每个元素最多 256 个属性。ZIP 成员上限 32 MiB、条目上限 1 万、打开期间累计解压上限 128 MiB；后续每次资源读取单独应用 32 MiB 上限，由调用者释放返回的字节。XML 嵌套上限 256 层，不解析外部实体，拒绝实体声明；HTML 的脚本和样式不进入正文。单个 document 仍完整解析；publication 可按章节加载，pager 在该 document 内按页续排。`exr_layout_create()` / `exr_layout_create_ex()` 使用同一续排引擎读到末尾并合并为完整布局。

HTML 的 script/style 内容按原始文本跳过，内部的 `<`、引号和伪标签不会吞掉后续正文，只有完整匹配的结束标签终止该区域。RTF `\uN` 后的 fallback 按 `\ucN` 计数：控制词、控制符号和 hex escape 各计一项，`\binN` 连同其二进制数据计一项；未转义的组边界终止跳过，原始 CR/LF 不消耗计数。

FreeType 提供字体、基础字形度量和像素，不负责分页。EXReader 自己决定字素边界、OpenType 替换与定位、双向级别、段落、换行、分页、基线和视觉位置。0.9 的 Unicode 17.0.0 扩展字素规则保护换行与命中位置；换行机会仍使用下述 UAX #14 子集。0.12 的原生 GSUB / GPOS 引擎支持拉丁连字与附标、阿拉伯连接形，Unicode UAX #9 决定逐行视觉次序；脚本范围和布局限制见下节。

正文查找为区分大小写的 UTF-8 子串查询。元数据搜索使用绑定参数的 SQLite LIKE，并转义 `%` / `_`，其大小写折叠规则为 SQLite 默认规则。

## 宿主字体集与缺字回退

0.13 支持 CSS `font-family` 列表、引号、CSS 转义、继承和宿主覆盖。指定名称先匹配书内字体，再匹配宿主字体的 FreeType family name，ASCII 字母不区分大小写；无匹配或缺字继续使用宿主的有序回退，不扫描系统字体。选脸按 family 顺序以及常规/粗体/斜体描述符匹配；整字素簇覆盖继续优先。字体已提供的粗斜体不重复合成。

`exr_layout_config_defaults()` 默认开启 `embedded_fonts`。EPUB/宿主 XHTML 的链接或内嵌样式表可声明 `@font-face`，支持 TTF/OTF、相对于 CSS 自身路径的 `url()` 和多个候选来源；只加载可见样式实际引用的 family，书内声明限于所属章节。`local()`、远程 URL 和本机文件 URL 不会访问系统或网络；缺失/损坏字体继续尝试下一来源，最终回退到宿主字体。关闭 `embedded_fonts` 仍可使用宿主字体名称；关闭 `document_css` 不加载书内声明，宿主 `user_css` 仍有效。混合字体集最多 32 个 face、编码字节合计 128 MiB，单次布局字体资源读取合计 128 MiB；最多 64 条字体声明，每声明最多尝试 8 个存在的本地候选资源。压缩 WOFF/WOFF2、EPUB 字体混淆解码和可变字体选择尚未实现。

`exr_layout_font(layout)` 返回有效字体集的借用句柄，`glyph.font_index` 索引该集合。`exr_font_source(font,index,&input,error)` 提供借用的编码字节与 face index，供宿主自行绘制；不要释放或修改借用数据。内置渲染器接受该有效集合、创建布局时的宿主字体，或 NULL（使用布局持有的字体）；传入其他集合仍按旧接口处理。页面持有字体引用，释放 document、pager 和原字体后仍可绘制。共享字体与字体表不计入页面缓存载荷预算。0.13 扩展了配置结构，宿主应使用同版本头文件重新编译。

`exr_font_open(path, ...)` 保留单文件、集合首个 face 的入口。`exr_font_create(inputs, count, ...)` 接收有序 `exr_font_input` 数组，每项为编码字体字节 `data/size` 和集合内的 `face_index`（普通字体为 0）。成功时复制全部输入，宿主随后可以释放或修改字节。字体集不可变，用 `exr_font_free()` 释放；布局、渲染和 session 通过现有字体参数接入，无需额外平台后端。字体集需在布局计算、渲染及 session 生命周期内有效，相同句柄的访问由宿主串行处理。

只接受 1–32 个可缩放、具有 Unicode cmap 的 face，累计输入字节上限 128 MiB。缺失输入、空字节或大于 `INT_MAX` 的 face index 返回 `EXR_ARGUMENT`；超限返回 `EXR_LIMIT`；损坏、不支持、没有 Unicode cmap 或不存在的 face 返回 `EXR_FONT`。复制失败返回 `EXR_MEMORY`。失败时清理已创建的部分，`*out = NULL`。文件入口仍支持 UTF-8 路径。

```c
exr_font_input sources[] = {
    {primary_bytes, primary_size, 0},
    {fallback_bytes, fallback_size, 0}
};
exr_font *fonts = NULL;
exr_status status = exr_font_create(sources, 2, &fonts, &error);
/* Font bytes can now be released. Use fonts for both layout and rendering. */
```

`exr_font_count(fonts)` 返回输入项数量，NULL 返回 0。`exr_font_has_glyph(fonts, index, scalar)` 查询指定 face 的 Unicode cmap 是否提供非零字形号；无效句柄、索引、Unicode 标量或缺字返回 0。这只代表标量覆盖，不代表 emoji 序列、连字、GSUB / GPOS 或变体序列支持。

排版优先寻找能覆盖整个可见字素簇的首个 face，跨内联样式也保持该选择。HIDDEN 条目不参与覆盖要求；tab 按空格检查并保留四倍 advance。没有单一 face 能覆盖整个簇时，各可见标量分别选择首个有字形的 face，字素边界继续保持完整。所有 face 都缺失的标量使用输入 0 的 glyph 0，并设置 `EXR_GLYPH_MISSING = 8`；它仍被绘制为该字体的缺字字形。HIDDEN 条目不设置 MISSING。

`exr_glyph.font_index` 是字体输入数组的索引，`glyph` 是该 face 内部的字形号。行高取实际所选 face 的最大 ascent/descent；塑形片段使用自己的 GPOS / legacy kern 结果，不再重复计算字偶距。灰度与 RGBA 栅格器使用同一个 face 选择；自定义渲染器必须同时使用 `font_index` 和 `glyph`。隐藏条目的字体索引没有绘制意义。该索引仅属于当前字体集，不能保存为跨会话字体标识。

框架不查找、下载或自带阅读字体，不实现 CSS `font-family` 匹配、自动读取 EPUB 字体、可变字体轴设置或彩色字形。整簇选字体依据 cmap，而非塑形结果。宿主负责提供字体字节、顺序、持久身份与许可。`examples/font.c` 演示读取两份字体、构造字体集、打印选择并渲染 PNG；支持 Windows Unicode 参数和文件路径。SDK 的 `examples/fonts` 是原创几何测试字形，不能用作正式阅读字体。

## 独立 OpenType 塑形

`exr_shape(font, font_index, utf8, size, options, &glyphs, &count, error)` 对一个字体 face 的单一方向 / 脚本片段进行塑形，输出逻辑次序的 `exr_shaped_glyph` 数组，使用 `exr_free()` 释放。调用者划分字体、脚本和方向片段；接口本身不执行双向视觉重排。输入字节和 options 只在调用期间借用。font 与 layout / shape / render 的访问需串行。

`exr_shape_defaults()` 返回 24 px、AUTO 方向、无合成样式、自动脚本和默认语言。`font_size` 接受 4–256 px，`style_flags` 只接受 BOLD / ITALIC；direction 为 AUTO / LTR / RTL。`script`、`language` 和 feature tag 使用 `EXR_TAG('l','a','t','n')` 这样的四字节 OpenType 标记，language 不是 BCP 47 字符串。script 为 0 时根据 Unicode Latin / Arabic 属性选择，否则使用 DFLT；language 为 0 使用默认 LangSys。请求脚本或语言未提供时，使用字体可用的 DFLT / 默认语言记录。

`features` 是最多 256 个 `{tag,value}` 的借用数组。value 为 0 禁用可选 feature，非零启用；Alternate lookup 的 value 是从 1 开始的替代项序号。默认替换阶段为 ccmp / locl、Arabic isol / fina / medi / init、rlig / rclt / calt / liga / clig；定位阶段为 curs / kern / mark / mkmk。字体的必需 feature 仍被执行；宿主还可请求字体提供的其他 feature。`context_before/after` 为片段两侧最近的非透明 Unicode 标量，0 表示边界，用于跨样式片段保留 Arabic 连接状态。

```c
exr_shape_options options = exr_shape_defaults();
exr_shaped_glyph *glyphs = NULL;
size_t count = 0;
options.font_size = 20;
options.script = EXR_TAG('l','a','t','n');
options.direction = EXR_DIRECTION_LTR;
exr_status status = exr_shape(font, 0, "ffi", 3, &options, &glyphs, &count, &error);
/* A font with a matching liga rule can return one glyph for UTF-8 range [0,3). */
exr_free(glyphs);
```

`start/end` 为输入 UTF-8 的源簇半开范围。连字可以合并多个字素，附着的 mark 与其所属簇共享范围；字形数不必等于标量数。`advance_x/advance_y` 和 `offset_x/offset_y` 均以 px 表示，x 向右、y 向上，offset 相对逻辑 pen；接口保留 GPOS 的两个 advance 分量。BOLD / ITALIC、HIDDEN / MISSING 使用现有 glyph 标志。缺字使用该 face 的 glyph 0；此入口不执行字体回退。隐藏格式字符保留源范围且不产生 advance。

自有解析器处理 GSUB 1–8 和 GPOS 1–9，包括单字形 / 多字形 / 替代 / 连字、上下文及链式上下文、extension、reverse substitution、单字 / 字偶 / class-pair 定位、cursive 和 mark-to-base / ligature / mark。Context 和 ChainContext 支持 1 / 2 / 3 格式，GDEF 用于类别、lookup flags 和 mark 过滤；anchor 支持设计坐标、轮廓点和普通 Device 修正。Latin 和 Arabic 有对应预处理，Arabic 透明字符与 ZWJ / ZWNJ 影响连接形。

输入上限 64 MiB、输出上限约 400 万字形，字体 OpenType 表累计上限 64 MiB；上下文最多 256 项，嵌套 lookup / attachment 有深度和工作量限制。空输入 `NULL,0` 成功，输出 NULL、count 为 0。无效 UTF-8 返回 `EXR_ENCODING`，参数错误返回 `EXR_ARGUMENT`，超限返回 `EXR_LIMIT`，损坏或不支持的 OpenType 数据返回 `EXR_FONT`；失败清空输出指针和 count。

当前未实现 Unicode canonical normalization / 规范重排、Indic / USE 音节分析与前置元音重排、AAT / morx、字体 variation / FeatureVariations / ItemVariationStore、cmap 14 变体序列、孤立 mark 的 dotted-circle 补字、彩色字形和竖排。选中的 VariationIndex 定位数据明确返回 `EXR_FONT`。

## 独立双向分析与段落方向

`exr_bidi_analyze(utf8, size, direction, &bidi, error)` 实现 Unicode 17.0.0 UAX #9 段落分析，direction 为 AUTO（首个强字符决定）、LTR 或 RTL。结果复制标量与源偏移，不借用输入；`exr_bidi_scalars()` 返回按逻辑顺序排列的 `{start,end,codepoint,level}` 借用视图。level 为 `UINT_MAX` 表示 X9 移除的格式控制。

`exr_bidi_reorder(bidi, first, count, &order, &out_count, error)` 对一个已选行片段应用 L1 / L2，输出视觉顺序的绝对标量索引，排除 X9 控制；first / count 是标量索引，不是 UTF-8 字节偏移。order 使用 `exr_free()` 释放，分析对象用 `exr_bidi_free()` 释放。空片段返回 NULL 和 0。该接口只返回次序，不改写输入、执行字形替换或绘制镜像。

```c
exr_bidi *bidi = NULL;
size_t scalar_count = 0, visual_count = 0, *order = NULL;
exr_status status = exr_bidi_analyze(text, text_bytes, EXR_DIRECTION_AUTO, &bidi, &error);
if (status == EXR_OK) {
    exr_bidi_scalars(bidi, &scalar_count);
    status = exr_bidi_reorder(bidi, 0, scalar_count, &order, &visual_count, &error);
}
exr_free(order);
exr_bidi_free(bidi);
```

输入需为有效 UTF-8，最多 64 MiB / 约 400 万标量；空字符串允许，NULL 输入返回 `EXR_ARGUMENT`。显式长度允许分析嵌入 NUL。非法编码返回 `EXR_ENCODING`，超限返回 `EXR_LIMIT`。完整 `BidiTest.txt` 和 `BidiCharacterTest.txt` 的 861,948 个段落方向用例检查级别与视觉索引；字体绘制由独立布局测试覆盖。

布局使用 `exr_layout_config.direction` 设置段落基础方向，默认为 AUTO；块级 `dir="ltr|rtl|auto"` 和 CSS `direction:ltr|rtl` 可以覆盖。`text-align:start/end` 随段落方向定位，left/right 保持物理方向。内联 dir / CSS direction 当前不自动建立嵌入或隔离，宿主需通过显式 Unicode LRE / RLE / LRI / RLI / FSI / PDI 等文本控制表达。

集成排版先解析当前可见段落的双向级别，暂定塑形用于选择断点，再以真实行边界重新塑形并拟合宽度，最后按簇视觉重排；奇数级别查询镜像字形。carry 保留原始源记录，行首不继承上一行的 Arabic 连接形、cursive 或字偶定位。拟合保留连字、字素簇和 GLUE 边界，必要时回退到更早的合法断点；不可拆首簇继续使用裁剪规则。普通排版、页级续排和表格单元格使用同一行队列。

同字体同字号的簇内颜色 / 粗斜体变化使用簇首样式；不同字号仍分开塑形，跨字号 mark 定位有限。未闭合塑形段最多 8192 个标量。行队列的原始、暂定、最终三个驻留字形数组按已分配容量合计限制为 16 MiB；临时塑形结果及 shaper 自身工作内存另计，不包含在这 16 MiB 内。每次文档排版的行队列累计塑形输入/输出记录上限为 64 Mi（67,108,864）项，最终行拟合最多回退 256 次；以上超限返回 `EXR_LIMIT`。独立 `exr_shape()` 另按上述输入 / 工作量上限处理。整个段落的双向标量与偏移元数据在页面缓存预算之外。

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

## 页级续排与页面缓存

`exr_pager_create(doc, font, config, &pager, error)` 基于已解析的文档创建排版游标，计算样式但不预排全部正文。doc、font、图片回调及 context 由宿主持有，必须在 pager 生命周期内有效；config 和 user CSS 在创建期间复制，返回后可以释放或修改原配置。改变字体或版式时重新创建 pager。

`exr_pager_next()` 每次继续排版并交出一个独立单页 `exr_layout`。单页内部的页索引恒为 0，源文字偏移、节点及资源索引仍属于输入 document；渲染时使用 `exr_render_page(page, font, 0, ...)`。宿主自行保存阅读页序号并释放不再需要的页。返回 `EXR_OK` 且 `*out == NULL` 表示 EOF，可以重复请求 EOF；排版失败时 `*out == NULL`，此顺序模式的游标需重新创建。

```c
exr_pager *pager = NULL;
exr_status status = exr_pager_create(doc, font, NULL, &pager, &error);
while (status == EXR_OK) {
    exr_layout *page = NULL;
    status = exr_pager_next(pager, &page, &error);
    if (status != EXR_OK || !page)
        break;
    /* Read layout views or render page index 0 before releasing this owned page. */
    exr_layout_free(page);
}
exr_pager_free(pager);
```

需要来回翻页时，使用借用模式 `exr_pager_get(pager, page_index, &page, error)`，page_index 从 0 开始。命中缓存直接返回布局并更新 LRU；向前请求只续排到目标页，中间经过的页不会自动加入缓存。请求已经淘汰的旧页时，从目标之前最近的保留检查点续排；没有合适检查点才从头重放。请求超出 EOF 的页返回 `EXR_ARGUMENT`。缓存未命中的排版或预算检查失败保留已有页缓存及其 LRU 顺序；后续命中仍可读取，后续未命中可从保留检查点恢复。

调用 `next()` 进入顺序拥有模式；调用 `get()` 或 `set_cache()` 进入借用缓存模式。同一 pager 不能混用这两种模式，否则返回 `EXR_ARGUMENT`。借用页不调用 `exr_layout_free()`，其契约有效期至下一次 get / set_cache / free。不同页需要长期同时持有时，可使用顺序模式自行管理 owned 布局。

`exr_pager_set_cache(pager, capacity, byte_budget, error)` 同时设置 1–64 页的数量上限和字节预算，默认 1 页、0 字节预算（不限制字节数）。降低限制时立即从 LRU 尾部淘汰，直至同时满足两个条件。每页按 `exr_layout_memory_size()` 计入预算；新页本身超过非零预算时返回 `EXR_LIMIT`，不淘汰已有页。`exr_pager_cached_count()` / `exr_pager_cached_bytes()` 返回驻留页数及计量字节数。

```c
exr_pager *pager = NULL;
const exr_layout *page = NULL;
exr_status status = exr_pager_create(doc, font, NULL, &pager, &error);
if (status == EXR_OK)
    status = exr_pager_set_cache(pager, 3, (size_t)8 * 1024 * 1024, &error);
if (status == EXR_OK)
    status = exr_pager_get(pager, 12, &page, &error);
/* Use borrowed page at index 0; do not free page. */
exr_pager_free(pager);
```

`exr_pager_position()` 返回已扫描到的规范化正文 UTF-8 字节位置，包括断行、字素簇和表格组的前瞻，可能领先最后输出页。重放时可回退；它用于观察当前排版进度，不是可序列化的恢复令牌。布局中的源范围和稳定锚点继续用于保存阅读位置。

0.14 的借用模式默认每 16 页保留一个恢复点，最多 4 个、驻留载荷合计 2 MiB。`exr_pager_set_checkpoints(pager,capacity,byte_budget,interval,error)` 可设置最多 64 个检查点及非零预算/间隔，capacity 为 0 关闭并释放全部检查点。其预算独立于页面缓存，按实际快照数组、遍历栈及引用的表格单元格布局计量；共享单元格载荷保守地计入每个引用它的快照。超预算或分配失败时跳过新检查点，保留已有检查点并正常返回页面。当前工作区与快照复制期间的临时内存另计。

快照保留原始/暂定/最终行、文档游标、表格 rowspan 组及累计工作量。双向分析按保存的原段落起点重新建立，不把跨行方向当作新段落。恢复点仅在同一个不可变 document、版式和 pager 生命周期内有效，不是持久化格式；顺序 `next()` / 全文布局不会额外保存检查点。`exr_pager_statistics()` 返回累计实际生成页数、驻留检查点数量/字节及成功恢复次数，可用于观察回放开销，NULL 返回全零统计。

续排保留当前行、断点后的 carry、尚未闭合的字素簇 / 塑形片段和文档遍历状态；同一字素簇可跨文本节点和样式，分页不重新切断其边界。表格先扫描轻量行列元数据，再逐个测量当前 rowspan 连通行组；可暂停的边界仍遵循现有 CSS、背景分片和表格分页规则。普通长单段不会在第一页前生成全段字形；双向级别分析仍先扫描可见段落。

SDK 的 `examples/page.c` 编译为 `exreader-page-example`，用法为 `book.epub font.ttf output.png [page] [part]`，page / part 均从 0 开始，默认 0。它只加载指定 EPUB 分段，设置 3 页、8 MiB 的页面缓存，按需续排目标页并输出 PNG，同时打印扫描位置、缓存页数及计量字节数。支持 Windows Unicode 参数和路径。

## 缓存内存计量

`exr_document_memory_size()` 和 `exr_layout_memory_size()` 返回对象拥有的分配 payload 字节数，包含数组已分配容量，不包含分配器元数据；NULL 返回 0，无法用 size_t 表达的合计饱和为 `SIZE_MAX`。这是对象计量，不是进程 RSS。共享压缩 archive、借用字体和其他外部对象不计入；引用同一图片像素的每个页面按完整像素及引用计数字节数保守计量。

页面预算只约束驻留页面的计量总量，分段预算只约束驻留 document 与完整 layout 的计量总量。publication 的共享压缩源、字体及其 OpenType 表缓存、pager 基础状态及当前行/字素簇/塑形段/表格组工作区、整段双向标量与偏移、图片资产池、正在加载的新对象和渲染临时 bitmap 都在该预算之外。文件仍完整解析为一个 document；单个超大字素簇或不可拆 rowspan 行组仍可能需要较大工作区。高于一页的不可拆表格组返回 `EXR_LIMIT`，页缓存预算不构成全程进程内存硬上限。

打开耗时、首画、续排、渲染、完整翻页和进程峰值内存的独立基准及复现命令见 [性能基准](PERFORMANCE.md)。

## 分段 publication 与 session

0.17 的 `exr_publication_navigation(publication,&entries,&count,error)` 返回借用的扁平目录树，寿命持续到 publication 释放。每项有 parent、part、label、href、base 和 role：parent 必须指向更早的条目，根为 SIZE_MAX；part 为对应分段索引，外部、未解析或重复路径无法唯一确定的目标为 SIZE_MAX。href 保留原 URI，相对于 base 解释；没有链接的目录组也可保留。role 是开放字符串，内置输出使用 toc、page-list、landmarks、nav-list 或原导航类型。

EPUB 在首次请求目录时读取并缓存 EPUB 3 manifest 中的 nav XHTML，未提供有效条目时读取 EPUB 2 NCX；NCX 遵循 OPF spine 的 toc ID，缺失引用在目录请求时返回 EXR_FORMAT。打开 publication 本身仍不解析导航或章节 XHTML。目录解析沿用有实体/深度限制的 XML 树，保留嵌套关系、Unicode 标题和相对链接；远程 href 只作为元数据返回。失败清空输出并保留重试机会，后续成功查询直接复用缓存。

宿主通过 `exr_publication_input.navigation/navigation_count` 提供任意自有格式的同类目录；构造时复制全部字符串和条目，查询不调用章节 loader。最多 10000 项，标题最多 64 KiB，href/base 最多 2046 字节，role 最多 256 字节，与分段目录的字符串合计限制为 64 MiB。输入验证 UTF-8、parent 和 part 范围；自有 role 和 URI 不需要注册。0.17 扩展了 publication 构造输入，宿主需重新编译。

0.15 的 `exr_publication_open_source()` 接收通用随机读取源 `{size,read_at,release,context}`。描述符被复制，打开时只读取 ZIP 目录和 EPUB 元数据；读取某章、CSS、图片或字体时才请求对应字节，不把整个压缩源复制进内存。`exr_publication_open(path)` 使用持有文件句柄的同一路径；`open_memory()` 仍复制调用者的输入。

`read_at(context,offset,buffer,size)` 返回实际字节数，允许短读并会继续补足，尚未读完便返回 0 或返回超过请求的数量会得到 `EXR_IO`。引擎检查所有区间；源大小与每次 ZIP 操作的累计读取量仍限制为 128 MiB，成员解压和 XML 限制不变。源字节必须保持不变，回调及同源对象的访问需串行，回调不能销毁或重入正在访问它的对象。引擎本身不联网，宿主可自行在回调后实现其他存储。

仅在 open 成功时接管 context；打开失败不调用 release。若 release 非 NULL，在 publication、session 和所有已加载章节文档都不再引用源后调用一次；即使先关闭 publication，章节仍可读取资源。release 为 NULL 时由宿主维持 context 的整个有效期。文件源使用同样的共享寿命，因此不再把完整压缩 EPUB 作为常驻字节保存；单章正文仍完整解析。

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
/* Use the borrowed document/layout before the next get/set_budget/clear/free. */
exr_session_free(session);
```

`exr_session_get()` 仅加载并完整排版所请求的分段；缓存命中直接复用文档和布局。达到 1–64 个分段的容量后按 LRU 淘汰最久未访问项，同时释放其文档和布局。`exr_session_set_budget(session, bytes, error)` 为同一缓存增加字节约束，0 表示不限制字节数；降低预算时立即淘汰 LRU 项，直至驻留总量不超预算。每项按 `exr_document_memory_size(doc) + exr_layout_memory_size(layout)` 计量。加载、排版失败或新项本身超过非零预算时保留已有缓存及 LRU 顺序；超出预算返回 `EXR_LIMIT`。

`exr_session_cached()` / `exr_session_cached_bytes()` 分别返回驻留数量和计量总字节数；`exr_session_clear()` 清空缓存，后续 get 会重新加载。新分段先加载并计量，再淘汰旧项，因此加载期间可临时多驻留一个分段；预算范围遵循前述对象计量规则。

分段的页号、节点 / 资源索引和规范化 UTF-8 偏移都是局部值，不能当作旧接口的全书偏移。宿主保存位置时需结合 part 索引或宿主唯一标识、id/path，以及局部偏移或 `exr_anchor`；不能仅靠可能重复的 id/path 区分分段。锚点只在所加载分段的正文内解析。整书总页数在各段排版完成前未知，本接口不预先排完整本书。

loader 和图片解码回调不能销毁或重入当前正在执行的 publication / session。`exr_session_get()` 拒绝同一 session 的重入访问；这不替代宿主对共享 publication / source 对象及其生命周期的串行管理。

session 按完整分段缓存文档和布局；需要单章内部的页级续排时，通过 `exr_publication_load()` 取得独立文档，再创建 pager。EPUB 压缩输入仍受 128 MiB、单 ZIP 成员仍受 32 MiB 上限约束。现有 `exr_document_open()`、书库导入、`exr_library_document()`、全书搜索和导出继续使用原文档模型，不自动变为流式解析。

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

EPUB 重复 spine 项可能产生路径相同、正文范围不同的章节。解析会比较所有同路径范围；不同位置取得同样最高匹配等级时返回 `AMBIGUOUS`，包括点书签，不选择第一个章节或按旧偏移消除歧义。

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

HTML、FB2、EPUB 和 DOCX 导出会预检实际写入 XML 的字段。正文均需符合 XML 1.0 字符范围；标题仅在 HTML、FB2、EPUB 中序列化，DOCX 只检查正文。非法 UTF-8 或 XML 1.0 禁止的字符返回 `EXR_ENCODING`，输出字节为 NULL、大小为 0。TXT / RTF 保持各自可表示的字符范围。

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

CSS `display:none` 只影响布局，不删除规范化正文；重新排版时原有文字位置保持不变。HTML `hidden` 属性在文档投影阶段排除，其行为与 CSS 隐藏不同。旧 `exr_document_export()` 仍为文本转换。0.18 新增下述结构导出。

## 宿主样式与布局输出

`exr_layout_create()` 保留默认入口。通过 `exr_layout_create_ex()` 配置宿主样式和图片解码器；配置及 CSS 字符串只在创建调用期间借用。

```c
exr_layout_config config = exr_layout_config_defaults();
config.page.width = 600;
config.direction = EXR_DIRECTION_AUTO;
config.document_css = 0; /* Disable linked, embedded and inline book CSS. */
config.user_css = "p {font-size:24px;line-height:1.6} img {max-width:100%}";
status = exr_layout_create_ex(doc, font, &config, &layout, &error);
```

书内 link/style 按文档顺序读取并限制在对应章节；内联 style 使用更高优先级。元素、`*`、`.class`、`#id`、组合、逗号列表、后代和 `>` 子选择器可用。支持 specificity、源码顺序、`!important` 和文字属性继承。宿主 `user_css` 的优先级高于全部书内规则（包括书内 `!important`），便于调用方控制阅读样式。关闭书内 CSS 后仍保留标题、粗体、斜体等语义默认值；宿主可以覆盖它们。

| 范围 | 已实现 |
| --- | --- |
| 文字 | font-family、font-size（4–256）、font-weight（合成粗体）、font-style（合成斜体）、color、line-height、direction（ltr/rtl）、text-align（left/start/center/right/end/justify）、text-indent |
| 盒模型 | width / max-width、margin / padding 及四边长属性、background-color（background 仅接受颜色）、统一 border-width / border-color / border-style（solid/none）和 border 简写 |
| 流布局 | display: none/block/inline/table/table-row/table-cell；break-before/after 和 page-break-before/after 的 page/always/auto |
| 尺寸 | px、pt、em、rem、百分比和零值；margin 可 auto；图片支持 height，普通块的 height 尚未应用 |
| 颜色 | #RGB、#RGBA、#RRGGBB、#RRGGBBAA；black/white/red/green/blue/gray/grey/transparent/navy/yellow/orange/purple |

`rem` 当前以宿主页默认字号为基准。`inherit` 支持文字属性；缩进和边框宽度不支持百分比。所有负尺寸均忽略，外边距不折叠。未知属性、选择器和 at-rule 会被跳过；尚不支持 @import、@media、变量、伪类、属性选择器、flex/grid、浮动、定位、完整空白规则和浏览器式盒模型分片。属性值和单位使用小写。样式表合计上限 1 MiB、4096 条规则、131072 项展开声明、每规则 256 项声明、2000 万次匹配工作；达到上限返回 `EXR_LIMIT`。

`exr_layout_glyphs()` 按逐行视觉顺序输出字形编号、字号、颜色 `0xRRGGBBAA`、合成粗/斜体标志、基线、源范围和字体索引；混排时文字偏移可能不单调。`cluster_start/end` 为当前源簇的 UTF-8 半开范围，可以跨文本节点和样式，连字可合并多个原始字素。`EXR_GLYPH_SHAPED = 16` 表示 advance / offset 已包含塑形定位；这些条目的 `start/end` 也使用源簇范围，`codepoint/node` 代表簇首源标量 / 节点，不承诺一条 glyph 对应一个标量。未塑形路径仍保留原标量范围。`boundaries` 保留源簇首的 `EXR_BOUNDARY_*`，同簇后续字形为 0。分段和文档使用各自局部偏移，簇索引不是永久标识。

`EXR_GLYPH_HIDDEN = 4` 标记格式、换行控制、变体选择符等不应绘制的条目，内置栅格器跳过这些字形，自定义绘制也需跳过；它们仍保留源文本范围。`bidi_level` 是解析后的级别，奇数为 RTL，`UINT_MAX` 表示 X9 控制。`offset_x/offset_y` 以 px 表示，y 向上；绘制原点为 `(x + offset_x, baseline - offset_y)`。自定义绘制不再额外应用 GPOS 或 pair kerning。布局不会拆开源簇，也不会在 `GLUE` 边界紧急断行；不可拆的组超过内容宽度时保留整组，`clip_left/right` 指明水平裁切范围。

`exr_layout_hit_test()` 按视觉簇整体宽度和方向返回源簇起点或终点，不返回连字或字素内部偏移。`exr_layout_lines()` 输出行矩形和视觉字形数组范围，其 start/end 仍是逻辑源范围；表格一行可有多个并列文字行。`exr_layout_boxes()` 输出背景块、图片和单元格的页面坐标、边框与背景，按页及节点前序排列。page 的 line/box 范围可直接迭代。坐标单位为逻辑像素，原点在页面左上方。

宿主可先按 boxes 顺序绘制背景、图片和边框，再绘制文字。`exr_layout_image(layout, resource)` 返回对应资源的解码后 RGBA 借用视图；缺失时返回 NULL。这些输出可直接用于自定义渲染器，不需要创建内置页面位图。

## 图片、表格与像素

内置 `exr_image_decode()` 接受 PNG/JPEG 字节并返回独立 RGBA 像素，用 `exr_bitmap_free()` 释放。布局按资源缓存图片；图片保持纵横比，限制在内容宽度和可用页高之内。width/height 同时存在时按容纳方式缩放，图片当前独占块。缺失、外部、损坏或不支持的图片显示带标志的占位框；资源/解码限制错误会中止布局。解码尺寸上限 8192×8192 且总像素不超过 16 Mi，编码输入上限 32 MiB，stb 临时分配上限 128 MiB，布局图片缓存上限 64 MiB。

宿主设置 `decode_image`、`release_image` 和 `image_context` 可替换解码器。回调收到资源元数据及编码字节；返回 `channels=4`、非预乘 RGBA、有效 width/height/stride。引擎复制像素，然后无论成功或失败都调用配套 release 回调一次；不得在 release 中释放借用的编码输入。`EXR_FORMAT` 表示占位框，其余非成功状态中止布局。要保留内置 PNG/JPEG 支持，宿主回调可以调用 `exr_image_decode()` 并在 release 中使用 `exr_bitmap_free()`。直接创建完整 layout 时，回调及 context 只需在 create 调用期间有效；使用 pager / session 时需在相应句柄整个生命周期内有效。渲染已有布局不会再次调用它们。

表格采用等宽列，支持单元格换行、colspan 和 rowspan。具有跨行单元格的相连行组一起分页；高于一页的行组返回 `EXR_LIMIT`。上限为 64 列、4096 行/单元格、8 层嵌套。尚不支持按内容自动分配列宽、跨页拆分单元格、重复表头、垂直对齐和 border-collapse。单元格的可见边框、背景和内边距由样式控制。

`exr_render_page()` 输出 1 通道灰度；`exr_render_page_color()` 输出 4 通道 RGBA。内置渲染器使用白底、双线性图片缩放、透明合成和 FreeType 字形，整页位图不超过 64 MiB。`stride` 是每行字节数。PNG 支持两种通道并保留输入 alpha；BMP 写为 24 位并将 alpha 合成到白底。写入时 `channels=0` 兼容灰度输入。框架不提供窗口、GPU 或事件循环。

## 书库

SQLite 数据库保存原文件 BLOB、封面 BLOB、元数据和 UTF-8 位置标注。书籍主键为库内整数。格式在导入时验证；正文大小用于检查进度和标注范围。书库使用 application_id 与 schema version 检查，拒绝不认识的现有数据库。0.7 将 schema v1 事务迁移到 v2，原标注保留其偏移、备注和 ID，选择器保持 NULL，因此解析为 `LEGACY`；不从新版正文反推旧引文。单句修改使用 SQLite 事务语义，书籍删除通过外键清理笔记。

宿主应零初始化输入 `exr_note`。保存新标注时，`exr_library_note()` 为当前书籍正文捕获文本选择器；修改同范围标注的备注保留已有选择器。宿主可以显式提供 `note.anchor` 重新锚定，锚点的 `start/end` 必须与笔记范围一致。查询的 `exr_note.anchor` 由结果数组拥有，使用 `exr_notes_free()` 一次释放全部内容。稳定锚点保存历史文本证据，实际显示前应调用 `exr_anchor_resolve()` 并检查其状态。

备注 `note.text` 最多 64 MiB，不含字符串终止字节；超限在写数据库前返回 `EXR_LIMIT`，输出 ID 为 0，已有笔记保持不变。恰好 64 MiB 的备注可以保存、读取和再次编辑。输出 ID 可传 `&note.id`：引擎在清零输出前保存输入值，因此更新仍使用原笔记 ID。

`exr_library_backup()` 使用 SQLite VACUUM INTO 生成可直接打开的完整备份；目标数据库不能已有非空内容。封面作为受大小限制的 BLOB 存储；宿主可调用图片解码接口生成像素，封面不自动缩放。媒体大文件的流式导入尚未实现。现有 ZIP / IndexedDB 备份需要未来的迁移工具。

## 嵌入平台

宿主负责文件选择、字体提供、页面纹理显示、触摸 / 鼠标 / 键盘事件和系统生命周期。像素或布局数据可转为纹理或原生绘图命令。Android 可经 JNI 调用 C，Apple 平台可经 Objective-C / Swift 导入 C 头文件；当前尚未提供这些宿主适配器。

## 结构保真的 EPUB 导出（0.18）

`exr_document_export_epub(doc, control, &bytes, &size, &error)` 序列化当前文档树，按原路径复制全部声明资源，输出可重新打开的 EPUB。成功后用 `exr_free(bytes)` 释放；失败清空 bytes/size。control 可为 NULL，回调在本次调用内借用，新增 EXPORT 阶段。输入文档不可在回调中修改或释放。

保留章节顺序与 linear 标志、嵌套元素、XML expanded names、属性、原始解码文本、相对链接、表格、CSS、图片、字体和封面资源。资源路径中的 `%/#/?/空格/Unicode` 在 manifest 中正确编码，ZIP 成员使用原始路径。重复 spine 路径只存一份相同 XHTML；同路径不同章节报错。EPUB 3 导航资源保留，EPUB 2 NCX 生成有层级和类别的 EPUB 3 导航。没有目录时按章节生成；匿名章节生成无冲突路径。

没有元素名字的语义节点映射为 XHTML 段落、标题、表格等；有名字的自定义元素保留 XML 名字与命名空间。序列化不保留原 XML 前缀拼写、注释、DTD 或字节排版。任意模型不一定能表示为有效 XML：非法名称、字符、命名空间、重复资源路径、保留路径和缺失资源明确失败。`META-INF/encryption.xml` / `rights.xml` 存在时拒绝导出，避免丢失解密或字体混淆信息。原 OPF 的作者、语言、标识符等尚未进入通用文档元数据模型；当前包重新生成 title/und language/identifier/modified，不承诺原 OPF 字段无损。

与读取限制一致：最多 10000 ZIP 成员，单成员 32 MiB，累计未压缩成员和压缩输出各限 128 MiB。此接口输出完整内存包；不是流式写入。它保留模型已有结构，不会恢复 TXT、旧 DOCX/RTF 等解析时已经丢失的信息。

## FB2 结构解析（0.19）

FB2 通过原生 XML 树解析，正文转换到通用语义节点和 XHTML 名字：章节/标题/段落、粗体/斜体、图片、表格及跨列属性、诗行、链接和脚注。`notes` / `comments` 正文中的 section 标记为 NOTE，并保留 ID 与脚注链接。多个 body 按原顺序进入同一分段；当前脚注正文也在阅读流中。未知扩展元素保留源 expanded name 和属性。

binary 使用严格 base64 解码，保留编码资源原字节；重复 ID、非法 padding 和缺失的本地图片/封面引用报错。图片 URI 的 Unicode 百分号转义可用。封面资源标记 `cover-image`。description 只提取书名与封面，不进入正文；binary 编码不进入正文。顶层 stylesheet 进入 head/style，命名 style 转成 class；CSS 选择器匹配转换后的元素名。嵌套深度和节点/字符串预算遵循现有模型限制，单 binary 最多 32 MiB。

已有图片、样式、表格、强调文字和链接可通过 0.18 的结构接口转 EPUB；它不会补齐当前排版器不支持的上/下标、删除线或诗歌专有排版。FB2 仍整文件构建 XML 树，未实现章内流式处理。

## DOCX 结构解析（0.20）

DOCX 读取 package 主文档关系，支持非默认主文档路径；解析 WordprocessingML transitional / strict 名字。正文进入相同 XHTML/语义树，保留段落、标题、字符与段落样式、书签、内部与外部链接、图片、换行/分页和合并表格。样式读取 docDefaults、默认 paragraph/character style、pStyle/rStyle、basedOn、直接格式；支持粗斜体、字号、颜色、字体名、对齐、间距、缩进及段落方向。继承链最多 64 层，属性读取总工作量限 2000 万。

DrawingML/VML 图片按关系读取，原编码字节进入 resources；可读取尺寸，重复引用共享资源。路径与 Unicode/百分号编码经过解析，外部图片只保留 URI，框架不访问网络。表格的 gridSpan/vMerge 转成 colspan/rowspan；gridBefore/gridAfter 用空单元格保留列位置，最多 256 列。插入修订与字段结果可见，删除修订和字段指令排除；AlternateContent 优先使用 Fallback，没有 Fallback 时取首个 Choice，不重复输出两支。

当前表格采用引擎的等宽列，尚未实现 Word 专有列宽、表格样式、边框与浮动锚点；图片仍按块排版。页眉页脚、嵌入字体、主题字体/颜色、完整 Word 样式算法及元数据仍待补齐。它是流式阅读模型，未复刻 Word 的打印页面。旧文字导出保持原行为；结构接口可把当前已解析的图片、样式、表格和链接转成 EPUB。

## DOCX 脚注与尾注（0.21）

正文 footnoteReference/endnoteReference 生成 LINK 与 `doc-noteref`，注释正文生成 NOTE 与 `doc-footnote` / `doc-endnote`，其中的引用标记生成 `doc-backlink`。重复引用共享同一注释正文，保留唯一引用 ID；脚注与尾注各按首次引用次序显示阿拉伯序号。正文书签加 `bookmark-` 前缀，避免与生成的注释 ID 冲突，内部链接同步转换。

注释分段按主文档关系读取，拥有自己的图片关系与路径基准，可复用主文档图片，也可携带不同图片。生成的图片资源 ID 在整书内唯一。正文中没有引用的注释和 separator/continuationSeparator 不进入阅读流；被引用却缺少正文、重复的普通注释 ID、嵌套注释引用会拒绝解析。普通注释最多 10000 个。当前统一追加在正文后；不按打印页面排脚注，也未实现分节重编号、罗马数字与自定义序号。

结构 EPUB 导出保留上述链接与注释语义。本次同时修正章节路径与非 XHTML 资源冲突的情况，导出会失败并保持空输出，不再覆盖资源。

## DOCX 编号列表（0.22）

首次遇到编号段落才读取 numbering 部件。支持 abstractNum/num、9 层 ilvl、样式继承的 numPr、直接关闭编号、start/startOverride、lvlOverride、lvlRestart、isLgl、lvlText 的 `%1`–`%9` 引用与 suff。每个 numId 保存独立计数，跨普通段落后续号；可生成嵌套 OL/UL/LI，段落、单元格和注释使用同一路径。

当前支持 decimal、decimalZero、lowerLetter/upperLetter、lowerRoman/upperRoman、bullet、none；字母和罗马数字的非正值、罗马数字大于 3999 时回退十进制。其他编号制返回 EXR_FORMAT，尚未实现语言相关计数、图片项目符号和 numStyleLink。定义 ID 重复、层级越界、缺失定义、失配引用会拒绝解析。每类定义最多 10000 个，引用的层级配置按需分配。

可见编号保存为段落开头的呈现性 span（role=presentation、aria-hidden=true），其字号/字体等可取自层级 rPr；原序号文本也进入规范化正文与搜索。列表设置 `list-style-type:none`，确保在外部 EPUB 阅读器中不会重复生成编号。此版本没有向核心排版器加入 Word 专用计数规则，也没有为一般 HTML/EPUB 的无文本 LI 自动绘制标记。布局仍使用现有列表缩进，未实现 Word 的精确悬挂缩进和编号制表位。

## RTF 字符与段落结构（0.23）

RTF 使用同一文档树保存分组作用域内的粗体/斜体、半点字号、颜色表引用、段落对齐、缩进、段前后距、行距与文字方向。plain/pard 恢复相应属性；par 创建段落，line 保留为段内换行。u/s 元素保留下划线与删除线语义，0.26 已加入绘制；inline highlight 尚未绘制背景。

词法器保留 0.12.1 的 Unicode fallback 规则：整条控制词、转义符号、十六进制字节和 bin 段各按一个 fallback 字符消费，fallback 内不执行格式或 destination；分组边界终止 fallback。支持 Windows-1252 与 Unicode 转义；其他 ansicpg 编码仍拒绝。表格、编号列表、脚注和样式表继承仍待后续接入。颜色表最多 4096 项，分组深度上限仍为 255。

RTF 已解析的文字、字号、颜色和段落结构可转成 EPUB；旧文字转换保持原行为。相同属性赋值复用现有字符串，避免逐段更新样式时重复计入模型预算。

## RTF 内嵌图片（0.24）

pict 的 pngblip/jpegblip 支持十六进制与 bin 数据，编码字节转移给资源表，IMAGE 节点保留 picw/pich、picwgoal/pichgoal 和缩放后的尺寸。尺寸不指定时使用内在尺寸。单图片最多 32 MiB、picture 分组最多 9996 个；拒绝非法十六进制、半字节残留和 PNG/JPEG 签名失配。wmetafile/emfblip 字节也可保留为资源，内置解码器不绘制它们，宿主可替换图片解码器。

识别紧跟可选 destination 标记的 shppict；已有可显示图片时跳过相邻 nonshppict 兼容分支，避免重复。未知 destination 继续跳过，不会由其中的已知词重新激活。没有编码类型的 pict 保持旧的忽略行为。图片可通过结构接口转 EPUB，字节与显示尺寸保留。

## RTF 字体名称、字段链接与元数据（0.25）

fonttbl 的名称（包括 Unicode 转义）转为 font-family，保留 deff 默认字体、f 切换和 plain 恢复。字体编号最多 4095；不扫描系统字体、不加载 fontemb/fontfile，字体字节仍由宿主或书籍资源提供。尚未使用 fcharset 解码其他传统代码页，ansicpg 范围保持 Windows-1252。

field/fldinst/fldrslt 保留字段的可见结果。HYPERLINK 支持引用 URL、`\l` 内部书签、`\o` 提示与 `\t` 目标框架参数；不会执行字段或访问链接。bkmkstart 生成 `bookmark-` 前缀的定位节点，内部链接同步编码。未知字段作为普通可见结果保留；忽略的未知 destination 不能被其中的 field/fonttbl 等词激活。

info/title 提取 UTF-8 书名并同步 XHTML head/title，其他 info 内容不进入正文。字体名、字段指令、书签名和书名各有 64 KiB 临时限制；字体名称和字段元数据累计限制为 64 MiB，已解析的字段指令立即释放。最多 10000 个字段。结构 EPUB 导出保留字体名称、链接、定位节点和书名。

## 通用文字饰线（0.26）

u 元素默认下划线，s/strike/del 默认删除线；CSS text-decoration-line 和简单 text-decoration 支持 none、underline、line-through 或两者组合。祖先饰线传播到文字后代，后代的 none 不移除祖先饰线；在饰线源元素上设置 none 可关闭该元素的默认修饰。宿主 user_css 可覆盖这些默认值。

布局字形输出 EXR_GLYPH_UNDERLINE / EXR_GLYPH_STRIKE 标志，普通及页级布局、检查点回放和表格复制均保留。灰度/RGBA 绘制按 FreeType 下划线度量和 OS/2 删除线度量绘制单实线，并遵守文字裁剪。文字 shaping 参数仍只接受粗体/斜体；饰线由布局/绘制层处理。OpenType 分段保留饰线标志，在跨饰线边界时保留 Arabic 相邻字符连接上下文。

DOCX 的默认、继承与直接 rPr 下划线/删除线在 run 层解析，允许直接关闭继承修饰，不把 Word 规则放进 CSS 引擎。RTF/FB2 与宿主模型使用同一饰线输出。当前没有双线、波浪线、跳过字形墨迹或独立饰线颜色；饰线使用当前文字颜色和字形字号。RTL、字体变化和其他样式边界仍遵循已有塑形范围限制。

## MOBI HUFF/CDIC 与记录边界（0.27）

原生 C 解码器支持 compression=0x4448 的 HUFF/CDIC：短码缓存、长码表、多个 CDIC、递归压缩词条与已展开词条缓存。循环引用返回 EXR_FORMAT，超过 64 层返回 EXR_LIMIT。完成文本解码后立即释放字典缓存，再进入文档解析。

MOBI 统一校验 PalmDB 记录目录、头长度与文本长度；三种压缩方式（无压缩、PalmDOC、HUFF）均移除记录尾附加项与多字节重叠尾。PalmDOC 回指限定在当前记录内，允许记录内重叠复制，拒绝跨记录回指。UTF-8 / Windows-1252 继续可用。

HUFF 最多 1048576 个词条，整书解压正文与每个展开词条各限 64 MiB，解码缓冲区/缓存合计分配上限 128 MiB，累计复制工作量 256 MiB、码字工作量 134217728 次。该分配预算不包含原书、词条元数据与后续文档模型。目录字段先预检，词条缓存按引用展开。当前仍提供 MOBI 正文模型；KF8 结构重建、图像/链接与富排版仍待补齐，加密书籍不支持。


## KF8 章节重建（0.28）

原生 C 解析 version=8 的 UTF-8 KF8，复用三种 MOBI 记录解压方式。FDST 分离正文流和附加流；INDX/TAGX 支持多个索引记录、多个控制字节、按值数量或按字节长度编码的 VWI。SKEL/FRAG 按索引次序拼接为独立 XHTML 章节，进入通用文档树；无骨架表时将完整正文流解析为一章。章节、属性与文字可经结构 EPUB 导出。

索引最多 262144 项，章节/资源最多 10000 项，重建文字受 64 MiB 缓冲区上限约束，累计插入搬移最多 256 MiB。记录目录、索引头、TAGX 掩码、IDXT 边界、VWI 溢出、片段长度与插入位置均验证；骨架原始区间不得重叠，不猜测修复损坏片段。附加流暂以 application/octet-stream 资源保留。当前未接通 kindle:flow/embed/pos 资源引用、FONT 解包、NCX、混合 MOBI/KF8 或 ORDT 特殊采样本编码；后续继续补齐。


## KF8 资源与 FONT（0.29）

kindle:flow 的 text/css 与 image/svg+xml 引用转为本地资源路径；kindle:embed 按首资源记录和一基 Base32 序号定位，重复引用共享一份资源。CSS 的 url()、文档 src/href/poster/data、内联样式与 style 正文接通资源表，保留 CSS 注释、普通字符串及阅读正文中的相同文字。CSS 资源依赖按队列处理，每份只处理一次，允许循环引用。

PNG/JPEG 可直接绘制；GIF/WebP 和 SVG 流保留为资源，须由宿主提供相应解码器。SVG 内部的 Kindle 引用、CSS 转义形式的 url 与 @import 尚未转换。FONT 支持无压缩、zlib、前 1040 字节 XOR 混淆或两者组合，校验字段、密钥区间、解压精确长度和压缩流尾；恢复字体原字节后交给现有字体选择和排版。支持 TTF/OTF/TTC/WOFF/WOFF2 签名，实际可用字体由 FreeType 构建能力决定。

每个新增图片或字体最多 32 MiB，全部章节/流/资产编码字节合计最多 128 MiB；字体解包另使用最多两份 32 MiB 临时缓冲区。未识别的嵌入资源签名、无效 URI、越界序号及同一流的 MIME 冲突返回 EXR_FORMAT。XHTML 资源接口保留重建后的原始字节，通用树上的链接是转换后的本地路径；结构 EPUB 输出使用树并保留已转换 CSS 与原始图片/字体。


## KF8 定位链接（0.30）

kindle:pos:fid:BASE32:off:BASE32 按片段序号及片段内字节偏移，映射到重建章节中该位置之前最近的命名锚点。解析器在元素开始时保留原始字节位置；ID 属性已完整解析，目标位于标签内部时可匹配当前标签。进入 body 时重置为章首；没有更近的命名锚点则链接到章首。读取 id、xml:id 和旧式 a/name，后者补同名 id 以接入通用链接解析。

输出为规范章节路径和百分号编码片段，支持 Unicode、空格、%、# 等 ID；同一 ID 可在不同章节重复，同章重复命名锚点返回 EXR_FORMAT。片段序号、偏移、重建章节范围、语法和 Base32 溢出均验证，越界失败，不重定向猜测目标。临时位置索引按命名元素数量增长，受通用节点上限约束，链接转换后释放。位置映射仅内部使用，公共节点的 start/end 仍是归一化正文范围。


## 文档导航与 KF8 NCX（0.31）

`exr_document_navigation(doc, &entries, &count, error)` 从文档声明的 nav/NCX 资源读取导航，返回独立拥有的 exr_navigation 数组；使用 `exr_navigation_free(entries, count)` 释放。快照可在文档释放后继续读取；没有作者目录时返回 NULL/0。该接口沿用 EPUB 和自定义资源的通用解析，条目包含 parent、part、label、href、base 和 role。publication_navigation 的借用语义保持原样，不要释放它返回的借用数组。

KF8 的 NCX INDX/CNCX 转为标准 NCX 资源，使用标签偏移（含多 CNCX 记录的 65536 基数）、级别、可选父子关系和 fid/off 定位，连接已有章内锚点。父子关系省略时从层级推导；显式关系必须与层级一致。目录元数据不加入正文；结构 EPUB 转换保留目录层级与目标。最多 10000 条目录、250 层嵌套；CNCX 单记录最多 65536 字节，总字符串数最多 262144、总字节最多 64 MiB。拒绝缺失标签、非完整 VWI、非法尾填充、级别跳跃、矛盾父子关系及无效目标。当前未接入 KF8 guide、混合 MOBI/KF8 头与 ORDT 特殊采样本编码。


## MOBI/KF8 混合容器（0.32）

旧 MOBI 头通过 EXTH 121 声明 KF8 头记录时，验证前一条恰为 BOUNDARY，再按 KF8 头的相对记录索引读取正文、HUFF 字典、FDST、SKEL/FRAG 和 NCX。旧正文不重复加入阅读流。前半部首资源到边界之间的记录作为共享资源前缀，保持序号与占位记录；后半部本地资源接在共享前缀后。图片、字体可以全部共享、部分共享或全部本地存储。

选择由 EXTH 121 明确驱动；不存在该字段或值为 0xffffffff 时保持旧 MOBI 解码，不扫描内容猜测边界。校验 EXTH 长度、计数、记录长度与重复边界字段、指针、标记、目标版本及共享资源起点。EXTH 最多 262144 项；两部分加密标志均须为零。解析器借用原输入的记录，不拼接或复制整份容器。


## KF8 guide 地标（0.33）

guide INDX/CNCX 保留类型、标签和片段目标，接入同一位置解析与导航快照。支持 tag 3 的片段序号、tag 6 的片段序号及可选偏移。输出 NCX navList class=landmarks；每个 navTarget 的 class 保存原始 guide 类型，start 规范化为 text。thumbimagestandard 是缩略图元数据，不作为阅读入口。NCX 解析器将 navList 的非空 class 暴露为导航 role，未声明时保持 nav-list。

有原目录时合并地标；仅有 guide 时生成按章节顺序的目录。转换后的 EPUB 3 导航保留地标标签、分组和目标；原始类型继续保存在随书复制的 NCX 资源。目录和地标合计最多 10000 条，guide 字符串、索引与目标均沿用现有验证和字节预算。公开导航快照的不同 role 可在转换时重新分组，条目 parent 以当前数组为准。


## KF8 SVG 资源引用（0.34）

被引用的 image/svg+xml 流以严格 XML 树解析，转换 src/href/XLink、样式属性与 SVG style 元素中的 Kindle 资源 URI，并保留元素/属性的 expanded namespace、无命名空间扩展和普通正文。复用已有 XML 树序列化器输出有效 SVG XML；CDATA、前缀与属性引号可重新编码，XML 注释不保留。外来命名空间的 style 元素不按 CSS 重写。

CSS 和 SVG 流共用一次入队的资源队列，可相互引用并形成环；依赖不递归内联。资源 URI 支持百分号编码片段，转换为本地路径加规范片段。SVG 根命名空间、XML、实体声明与依赖引用均验证，所有输出沿用模型/缓冲区和合计资源预算。框架内置仍只解码 PNG/JPEG；SVG 图形绘制由宿主 decode_image 提供。本次补齐资源关系与结构保真，没有新增 SVG 矢量栅格器。CSS 转义形式的 url 和 @import 仍未转换。


## KF8 ORDT 索引与骨架兼容（0.35）

支持 INDX 的 ORDT 标签映射，包含 codepage 65002 标记及带显式 ORDT 表的普通 UTF-8 索引头。校验两张表的签名、计数、偏移、边界、互不重叠及 TAGX 非重叠；用 ORDT2 将标签字节映射回字节，再解读 FRAG 十进制插入位置或 guide 类型。子索引可继承主表，也可声明相同映射；矛盾映射返回 EXR_FORMAT。当前映射最多 256 项、每项结果须为 0..255，不实现其他未知宽字符索引变体。CNCX 仍使用书籍 UTF-8 字符串。

真实文件还包含重复的 SKEL 片段计数与起止元组。相同重复值已兼容；冲突值拒绝。guide 类型拥有独立短字符串，索引解析失败时统一清理已解码条目，避免引用临时解码数组。


## MOBI/KF8 书名与封面（0.36）

读取 MOBI full-name 字段与 EXTH 503 更新书名，最后一个非空更新值优先；末尾 NUL 填充移除，内部 NUL/非法 UTF-8/XML 字符拒绝。按标题所属头的 UTF-8/Windows-1252 编码解码，原始和解码后的标题各限 64 KiB。混合文件优先现代头，未提供书名或封面时回退旧头；显式 cover=0xffffffff 保持无封面，不回退旧封面。

EXTH 201 的零基封面资源序号使用同一共享/本地资源寻址；已保留的资源直接复用，未在正文出现的封面按需复制。封面须为已识别图像，标记为通用 cover-image 属性，可通过现有资源接口读取；旧 MOBI 正文转换也可保留独立封面。标题和封面属性经结构 EPUB 输出保留。书库导入在没有用户标题覆盖时使用已解析书名；本节不改变 SQLite cover 字段的显式设置接口。


## 书库自动封面导入（0.37）

exr_library_import 统一读取文档资源中的第一个 cover-image token，存入原有 cover 字段，格式适配器不参与数据库逻辑。EPUB、FB2、MOBI/KF8 共用这条路径，标题仍可由调用者覆盖。封面字节最多 8 MiB；超限只省略快捷封面副本，完整封面继续留在保存的原书中，可通过书库文档资源访问。

封面读取在数据库插入前完成。声明封面无法读取时返回相应错误，书籍 ID 为零，不留下半条记录；源书、书名和封面以同一条 INSERT 写入。所有参数绑定结果均检查。现有单独修改封面的接口可继续用于用户编辑。


## 通用固定版面构造（0.38）

`exr_layout_create_positioned(doc, font, input, config, &layout, error)` 接收已定位的页面、exr_glyph、exr_line、exr_box 和 exr_paint 数组，不重新塑形、换行或分页。各页原始坐标从左上起、y 向下，保持比例居中适配 config.page 的 width/height/margin；其余重排样式字段不参与定位排版。图片解码和取消控制继续使用现有配置。没有字形时可不提供字体。

exr_paint 按顺序引用全局字形或色块/图片数组，同一元素可重复绘制。`exr_layout_paints(layout, page, &count)` 返回独立布局快照中该页的借用指令；现有页面、行、字形、图片、色块、位置命中和绘制 API 继续可用。输入数组和文档可在构造成功后释放；字体被保留，解码图片由布局拥有。该接口面向任何固定版面来源，当前尚未接入 PDF 文件解析。

input 必须清零并填写 struct_size；较大的结构仅在未知尾字节全零时兼容，非零未知扩展拒绝。页面/指令数组元素布局固定，扩展通过新的输入尾字段表达。页面数组至多 10000 项，其余数组各至多 4194304 项，复制载荷合计最多 128 MiB；解码图片另用既有 64 MiB 预算。页面行、色块和指令范围须连续覆盖对应数组；行范围连续覆盖字形数组。页与行的 UTF-8 范围、簇范围、字体/节点/资源索引和跨页引用均验证。行内不同簇按视觉 x 顺序提供，绘制顺序通过指令单独决定。

原始尺寸 0.001..10000000；视口 1..16384，margin 必须留出正面积。坐标和变换后坐标必须有限且绝对值不超过 10000000，字形渲染尺寸最多 4096。小于 1/64 像素的字形不栅格化；单字形位图在调用 FreeType 绘制前限制为 8192 边长和 1600 万像素。页面位图仍限 64 MiB。当前指令包含定位文字、矩形与图片；任意路径、仿射绘制和裁剪栈后续继续补齐。
