# Native C API 0.18.0

S013–S100 是保留的历史开发步骤标识，原来被写成 0.13–0.100；产品版本现按 [里程碑映射](VERSIONING.md) 归并。步骤编号用于追溯接口变化，不表示独立发行版本。

公开入口为 `include/exreader.h`；S091 起使用 ABI epoch 1，兼容规则见 [SDK 兼容约定](SDK_COMPATIBILITY.md)。0.12 新增独立双向分析与 OpenType 塑形接口，`exr_glyph` 末尾增加 `offset_x/offset_y/bidi_level`，`exr_layout_config` 末尾增加段落 `direction`，并增加 `EXR_GLYPH_SHAPED` 标志。较早的这些布局变化发生在 ABI epoch 建立之前。宿主按兼容约定选择头文件和库。所有路径和字符串使用 UTF-8。所有 `exr_status` 函数返回 `EXR_OK` 表示成功；可选 `exr_error*` 接收错误详情。

0.12.1 修复审计发现的长附标序列塑形开销、重复章节锚点、超限备注写入、XML 非法字符导出、跨行塑形上下文、RTF Unicode fallback 和 HTML script/style 原始文本处理；`exr_library_note()` 同时支持输出 ID 指向输入 `note.id`。回归覆盖见 [验证记录](NATIVE_VALIDATION.md#0121-audit-fixes)。

## 所有权与并发

### 取消和进度

S016 提供 `exr_control`：可选 `cancelled(context)`、`progress(context,stage,completed,total)` 和借用的 context。回调同步运行在调用线程，引擎不创建后台线程，也不调度 UI；宿主负责选择工作线程。stage 区分随机读取、样式、分页、塑形和绘制，total 为 0 表示未知；嵌套塑形片段或新的资源操作会重新开始自己的局部计数。回调不能销毁或重入正在访问的对象。

通过 `exr_layout_config.control` 控制布局/分页，通过 `exr_shape_options.control` 控制独立塑形，通过 `exr_source.control` 控制读取。`exr_pager_set_control(pager,&control,error)` 可在非忙碌状态替换回调，传 NULL 关闭。取消是协作式的，在阶段边界、文本/lookup 工作批次和图片绘制行批次检查。分页的整段双向分析及依赖库调用会在其相邻检查点响应取消。

取消返回 `EXR_CANCELLED`，失败输出保持 NULL/0。借用分页模式保留之前的页缓存，命中缓存不运行取消回调；解除取消后，下次未命中可从检查点恢复。顺序 `next()` 在任何错误后仍需重建 pager。`exr_render_page_ex(layout,font,page,channels,&control,&bitmap,error)` 接受 channels 为 1 或 4，取消释放并清空部分位图。原来的绘制函数等价于不传 control；绘制调用的 context 只需在这次调用期间有效。

随机读取回调的 control 随源描述符复制，context 必须与保留的源同寿命；布局/分页的 control 随配置复制，context 必须维持到相应工作结束。返回的独立页面不持有布局时的控制回调，之后可用不同的 control 绘制。配置、塑形参数和源描述符在 S016 扩展了字段，需重新编译宿主。

- `exr_document`、`exr_font`、`exr_layout`、`exr_library`、`exr_publication`、`exr_session`、`exr_pager`、`exr_bidi` 为不透明句柄，使用各自析构函数释放。
- document 的 text / title / blocks / nodes / chapters / resources 和 layout 的 pages / lines / glyphs / boxes / image 为只读借用视图，所属对象释放后失效。树节点属性和文本也属于 document。借用的图片像素不可修改或释放。
- 布局拥有输出数据及所引用的图片像素，不保留文档指针。文档释放后仍可绘制；需要源节点内容或资源名称时保留文档。渲染时需传入生成该布局时使用的同一个字体集句柄；字号变化由库设置。相同字体、布局或书库句柄的调用由宿主串行处理；不共享对象的独立句柄可独立使用。共享 publication、session、pager 或压缩 archive 的文档，其调用及生命周期变更也由宿主串行处理；引擎不创建工作线程；SQLite 自身的互斥不代替这些宿主串行约束。
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

S013 支持 CSS `font-family` 列表、引号、CSS 转义、继承和宿主覆盖。指定名称先匹配书内字体，再匹配宿主字体的 FreeType family name，ASCII 字母不区分大小写；无匹配或缺字继续使用宿主的有序回退，不扫描系统字体。选脸按 family 顺序以及常规/粗体/斜体描述符匹配；整字素簇覆盖继续优先。字体已提供的粗斜体不重复合成。

`exr_layout_config_defaults()` 默认开启 `embedded_fonts`。EPUB/宿主 XHTML 的链接或内嵌样式表可声明 `@font-face`，支持 TTF/OTF、相对于 CSS 自身路径的 `url()` 和多个候选来源；只加载可见样式实际引用的 family，书内声明限于所属章节。`local()`、远程 URL 和本机文件 URL 不会访问系统或网络；缺失/损坏字体继续尝试下一来源，最终回退到宿主字体。关闭 `embedded_fonts` 仍可使用宿主字体名称；关闭 `document_css` 不加载书内声明，宿主 `user_css` 仍有效。混合字体集最多 32 个 face、编码字节合计 128 MiB，单次布局字体资源读取合计 128 MiB；最多 64 条字体声明，每声明最多尝试 8 个存在的本地候选资源。压缩 WOFF/WOFF2、EPUB 字体混淆解码和可变字体选择尚未实现。

`exr_layout_font(layout)` 返回有效字体集的借用句柄，`glyph.font_index` 索引该集合。`exr_font_source(font,index,&input,error)` 提供借用的编码字节与 face index，供宿主自行绘制；不要释放或修改借用数据。内置渲染器接受该有效集合、创建布局时的宿主字体，或 NULL（使用布局持有的字体）；传入其他集合仍按旧接口处理。页面持有字体引用，释放 document、pager 和原字体后仍可绘制。共享字体与字体表不计入页面缓存载荷预算。S013 扩展了配置结构，宿主应使用同版本头文件重新编译。

`exr_font_open(path, ...)` 保留单文件、集合首个 face 的入口。`exr_font_create(inputs, count, ...)` 接收有序 `exr_font_input` 数组，每项为编码字体字节 `data/size` 和集合内的 `face_index`（普通字体为 0）。成功时复制全部输入，宿主随后可以释放或修改字节。字体集不可变，用 `exr_font_free()` 释放；布局、渲染和 session 通过现有字体参数接入，无需额外平台后端。字体集需在布局计算、渲染及 session 生命周期内有效，相同句柄的访问由宿主串行处理。

`exr_font_create_glyphs(inputs, count, ...)` 复用相同的输入、复制与预算规则，另外允许没有 Unicode cmap 的可缩放字体。用于宿主已确定字形编号的固定版面；这类 face 的 Unicode 字符查询返回未覆盖，定位字形仍能直接绘制。有 Unicode cmap 的 face 保留正常字符查询。它不猜测字形编号与字符的关系。

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

S014 的借用模式默认每 16 页保留一个恢复点，最多 4 个、驻留载荷合计 2 MiB。`exr_pager_set_checkpoints(pager,capacity,byte_budget,interval,error)` 可设置最多 64 个检查点及非零预算/间隔，capacity 为 0 关闭并释放全部检查点。其预算独立于页面缓存，按实际快照数组、遍历栈及引用的表格单元格布局计量；共享单元格载荷保守地计入每个引用它的快照。超预算或分配失败时跳过新检查点，保留已有检查点并正常返回页面。当前工作区与快照复制期间的临时内存另计。

快照保留原始/暂定/最终行、文档游标、表格 rowspan 组及累计工作量。双向分析按保存的原段落起点重新建立，不把跨行方向当作新段落。恢复点仅在同一个不可变 document、版式和 pager 生命周期内有效，不是持久化格式；顺序 `next()` / 全文布局不会额外保存检查点。`exr_pager_statistics()` 返回累计实际生成页数、驻留检查点数量/字节及成功恢复次数，可用于观察回放开销，NULL 返回全零统计。

续排保留当前行、断点后的 carry、尚未闭合的字素簇 / 塑形片段和文档遍历状态；同一字素簇可跨文本节点和样式，分页不重新切断其边界。表格先扫描轻量行列元数据，再逐个测量当前 rowspan 连通行组；可暂停的边界仍遵循现有 CSS、背景分片和表格分页规则。普通长单段不会在第一页前生成全段字形；双向级别分析仍先扫描可见段落。

SDK 的 `examples/page.c` 编译为 `exreader-page-example`，用法为 `book.epub font.ttf output.png [page] [part]`，page / part 均从 0 开始，默认 0。它只加载指定 EPUB 分段，设置 3 页、8 MiB 的页面缓存，按需续排目标页并输出 PNG，同时打印扫描位置、缓存页数及计量字节数。支持 Windows Unicode 参数和路径。

## 缓存内存计量

`exr_document_memory_size()` 和 `exr_layout_memory_size()` 返回对象拥有的分配 payload 字节数，包含数组已分配容量，不包含分配器元数据；NULL 返回 0，无法用 size_t 表达的合计饱和为 `SIZE_MAX`。这是对象计量，不是进程 RSS。共享压缩 archive、借用字体和其他外部对象不计入；引用同一图片像素的每个页面按完整像素及引用计数字节数保守计量。

页面预算只约束驻留页面的计量总量，分段预算只约束驻留 document 与完整 layout 的计量总量。publication 的共享压缩源、字体及其 OpenType 表缓存、pager 基础状态及当前行/字素簇/塑形段/表格组工作区、整段双向标量与偏移、图片资产池、正在加载的新对象和渲染临时 bitmap 都在该预算之外。文件仍完整解析为一个 document；单个超大字素簇或不可拆 rowspan 行组仍可能需要较大工作区。高于一页的不可拆表格组返回 `EXR_LIMIT`，页缓存预算不构成全程进程内存硬上限。

打开耗时、首画、续排、渲染、完整翻页和进程峰值内存的独立基准及复现命令见 [性能基准](PERFORMANCE.md)。

## 分段 publication 与 session

S017 的 `exr_publication_navigation(publication,&entries,&count,error)` 返回借用的扁平目录树，寿命持续到 publication 释放。每项有 parent、part、label、href、base 和 role：parent 必须指向更早的条目，根为 SIZE_MAX；part 为对应分段索引，外部、未解析或重复路径无法唯一确定的目标为 SIZE_MAX。href 保留原 URI，相对于 base 解释；没有链接的目录组也可保留。role 是开放字符串，内置输出使用 toc、page-list、landmarks、nav-list 或原导航类型。

EPUB 在首次请求目录时读取并缓存 EPUB 3 manifest 中的 nav XHTML，未提供有效条目时读取 EPUB 2 NCX；NCX 遵循 OPF spine 的 toc ID，缺失引用在目录请求时返回 EXR_FORMAT。打开 publication 本身仍不解析导航或章节 XHTML。目录解析沿用有实体/深度限制的 XML 树，保留嵌套关系、Unicode 标题和相对链接；远程 href 只作为元数据返回。失败清空输出并保留重试机会，后续成功查询直接复用缓存。

宿主通过 `exr_publication_input.navigation/navigation_count` 提供任意自有格式的同类目录；构造时复制全部字符串和条目，查询不调用章节 loader。最多 10000 项，标题最多 64 KiB，href/base 最多 2046 字节，role 最多 256 字节，与分段目录的字符串合计限制为 64 MiB。输入验证 UTF-8、parent 和 part 范围；自有 role 和 URI 不需要注册。S017 扩展了 publication 构造输入，宿主需重新编译。

S015 的 `exr_publication_open_source()` 接收通用随机读取源 `{size,read_at,release,context}`。描述符被复制，打开时只读取 ZIP 目录和 EPUB 元数据；读取某章、CSS、图片或字体时才请求对应字节，不把整个压缩源复制进内存。`exr_publication_open(path)` 使用持有文件句柄的同一路径；`open_memory()` 仍复制调用者的输入。

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

CSS `display:none` 只影响布局，不删除规范化正文；重新排版时原有文字位置保持不变。HTML `hidden` 属性在文档投影阶段排除，其行为与 CSS 隐藏不同。旧 `exr_document_export()` 仍为文本转换。S018 新增下述结构导出。

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
| 盒模型 | width / max-width、margin / padding 及四边长属性、background-color（background 仅接受颜色）、统一 border-width / border-color / border-style（solid/none/hidden）和 border 简写；表格 border-collapse（collapse/separate/inherit） |
| 流布局 | display: none/block/inline/table/table-row/table-cell；break-before/after 和 page-break-before/after 的 page/always/auto |
| 浮动 | float: none/left/right/inherit；clear: none/left/right/both/inherit；图片、普通块、表格的逐行避让，范围见下文 |
| 尺寸 | px、pt、em、rem、百分比和零值；margin 可 auto；图片支持 height；表格单元格和浮动块的 height 提供内容下限，其余普通块尚未普遍应用 |
| 颜色 | #RGB、#RGBA、#RRGGBB、#RRGGBBAA；black/white/red/green/blue/gray/grey/transparent/navy/yellow/orange/purple |

`rem` 当前以宿主页默认字号为基准。`inherit` 支持文字属性；缩进和边框宽度不支持百分比。所有负尺寸均忽略，外边距不折叠。未知属性、选择器和 at-rule 会被跳过；尚不支持 @import、@media、变量、伪类、属性选择器、flex/grid、定位、完整空白规则和浏览器式盒模型分片。属性值和单位使用小写。样式表合计上限 1 MiB、4096 条规则、131072 项展开声明、每规则 256 项声明、2000 万次匹配工作；达到上限返回 `EXR_LIMIT`。

`exr_layout_glyphs()` 按逐行视觉顺序输出字形编号、字号、颜色 `0xRRGGBBAA`、合成粗/斜体标志、基线、源范围和字体索引；混排时文字偏移可能不单调。`cluster_start/end` 为当前源簇的 UTF-8 半开范围，可以跨文本节点和样式，连字可合并多个原始字素。`EXR_GLYPH_SHAPED = 16` 表示 advance / offset 已包含塑形定位；这些条目的 `start/end` 也使用源簇范围，`codepoint/node` 代表簇首源标量 / 节点，不承诺一条 glyph 对应一个标量。未塑形路径仍保留原标量范围。`boundaries` 保留源簇首的 `EXR_BOUNDARY_*`，同簇后续字形为 0。分段和文档使用各自局部偏移，簇索引不是永久标识。

`EXR_GLYPH_HIDDEN = 4` 标记格式、换行控制、变体选择符等不应绘制的条目，内置栅格器跳过这些字形，自定义绘制也需跳过；它们仍保留源文本范围。`bidi_level` 是解析后的级别，奇数为 RTL，`UINT_MAX` 表示 X9 控制。`offset_x/offset_y` 以 px 表示，y 向上；绘制原点为 `(x + offset_x, baseline - offset_y)`。自定义绘制不再额外应用 GPOS 或 pair kerning。布局不会拆开源簇，也不会在 `GLUE` 边界紧急断行；不可拆的组超过内容宽度时保留整组，`clip_left/right` 指明水平裁切范围。

`exr_layout_hit_test()` 按视觉簇整体宽度和方向返回源簇起点或终点，不返回连字或字素内部偏移。`exr_layout_lines()` 输出行矩形和视觉字形数组范围，其 start/end 仍是逻辑源范围；表格一行可有多个并列文字行。`exr_layout_boxes()` 输出背景块、图片和单元格的页面坐标、边框与背景，每页先按节点前序输出普通盒子，再按表格节点输出共享边框图层矩形。page 的 line/box 范围可直接迭代。坐标单位为逻辑像素，原点在页面左上方。

宿主可先按 boxes 顺序绘制背景、图片和边框，再绘制文字；标有 EXR_BOX_BORDER 的共享边框矩形需要按下文的图层规则合成。`exr_layout_image(layout, resource)` 返回对应资源的解码后 RGBA 借用视图；缺失时返回 NULL。这些输出可直接用于自定义渲染器，不需要创建内置页面位图。

## 图片、表格与像素

内置 `exr_image_decode()` 接受 PNG/JPEG 字节并返回独立 RGBA 像素，用 `exr_bitmap_free()` 释放。布局按资源缓存图片；图片保持纵横比，限制在内容宽度和可用页高之内。width/height 同时存在时按容纳方式缩放，未声明 float 的图片仍按块处理；浮动图片按下文参与逐行绕排。缺失、外部、损坏或不支持的图片显示带标志的占位框；资源/解码限制错误会中止布局。解码尺寸上限 8192×8192 且总像素不超过 16 Mi，编码输入上限 32 MiB，stb 临时分配上限 128 MiB，布局图片缓存上限 64 MiB。

宿主设置 `decode_image`、`release_image` 和 `image_context` 可替换解码器。回调收到资源元数据及编码字节；返回 `channels=4`、非预乘 RGBA、有效 width/height/stride。引擎复制像素，然后无论成功或失败都调用配套 release 回调一次；不得在 release 中释放借用的编码输入。`EXR_FORMAT` 表示占位框，其余非成功状态中止布局。要保留内置 PNG/JPEG 支持，宿主回调可以调用 `exr_image_decode()` 并在 release 中使用 `exr_bitmap_free()`。直接创建完整 layout 时，回调及 context 只需在 create 调用期间有效；使用 pager / session 时需在相应句柄整个生命周期内有效。渲染已有布局不会再次调用它们。

表格支持指定列宽、单元格换行、colspan 和 rowspan，默认按内容测量列宽。CSS 的 col/colgroup/cell 宽度与 HTML width 属性参与列分配，详见“表格指定列宽”补充。具有跨行单元格的相连行组一起分页；高于一页的行组返回 `EXR_LIMIT`。上限为 64 列、4096 行/单元格、8 层嵌套。支持当前实线边框子集的 border-collapse，规则见下文；尚不支持跨页拆分单元格和重复表头。单元格的可见边框、背景和内边距由样式控制。

`exr_render_page()` 输出 1 通道灰度；`exr_render_page_color()` 输出 4 通道 RGBA。内置渲染器使用白底、双线性图片缩放、透明合成和 FreeType 字形，整页位图不超过 64 MiB。`stride` 是每行字节数。PNG 支持两种通道并保留输入 alpha；BMP 写为 24 位并将 alpha 合成到白底。写入时 `channels=0` 兼容灰度输入。框架不提供窗口、GPU 或事件循环。

## 书库

SQLite 数据库保存原文件 BLOB、封面 BLOB、元数据和 UTF-8 位置标注。书籍主键为库内整数。格式在导入时验证；正文大小用于检查进度和标注范围。书库使用 application_id 与 schema version 检查，拒绝不认识的现有数据库。0.7 将 schema v1 事务迁移到 v2，原标注保留其偏移、备注和 ID，选择器保持 NULL，因此解析为 `LEGACY`；不从新版正文反推旧引文。单句修改使用 SQLite 事务语义，书籍删除通过外键清理笔记。

宿主应零初始化输入 `exr_note`。保存新标注时，`exr_library_note()` 为当前书籍正文捕获文本选择器；修改同范围标注的备注保留已有选择器。宿主可以显式提供 `note.anchor` 重新锚定，锚点的 `start/end` 必须与笔记范围一致。查询的 `exr_note.anchor` 由结果数组拥有，使用 `exr_notes_free()` 一次释放全部内容。稳定锚点保存历史文本证据，实际显示前应调用 `exr_anchor_resolve()` 并检查其状态。

备注 `note.text` 最多 64 MiB，不含字符串终止字节；超限在写数据库前返回 `EXR_LIMIT`，输出 ID 为 0，已有笔记保持不变。恰好 64 MiB 的备注可以保存、读取和再次编辑。输出 ID 可传 `&note.id`：引擎在清零输出前保存输入值，因此更新仍使用原笔记 ID。

`exr_library_backup()` 使用 SQLite VACUUM INTO 生成可直接打开的完整备份；目标数据库不能已有非空内容。封面作为受大小限制的 BLOB 存储；宿主可调用图片解码接口生成像素，封面不自动缩放。媒体大文件的流式导入尚未实现。现有 ZIP / IndexedDB 备份需要未来的迁移工具。

## 嵌入平台

宿主负责文件选择、字体提供、页面纹理显示、触摸 / 鼠标 / 键盘事件和系统生命周期。像素或布局数据可转为纹理或原生绘图命令。Android 可经 JNI 调用 C，Apple 平台可经 Objective-C / Swift 导入 C 头文件；当前尚未提供这些宿主适配器。

## 结构保真的 EPUB 导出（S018）

`exr_document_export_epub(doc, control, &bytes, &size, &error)` 序列化当前文档树，按原路径复制全部声明资源，输出可重新打开的 EPUB。成功后用 `exr_free(bytes)` 释放；失败清空 bytes/size。control 可为 NULL，回调在本次调用内借用，新增 EXPORT 阶段。输入文档不可在回调中修改或释放。

保留章节顺序与 linear 标志、嵌套元素、XML expanded names、属性、原始解码文本、相对链接、表格、CSS、图片、字体和封面资源。资源路径中的 `%/#/?/空格/Unicode` 在 manifest 中正确编码，ZIP 成员使用原始路径。重复 spine 路径只存一份相同 XHTML；同路径不同章节报错。EPUB 3 导航资源保留，EPUB 2 NCX 生成有层级和类别的 EPUB 3 导航。没有目录时按章节生成；匿名章节生成无冲突路径。

没有元素名字的语义节点映射为 XHTML 段落、标题、表格等；有名字的自定义元素保留 XML 名字与命名空间。序列化不保留原 XML 前缀拼写、注释、DTD 或字节排版。任意模型不一定能表示为有效 XML：非法名称、字符、命名空间、重复资源路径、保留路径和缺失资源明确失败。`META-INF/encryption.xml` / `rights.xml` 存在时拒绝导出，避免丢失解密或字体混淆信息。原 OPF 的作者、语言、标识符等尚未进入通用文档元数据模型；当前包重新生成 title/und language/identifier/modified，不承诺原 OPF 字段无损。

与读取限制一致：最多 10000 ZIP 成员，单成员 32 MiB，累计未压缩成员和压缩输出各限 128 MiB。此接口输出完整内存包；不是流式写入。它保留模型已有结构，不会恢复 TXT、旧 DOCX/RTF 等解析时已经丢失的信息。

## FB2 结构解析（S019）

FB2 通过原生 XML 树解析，正文转换到通用语义节点和 XHTML 名字：章节/标题/段落、粗体/斜体、图片、表格及跨列属性、诗行、链接和脚注。`notes` / `comments` 正文中的 section 标记为 NOTE，并保留 ID 与脚注链接。多个 body 按原顺序进入同一分段；当前脚注正文也在阅读流中。未知扩展元素保留源 expanded name 和属性。

binary 使用严格 base64 解码，保留编码资源原字节；重复 ID、非法 padding 和缺失的本地图片/封面引用报错。图片 URI 的 Unicode 百分号转义可用。封面资源标记 `cover-image`。description 只提取书名与封面，不进入正文；binary 编码不进入正文。顶层 stylesheet 进入 head/style，命名 style 转成 class；CSS 选择器匹配转换后的元素名。嵌套深度和节点/字符串预算遵循现有模型限制，单 binary 最多 32 MiB。

已有图片、样式、表格、强调文字和链接可通过 S018 的结构接口转 EPUB；它不会补齐当前排版器不支持的上/下标、删除线或诗歌专有排版。FB2 仍整文件构建 XML 树，未实现章内流式处理。

## DOCX 结构解析（S020）

DOCX 读取 package 主文档关系，支持非默认主文档路径；解析 WordprocessingML transitional / strict 名字。正文进入相同 XHTML/语义树，保留段落、标题、字符与段落样式、书签、内部与外部链接、图片、换行/分页和合并表格。样式读取 docDefaults、默认 paragraph/character style、pStyle/rStyle、basedOn、直接格式；支持粗斜体、字号、颜色、字体名、对齐、间距、缩进及段落方向。继承链最多 64 层，属性读取总工作量限 2000 万。

DrawingML/VML 图片按关系读取，原编码字节进入 resources；可读取尺寸，重复引用共享资源。路径与 Unicode/百分号编码经过解析，外部图片只保留 URI，框架不访问网络。表格的 gridSpan/vMerge 转成 colspan/rowspan；gridBefore/gridAfter 用空单元格保留列位置，最多 256 列。插入修订与字段结果可见，删除修订和字段指令排除；AlternateContent 优先使用 Fallback，没有 Fallback 时取首个 Choice，不重复输出两支。

当前表格采用引擎的自动列宽，尚未实现 Word 专有列宽、表格样式、边框与浮动锚点；图片仍按块排版。页眉页脚、嵌入字体、主题字体/颜色、完整 Word 样式算法及元数据仍待补齐。它是流式阅读模型，未复刻 Word 的打印页面。旧文字导出保持原行为；结构接口可把当前已解析的图片、样式、表格和链接转成 EPUB。

## DOCX 脚注与尾注（S021）

正文 footnoteReference/endnoteReference 生成 LINK 与 `doc-noteref`，注释正文生成 NOTE 与 `doc-footnote` / `doc-endnote`，其中的引用标记生成 `doc-backlink`。重复引用共享同一注释正文，保留唯一引用 ID；脚注与尾注各按首次引用次序显示阿拉伯序号。正文书签加 `bookmark-` 前缀，避免与生成的注释 ID 冲突，内部链接同步转换。

注释分段按主文档关系读取，拥有自己的图片关系与路径基准，可复用主文档图片，也可携带不同图片。生成的图片资源 ID 在整书内唯一。正文中没有引用的注释和 separator/continuationSeparator 不进入阅读流；被引用却缺少正文、重复的普通注释 ID、嵌套注释引用会拒绝解析。普通注释最多 10000 个。当前统一追加在正文后；不按打印页面排脚注，也未实现分节重编号、罗马数字与自定义序号。

结构 EPUB 导出保留上述链接与注释语义。本次同时修正章节路径与非 XHTML 资源冲突的情况，导出会失败并保持空输出，不再覆盖资源。

## DOCX 编号列表（S022）

首次遇到编号段落才读取 numbering 部件。支持 abstractNum/num、9 层 ilvl、样式继承的 numPr、直接关闭编号、start/startOverride、lvlOverride、lvlRestart、isLgl、lvlText 的 `%1`–`%9` 引用与 suff。每个 numId 保存独立计数，跨普通段落后续号；可生成嵌套 OL/UL/LI，段落、单元格和注释使用同一路径。

当前支持 decimal、decimalZero、lowerLetter/upperLetter、lowerRoman/upperRoman、bullet、none；字母和罗马数字的非正值、罗马数字大于 3999 时回退十进制。其他编号制返回 EXR_FORMAT，尚未实现语言相关计数、图片项目符号和 numStyleLink。定义 ID 重复、层级越界、缺失定义、失配引用会拒绝解析。每类定义最多 10000 个，引用的层级配置按需分配。

可见编号保存为段落开头的呈现性 span（role=presentation、aria-hidden=true），其字号/字体等可取自层级 rPr；原序号文本也进入规范化正文与搜索。列表设置 `list-style-type:none`，确保在外部 EPUB 阅读器中不会重复生成编号。此版本没有向核心排版器加入 Word 专用计数规则，也没有为一般 HTML/EPUB 的无文本 LI 自动绘制标记。布局仍使用现有列表缩进，未实现 Word 的精确悬挂缩进和编号制表位。

## RTF 字符与段落结构（S023）

RTF 使用同一文档树保存分组作用域内的粗体/斜体、半点字号、颜色表引用、段落对齐、缩进、段前后距、行距与文字方向。plain/pard 恢复相应属性；par 创建段落，line 保留为段内换行。u/s 元素保留下划线与删除线语义，S026 已加入绘制；inline highlight 尚未绘制背景。

词法器保留 0.12.1 的 Unicode fallback 规则：整条控制词、转义符号、十六进制字节和 bin 段各按一个 fallback 字符消费，fallback 内不执行格式或 destination；分组边界终止 fallback。支持 Windows-1252 与 Unicode 转义；其他 ansicpg 编码仍拒绝。表格、编号列表、脚注和样式表继承仍待后续接入。颜色表最多 4096 项，分组深度上限仍为 255。

RTF 已解析的文字、字号、颜色和段落结构可转成 EPUB；旧文字转换保持原行为。相同属性赋值复用现有字符串，避免逐段更新样式时重复计入模型预算。

## RTF 内嵌图片（S024）

pict 的 pngblip/jpegblip 支持十六进制与 bin 数据，编码字节转移给资源表，IMAGE 节点保留 picw/pich、picwgoal/pichgoal 和缩放后的尺寸。尺寸不指定时使用内在尺寸。单图片最多 32 MiB、picture 分组最多 9996 个；拒绝非法十六进制、半字节残留和 PNG/JPEG 签名失配。wmetafile/emfblip 字节也可保留为资源，内置解码器不绘制它们，宿主可替换图片解码器。

识别紧跟可选 destination 标记的 shppict；已有可显示图片时跳过相邻 nonshppict 兼容分支，避免重复。未知 destination 继续跳过，不会由其中的已知词重新激活。没有编码类型的 pict 保持旧的忽略行为。图片可通过结构接口转 EPUB，字节与显示尺寸保留。

## RTF 字体名称、字段链接与元数据（S025）

fonttbl 的名称（包括 Unicode 转义）转为 font-family，保留 deff 默认字体、f 切换和 plain 恢复。字体编号最多 4095；不扫描系统字体、不加载 fontemb/fontfile，字体字节仍由宿主或书籍资源提供。尚未使用 fcharset 解码其他传统代码页，ansicpg 范围保持 Windows-1252。

field/fldinst/fldrslt 保留字段的可见结果。HYPERLINK 支持引用 URL、`\l` 内部书签、`\o` 提示与 `\t` 目标框架参数；不会执行字段或访问链接。bkmkstart 生成 `bookmark-` 前缀的定位节点，内部链接同步编码。未知字段作为普通可见结果保留；忽略的未知 destination 不能被其中的 field/fonttbl 等词激活。

info/title 提取 UTF-8 书名并同步 XHTML head/title，其他 info 内容不进入正文。字体名、字段指令、书签名和书名各有 64 KiB 临时限制；字体名称和字段元数据累计限制为 64 MiB，已解析的字段指令立即释放。最多 10000 个字段。结构 EPUB 导出保留字体名称、链接、定位节点和书名。

## 通用文字饰线（S026）

u 元素默认下划线，s/strike/del 默认删除线；CSS text-decoration-line 和简单 text-decoration 支持 none、underline、line-through 或两者组合。祖先饰线传播到文字后代，后代的 none 不移除祖先饰线；在饰线源元素上设置 none 可关闭该元素的默认修饰。宿主 user_css 可覆盖这些默认值。

布局字形输出 EXR_GLYPH_UNDERLINE / EXR_GLYPH_STRIKE 标志，普通及页级布局、检查点回放和表格复制均保留。灰度/RGBA 绘制按 FreeType 下划线度量和 OS/2 删除线度量绘制单实线，并遵守文字裁剪。文字 shaping 参数仍只接受粗体/斜体；饰线由布局/绘制层处理。OpenType 分段保留饰线标志，在跨饰线边界时保留 Arabic 相邻字符连接上下文。

DOCX 的默认、继承与直接 rPr 下划线/删除线在 run 层解析，允许直接关闭继承修饰，不把 Word 规则放进 CSS 引擎。RTF/FB2 与宿主模型使用同一饰线输出。当前没有双线、波浪线、跳过字形墨迹或独立饰线颜色；饰线使用当前文字颜色和字形字号。RTL、字体变化和其他样式边界仍遵循已有塑形范围限制。

## MOBI HUFF/CDIC 与记录边界（S027）

原生 C 解码器支持 compression=0x4448 的 HUFF/CDIC：短码缓存、长码表、多个 CDIC、递归压缩词条与已展开词条缓存。循环引用返回 EXR_FORMAT，超过 64 层返回 EXR_LIMIT。完成文本解码后立即释放字典缓存，再进入文档解析。

MOBI 统一校验 PalmDB 记录目录、头长度与文本长度；三种压缩方式（无压缩、PalmDOC、HUFF）均移除记录尾附加项与多字节重叠尾。PalmDOC 回指限定在当前记录内，允许记录内重叠复制，拒绝跨记录回指。UTF-8 / Windows-1252 继续可用。

HUFF 最多 1048576 个词条，整书解压正文与每个展开词条各限 64 MiB，解码缓冲区/缓存合计分配上限 128 MiB，累计复制工作量 256 MiB、码字工作量 134217728 次。该分配预算不包含原书、词条元数据与后续文档模型。目录字段先预检，词条缓存按引用展开。当前仍提供 MOBI 正文模型；KF8 结构重建、图像/链接与富排版仍待补齐，加密书籍不支持。


## KF8 章节重建（S028）

原生 C 解析 version=8 的 UTF-8 KF8，复用三种 MOBI 记录解压方式。FDST 分离正文流和附加流；INDX/TAGX 支持多个索引记录、多个控制字节、按值数量或按字节长度编码的 VWI。SKEL/FRAG 按索引次序拼接为独立 XHTML 章节，进入通用文档树；无骨架表时将完整正文流解析为一章。章节、属性与文字可经结构 EPUB 导出。

索引最多 262144 项，章节/资源最多 10000 项，重建文字受 64 MiB 缓冲区上限约束，累计插入搬移最多 256 MiB。记录目录、索引头、TAGX 掩码、IDXT 边界、VWI 溢出、片段长度与插入位置均验证；骨架原始区间不得重叠，不猜测修复损坏片段。附加流暂以 application/octet-stream 资源保留。当前未接通 kindle:flow/embed/pos 资源引用、FONT 解包、NCX、混合 MOBI/KF8 或 ORDT 特殊采样本编码；后续继续补齐。


## KF8 资源与 FONT（S029）

kindle:flow 的 text/css 与 image/svg+xml 引用转为本地资源路径；kindle:embed 按首资源记录和一基 Base32 序号定位，重复引用共享一份资源。CSS 的 url()、文档 src/href/poster/data、内联样式与 style 正文接通资源表，保留 CSS 注释、普通字符串及阅读正文中的相同文字。CSS 资源依赖按队列处理，每份只处理一次，允许循环引用。

PNG/JPEG 可直接绘制；GIF/WebP 和 SVG 流保留为资源，须由宿主提供相应解码器。SVG 内部的 Kindle 引用、CSS 转义形式的 url 与 @import 尚未转换。FONT 支持无压缩、zlib、前 1040 字节 XOR 混淆或两者组合，校验字段、密钥区间、解压精确长度和压缩流尾；恢复字体原字节后交给现有字体选择和排版。支持 TTF/OTF/TTC/WOFF/WOFF2 签名，实际可用字体由 FreeType 构建能力决定。

每个新增图片或字体最多 32 MiB，全部章节/流/资产编码字节合计最多 128 MiB；字体解包另使用最多两份 32 MiB 临时缓冲区。未识别的嵌入资源签名、无效 URI、越界序号及同一流的 MIME 冲突返回 EXR_FORMAT。XHTML 资源接口保留重建后的原始字节，通用树上的链接是转换后的本地路径；结构 EPUB 输出使用树并保留已转换 CSS 与原始图片/字体。


## KF8 定位链接（S030）

kindle:pos:fid:BASE32:off:BASE32 按片段序号及片段内字节偏移，映射到重建章节中该位置之前最近的命名锚点。解析器在元素开始时保留原始字节位置；ID 属性已完整解析，目标位于标签内部时可匹配当前标签。进入 body 时重置为章首；没有更近的命名锚点则链接到章首。读取 id、xml:id 和旧式 a/name，后者补同名 id 以接入通用链接解析。

输出为规范章节路径和百分号编码片段，支持 Unicode、空格、%、# 等 ID；同一 ID 可在不同章节重复，同章重复命名锚点返回 EXR_FORMAT。片段序号、偏移、重建章节范围、语法和 Base32 溢出均验证，越界失败，不重定向猜测目标。临时位置索引按命名元素数量增长，受通用节点上限约束，链接转换后释放。位置映射仅内部使用，公共节点的 start/end 仍是归一化正文范围。


## 文档导航与 KF8 NCX（S031）

`exr_document_navigation(doc, &entries, &count, error)` 从文档声明的 nav/NCX 资源读取导航，返回独立拥有的 exr_navigation 数组；使用 `exr_navigation_free(entries, count)` 释放。快照可在文档释放后继续读取；没有作者目录时返回 NULL/0。该接口沿用 EPUB 和自定义资源的通用解析，条目包含 parent、part、label、href、base 和 role。publication_navigation 的借用语义保持原样，不要释放它返回的借用数组。

KF8 的 NCX INDX/CNCX 转为标准 NCX 资源，使用标签偏移（含多 CNCX 记录的 65536 基数）、级别、可选父子关系和 fid/off 定位，连接已有章内锚点。父子关系省略时从层级推导；显式关系必须与层级一致。目录元数据不加入正文；结构 EPUB 转换保留目录层级与目标。最多 10000 条目录、250 层嵌套；CNCX 单记录最多 65536 字节，总字符串数最多 262144、总字节最多 64 MiB。拒绝缺失标签、非完整 VWI、非法尾填充、级别跳跃、矛盾父子关系及无效目标。当前未接入 KF8 guide、混合 MOBI/KF8 头与 ORDT 特殊采样本编码。


## MOBI/KF8 混合容器（S032）

旧 MOBI 头通过 EXTH 121 声明 KF8 头记录时，验证前一条恰为 BOUNDARY，再按 KF8 头的相对记录索引读取正文、HUFF 字典、FDST、SKEL/FRAG 和 NCX。旧正文不重复加入阅读流。前半部首资源到边界之间的记录作为共享资源前缀，保持序号与占位记录；后半部本地资源接在共享前缀后。图片、字体可以全部共享、部分共享或全部本地存储。

选择由 EXTH 121 明确驱动；不存在该字段或值为 0xffffffff 时保持旧 MOBI 解码，不扫描内容猜测边界。校验 EXTH 长度、计数、记录长度与重复边界字段、指针、标记、目标版本及共享资源起点。EXTH 最多 262144 项；两部分加密标志均须为零。解析器借用原输入的记录，不拼接或复制整份容器。


## KF8 guide 地标（S033）

guide INDX/CNCX 保留类型、标签和片段目标，接入同一位置解析与导航快照。支持 tag 3 的片段序号、tag 6 的片段序号及可选偏移。输出 NCX navList class=landmarks；每个 navTarget 的 class 保存原始 guide 类型，start 规范化为 text。thumbimagestandard 是缩略图元数据，不作为阅读入口。NCX 解析器将 navList 的非空 class 暴露为导航 role，未声明时保持 nav-list。

有原目录时合并地标；仅有 guide 时生成按章节顺序的目录。转换后的 EPUB 3 导航保留地标标签、分组和目标；原始类型继续保存在随书复制的 NCX 资源。目录和地标合计最多 10000 条，guide 字符串、索引与目标均沿用现有验证和字节预算。公开导航快照的不同 role 可在转换时重新分组，条目 parent 以当前数组为准。


## KF8 SVG 资源引用（S034）

被引用的 image/svg+xml 流以严格 XML 树解析，转换 src/href/XLink、样式属性与 SVG style 元素中的 Kindle 资源 URI，并保留元素/属性的 expanded namespace、无命名空间扩展和普通正文。复用已有 XML 树序列化器输出有效 SVG XML；CDATA、前缀与属性引号可重新编码，XML 注释不保留。外来命名空间的 style 元素不按 CSS 重写。

CSS 和 SVG 流共用一次入队的资源队列，可相互引用并形成环；依赖不递归内联。资源 URI 支持百分号编码片段，转换为本地路径加规范片段。SVG 根命名空间、XML、实体声明与依赖引用均验证，所有输出沿用模型/缓冲区和合计资源预算。框架内置仍只解码 PNG/JPEG；SVG 图形绘制由宿主 decode_image 提供。本次补齐资源关系与结构保真，没有新增 SVG 矢量栅格器。CSS 转义形式的 url 和 @import 仍未转换。


## KF8 ORDT 索引与骨架兼容（S035）

支持 INDX 的 ORDT 标签映射，包含 codepage 65002 标记及带显式 ORDT 表的普通 UTF-8 索引头。校验两张表的签名、计数、偏移、边界、互不重叠及 TAGX 非重叠；用 ORDT2 将标签字节映射回字节，再解读 FRAG 十进制插入位置或 guide 类型。子索引可继承主表，也可声明相同映射；矛盾映射返回 EXR_FORMAT。当前映射最多 256 项、每项结果须为 0..255，不实现其他未知宽字符索引变体。CNCX 仍使用书籍 UTF-8 字符串。

真实文件还包含重复的 SKEL 片段计数与起止元组。相同重复值已兼容；冲突值拒绝。guide 类型拥有独立短字符串，索引解析失败时统一清理已解码条目，避免引用临时解码数组。


## MOBI/KF8 书名与封面（S036）

读取 MOBI full-name 字段与 EXTH 503 更新书名，最后一个非空更新值优先；末尾 NUL 填充移除，内部 NUL/非法 UTF-8/XML 字符拒绝。按标题所属头的 UTF-8/Windows-1252 编码解码，原始和解码后的标题各限 64 KiB。混合文件优先现代头，未提供书名或封面时回退旧头；显式 cover=0xffffffff 保持无封面，不回退旧封面。

EXTH 201 的零基封面资源序号使用同一共享/本地资源寻址；已保留的资源直接复用，未在正文出现的封面按需复制。封面须为已识别图像，标记为通用 cover-image 属性，可通过现有资源接口读取；旧 MOBI 正文转换也可保留独立封面。标题和封面属性经结构 EPUB 输出保留。书库导入在没有用户标题覆盖时使用已解析书名；本节不改变 SQLite cover 字段的显式设置接口。


## 书库自动封面导入（S037）

exr_library_import 统一读取文档资源中的第一个 cover-image token，存入原有 cover 字段，格式适配器不参与数据库逻辑。EPUB、FB2、MOBI/KF8 共用这条路径，标题仍可由调用者覆盖。封面字节最多 8 MiB；超限只省略快捷封面副本，完整封面继续留在保存的原书中，可通过书库文档资源访问。

封面读取在数据库插入前完成。声明封面无法读取时返回相应错误，书籍 ID 为零，不留下半条记录；源书、书名和封面以同一条 INSERT 写入。所有参数绑定结果均检查。现有单独修改封面的接口可继续用于用户编辑。


## 通用固定版面构造（S038）

`exr_layout_create_positioned(doc, font, input, config, &layout, error)` 接收已定位的页面、exr_glyph、exr_line、exr_box 和 exr_paint 数组，不重新塑形、换行或分页。各页原始坐标从左上起、y 向下，保持比例居中适配 config.page 的 width/height/margin；其余重排样式字段不参与定位排版。图片解码和取消控制继续使用现有配置。没有字形时可不提供字体。

exr_paint 按顺序引用全局字形或色块/图片数组，同一元素可重复绘制。`exr_layout_paints(layout, page, &count)` 返回独立布局快照中该页的借用指令；现有页面、行、字形、图片、色块、位置命中和绘制 API 继续可用。输入数组和文档可在构造成功后释放；字体被保留，解码图片由布局拥有。该接口面向任何固定版面来源，当前尚未接入 PDF 文件解析。

input 必须清零并填写 struct_size；较大的结构仅在未知尾字节全零时兼容，非零未知扩展拒绝。页面/指令数组元素布局固定，扩展通过新的输入尾字段表达。页面数组至多 10000 项，其余数组各至多 4194304 项，复制载荷合计最多 128 MiB；解码图片另用既有 64 MiB 预算。页面行、色块和指令范围须连续覆盖对应数组；行范围连续覆盖字形数组。页与行的 UTF-8 范围、簇范围、字体/节点/资源索引和跨页引用均验证。行内不同簇按视觉 x 顺序提供，绘制顺序通过指令单独决定。

原始尺寸 0.001..10000000；视口 1..16384，margin 必须留出正面积。坐标和变换后坐标必须有限且绝对值不超过 10000000，字形渲染尺寸最多 4096。小于 1/64 像素的字形不栅格化；单字形位图在调用 FreeType 绘制前限制为 8192 边长和 1600 万像素。页面位图仍限 64 MiB。当前指令包含定位文字、矩形与图片；任意路径、仿射绘制和裁剪栈后续继续补齐。


## 通用固定页面视口（S061）

`exr_viewport_create(&geometry, scale, &viewport, &error)` 为任意固定版面来源生成正向和逆向仿射矩阵，不分配内存。`geometry.bounds` 是原始坐标的 `[x0,y0,x1,y1]`，`unit_scale` 是正数单位倍率；`rotation` 为顺时针 0/90/180/270 度，`y_down` 表示原坐标是否向下增加。输出从左上开始、y 向下，包含实际宽高、绘制矩阵和命中测试所需的逆矩阵。`scale=1` 保留单位倍率后的自然尺寸，调用方可自行据此适配窗口或设备像素比。

矩阵使用 `[a,b,c,d,e,f]`：`x'=a*x+c*y+e`，`y'=b*x+d*y+f`。输入/输出坐标和矩阵元素限绝对值 10000000；无面积、非法旋转或非有限参数返回 EXR_ARGUMENT，尺寸/逆矩阵超出预算返回 EXR_LIMIT，失败时输出清零。该函数与 PDF、字体、图像和 UI 都无绑定；它不打开 PDF 文件。


## 通用 C 画布（S062）

`exr_canvas_create` 创建立即绘制的灰度/RGBA 画布；配置中的 width/height 必填，channels=0 默认 RGBA，background 为 0xRRGGBBAA，mask_budget=0 默认 64 MiB。它与 PDF、文档树、字体和 UI 无绑定。输入的路径、样式、矩阵、图片及遮罩仅在绘制调用期间借用，调用后即可释放或修改。

- `exr_canvas_path` 接收 move/line/quad/cubic/close 段和仿射矩阵，支持 nonzero/evenodd 填充与虚线、端点、连接描边。用 `exr_draw_style_defaults()` 初始化样式；NULL 样式等同默认黑色填充。stroke_matrix 默认与路径矩阵相同；显式传入单位矩阵可形成不随路径缩放的描边。
- `exr_canvas_clip` 与当前裁切区域相交。save/restore 保存裁切区域，样式按每次调用传入；最多 160 层，引用同一个不可变掩码时不复制像素。
- `exr_canvas_image` 读取通用 exr_image_layer：RGBA 位图可拥有不同尺寸/插值方式的 opacity mask，mask_mode 使用 EXR_MASK_GRAY 或 EXR_MASK_ALPHA；支持预混合底色移除。图层最多 16 层，循环、目标别名和非法矩阵拒绝。
- `exr_canvas_bitmap` 返回当前借用图像，`exr_canvas_take` 转移像素所有权，随后用 `exr_bitmap_free` 释放；取走后画布不再接受绘制。`exr_canvas_memory_size` 报告画布、拥有的像素和裁切掩码载荷，不含瞬时曲线/边数组或宿主图片。

输出最多 64 MiB、边长最多 16384，单路径命令/边数限制沿用 C 矢量核，全部绘制共享 256M 工作预算和取消控制。任何失败的绘制都将画布置为失败状态，后续 take 返回首个失败，避免交付半张图片。PDF 路径、字形轮廓、图片和裁切已调用相同的通用画布；其字体/格式读取留在解析器一侧。


## 字形轮廓读取（S063）

`exr_font_glyph_outline(font, font_index, glyph_id, &segments, &count, control, error)` 返回独立拥有的 move/line/quad/cubic/close 路径，用 `exr_free` 释放。坐标归一化为 1000 em，基线原点为零、y 向上，不进行 hinting 或位图栅格化。读取后可释放字体，路径继续有效；空字形返回 NULL/0。该接口按实际 glyph ID 读取，也支持 `exr_font_create_glyphs` 创建的无 Unicode cmap 字体。

例如将字号 `size` 的轮廓画到基线 `(x, baseline)`，可给 `exr_canvas_path` 传入 `[size/1000, 0, 0, -size/1000, x, baseline]`。宿主也可自行消费这些曲线，不使用引擎画布。无效字体/索引/字形返回 EXR_ARGUMENT，预算与取消控制沿用轮廓核；失败清空路径/count。与 shape/layout/render 一样，同一个字体对象不能并发参与这些操作。


## 通用流式绘制回调（S064）

`exr_draw_sink` 提供 path、image、clip、state 四种回调及 context。解析器可以直接输出通用路径、样式、矩阵和分层图片；宿主可使用原生图形接口、记录器或检查工具消费这些数据。回调参数只在该次回调期间借用，需保存时自行复制。未提供的回调被跳过，回调返回非 EXR_OK 可终止遍历。

`exr_canvas_get_sink(canvas, &sink, &error)` 将同一协议连接到内置 C 画布，无须另写适配绘制代码。sink 借用画布，不增加其生命周期。

clip 的 accumulate=0 立即与当前裁切相交，accumulate=1 将路径加入待提交的并集。state 的 EXR_DRAW_BEGIN_CLIP 清理未提交并集，EXR_DRAW_END_CLIP 将已累计的并集与当前裁切相交；没有累计路径时不改变裁切，可通过累计一次空路径显式建立空裁切。EXR_DRAW_SAVE/RESTORE 继续保存/恢复当前裁切。渲染消费者需要处理全部四类事件；只提供部分回调适合内容检查。

PDF 的私有格式适配器已改为输出这一协议：字体编号先转为通用字形路径，图片保留独立分辨率遮罩，裁切组不依赖位图后端。内置 PDF 栅格化只是通用回调的一个消费者，格式解析与像素输出已经分开。


## 开放固定页面文档模型（S065）

`exr_fixed_create` 接收通用页目录和按需 draw 回调，不要求来源是 PDF。`exr_fixed_input` 清零并设置 struct_size；成功时复制标题、页 ID/标签和 geometry，并接管 context 的 release 回调。失败时上下文仍由调用方管理。空 ID 自动生成为 page-1 等，有效 ID 必须唯一；目录顺序保持不变。页数最多 10000，单字符串最多 64 KiB，字符串载荷总计最多 8 MiB。未知扩展尾部只有全零时可兼容。

标题和 `exr_fixed_pages` 返回的快照属于文档，可在创建后释放输入目录/字符串。`exr_fixed_memory_size` 仅统计拥有的目录及元数据，不假定提供者上下文的内部结构；释放文档时调用 release。创建和查询不会调用 draw，因此不会预先绘制全书。

`exr_fixed_draw(document, page, matrix, sink, control, error)` 按需调用该页提供者，矩阵 NULL 等同单位矩阵，不自动添加裁切或状态变化，适用于宿主自绘和内容检查。提供者须跳过未实现的 sink 回调。`exr_fixed_render` 则统一创建自然视口和页面裁切，接入 C 画布并返回独立图像；NULL 选项使用白底 RGBA，显式零背景使用透明 RGBA。无论提供者在何时失败，返回图像都保持为空。

同一文档不能并发绘制，也不能在回调中重入绘制或释放文档；元数据查询可在回调中使用。提供者和绘制消费者均可返回错误或取消，状态及诊断会传回调用方。该模型不强制 DOM、字体库、持久化或某种解析器实现。


## 公开固定格式打开 / PDF（S066）

`exr_fixed_open(path, options, &document, error)` 接受 UTF-8 文件路径；`exr_fixed_open_memory(EXR_PDF, bytes, size, options, &document, error)` 复制输入字节，调用后可释放原缓冲。当前内置固定格式为 PDF，自定义格式继续通过 `exr_fixed_create` 接入。输入最多 128 MiB；文件入口接管已读取缓冲，不再重复复制整本文件。打开时读取交叉引用、页树和页目录，字体、内容和图片按绘制请求解析。文件入口暂以文件名作为默认标题，内存入口没有文件名时标题为空。

options 可为 NULL；非空时清零并设置 struct_size。fallback_font 是可选的宿主有序字体集，打开成功后被文档保留，调用方可释放自己的引用。未嵌入的简单字体按名称/粗斜体匹配宿主字体；支持字体集合中的指定 face_index。没有可用宿主字体时，该页绘制明确失败，不搜索系统字体；坏的嵌入程序也不被替换。同页相同字体字节和集合索引共享底层字体 face，避免多个 PDF 字体声明重复解析同一宿主字体。

通过 `exr_fixed_pages` 读取页目录，使用 `exr_fixed_render` 绘制任意一页，或 `exr_fixed_draw` 接收通用路径/图片/裁切回调自行绘制。一个页面解析/编解码/绘制失败后会丢弃该次惰性解析缓存；下一次访问重新建立读取器，其他页面仍可继续使用。页面几何、源字节和宿主字体保持有效。options.control 只用于打开过程；绘制和取消由各次 draw/render 参数控制。

`examples/fixed.c` 展示打开、可选字体、页查询、渲染和 PNG 输出；安装 SDK 的示例工程也构建它。Windows 示例通过统一 UTF-8 参数入口支持中文文件名。PDF 文字搜索/选择/标注接入、Info/XMP 元数据以及尚未实现的复杂绘制特性继续补齐。


## 通用固定页文字快照（S067）

`exr_fixed_text_create` 复制显式长度的 UTF-8 和 `exr_text_region` 数组；文字允许内嵌 NUL。每个 region 保存 UTF-8 字节区间、源页面坐标四边形以及竖排/不可见标志。区间可重叠，一个区间可有多个四边形，数组顺序由提供者定义。接口不假定 PDF、DOM 或特定阅读顺序。四个点的排列由提供者说明，不能从 region 推断精确字形墨迹。

`exr_fixed_input.text` 是可选尾字段，旧版 required prefix 仍可创建文档。`exr_fixed_load_text` 按需调用提供者，返回独立拥有的快照；文档释放后仍能读取快照。用 string/regions getter 读取，最终调用 `exr_fixed_text_free`。没有提供者时返回 EXR_FORMAT；失败或取消不会返回部分结果，回调重入被拒绝。

文字最多 64 MiB、region 最多 4M、总载荷最多 128 MiB。创建校验 UTF-8、区间边界、有限坐标和标志，并支持取消。S068 起内置 PDF 也提供文字快照。


## PDF 文字快照（S068）

`exr_fixed_load_text` 现在支持内置 PDF。结果按内容操作符顺序连接 ToUnicode / 已知编码语义映射，保留多字符连字、NUL、非 BMP 字符以及嵌套 Form 的完整变换。源坐标仍未应用页面 CropBox、Rotate 和 UserUnit；使用公开 viewport 矩阵映射到屏幕。无需宿主字体，也不需要可绘制的嵌入字体轮廓。

水平区域依次为左下、右下、右上、左上，经文字和 Form/CTM 变换。高度优先用 descriptor 的 Ascent/Descent，其次 FontBBox，缺失时估计为 -200 至 800 em/1000。竖排区域第一边沿文字推进方向，厚度使用声明的水平字宽。区域是逻辑字格，不是实际墨迹边界；连字对应整个语义范围。Tr 3/7 标为不可见；裁切、遮挡、alpha 和页面外文字不在语义层过滤。

文字提供者每页最多 32 MiB - 1 字节、region 数组最多 64 MiB。图片无须解码，失败/取消丢弃部分结果且下一页可重试。此阶段保持内容顺序，不推断空格/换行，不重建 tagged PDF 阅读顺序或 ActualText。


## 固定页搜索、选择和点击（S069）

`exr_fixed_text_find(text, query, query_size, from, control, &start, &end, error)` 按显式长度做精确、大小写敏感 UTF-8 搜索，包含 NUL；from 落在多字节内部时向后移动到下一边界。无结果时 start/end 为 SIZE_MAX，查询最多 1 MiB。KMP 时间为 O(正文+查询)，临时前缀表最多 4 MiB，可取消。重排正文 `exr_document_find` 也复用此实现，但保留原有 NUL 结尾 query 参数。

`exr_fixed_text_select` 接受 UTF-8 字节范围，复制所有相交的非空文字 region，保持提供者顺序。空选择返回 NULL/0；多个 region 同范围时全部保留，部分连字也返回整个连字的原范围和字格。结果用 exr_free 释放。

`exr_fixed_text_hit` 在源页面坐标中计算点到实际四边形的距离，max_distance 指定允许距离，exclude_flags 可过滤不可见或竖排区域；返回 region 索引，无命中为 SIZE_MAX。同距离选择数组中第一个 region。支持旋转、斜切和退化线段，不用包围盒代替字格；先用 viewport.inverse 把屏幕坐标映射回源坐标。它返回整个语义范围，宿主决定连字内部光标策略。选择和命中均线性遍历当前页并支持取消。


## 固定页稳定标注锚点（S070）

`exr_fixed_anchor_create(page_id, text, start, end, &anchor, error)` 保存页 ID、原字节范围、最多 64 KiB 的精确引用及两侧各 32 个 Unicode 标量上下文。exact/prefix/suffix 带显式长度，可包含 NUL；输出须为空，创建成功后独立拥有所有字节，使用 exr_fixed_anchor_free 释放。宿主可直接序列化这些公开字段，备注、颜色和分类由宿主管理。

`exr_fixed_anchor_resolve` 在指定页快照内比较引用与上下文，返回 FOUND/MISSING/AMBIGUOUS。只有 FOUND 提供新范围，可再次交给 exr_fixed_text_select 获取当前字格。页 ID 不匹配不会跨页猜测；原偏移不用于打破重复内容的平局。支持空范围书签与可取消线性搜索；与重排正文锚点共用匹配实现。此接口定位宿主创建的标注，不读取或改写 PDF 内置 annotation 对象，也尚未连接 SQLite 固定页备注表。


## PDF 书库与固定页备注（S071）

`exr_library_import(EXR_PDF, ...)` 保存原始 PDF 和页数，不预先提取全书文字；标题空缺时使用 Untitled。通过 exr_library_fixed 重新打开固定文档，options 可提供宿主字体和打开取消。PDF 的 book.position 是从零开始的页索引，页数值可表示阅读结束；重排书籍仍使用原正文偏移。书名、标签、收藏、封面、删除和备份接口共用现有书库。

`exr_library_fixed_note` 接受 exr_fixed_note 的 id/book_id/page/start/end/text。新增时 id=0，更新要求原 id 属于该 book。每次写入从保存的原书读取指定页并捕获稳定锚点，输入 anchor 不参与写入；参数 control 支持取消，失败不写入。备注最多 1 MiB，引用最多 64 KiB。区间为当前页 UTF-8 边界，允许空范围书签。

`exr_library_fixed_notes` 按页、范围和 id 返回独立拥有的备注及锚点，使用 exr_fixed_notes_free 释放；引用和上下文以 BLOB 保存，保留内嵌 NUL。读取校验类型、UTF-8、范围与选择器，失败不返回部分列表；查询最多 100000 条、64 MiB 逻辑载荷。remove_fixed_note 删除备注，删除原书自动级联。备份包含原文件与固定备注。重排 note 接口会拒绝 PDF。

SQLite schema 升至 3，v1/v2 自动在事务内迁移；迁移失败完整回滚。旧二进制不能打开 schema 3。备注暂为 SDK 自有数据，不写回 PDF 文件。


## 通用有声书时间线（S072）

`exr_audio_create` 复制轨道、章节及图文同步表。轨道按输入顺序连接，duration_ms 必须为已知非零时长；所有时间使用 uint64 毫秒并检查总和溢出。ID 可由宿主给出，空轨道/章节 ID 自动生成 track-N/chapter-N，同表中必须唯一。URI 和媒体类型是宿主元数据，不自动访问网络或假定编解码器。

章节以全局半开区间表示，可跨轨道。parent 必须为 SIZE_MAX 或之前的包含章节；不同根章节可以重叠。同步片段包含任意 part_id、宿主 UTF-8 字节范围及全局音频区间，可重叠。框架不要求该 ID 对应特定文档格式，也不读取正文来验证其字节范围。

`exr_audio_locate` 二分定位轨道和本地时间；轨道边界归下一轨，总结束时间归末轨 EOF。`exr_audio_sync_at` 枚举当前时间覆盖的片段；`exr_audio_sync_text` 从文字范围或点位置反查同步片段。通过 from=index+1 继续枚举，未命中为 SIZE_MAX。查询保持宿主顺序，支持取消。getters 返回 audio 拥有的不可变表，memory_size 统计拥有的表与字符串。

输入结构设 struct_size，未知尾部只接受全零。最多 10000 轨、100000 章、1000000 同步片段；单字符串最多 64 KiB、全部字符串最多 16 MiB，表载荷最多 128 MiB。该阶段交付时间线与同步模型，解码、声音输出、倍速与播放会话继续接入。


## 有声书播放后端与续播（S073）

`exr_audio_player_create` 保留 audio，接管成功创建后的 backend context。创建、首次播放前跳转/恢复/改倍速均不打开设备；最后释放 player 时若访问过后端则发送 CLOSE，再调用 release。callback 同步接收 LOAD/PLAY/PAUSE/SEEK/RATE/CLOSE、轨道元数据、本地时间、倍速及 generation。LOAD 替换当前源并停在暂停状态，SEEK/RATE 保持播放状态，CLOSE 关闭当前后端，不依赖命令中的来源描述选择设备。具体编解码、变速算法与声音设备由宿主后端实现。

play/pause/seek/rate 控制请求状态，倍速范围为 (0,16]，后端可按实际能力拒绝。已完成时 play 从头开始；在非末轨 EOF 开始播放会进入下一轨。get 返回轨道、全局/本地位置、倍速和请求播放状态。宿主通过 report 上报真实本地位置及 EOF；EOF 自动切换下一轨或结束。每组改变状态的命令使用新的 generation，过期、回退和不同轨道回报不改变当前状态。读状态可在 callback 内使用，重入修改会被拒绝；同一 player 不支持并发访问。

命令失败时保留最后确认的位置和倍速、清除请求播放状态并标为 needs_reload，同时尝试暂停后端。下一次操作从 LOAD 恢复，不把部分成功当成完成。后端无诊断的错误会补充信息。

通过 get 的 track_id/offset_ms/rate 保存书签或续播点，再调用 restore 恢复为暂停；在原书前面插入其他轨道也可依照稳定 ID 找回位置。宿主负责持久化这些字段和备注。audio_time 提供轨道本地时间到全局时间的 O(1) 映射。此阶段测试使用可控后端，平台声音设备适配和实际音频解码尚未交付。


## C 原生 WAV 按需解码（S074）

`exr_wave_open` 从 UTF-8 路径打开 RIFF/WAVE，`exr_wave_open_source` 接受宿主随机读取源。源上下文只在成功打开后接管；source.control 仅用于打开，此后各次 read 使用自己的 control。打开只扫描 chunk 头和必要的 fmt 字段，跳过音频载荷；不常驻复制整段音频。文件读取支持 64 位偏移，原电子书文件源仍保留 128 MiB 上限。

支持 little-endian 整数 PCM 8/16/24/32 位、IEEE 浮点 32/64 位，以及 WAVEFORMATEXTENSIBLE 的 PCM/float GUID、有效位和声道掩码。最多 32 声道，采样率 1–768000 Hz，检查块对齐、字节率、RIFF/chunk 长度和填充。format getter 返回采样率、声道、容器/有效位、掩码及总帧数。

`exr_wave_read` 按帧定位，输出交错 float 样本；调用方准备 frames*channels 容量，每次最多 65536 帧。内部只用 4 KiB 读取缓冲，源短读取会重试。整数样本归一化，float 超幅裁切至 [-1,1]，NaN/Inf 拒绝；取消或运行时错误将整个请求输出清零并返回 read=0。EOF 返回剩余帧数，尾部输出为零。同一 reader 拒绝重入读取。

当前不解码压缩 WAV、RF64、RIFX 或多个 data 块；MP3/AAC/M4B 解码、变速处理和操作系统声音输出继续接入。


## 有声书续播与时间书签持久化（S075）

`exr_library_audio_resume` / resume_get 保存和读取 track_id、offset_ms、rate。宿主提供稳定 audio_id，不绑定文件 URI、书籍格式或 books 行 ID；可用于独立有声书或书籍的配音轨道。把 player_get 的相应字段写入 checkpoint，重开后通过 player_restore 恢复。没有保存记录时 get 返回 found=0、空 checkpoint；读取结果使用 exr_audio_checkpoint_free 释放。

`exr_library_audio_bookmark` 新增/修改带标签的时间书签，id=0 表示新增，更新必须属于同一个 audio_id。bookmarks 按 id 返回独立列表，用 exr_audio_bookmarks_free 释放。remove_audio_bookmark 删除单项，clear_audio 在事务中同时删除该 key 的续播与全部书签。独立 key 由宿主管理生命周期，删除普通书籍不会隐式清理它。备份包含这些表。

时间以 8 字节小端 BLOB 保留完整 uint64 范围；恢复到实际时间线时，player 仍校验轨道 ID 与本地时长。保存不自动读取声音文件。audio_id 最多 4096 字节，track_id/标签最多 64 KiB；标识非空且文本须为 UTF-8。查询最多 100000 项和 64 MiB 逻辑载荷，损坏记录不会返回部分结果。schema 4 从 v1/v2/v3 在事务内迁移；旧版二进制会拒绝新版本库。


## 安装后的 WAV 宿主示例（S076）

`examples/wave.c` 只依赖公开头文件和 SDK 动态库，按 1024 帧读取 WAV 并打印采样率、声道、总帧数和峰值。它提供交错 float 数据接入宿主声音设备的入口，不打开设备。安装包包含可用标准库脚本重新生成的原创 400 Hz PCM 样本。命令为 `exreader-wave-example input.wav`，Windows 入口支持 UTF-8 路径。三桌面 CI 在独立安装 SDK 后构建并运行此示例，Windows 还覆盖中文文件名。


## Swift 接入（S077）

安装后的 include/module.modulemap 提供 `import CEXReader`，直接开放全部 C 接口。`bindings/swift/EXReader.swift` 提供 ARC 管理的字体、固定文档、独立文字快照和 WAV 封装；返回的图像 Data、文字 Data 和 region 数组具有独立生命周期。字体字节在 C 内复制，PDF 持有字体引用；同一固定文档/WAV 的可变操作由封装锁串行执行。Swift 类不声明 Sendable，宿主负责对象跨并发域的安排。

文字区间保持 UTF-8 字节范围，不能直接当作 Swift String 的字符索引。find 接受 Data，保留 NUL 和多字节语义；Bitmap 返回原始像素、stride 和 channels，宿主自行接显示后端。WAV 返回交错 float 样本，文件权限和声音设备仍由应用管理。Swift 不替换 C 的通用构造、绘制回调或音频后端模型，这些接口可直接通过 CEXReader 使用。

macOS 可用 `swiftc -I SDK/include -L SDK/lib -lexreader -Xlinker -rpath -Xlinker SDK/lib bindings/swift/EXReader.swift bindings/swift/Smoke.swift -o swift-example` 构建示例，传入 SDK/examples 目录运行。Apple CI 运行独立安装 SDK 的 Swift 示例，并对 iOS/iPadOS arm64 设备与模拟器目标分别检查封装。


## JNI / Java / Android 接入（S078）

`EXR_BUILD_JNI=ON` 构建可选 exreader_jni 动态库；Android 默认启用，普通桌面默认关闭，不增加 C 核的 JDK 依赖。桌面构建绑定需要 JDK 头文件；运行时一并放置 exreader 与 exreader_jni。安装包包含 bindings/jni 中的 Java 源码和 Android 混淆保留规则。Android 两个库都使用 16 KiB ELF 页面对齐。

`org.exreader.EXReader.Pdf` 从 byte[] 打开 PDF，可传宿主字体与 TTC 索引，返回页数、独立 RGBA Bitmap 和 TextPage。文字以标准 UTF-8 byte[] 保存，字节范围、源坐标 quad 与标志使用各自类型数组；转换为 String 时不使用 JNI Modified UTF-8，因此保留 NUL 和非 BMP 字符。`Wave` 从标准 UTF-8 文件路径按帧返回 float[]，并提供采样格式。

Pdf/Wave 实现 AutoCloseable；使用 try-with-resources 或显式 close，重复关闭安全，关闭后操作抛出 IllegalStateException。每个 Java 对象同步串行调用 C 句柄，输入在 native 创建期间复制，输出数组不借用 C 生命周期。Native 错误转换为带 code 的 EXReaderException；参数和 OOM 异常保留 JVM 状态，所有失败路径释放已创建的 native 数据。

桌面 CI 用真实 JVM 和 `-Xcheck:jni` 运行安装后绑定，Android CI 交叉编译 JNI 库。此阶段封装 PDF 和 WAV 常用调用；其余完整 C 接口可从 Android NDK 直接接入，Android 应用生命周期、内容 URI 授权、声音输出及真机运行继续补齐。


## RTF 表格结构（S079）

RTF 的 trowd/cell/row 现在构造通用 table/tr/td 文档树。单元格保留多段落、空单元格、既有内联样式、链接和图片；连续行组成同一表，正文恢复后下一行开始新表。cellx 定义可位于内容前或内容后，坐标作为 data-rtf-cellx 属性保留；没有 cellx 时按实际单元格构造。

接入现有表格换行、跨页、宿主布局查询和结构化 EPUB 导出。内置布局使用自动列宽，不将原始 twip 边界当作已实现的精确列宽。每行最多 256 列，检查缺失 cell/row、定义数量不符、重复行开始及非递增边界。此阶段拒绝嵌套表与合并标记，随后补合并结构。跳过的目的地和 Unicode fallback 不会意外执行表格控制字。


## RTF 合并单元格（S080）

clmgf/clmrg 与 clvmgf/clvmrg 现在生成标准 colspan/rowspan。行结束时线性重建链接，将续接物理格转换为所属单元格内的普通 div 内容容器；非空文字、段落样式、链接和图片保留，空续接容器隐藏，避免增加虚假的空行。宿主仍读取通用表格节点和属性。

支持横向、纵向及矩形组合合并，纵向续接要求上一行的覆盖列数和声明边界一致。检查孤立续接、宽度变化、冲突标记与跨间断的连接；单元格定义前后的标记都随 cellx 解析。trleft 与 cellx 原始坐标以属性保留。合并后的整组高度仍受现有分页规则约束，嵌套表与精确原始列宽排版尚未实现。


## RTF 脚注、尾注与回链（S081）

footnote 组现在创建独立的通用 aside / EXR_NODE_NOTE；ftnalt 标为 doc-endnote，其余标为 doc-footnote。正文 chftn 位置生成 doc-noteref 链接，注释末尾有 doc-backlink，所有目标使用稳定的文档内 ID。没有显式标记时在注释位置补引用；编号暂按出现顺序生成。

解析期间注释独立构造，完成后按出现顺序接到正文末尾，保持主文连续；注释里的段落、样式、链接和图片保留，父表格内的引用不会把注释正文写进单元格。通用 ID 解析和 EPUB 结构导出继续使用相同模型。此阶段是语义结构与文末注释，不承诺逐页页脚定位或原始自定义编号。最多 10000 条，拒绝嵌套注释、悬空引用及注释内嵌套表格。


## RTF 列表层级与显示标签（S082）

ls/ilvl 现在构造通用 ol/ul 与 li，保留列表实例 ID 和 0–8 级层级。listtext/pntext 的实际编号或项目符号继续作为带样式的显示标签保留，避免重复生成；标记 span 使用 presentation/aria-hidden，语义列表项独立可读。普通段落、不同单元格、不同列表实例分别分组；脚注解析后恢复父列表状态。

开始即跳到较深层级时生成 presentation 容器补齐树结构，原始层级仍可查询。列表容器不额外增加原段落已有的缩进。此阶段沿用原文件给出的显示标签；没有标签时只保留列表结构，完整 numbering/listoverride 计数定义继续补齐。


## RTF 自动编号（S083）

解析 listtable / listoverridetable，在没有 listtext 时生成编号；已有显示标签原样保留，同时推进计数。支持 decimal、大小写 Roman / Letter、补零、项目符号和无编号，保留 leveltext 模板、多级引用、legal 前级十进制化、norestart、follow 和独立实例的起始值/格式覆盖。编号字符格式与正文独立，列表缩进只补正文未显式指定的值。通用 ol 的 start/type 和 data-rtf-number-format 保留语义。

最多 2000 个定义和覆盖实例、每个 9 层、模板 255 个标量，计入既有元数据字节预算；计数溢出返回 EXR_LIMIT。未实现的编号制式在缺少原标签时返回 EXR_FORMAT。控制参数严格限制为 signed int32；正文 hex NUL 拒绝，模板内编号占位符允许零值。Roman 超过 3999 和非正 Roman/字母值使用十进制回退。


## 结构化 HTML 资源包（S084）

`exr_document_export_html_bundle` 输出 ZIP 字节和独立的 entry_path 字符串，两者分别用 exr_free 释放。解压整个包，再打开 entry_path 指定的 XHTML 文件；这是带资源的目录包，不是单文件 HTML。入口提供阅读顺序、NCX 层级目录与原 EPUB nav 的入口链接，名称遇到原文件时自动避让。

章节使用既有 XML 文档树序列化器，保留元素、属性、表格、列表、样式和章节相对链接；图片、字体、CSS、封面等声明资源按原路径与字节复制，辅助 XHTML 一并保留。不合并章节、不内联资源，不改写原始链接。EPUB 原有特殊 URI 和浏览器不支持的资源也原样保留；浏览器最终显示由浏览器自己的样式与格式能力决定。

复用结构 EPUB 导出的路径冲突、缺失资源、XML、加密/字体混淆校验和字节预算。失败或取消清空 data/size/entry_path，不写文件、不联网。旧 exr_document_export(EXR_HTML) 继续提供纯正文转换。


## 精确重复导入（S085）

`exr_library_import_unique` 按格式与原文件全部字节查找重复，命中时返回最小的已有正 ID、created=0；不改已有书名、作者、进度、封面或标注。没有重复时调用既有解析与封面导入，成功提交后返回新 ID、created=1。旧 import 继续允许多个副本。

查询、插入和提交使用同一写事务，跨连接同时导入不会增加两个副本；SQLite 连接互斥量保护同一连接上的整个操作。失败时 id/created 清零，回滚新增数据。沿用 128 MiB 原文件上限与 schema 4，不增加数据库迁移或常驻索引。当前先按格式和字节数筛选，再作精确 BLOB 比较；大书库查询成本随候选文件总字节数增加。不同编码、重新打包、转换格式或仅正文相同的文件视为不同来源。


## 章节 CFI 内容路径（S086）

`exr_document_cfi_path_create` / resolve 实现 [EPUB CFI 1.1](https://w3c.github.io/epub-specs/epub33/epubcfi/) 的内容文档路径组件，例如 `/4[body]/2[p]/1:3`。调用方单独提供 chapter；接口不添加 package spine 前缀、`!` 或 `epubcfi(...)`，也不做 URI 百分号解码。章节必须具有唯一的 XML 文档元素，不能把多根的普通文本模型当作原始 XHTML。

`exr_cfi_point.node` 指向文档节点。文字节点的 offset 是原始未折叠文字内的 UTF-16 单元数，包括 surrogate pair 中间的位置；元素 offset=SIZE_MAX 表示元素本身，其余 offset 是直接子节点边界。它与规范化正文 UTF-8 偏移不同。连续文字节点按 CFI 的同一个逻辑文字块计数，解引用可返回等价的前一个文字节点末端。空文字块和首尾 virtual element 转为父元素的子节点边界。根元素自身对应空的局部路径。

ID / xml:id 按 CFI 字符规则转义，索引失配时可在同章寻找唯一 ID 修正；缺失或多重匹配返回 EXR_FORMAT。side=0/1/2 分别表示未指定、before、after，终端携带标准 `;s=b/a` 参数。路径最多 64 KiB、256 层，ID 断言最多 4096 字节，支持取消。失败时 path=NULL 或 point.node/offset=SIZE_MAX。

此阶段拒绝文本位置断言、范围、图像 alt 偏移、跨文档重定向、时间和空间偏移；完整 EPUB 包路径仍需保留 OPF spine 的原始结构后接入。


## 原始 EPUB 整书位置 CFI（S087）

`exr_document_cfi_create` / resolve 处理 `epubcfi(package_path!content_path)` 的位置。原始 container 与 OPF 只在请求时读取，使用实际元素树生成 package / spine / itemref 路径与 ID 断言，不假设 spine 固定为 `/6`。读取仍受既有 ZIP 资源限制；不增加常驻 OPF 副本。

完整验证 OPF itemref 与文档阅读顺序的对应关系，重复引用同一资源的条目分别定位，linear=no 仍占自己的 spine 位置。解析成功返回 chapter 和该章原始 DOM 的 point。原有 ID 断言可同时修正 package 与章节的过时索引；多次 `!` 或非 spine 引用拒绝。

此接口要求仍持有原压缩包的完整 EPUB 文档，辅助非 spine 章节不能伪装为标准 spine CFI；从 publication_load 单独加载的章节也不能用自己的局部索引冒充整书顺序。宿主构造文档继续使用独立内容路径接口，输出结构 EPUB 后重新打开才有真实 package 坐标。输入为原始 CFI 字符串，不自动解析 URL 或百分号转义。范围、文本断言、iframe 等额外重定向和音视频空间/时间位置继续补齐。


## 按需出版物 CFI（S088）

`exr_publication_cfi_create` 接受内置 EPUB publication、part、由它加载的独立章节文档与章节局部 point。创建前验证原始压缩源归属和章节路径；重复 spine 项仍由显式 part 区分。完整文档的 CFI 接口继续使用原有完整阅读顺序校验。

`exr_publication_cfi_resolve` 先按原 OPF 定位 part，只加载那个章节，再解析内容路径。成功返回 part、独立文档和文档内 point；文档用 document_free 释放，可比 publication 活得更久。其他章节的 XHTML 损坏不会阻止访问正常目标；失败或取消返回 document=NULL、part/point.node/point.offset=SIZE_MAX。

操作不创建 session、不预排版、不加入常驻缓存。内置 EPUB 提供者以外的宿主出版物返回 EXR_FORMAT，可继续使用通用局部路径接口。与 publication_load 一样拒绝重入；输入输出的 XML 文本位置仍使用原始 DOM / UTF-16 约定。


## EPUB CFI 选区范围（S089）

`exr_document_cfi_range_create` / range_resolve 使用标准 `epubcfi(P,S,E)` 三段形式，支持同一文本块、元素与跨 spine 章节范围；共同路径按完整步骤提取，不按数字字符串的前几个字符截断。`exr_cfi_range` 分别保存起止 chapter 与原始 DOM point，零长度范围可用，端点不得指定 side bias。

解析在完成两端 ID 修正后，重新生成规范路径并按 CFI 的自然数字顺序验证起点不晚于终点。偏移 2 正确位于 10 之前；旧索引表面倒置但 ID 修正后顺序正确的范围可恢复。断言内转义逗号不分割范围。错误或取消清空全部端点。

完整文档和按需出版物的单点 resolve 现在按规范取范围的起点；它们只处理起点的语义目标，不验证另一端是否存在。需要两端有效性与顺序检查时使用 range_resolve，该接口目前要求完整 EPUB 文档。原始文本 UTF-16 单元、未折叠空白和章节作用域规则保持一致。文本位置断言、额外文档嵌入、时间和空间偏移仍待实现。


## CFI 文本断言与位置修正（S090）

内容路径现在读取标准 `[before,after]`、仅前文或仅后文断言，可附带 side bias。验证使用同章原始 XML 文字的连续视图，忽略元素边界，把 XML 空白（空格、TAB、CR、LF）连续序列折叠为一个空格。它不借用排版投影，不删除未显示元素里的文字，也不做 Unicode 规范化。

现有位置与上下文吻合时保留原位置；不吻合或旧文本偏移超出文本块时，在同章查找唯一的组合上下文，找回原始 DOM / UTF-16 位置。找不到或存在多个匹配返回 EXR_FORMAT；不选择最近偏移。修正后的折叠空白位置使用最早等价的原始边界。祖先路径必须仍可通过步骤/ID 解析，不跨章猜测。

`exr_document_cfi_path_create_quoted`、`exr_document_cfi_create_quoted` 和 `exr_publication_cfi_create_quoted` 每侧捕获 1–32 个 Unicode 标量，并自动进行 CFI 字符转义；空文字不附加无意义的空断言。生成带断言的位置需要标量边界，拒绝 surrogate pair 中间的位置；普通不带断言的 CFI 仍允许 UTF-16 单元边界。修正与生成都保留 side bias。

规范化视图是单次操作的临时缓冲，最多 64 MiB 减一字节，不常驻，不建立逐字符映射表；位置回查用第二遍遍历。查询最多两次线性 KMP 扫描，拒绝歧义，支持取消。现有路径断言每侧上限 4096 字节。完整文档、范围和按需单点入口共享这些规则。


## SDK ABI 与安装包接入（S091）

`EXR_ABI_VERSION` / `exr_abi_version()` 提供从 S091 起的 ABI epoch 1。版本字符串仍用 EXR_VERSION / exr_version。ABI 与库版本、SQLite schema 分别管理；同一 epoch 的数组记录不能追加字段改变步长，带 struct_size 的输入维持原始前缀。完整规则见 [SDK_COMPATIBILITY.md](SDK_COMPATIBILITY.md)。

安装包新增可搬迁的 CMake config：`find_package(EXReader 0.18.0 EXACT CONFIG REQUIRED)`，宿主链接 `EXReader::exreader`，由导入目标提供头文件和对应平台的动态库/导入库路径。全部安装后示例已改用该入口，compat 示例核对 package/header/runtime 的 ABI 和 release。引擎自身继续只需要 C 编译器；独立的 C++17 消费者验证不会引入 C++ 运行时到引擎。


## 通用持久化全文索引（S092）

`exr_text_index` 使用独立 SQLite 索引文件，application_id=EXRI、schema 1；不把新表塞进普通 schema 4 书库。宿主提供稳定 source/part 标识和 UTF-8 文字，可用章节、固定页面或任意其他分段，不假定格式、书籍 ID 类型或 UI。索引是可重建的派生数据，普通书库备份不包含该独立文件。

`exr_text_index_put` 原子替换一个分段，`remove(source,part)` 删除一段，part=NULL 删除该来源全部分段。外部内容 FTS5 表与正文表在同一事务内更新，INSERT/COMMIT 失败或取消均回滚。source 非空、part 可为空，标识各最多 4096 UTF-8 字节；每段正文最多 64 MiB 减一字节，保留 NUL，不折叠空白或转换大小写。

`exr_text_index_query` 接受 1–4096 UTF-8 字节的字面子串，可按 source 筛选。三个及以上 Unicode 标量用 SQLite FTS5 case-sensitive trigram 选候选，再由共享 C KMP 字节匹配器确认；一两个标量或含 NUL 的查询扫描文字候选，因而支持中文单字/双字搜索。含 NUL 的分段始终进入候选核验，避免 tokenizer 边界影响其后方文字。引号和 AND/OR 等都按普通文字处理，不执行搜索表达式。

`exr_text_query_next` 逐个返回 source、part、原始文字/长度与 UTF-8 start/end，包括重叠命中，顺序为内部行顺序再偏移。一个查询只保留一份模式前缀表，跨 next 继续匹配，不为每次命中重建搜索表。返回指针借用到下次 next 或 free；正文可能有 NUL，使用 text_size。EOF 返回 found=0，错误清空输出并使查询失效，释放后可重新开始。

同一索引句柄最多一个存活查询，查询释放前拒绝该句柄的写入。查询持有索引，可晚于 index_close 释放；独立连接可用 WAL 同时写入，读取快照从第一次 step 开始。操作与生命周期由宿主串行管理，控制回调上下文借用到 query_free；支持协作取消。

构建选项 `EXR_ENABLE_TEXT_INDEX` 默认 ON，复用现有 SQLite C 组件。需要更小核心时设 OFF，公开函数仍保留 ABI，但 available=0、open 返回 EXR_FORMAT；其他阅读功能仍可使用。`exr_text_index_available` 可在宿主界面决定是否提供索引操作。此接口尚不自动遍历书库建索引，也不提供模糊/词干/相关性排名；宿主决定分段和重建时机。


## 流式来源索引重建（S093）

`exr_text_index_replace(index,source,provider,context,control,...)` 在一个事务内替换整个来源。provider 按递增 ordinal 返回 `exr_text_part{id,text,size}`，found=0 结束；空序列清空该来源。最多 100000 个分段，分段 ID 必须唯一，文字/ID 上限与 put 相同。输入仅借用到下一次回调或 replace 返回，宿主可在下一次回调释放上一个章节，不必同时保留整本书。

旧 FTS posting 和正文与新分段一并提交。provider 错误、错误详情中报告的失败、重复 ID、非法 found、UTF-8/字节限制、取消或提交失败均回滚，保留整个旧来源。最终进度回调仍可取消提交。回调不能重入当前 index；其他来源不受替换影响。现有 WAL 索引的打开不再申请写事务，只在初始化时加锁并再次核对 schema，因此独立连接可在重建期间打开并读取旧快照。

安装后的 `exreader-search-example input.epub index.sqlite literal-query` 演示按阅读顺序逐章加载、回收上一章、原子重建与最多 20 条搜索结果。source 使用调用方文件路径，part 采用示例自选的序号；这是宿主选择，不是索引模型对标识的限制。原始 C 接口可接任意格式和宿主解析器。


## 稳定阅读进度持久化（S094）

`exr_library_progress` 接收宿主从当前文档用 anchor_create(position,position) 捕获的点锚，原子保存 books.position 与前后文/章节作用域。exact 必须是空字符串、start=end 且位于存储正文 extent 内。宿主负责把锚点对应到正确的书籍；接口只验证范围与选择器编码，不为每次进度更新重新解析原文件。

`exr_library_progress_get` 返回独立锚点和已保存的状态，锚点用 anchor_free 释放。没有选择器的旧记录返回 LEGACY、exact=NULL 和数值位置，不伪造为已恢复；保存的选择器可交给 anchor_resolve 在新文档中重新定位。输出必须为空，错误清空输出。PDF 的进度单位是页面，此文本锚点接口拒绝 PDF，现有 page position 继续使用。

`exr_library_update` 仅修改元数据且位置不变时保留选择器；通过旧接口修改数值位置时自动清除旧选择器，避免把新位置与旧上下文混配。`clear_progress` 仅删除选择器，不改变数值位置。删除书籍级联删除进度选择器，备份包含它们，精确去重导入不会重置既有进度。

书库升级为 schema 5。v1–v4 在事务中补齐所需表和触发器，失败完整回滚，旧数值进度保持为 LEGACY。ABI epoch 仍为 1，SQLite schema 兼容版本独立管理。本阶段持久化上下文；正文 extent 重新计算与旧标注/进度的批量重定位继续接入。


## 书库正文重新定位（S095）

`exr_library_reanchor(library,book,fallback_position,control,report,...)` 重新解析存储原书，计算当前正文长度，并在同一事务中重新定位文本标注与阅读进度。唯一匹配更新范围和上下文；MISSING、AMBIGUOUS 或无选择器的 LEGACY 不猜测位置。PDF 使用固定页位置，此入口返回 EXR_FORMAT。

宿主必须提供当前正文内的 UTF-8 标量边界 fallback_position；阅读进度无法定位时使用该位置，但保留原选择器与状态。下次可再次尝试恢复。未定位标注的公开 start/end 为 SIZE_MAX，anchor.start/end 保留旧范围，原选文、上下文和备注不丢失；不得直接用未定位范围绘制高亮。

report 返回新旧正文长度、进度位置、进度匹配及逐条 note_id/旧范围/匹配结果，用 `exr_library_relocation_free` 释放。输出须为空，失败清零。每次只读取一个标注选择器，不把全部备注复制进迁移内存；报告最多 64 MiB。取消、数据库写入或 COMMIT 失败均回滚全部变化。控制回调不能重入当前书库。

`exr_library_note_text(library,note_id,text,...)` 只修改备注，不改变范围与选择器，适用于未定位标注。普通 library_note 可在宿主选定新范围后重新捕获选择器。备注须为有效 UTF-8，最长 64 MiB；损坏的存储备注读取返回 EXR_DATABASE。

schema 6 为标注保存定位状态，并允许进度保留 LEGACY 历史位置。v1–v5 事务迁移到最新结构；v5 的旧进度表重建与标注列添加一起提交。原书字节不改写，ABI epoch 仍为 1。


## 通用文本标注交换（S096）

`exr_text_annotation_export` / import 使用 W3C Web Annotation 的紧凑 JSON-LD 子集：固定 `http://www.w3.org/ns/anno.jsonld` context，单个 Annotation、单个 TextualBody（纯文本）及单个 SpecificResource/TextQuoteSelector。结构保留可选 id、source、备注、exact、prefix、suffix。独立于书库和格式；不分配书籍 ID、不访问网络、不把第三方资源自动映射到本地文件。

source 由宿主指定，应标识准确的目标文档或章节。SDK 的 UTF-8 字节范围与内部 chapter 路径不输出为标准字符位置；导入 anchor.start/end=SIZE_MAX、chapter=NULL。宿主先依据 source 选定目标文档/章节，再使用 anchor_resolve 得到当前范围；找不到或歧义时保留原 JSON/选择器等待处理。章节作用域由 source 与宿主映射维护，不应把章内选文当成整书全局选择器。

导入输出必须为空，结果用 text_annotation_free 释放。导出字符串用 exr_free 释放，size 不含末尾 NUL。整个 JSON 最多 1 MiB，source/id 最多 4096 UTF-8 字节；选文和上下文沿用 anchor 的 64 KiB/每侧 32 标量限制。支持标准 JSON 转义与 UTF-16 surrogate pair，拒绝非法 UTF-8、孤立 surrogate、嵌入 NUL、已识别字段重复、尾随垃圾及超过 32 层的附加元数据。附加元数据仅验证并跳过，不建立通用 JSON DOM，也不在重新导出时保留。

这是明确的单标注交换子集，不是任意 JSON-LD 处理器。context 改写、数组 body/target/selector、HTML 正文、TextPositionSelector、target scope/state、selector refinedBy 等返回错误，避免忽略额外目标约束。固定页坐标、媒体时间、集合批处理与第三方选择器转换尚未接通。


## 按需固定页元数据与 PDF Info（S097）

`exr_fixed_load_metadata` 返回独立的 UTF-8 key/value 数组，用 metadata_free 释放，可比文档活得更久。允许重复 key，不绑定书籍 ID、格式或 UI。最多 4096 项、单字符串 64 KiB、总字符串 8 MiB。空结果 count=0/entries=NULL；错误或取消清空输出。自定义 fixed_input 可追加 metadata 回调，返回借用数组和字符串（到下次提供者操作前有效），SDK 立即深拷贝。回调错误详情、重入限制和最终取消规则与文本加载一致；未提供回调返回 EXR_FORMAT。原始和带 text 的旧 input 前缀继续兼容 ABI epoch 1。

PDF 提供者按需读取有效修订的 Info 字典：Title、Author、Subject 映射到 Dublin Core terms 的 title/creator/description；Keywords、Producer 使用 Adobe PDF 1.3 命名空间；Creator、CreationDate、ModDate 使用 XMP 1.0 的 CreatorTool/CreateDate/ModifyDate。日期保留原 PDF 字符串，不转换为 ISO 时间，不据此推断时区。未设置或 null 项不返回，空字符串值保留。

支持 PDFDocEncoding、带 BOM 的 UTF-16BE/UTF-8、间接字符串、classic/xref-stream 及增量修订中的 Info 继承；最新显式 null 不恢复旧字典。非法编码、非文本值和超限数据返回错误，失败后仍可绘制页面或重试元数据。解析只在请求时进行，不为每页常驻复制元数据。

书库 PDF 导入取得 Info 标题/作者，调用方非空 title 优先；缺少标题仍回退 Untitled。导入时遇到损坏的元数据不会产生部分书籍记录；已有精确去重结果继续保留原用户元数据。fixed_title 的文件名/宿主标题规则保持独立，原文件字节不改写。XMP XML、额外自定义 Info 项与元数据回写尚未接通。


## 通用 XMP 与 PDF 元数据优先级（S098）

`exr_metadata_read_xmp(data,size,control,entries,count,...)` 直接接收 XML packet，复用既有 Expat。输入不依赖 PDF、书库或宿主模型；输出沿用 owned metadata_entry 数组与 metadata_free。支持 UTF-8/带 BOM 的 UTF-16 XML、空文档主体的 RDF Description 简写属性、简单文字属性、rdf:Seq/Bag 多值和 rdf:Alt。Alt 选择 x-default，否则取第一个备选；重复 x-default 返回错误。多作者/多关键词按原始顺序和重复值保留。

属性名以 namespace URI + local name 组成 key，不依赖 XML 前缀。Dublin Core elements 1.1 的属性映射为 dc/terms URI，其他命名空间保留原 URI。输出只提供当前文字值，不保存 RDF 类型、语言标签或原始 XML；它是阅读元数据提取接口，不是 RDF 往返序列化器。仅接收空或缺省 rdf:about 的文档主体；命名主体返回错误。嵌套资源、结构化属性、rdf:resource 和 parseType 整项跳过，包括此前已读到的同属性部分列表值。

packet 最多 1 MiB，嵌套最多 64 层，输出最多 4096 值，key 最多 4096 字节、value 最多 64 KiB、总字符串最多 8 MiB。DTD/实体声明被拒绝；不读取网络或外部实体。损坏 XML、超限、取消均清空输出，最终进度回调仍可取消。

PDF Catalog Metadata stream（含已有解码器支持的 Flate 等 lossless filter）接入同一解析器。XMP 的已提取属性替换同 key 的 Info 值，其余 Info 项保留；多值不压平。书库选择首个非空标题，并把多个非空作者用 `; ` 合并到既有 author 字符串；元数据接口仍返回独立作者。宿主非空 title 继续优先。失败不会阻止独立页面绘制，也不生成部分书库记录。元数据写回仍待实现。


## Swift / JNI 元数据适配（S099）

Swift 的 `EXReaderFixedDocument.metadata()` 与 `EXReaderMetadata.readXMP(Data)` 返回独立 `[EXReaderMetadataEntry]`，每项包含 key/value String。PDF 操作用现有对象锁串行执行；读取后不保留 C 指针，结果可比原文档与输入 Data 活得更久。

Java 的 `Pdf.metadata()` 和静态 `EXReader.readXMP(byte[])` 返回独立 MetadataEntry[]，保留重复 key 与原始顺序。JNI 使用标准 UTF-8 byte[] 传输并在 Java 解码 String，保留中文和非 BMP 字符；批量转换逐项释放局部引用，避免大量属性耗尽 JNI 局部引用表。PDF 关闭后 metadata() 与其他操作一样抛 IllegalStateException。

两个封装沿用 C 的资源限制和解析错误。新增宿主验证覆盖输入缓冲清零后的字符串存活、多作者、中文/emoji、4096 个重复属性、无元数据 PDF 和错误传递。手机端的设备运行验证仍须连接真机完成。


## 通用页标注快照与 PDF 原生标注读取（S100）

`exr_fixed_load_annotations(document,page,control,annotations,count,...)` 按页返回 owned `exr_page_annotation` 数组，使用 page_annotations_free 释放，可比原文档活得更久。id 可为空字符串，kind 为宿主自由定义的 UTF-8 类型名；bounds 是规范化的源坐标矩形，quads 为每组 8 个 double 的四点坐标，properties 是可重复 key 的 UTF-8 元数据。输入不绑定高亮枚举、书库记录或 UI。

自定义 fixed_input 可追加 annotations 回调，返回借用数组（到下次提供者操作前有效）；SDK 深拷贝字符串、几何和属性。每页最多 4096 项，全部记录、几何、属性与字符串合计最多 8 MiB；单字符串最多 64 KiB，单项属性最多 4096 个，坐标须有限且绝对值不超过 1e7。重入、无提供者、无效页、损坏结果和取消返回空输出。原始、带 text 和带 metadata 的旧 input 前缀维持 ABI epoch 1。

PDF 提供者读取页面 Annots 数组，跳过 null/失效间接引用，接受各种 Subtype 名称，返回 NM、Rect、可选 QuadPoints，以及 Contents、T、Subj、CreationDate、M。五项文字分别映射到 dc/terms description、creator、subject 与 XMP CreateDate、ModifyDate；复用 Info 的 PDFDocEncoding/UTF-16BE/UTF-8 解码。没有 NM 时 id 为空，不用数组序号伪造稳定身份。Rect 规范化端点，QuadPoints 保持原数组顺序；宿主依照类型解释点序并转换至视口。

原生标注与 SDK 书库里的 fixed_notes 是不同数据来源，不会互相覆盖或自动同步。该接口提供读取与几何数据；Text/Highlight 编辑和 normal Form 外观绘制见下一节。颜色/边框/动作/关系的通用属性接口、富文本与表单行为继续补齐。失败后其他页面操作仍可重试，单页缓存最多保留最近一次加载的原生标注。


## PDF 原生标注编辑与外观绘制（0.18 开发补充）

`exr_pdf_annotation_write(data,size,page,annotation,options,out,out_size,error)` 接收 PDF 字节和零起始页号，以该页非空 UTF-8 `annotation.id` 匹配原生 NM。匹配项存在时更新，不存在时新增；同页出现多个相同 NM 返回 `EXR_FORMAT`。`annotation.kind` 目前只接受 `Text` 或 `Highlight`。写回要求 PDF 文件头版本至少 1.4；加密文件和非 null Catalog `Perms` 认证权限约束返回 `EXR_FORMAT`。

`bounds` 为源页面坐标的正面积矩形，坐标须有限且绝对值不超过 1e7，宽高也各不超过 1e7。Text 不接受 quads；Highlight 要求至少一组四点，每组为矩形内四个不同凸角点。QuadPoints 保持宿主输入顺序，支持周界序和常见的 Z 序；生成的 AP 外观按凸包连接四点填充，不把 Z 序直接绘成自交路径。

properties 最多五项，每个 key 只出现一次；支持读取接口使用的完整 URI：`http://purl.org/dc/terms/description`、`http://purl.org/dc/terms/creator`、`http://purl.org/dc/terms/subject`、`http://ns.adobe.com/xap/1.0/CreateDate` 和 `http://ns.adobe.com/xap/1.0/ModifyDate`，分别写入 Contents、T、Subj、CreationDate、M。更新替换支持的字段和外观，未提供的旧文字属性被清除，其他字典字段保留。生成新外观时清除旧富文本 RC 和旧外观状态 AS。

ID 和属性值须为有效 UTF-8 C 字符串；UTF-8 载荷各最多 64 KiB，写入的 UTF-16BE 字节也各最多 64 KiB（包含 BOM），因此纯 ASCII 最多 32767 字符。日期保持原字符串。每项标注最多 32768 组 quads（262144 个数值，沿用 PDF 数组上限），每页最多 4096 项标注；单次追加修订最多 64 MiB，完整返回 PDF 最多 128 MiB。

`exr_pdf_annotation_write_defaults()` 返回完整 options，包含 `struct_size`、`color=0xffff00`、`opacity=0.35` 和 control；color 是 0xRRGGBB，opacity 接受 [0,1]，0 表示完全透明。NULL options 在新增和更新时都使用这些默认值，会重设已有标注的颜色和透明度。希望更新时使用其他外观的宿主须显式传入选项。

`exr_pdf_annotation_remove(data,size,page,id,control,out,out_size,error)` 移除指定 NM 的标注及同页关联的 Popup，可删除其他 Subtype；只将真实 Popup 当作关联弹窗。此入口没有 PDF 1.4 的写回版本限制。没有匹配项时返回原字节的独立副本；重复 NM 返回错误。删除实际修改同样拒绝认证 `Perms` 约束。

两个入口只在调用期间借用输入，返回独立拥有的完整新 PDF，以 `exr_free()` 释放；不直接覆盖磁盘文件。失败或取消清空 out/out_size，最终进度回调仍可取消。编辑追加新的对象、xref 和 trailer，保留原文件每个字节、Root/Info/ID 的值与引用、未修改对象及未知字段；被重新输出的实数保留原始拼写。增量删除不是安全擦除，历史修订中的标注文字与外观仍可恢复。宿主负责保存新文件，以及显式同步 SDK 书库 fixed_notes；书库备注不会自动变成 PDF 原生标注。

`exr_fixed_draw` / `exr_fixed_render` 在页面正文之后绘制原生标注的 `/AP/N` normal Form，既支持直接 Form，也支持按 `/AS` 选择状态字典中的 Form。使用 Rect、BBox、Matrix 和 Form 自有资源或页面资源，将外观裁切并映射到源页；每项外观与正文的绘制状态隔离。Invisible、Hidden、NoView 标注不绘制，没有可用 normal 外观时跳过。单页解码外观流合计最多 64 MiB，并共享工作预算和取消控制。

带 NoZoom/NoRotate 的可见外观、Form `/Group`（包括透明度组）目前返回 `EXR_FORMAT`；其他尚未支持的 Form 内容仍沿用 PDF 绘制器的错误规则。此入口绘制既有外观，不为任意标注类型合成外观，也不执行表单交互、动作或脚本。


## Unicode 默认断行与原生音频（0.18 开发补充）

UAX #14 已实现 Unicode 17 默认 LB1–LB31，包括引号、数字、Brahmic、Hangul、RI 和 emoji 上下文。官方 19,338 个 raw 规则案例全部通过。`exr_text_analyze` 与排版将默认断行机会与 UAX #29 字素边界取交集，因此不提供字素内部断点；词内紧急换行策略继续保留。上下文向后读取只在相关规则需要时使用，不为普通左到右章节分配整段位置数组。字典断词、可见软连字符、完整 Indic 塑形和竖排仍需独立完成。前面的 S009 历史范围描述的是当时实现。

PDF 写回现还支持 `Underline`、`StrikeOut`、`Squiggly`。这三类的前两点声明文字上边，后两点是相应下边，接受 Z 序或周界序，拒绝首边为对角线；保留原始 QuadPoints。外观为实际矢量填充，重叠只叠加一次透明度。Squiggly 每个 quad 最多 16384 个波折间隔，外观路径最多 1048576 条命令，超过返回 EXR_LIMIT。其余写回、所有权和权限规则沿用前节。

`exr_flac_open` / `exr_flac_open_source` / `exr_flac_read` 按需解码 raw FLAC。支持 1–8 声道、4–32 位、1–1048575 Hz、constant/verbatim、fixed 0–4、LPC 1–32、Rice/Rice2/escape、wasted bits、独立声道和三种立体声还原。校验 header CRC8、frame CRC16、预测器与样本整数范围，不验证整流 MD5；不支持 Ogg 容器。打开只读取元数据，未声明长度时 frames=UINT64_MAX，到验证 EOF 后更新真实长度。

FLAC 元数据最多 64 MiB / 65536 块；SEEKTABLE 最多 65536 点、保留最多 4096 点，另有最多 4096 个验证后的稀疏检查点和续扫位置。单帧最多 32 MiB / 65535 样本，样本工作区最多 4 MiB；每次 read 最多 65536 帧、seek 扫描最多 16M 样本帧或 256 MiB。达到扫描预算返回 EXR_LIMIT，验证后的进展保留，可再次读取同一位置继续。失败/取消清空请求输出和 read；source 上下文只在打开成功时接管，打开时的 control 不保留。

`exr_pcm_create` 提供与格式无关的按帧 float PCM 读取模型；宿主可接自己的编解码器、解密源或合成音频。`exr_pcm_open` / open_source 自动识别原生 WAV/FLAC。info 包含 sample_rate、channels、channel_mask 和 frames；mask=0 不假定声道顺序，frames=UINT64_MAX 不虚构时长，FLAC 确认 EOF 后同步真实长度。自定义 provider 的未知长度不从任意 seek 的短读推测。每次最多 65536 帧、32 声道，回调需返回完整请求或 EOF，所有样本必须有限。SDK 保留错误详情，拒绝重入，取消/错误清空输出；context 只在成功 create 后接管。

`exr_audio_output_backend` 返回目标平台的编译后端名：Windows waveOut、macOS/iOS/iPadOS AudioQueue、Android OpenSL ES、Linux 动态 ALSA。这不等同于设备存在。open 使用默认设备，接受 8000–192000 Hz、一或二声道；不打开文件、不创建引擎线程。系统设备访问失败返回 EXR_IO。

`exr_audio_output_write` 复制交错有限 float 数据、裁切至 [-1,1]、转为 PCM16，非阻塞提交；每次最多 65536 帧。调用方总要处理 written，设备错误也可能发生在部分数据已提交后，不能重发已接受的数据。队列满或暂停时 written=0，宿主稍后重试；pause 保留队列，flush 丢弃待播数据并保留逻辑暂停状态。pending 是保守队列估算，不是精确播放时钟。Windows/Apple/Android 最多四个 4096 帧块；ALSA 使用有限设备缓冲，不能保留队列暂停的设备返回 EXR_FORMAT。

声音输出由宿主串行调用并管理生命周期。移动应用的音频会话、前后台、路由和中断策略仍由宿主管理。普通测试不打开扬声器，显式 `exreader-audio-output-test --device` 只提交静音用于手动验证；编译通过不代表真机音频验收。


## 软连字符、MP3 与原文件元数据（0.18 开发补充）

软连字符 U+00AD 仅在选中该断点换行时显示，首选 U+2010，字体序列都缺失时尝试 ASCII 连字符。实际字形宽度、字号和字体回退参与最终拟合；放不下时退让，完整布局、页级续排和检查点使用同一路径。glyph.codepoint 仍为原 U+00AD，保留原 UTF-8 两字节范围，显示由 glyph ID 和 HIDDEN 标志决定；不向正文插入额外字符。

`exr_mp3_open` / open_source / read 使用可选 minimp3 C codec。`EXR_ENABLE_MP3` 默认 ON；设为 OFF 不下载组件，保留所有 ABI 符号，available()=0、打开返回 EXR_FORMAT。支持普通比特率的 MPEG-1/2/2.5 Layer III、CBR/VBR、ID3v2/ID3v1/APEv2 边界与 Xing/LAME 无缝样本裁剪；不支持 free-format、Layer I/II 或 MP3 CRC 验证。原生合成由 minimp3 完成，不称为本项目自研算法。

打开只读取标签和起始帧；无法可靠得知长度时 frames=UINT64_MAX，验证 EOF 后更新。随机读取保存完整 reservoir/overlap 解码状态，最多 128 个 checkpoint，整个工作区小于 1 MiB，首次只分配一个检查点。每次 read 最多 65536 帧，扫描最多 16M 帧或 256 MiB；EXR_LIMIT 后同一目标可续扫。首个合法帧头候选位置须小于 65536，跨边界的后续帧验证可以继续读取；标签最多 64 MiB / 64 项。错误和取消清空输出，先前验证的扫描进展保留。PCM 自动识别已接 MP3，并报告已知的 gapless 样本数。

`exr_pdf_metadata_write` 对八个 Info URI 做 patch：title、creator、description、Keywords、CreatorTool、Producer、CreateDate、ModifyDate，URI 沿用读取接口。缺省 key 不改，NULL 删除整个 key，普通字符串空串保留；重复或不支持的 key 返回错误。Info 与已存在的 XMP 同步更新，保留未改 Info/Catalog 字典字段和复杂 RDF 结构；被修改的整个 XMP property（含语言/列表值）会替换。没有 XMP 时只更新 Info，因此可处理 PDF 1.3。

日期为 typed 值：接受合法 PDF D: 或 ISO8601 的年、年月、日期、时分、时分秒及显式时区；分别生成 Info 与 XMP 所需格式。不虚构缺失时区或精度，不改未选中的旧日期；小时-only、非零小数秒、非法日期和日期空串返回 EXR_ARGUMENT。零小数秒可归为整秒，NULL 可删除日期。

输出为独立完整 PDF，增量保留原字节，用 exr_free 释放。count=0 返回独立原样副本；认证权限、加密、XFA、命名/空白 RDF 主体、DTD 和无法同步的 XML 返回错误，不输出半个文件。XMP 流重建为 UTF-8，保留命名空间及未改结构的语义，不保留原 XML 词法拼写或旧 Metadata stream 的未知字典键。编辑要求 UTF-8 和编码后的 UTF-16 文本各最多 64 KiB，XMP 最多 1 MiB。

Swift `EXReaderPCM` 和 Java `EXReader.Pcm` 统一读取启用的 PCM 解码器；句柄操作串行，返回独立 float 样本，时长 getter 可反映后续 EOF 发现。未知长度分别表示 nil 和 -1。`examples/pcm.c` 默认只检查音频；显式 --play 才打开系统设备，按 backpressure 提交并等待队列排空。


## 竖排、Type3、AAC/M4B 与 EPUB 原书编辑（0.18 开发补充）

通过 CSS writing-mode: vertical-rl / vertical-lr 选择统一页面方向，text-orientation 支持 mixed / upright / sideways。Unicode 17 UAX #50 决定字素朝向；Tr 仅在字体确实提供竖向替代时直立，Tu 无替代仍直立。原生 shape_vertical 使用 vmtx、vrt2（优先于 vert）与 vkrn，没有 vmtx 时采用 em 度量。字素方向跨样式保持一致，页级续排、检查点、缓存和命中使用同一排版路径。不同块之间的 writing-mode 切换现已通过局部上下文续排，ruby 继续补齐。

公开 glyph/line/box 数组始终使用物理页面坐标。VERTICAL 表示 advance 及 clip_left/right 沿 y 轴，SIDEWAYS 表示顺时针 90 度；exr_glyph_matrix 将现有 1000-em、y-up 字形轮廓映射到物理页面。UTF-8 范围、锚点和 CFI 仍是逻辑顺序。exr_layout_writing_mode 返回普通重排页方向；positioned 输入可逐字形混用轴，应读取 glyph flags。所有原有固定步长结构保持 ABI epoch 1。

PDF Type3 支持 Encoding/Differences/ToUnicode/Widths、FontBBox 和完整 FontMatrix，CharProcs 复用现有 C 内容解释器绘制路径、Form、stencil 图片及嵌套文字。父字形输出一次文字语义，CharProc 内部装饰文字不重复进入选择/搜索。d0 继承并可覆盖颜色；d1 继承填充/描边色，拒绝有色绘图及非 stencil 图片。Tr 3/7 隐藏；Type3 父字形不形成普通字体文本 clip。递归共享 32 层及全局工作预算，.notdef 用于缺失编码。自绘 sink 须按层保存 BEGIN_CLIP/END_CLIP 的 pending text union，内置 canvas 已支持嵌套；SAVE/RESTORE 的 clip 状态与 pending union 分开管理。

EXR_ENABLE_AAC 默认 OFF；启用后用固定版本 FAAD2 C codec 解码，关闭时不下载组件，所有 AAC/M4B 符号仍存在并报告不可用。exr_aac_* 支持 ADTS 单 raw block、channel_configuration 1–7、AAC-LC/PNS/SBR/PS，输出 1–8 声道独立 float PCM；不支持 PCE、ADIF、LATM、DRM，也不验证 ADTS CRC。ADTS 没有编码器裁剪信息，保留完整 timeline，未知 frames 为 UINT64_MAX，EOF 后更新。

exr_m4b_* 支持普通未分片 M4A/M4B 的 mp4a AAC，按需读取 sample/chunk/time 表及音频包，不常驻复制 mdat 或完整 sample 表。支持 stsz/stz2、stco/co64、单段 rate=1 audio edit 与可选 leading empty edit，正确处理 priming、末包短 duration 和前导静音；movie edit 终点按半开区间向上取样本边界并与精确 media 尾界相交。拒绝加密、外部 data reference、多 sample description、分片、多段/变速 edit 和非零 composition offsets。章节/封面元数据尚未从 M4B 导入。

AAC/M4B 为精确跳播保留当前完整解码器状态，后退从头重放；每次 read 最多 65536 帧，重放至多 16M 帧，输入工作量有界。EXR_LIMIT 后同一目标可续扫，不能当作快速随机状态快照。PCM 自动识别已接 ADTS、带 ID3 的 AAC 和常见 ISO-BMFF 首 box；自有 demux/边界/ownership 与第三方解码算法分别记录在许可证清单。六平台 CI 将显式开启可选 codec 验证，默认轻核构建仍关闭 AAC。

exr_epub_metadata_write 编辑单个本地 OPF 的 DC title/creator/subject/description/publisher/contributor/date/type/format/source/language/relation/coverage/rights，key 使用 dcterms URI。缺省不改，整 key 的多值及传递 refinements 一起替换，保留首个原 id；NULL 删除可选属性，普通空串保留，title/language 不能空或删除。identifier 不提供写入，避免破坏字体混淆标识。未知结构和命名空间保留语义，XML 统一 UTF-8 序列化。

cover 为 NULL 时不变；空 data/size 清除封面 designation 并保留原资源；PNG/JPEG 替换做 MIME/签名检查，沿用已有封面 URI 以保住书内链接，并更新共享该资源的 manifest media-type。没有封面时创建不冲突的本地资源与 EPUB2/3 designation。签名/rights 文件、歧义 cover、加密 cover、metadata/cover 写入时的 element base URI，以及 cover 覆盖保留包成员 返回错误；仅混淆字体的 encryption.xml 可原样保留，清 designation 不需要解密。封面最多 16 MiB，XML 输入每个最多 4 MiB、输出 OPF 8 MiB、ZIP 128 MiB/10000 entries，元数据值 64 KiB/64 keys。未改 ZIP 成员按原压缩字节复制，输出 mimetype 为第一个无压缩成员；ZIP 容器字节及 OPF 词法拼写可以变化。输出独立内存以 exr_free 释放，无修改时独立原样复制，失败/取消清空输出。


## 混轴续排、可变字体、保音高变速和 PDF 内联图（0.18 开发补充）

横排/vertical-rl/vertical-lr 可以作为块级局部 writing context 相互嵌套，最多 8 层。父子都复用同一个 pager walker、表格/图片路径与 assets，不另造递归排版器。长块按片生成，父页放不下时保留 fragment，随机页 checkpoint 克隆局部 continuation 并将内存计入预算；正文范围和开放数组始终映射到原逻辑文本。首个可见 linear spine chapter 的外层决定主 viewport，普通 inline span 使用父 flow 方向。超页不可拆的 table rowspan group 仍返回 EXR_LIMIT，表格单元格仍是有界的当前行组临时布局。背景 box 的 start/end 夹到其所在页，便于原样送入 positioned 接口。

exr_font_axes 返回独立 axis 快照，包含 OpenType tag、隐藏标志、最小/默认/最大/当前设计坐标；静态字体返回 NULL/0。exr_font_create_variable 从原字体列表和稀疏 font_index/tag/value 创建全新实例，未指定轴保留该 face/named instance 的值。最多 64 轴/face、2048 assignments，拒绝重复、未知、非有限和越界值，设计坐标按 16.16 量化。字体字节继续复制；新实例不会改变旧字体和既有 layout；书内字体合并保留宿主实例坐标。exr_font_source 仍返回原编码字节，宿主复现非默认实例时应另读取 axes。轴由宿主指定，当前不解析 CSS font-variation-settings，也不按 wght/ital 自动选择 CSS 字体实例。

FreeType 处理可变轮廓、HVAR/VVAR 度量及 avar 归一化；C OpenType 引擎处理 GDEF 1.3 ItemVariationStore、ValueRecord/anchor 的 VariationIndex（含 longWords）和 GSUB/GPOS 1.1 FeatureVariations 的首匹配 axis-range 条件集。每次 shape 只获取一次归一化坐标，默认 rvrn 在普通替换之前执行；保留原工作/取消限额。不接受的坏表清空输出，普通静态字体路径保持不变。

exr_stretch_* 是不持有 decoder、文件、设备或 player 的流式 WSOLA 处理器。7350–192000 Hz、1–8 声道、0.5–2 倍固定速度；浮点样本交错排列。push/pull 每次最多 65536 帧，push 只接受环形缓冲可用空间，pull 最多一个输出 hop；反复拉取输出后重试输入。不同块切分输出逐样本相同，1 倍速为 bit-exact 旁路。finish 结束输入，再 pull 到 drained；最终样本数按 round(input/reported_rate) 精确计算，reported_rate 是 Q32 实际值。reset 丢弃当前流并更改速度，格式不变。创建后处理路径不再分配，最高配置内存小于 1 MiB；约 20 ms 窗/10 ms hop/±5 ms 搜索，所有声道共享匹配偏移。取消不提交新输出并保留待取样本供重试。短输入/EOF 零延伸；这是低延迟语音/阅读用途算法，瞬态音乐保真不在当前验收范围。宿主可把 PCM、stretch、audio output 串联。

PDF BI/ID/EI 现支持 RAW、DCT JPEG 与现有 Flate/LZW/ASCII85/ASCIIHex/RunLength/predictor 能力及短键/色空间缩写。RAW 按 W/H/BPC/通道精确算行字节；滤镜使用自己的真实终止位置后再验证 EI，不用像素子串搜索。JPEG 按 marker/entropy/FF00/restart 跳到真实 EOI，APP 内的伪 EOI 不结束数据。Form/Type3 资源作用域、Indexed 别名和 stencil 复用现有图片路径，临时 synthetic stream 的解码缓存每张释放；图片无需改变公开 draw ABI。边长 8192、16 Mi 像素、每图 decoded 64 MiB、临时缓存 128 MiB、同页及嵌套 Form/CharProc 累计解压工作 256 MiB。未知首滤镜无法安全定位结束时明确报错。JPEG 像素支持 gray/RGB8，以及下述 CMYK/YCCK 四分量路径；显式 ColorTransform override 仍不支持，文字提取可安全跳过该图。


## Devanagari、ruby、PDF 色彩与平台分页接口（0.18 开发补充）

C OpenType 路径现在对 Devanagari 的 deva/dev2 script 进行音节分类、组合顺序整理、排除合成字的 base+nukta 分解、缺基字符的破折圈补入、reph/pre-base matra 重排以及按阶段启用的基本字形特性；使用已有 GSUB/GPOS 解析器和工作/取消预算。ZWJ/ZWNJ 参与字体规则并控制 half/reph。音节内重排后的 glyph 共享完整音节 UTF-8 范围，音节间保持逻辑范围单调；公开结构大小不变。其它脚本获得 Unicode 17 script tag，但尚无各自的 Indic 专用音节重排实现。

EPUB/结构文档的 ruby/rb/rt/rp/rtc 使用不可拆的内部 inline 项参与原换行与续排；提交页面时展开为正文和注音各自的真实 glyph/line，内部标记不出现在公开数组。支持横排、vertical-rl/lr、默认半字号、over/under、center/start/space-between/space-around、rbspan 与最多 8 层注音。隐式 base→rt 对可逐组分页；显式 rb 或 rtc 的交错源码组保持整体，避免同页单区间模型丢失源归属。正文与注音各自可命中、选择、定位、导出 positioned 布局并恢复 checkpoint。嵌套 ruby 不支持；每个 ruby 最多 256 个正文/注音分段、每个当前组最多 8192 shaped glyph，超出页宽的不可拆组返回 EXR_LIMIT。树中图片等非文本内容不具备 ruby 内的布局语义。

PDF vector、XObject 与 inline image 通过同一个私有颜色模型处理 Device、Indexed、CalGray、CalRGB、Lab 和 ICCBased Alternate。图形状态保留输入色空间，绘制回调接收转换后的 DeviceRGB；q/Q、Form 和 Type3 作用域沿用原状态栈。固定输出策略是 Bradford 白点适配至 D65、XYZ 黑点补偿、线性 sRGB 转换及最终色域裁剪。ICCBased 的原 Alternate 路径与新增配置转换见下节；OutputIntent、Pattern 和非设备颜色图像的 SMask Matte 尚未实现；Separation 的新增范围见下节颜色函数补充。模型嵌套最多 16，页面颜色缓存最多 128 个/32 MiB，支持取消与失败清理。

Swift EXReaderDocument/Publication/Pager/ReflowPage 和 Java EXReader.Document/Publication/Pager/ReflowPage 提供内存/本地文档、EPUB manifest/spine 按章加载和逐页排版。next 返回独立页面，EOF 返回 nil/null；排版错误后分页器失效。所有文本索引为章内规范化 UTF-8 字节，缺省 node/resource 索引为 -1。Swift 复制无指针 C glyph/line/box 记录，Java 返回类型化 LayoutSnapshot；节点名称、属性和原始文本为独立字符串。fontSource 提供实际字体 bytes、face index 和可变轴坐标，image 提供独立 RGBA 数据；宿主可以使用这些快照自行绘制。

同一 publication 及其加载的 document/pager/page 共用串行 gate，保护共享 archive/image 的引用和访问。Swift 另串行访问共享 EXReaderFont，锁顺序为文档再字体，PDF fallback 字体使用同一个字体 gate。Java 对原生文档使用内部引用计数，关闭 publication/document/pager 后已取得的子对象仍有效；各 AutoCloseable 对象需显式 close。Swift 使用 ARC；页面保留 document/font，可独立于分页器存活。快照和位图可在对应页面释放后继续使用。平台包装未接入取消回调和随机缓存配置，C 接口保留这些能力。HTML 的既有导入路径仍为正文提取；保留结构的路径使用 EPUB/FB2/DOCX/RTF/宿主文档。


## M4B 元数据、封面与章节快照（0.18 开发补充）

命名文本标签同时支持 QuickTime keys/mdta 与 iTunes freeform。mdta 的常见小写键（如 title/artist）和 com.apple.quicktime.* 键，以及 com.apple.iTunes 的大写 freeform 名称，归一为相同标准属性。未知 mdta 键保留为 `mdta:<原名>`；未知 freeform 键为 `----:<mean>:<name>`，两段按 UTF-8 字节做 RFC 3986 percent-encoding；其他未知 ilst 文本键为 `ilst:<四字节类型>`，同样编码。保留重复值和原始顺序；其他 keys namespace、非文本数字/二进制数据和未知隐式 data 类型跳过。keys 表最多 256 项/1 MiB 原始名字，每个名字及最终键最多 64 KiB；解析结果继续计入已有值数和文本预算。

exr_m4b_inspect / exr_m4b_inspect_source 只读取 ISO-BMFF 目录和选中的元数据 payload，不打开 AAC decoder，也不扫描 mdat。AAC=OFF 时同样可用。inspect_source 在调用期间借用 source，不接管 context、不调用 release；结果独立拥有字符串、章节和原始封面，inspection_free 后释放。文件入口支持大文件与 UTF-8 路径，始终关闭临时文件。

支持 moov/meta、moov/udta/meta 的 iTunes ilst：title/creator/contributor/date/description/rights 使用 dcterms URI，album/genre 使用 XMP DynamicMedia URI；aART 和 ©ART 都归一为 creator；同一键多值保留。data 类型支持 UTF-8 与 UTF-16BE（含 surrogate），拒绝嵌入 NUL 和错误编码；最多移除一个末尾终止符。covr 选第一张支持的 JPEG/PNG，检查 data 类型和文件签名，返回原始编码字节；完整图片验证由 image decoder 负责。最大 256 值/1 MiB 文本、每值 64 KiB、封面 16 MiB；全调用最多读 32 MiB/扫描 65536 个 box，支持 source.control 取消。

读取 mvhd v0/v1 的电影时长和 Nero chpl v0/v1 章节；100 ns 章节时刻向下转换为毫秒，必须在已知时长内严格递增。稳定章节 ID 从原时间戳生成，parent 为 SIZE_MAX；每章 end 为下一章 start，最后一章 end 为电影时长。未知时长/end 使用 UINT64_MAX；无 mvhd 可返回未知时长，缺省元数据/封面/章节返回空。毫秒精度下重复的章节时刻不接受。不进行音轨/DRM 可播放性验证，也不自动修改书库。

没有非空 chpl 时，读取首个 tref/chap 引用的 QuickTime text/tx3g 章节轨道。要求本文件内的自包含数据引用、单样本描述，支持 stsz 固定/可变长度、stz2 4/8/16 位、stco/co64 和多段 stsc/stts；容器样本表解析与 AAC 解码共用。只定位并读取章节样本，不扫描音频 mdat；所有样本必须位于 mdat 内。标题支持 UTF-8、带 BOM 的 UTF-16BE/LE，忽略样式修饰但检查其容器边界。tkhd/mdhd 与 elst 均支持 v0/v1；可有前导空编辑和一个速率为 1 的向前媒体段，保留裁剪点仍在显示的章节，末章结束时间取轨道、编辑段与电影有效末端的最小值。不同时间刻度相加后只取整一次，防止毫秒偏移。

QuickTime 章节 ID 使用轨道 ID 与原始解码时刻，parent 为 SIZE_MAX，数据仍为独立快照。最多 256 轨道/章节引用/mdat、4096 章节样本；每样本 64 KiB，章节与标签共同受 1 MiB 文本预算约束。全调用沿用 32 MiB 读取和 65536 box 上限、取消与借用 source 语义。非空 Nero chpl 优先，不重复合并目录。多媒体编辑、变速/倒放、ctts 重排、片段化章节、外部数据引用与多语言轨道选择尚未提供。

inspection_metadata、inspection_chapters、inspection_cover、inspection_duration 返回只读快照视图。宿主可将 exr_audio_chapter 和时长交给 exr_audio_create，指定自己的轨道 URI；audio_create 会再复制输入，因此可立即释放 inspection。Swift EXReaderMetadata.readM4B 和 Java EXReader.readM4b 返回独立 AudioBookMetadata（entries/chapters/duration/encoded cover），没有原生句柄需要保留。Swift 未知时间用 nil，Java 用 -1；无法放入 Java signed long 的已知时间返回 EXR_LIMIT。


## PDF 专色与标量颜色函数（0.18 开发补充）

Separation 普通命名专色现支持文件声明的 device/CIE alternate 和单输入 Type 2 指数函数、Type 3 分段函数。vector、XObject、inline image、Indexed base 和 ICC Alternate 复用同一转换路径；绘制回调仍输出屏幕 DeviceRGB，既有公开记录不变。默认 tint 为 1，输入先夹到色空间和函数 Domain；输出按各层 Range 再交 alternate。Type 2 处理 C0/C1 默认值、整数/分数与负指数的合法实数域，拒绝非有限中间结果。Type 3 保留半开区间边界、逆向 Encode、子函数 Domain/Range、单段及末尾零宽区间的 Encode 起点规则。

特殊色名 None 不落墨，忽略无需执行的 alternate/tintTransform；填充和描边只在送出 paint 快照时置透明，原图形状态的 alpha 不被改写。图片返回透明像素，q/Q 和后续设备色操作可正常恢复。文字语义与裁切操作仍沿用原路径。物理印版/套印与完整透明度语义尚未实现，不能视为完整印刷色彩支持。

私有函数模型最多 16 层、1024 节点、64 个分段和 1 MiB payload，循环引用/坏维数/非法域直接失败；编译过程支持取消。模型内存计入原颜色缓存，求值复杂度计入原 PDF 图片工作预算；源码对象查找仍使用原 256 Mi 工作上限。不新增运行时依赖，不改变 ABI epoch、版本号或书库 schema。


### PDF 线性采样函数

单输入 FunctionType 0 现支持 Order 1，样本为 MSB-first 的 1/2/4/8/12/16/24/32 位整数，1–4 输出。输入按 Domain→Encode→Size 映射并做相邻样本线性插值，输出再按 Decode→Range 映射；默认 Encode 为 [0 Size−1]，默认 Decode 为 Range。支持反向映射、单样本/零宽域、跨字节和 32 位最低有效字节，采样函数也可作为 Type 3 子函数。

采样表必须来自 stream，经既有无损滤镜解码后精确匹配表长，再复制进函数模型；表数据、节点和映射数组共同受 1 MiB 编译载荷预算限制，节点开销在分配前计入。模型不借用 stream 样本指针，求值费用继续计入 PDF 图片工作预算。多输入和 Order 3 的后续实现见下节补充。

### PDF Type 4 计算器颜色函数（0.18 开发中）

普通 Separation 的 tintTransform 现支持单输入、1–4 输出的 Type 4 stream，也可作为 Type 3 子函数。所有表 42 算术、关系、布尔/32 位位运算、栈操作和 if/ifelse 均有实现。语法采用 PDF 十进制数字与注释；花括号条件表达式编译成仅向前跳转的指令，没有变量、过程对象、循环或任意 PostScript 执行。整数溢出的 add/sub/mul/neg/abs 提升为实数，idiv/mod 严格要求整数；round 的半整数向较大整数舍入，包括 −6.5→−6。最终栈必须恰好包含声明的数值输出，Domain/Range 继续沿用共用函数路径。

每程序最多 64 KiB 解码源码、4096 指令、32 层条件嵌套、100 操作数；实际指令内存计入整个函数图的 1 MiB 预算。长程序每 256 条执行指令检查取消。按指令和栈搬运成本收费，向量颜色选择/设置共享每次 content/Form 遍历的 256M 工作量上限，图片沿用既有 sample/function 工作预算。编译后的数据由颜色模型持有，取消上下文仅在当前同步 render 期间借用；无公开 ABI 变化。

## COLR v0 彩色轮廓字形（0.18 开发补充）

横排、竖排、侧转和 positioned 绘制均按 COLR v0 层序绘制轮廓，使用 CPAL 第 0 套调色板；前景条目 0xffff 使用字形文字颜色，其余条目保留调色板 RGB/alpha，并乘文字颜色的 alpha。沿用 straight RGBA source-over、灰度输出和行内裁切；粗斜体逐层处理，下划线/删除线按原字形前景色只绘制一次。字形和 UTF-8 语义仍为一个原始塑形结果，不把绘制图层加入文档树、命中区域或标注位置。

`exr_font_color_palettes` 查询 CPAL 调色板和条目数，无 CPAL 返回 0/0；`exr_font_color_layers` 根据显式调色板序号与前景色，返回独立的 `exr_font_color_layer { glyph, color }` 数组，按从后到前排列，color 为 RRGGBBAA；用 exr_free 释放。没有 COLR v0 图层时返回 NULL/0，未知调色板/字形序号返回 EXR_ARGUMENT，支持取消和失败清空输出。快照可比字体活得更久，glyph ID 仍属于对应字体面；宿主可结合 glyph_outline 读取各层路径，自行绘制或选用其他调色板。查询其他调色板不会改变默认页面绘制。所有操作继续遵循同一字体实例串行访问规则。

单字形最多 256 层，每层位图最多 8192×8192 且不超过 16M 像素。页面文字共用 256M 工作预算，计入图层遍历、必要的调色板复制和栅格像素；调色板按字体面缓存，避免每个字形重复复制。长位图按行检查取消，错误时释放整页输出。默认 API 未修改既有公开记录；新增查询函数和独立图层记录，ABI epoch 仍为 1。当前范围是 COLR v0 与 CPAL 颜色；COLR v1 渐变/合成、SVG 字体待实现；CBDT/CBLC 支持见下节。

## sbix 彩色位图字形（0.18 开发补充）

原生读取 sbix v1 的 PNG/JPEG 与 dupe 引用，复用图片解码器。字体以忽略 FreeType sbix 绘制的方式打开，保持 hmtx/vmtx 的连续排版度量，也能打开 glyf 为空的 sbix 字体。字形可在不同 strike 中缺省：选覆盖该字形的最小较大/相等 ppem，否则选最大的较小 ppem，相同 ppem 取源目录最先一项；PPI 不影响当前以像素为单位的选择。dupe 继承目标图像记录的位置偏移，沿用当前字形的设计原点。

宿主字体输入和 EPUB `@font-face` 的字体探测共用同一打开入口；内嵌 sbix 不再被旧的 FreeType scalable 检查跳过。书内字体仍按原 CSS 家族别名和章节作用域选择，页对象保留有效字体的所有权。

`exr_font_glyph_image` 按像素字号返回独立 `exr_glyph_image`：bitmap 是原始 strike 的 straight RGBA 像素，scale 为缩放比例，left/top 是相对字形原点的最终像素偏移（右/下为正）。有轮廓时，按 sbix 规则叠加字形包围盒左下原点。没有图像返回全零记录；像素用 exr_bitmap_free 释放，可比字体与源数据活得更久。image 不含文字透明度或合成粗斜体，advance 独立保留在塑形/排版模型。宿主可保存这些快照并自行缓存或绘制。

默认页面绘制优先 sbix，其次 COLR v0，再用普通字形；图片保留原色并乘文字 alpha，双线性缩放、灰度、竖排侧转和行内裁切复用共用像素合成。flags 中 EXR_GLYPH_IMAGE_OUTLINE_OVERLAY 表示先画位图再覆盖轮廓，轮廓合成粗斜体照常，位图不做合成变形；装饰线仍绘制一次。每面最多 256 strike，缓存的只是已验证目录；dupe 最多遍历 16 条记录，拒绝循环/越界。编码图像最多 32 MiB，解码和缩放后各受 8192 边长/16M 像素限制；目录读取、解码与绘制费用计入文字页 256M 预算，支持取消与失败清空结果。

当前没有解码图像缓存，每次查询/绘制按需解码；宿主可通过上述独立快照实现自己的缓存。TIFF、Apple PDF/mask/flip、COLR v1 与 SVG 字体仍待实现。sbix 定位、选择和旗标语义见 [OpenType sbix 规范](https://learn.microsoft.com/en-us/typography/opentype/spec/sbix)。

## CBDT/CBLC 彩色位图字体（0.18 开发补充）

宿主输入和 EPUB 内嵌字体均接受只有 CBDT/CBLC 的 SFNT 字体。原生读取版本 3.0、index formats 1–5 和 PNG image formats 17/18/19，复用 `exr_font_glyph_image` 返回独立 RGBA 快照。默认绘制顺序为 sbix、CBDT、COLR v0、普通轮廓。按字形覆盖选择 strike 的规则与 sbix 相同；空记录无图像，合法位图字形的 outline 查询返回 NULL/0。

排版使用 head 的设计单位和 hmtx/vmtx，字号连续缩放，不按 strike 整数跳动。缺省 vmtx 时竖向 advance 为 em；有 big metrics 时使用明确的竖向原点，只有横向 small metrics 时按位图尺寸和逻辑 advance 居中。装饰线使用字体 post/OS2 度量；位图保留原色并乘文字 alpha，不做合成粗斜体。

第一次读取验证全部索引的边界、offset 单调性、稀疏 glyph ID 的严格递增和数据范围，分块读取且计入工作预算；只缓存目录。每面最多 256 个 strike，PNG 编码、解码、缩放和取消沿用 sbix 限额。当前支持 square ppem、bitDepth 32；format 17 接受横向 small metrics，非方形 strike、仅竖向 small metrics 和其他编码返回 EXR_FORMAT。规范见 [CBDT](https://learn.microsoft.com/en-us/typography/opentype/spec/cbdt) 与 [CBLC](https://learn.microsoft.com/en-us/typography/opentype/spec/cblc)。

GSUB 匹配允许字体明确引用隐藏字符的 glyph ID，包括 ZWJ、标签字符和变体选择符；只有没有匹配的可忽略字符才跳过，GDEF/lookup 的过滤规则优先。普通 ZWNJ 继续阻断连接，也可被字体明确列为组件。合字、上下文、链式上下文和反向替换共用该匹配规则，消费后的合字保留完整 UTF-8 字素范围；未消费的隐藏记录保留零宽和 HIDDEN 标志。字形选择来自字体表，不内置特定 emoji 列表。

## Unicode 变体字形（0.18 开发补充）

原生 shape 在 GSUB 之前读取 cmap 14 的默认和非默认变体映射，覆盖 BMP、补充平面和 Mongolian 变体选择符。支持的选择符被消费，字形保留完整 UTF-8 字素范围；未知或连续多余的选择符维持 HIDDEN/零宽。无基础字符普通 cmap 映射、但有明确非默认变体映射时，也能塑形该序列。`exr_font_has_glyph` 仍只报告单字符 cmap 覆盖。

完整布局、页级续排和竖排使用同一路径。即使字体没有 GSUB/GPOS 表也会应用 cmap 14；同行内元素改变字号时，隐藏选择符继续与基础字符一起塑形。字体回退在覆盖整个字素的候选中优先选择提供该变体映射的字体；都不支持该序列时保留原来的单字符回退顺序。字体由宿主提供，未做系统字体查找。

## PDF All 注册色（0.18 开发补充）

`[/Separation /All alternateSpace tintTransform]` 在固定 sRGB 输出上按 `R=G=B=1−clamp(tint,0,1)` 绘制；0 为白、1 为黑，选择颜色空间后的缺省 tint 为 1。All 和 None 均忽略备用颜色空间及变换函数的执行，All 仍实际绘制。路径、描边、XObject/内联图片、Indexed 调色板和 Form 继承使用同一颜色模型；图片 Decode、状态保存/恢复和后续设备色操作照常生效。

采用 [ISO 32000-2 §8.6.6.4](https://developer.adobe.com/document-services/docs/assets/5b15559b96303194340b99820d3a70fa/PDF_ISO_32000-2.pdf) 对加色设备明确的反向 tint 规则。该输出是屏幕 RGB；物理印版、套印和色彩管理继续由后续工作补齐。

## PDF DeviceN 多通道颜色（0.18 开发补充）

DeviceN 接受 1–32 个色名、device/CIE/ICC alternate 和最多四输出的 Type 0/4 变换，按色名数组顺序将输入压栈，逐输入应用 Domain，逐输出应用 Range。单通道也可使用已有 Type 0/2/3。默认所有 tint 为 1；路径填充、描边、XObject/内联图片、Indexed 调色板、图片 Decode 和颜色键掩码共用同一模型，绘制快照仍为屏幕 RGB。

可选属性字典（包括 Subtype NChannel）按复合色的 tintTransform 输出显示，未模拟 Process/Colorants/InkHints 的物理油墨行为。全部色名为 None 时不落墨；混合 None 仍按文件声明的复合变换处理。拒绝 All、重复的非 None 色名、空列表、超过 32 通道和超过 127 字节的色名。物理分色、套印及其余 ICC/输出意图仍待实现；Type 2/3 本身只接受一个输入。

最多 32 输入计入原计算器的 100 项操作数栈，不能再额外占用一套栈；保持 4096 指令、64 KiB 源码、1 MiB 函数图载荷及既有取消和页面工作预算。图片相关 Decode/Mask 缓冲扩到 64 项，逐像素只读写实际通道数；JPEG 支持单通道、三通道及下述四分量 CMYK/YCCK 解码。不新增依赖或公开结构字段。


## PDF 多输入与三次采样（0.18 开发补充）

FunctionType 0 接受 1–32 输入、1–4 输出，按 PDF 定义以首输入轴最快、同一点各输出交错的顺序读取采样表。Order 1 使用多线性插值；Order 3 使用 a=−1/2 的张量积三次卷积，边界复制端点样本，两点轴退化为线性，单点轴保持常值。三次插值允许超调，先 Decode 后 Range 裁剪。各轴独立应用 Domain/Encode/Size，保留反向 Encode、单点、零宽域和所有八种样本位深。DeviceN、Separation、Indexed、XObject 和内联图片复用同一实现。

整个函数图仍受 1 MiB 载荷限制；维数乘法在分配前检查，最坏插值邻点组合最多 65536，超出返回 EXR_LIMIT。单点轴不增加组合数，因此 32 轴的退化网格可正常读取。求值按实际非整数坐标展开，每 256 组合检查取消；最坏计算量计入原页面/图片预算。不新增依赖、公开结构字段或版本号。


## CBZ 漫画固定页（0.18 开发补充）

`EXR_CBZ` 在既有枚举末尾追加，不更改旧值。内存入口 `exr_fixed_open_memory(EXR_CBZ, ...)` 复制原文件；文件入口 `exr_fixed_open("book.cbz", ...)` 保留随机读取文件源，扩展名不区分 ASCII 大小写。内存输入仍限 128 MiB；文件源限 2 GiB。使用同一 `exr_fixed_document`、viewport、draw sink 和 render 接口，图片像素作为原页面坐标，左上原点、y 向下。页 ID/标签为原始归档路径；按 ASCII 大小写不敏感、数字自然顺序排序，等价项按原始名字字节确定次序。

读取 PNG/JPEG 页；非图片附件和 macOS 隐藏文件跳过。遇到已知但未支持的 WebP/GIF/BMP/AVIF/TIFF 图片返回 EXR_FORMAT，不悄悄丢页。拒绝重复页路径、非法 UTF-8/非规范路径、加密和不支持的 ZIP 压缩；支持 stored/deflate 和已有 miniz ZIP64。最多 10000 个归档成员，每页编码数据 32 MiB、8192 边长、16M 像素。打开时逐页按 4 KiB 块探测图片头，单页头最多 1 MiB、全书头扫描最多 64 MiB；不解码或缓存整书像素。绘制时只提取目标页、校验完整 CRC 后解码，完成即释放。正常比例且对齐像素的绘制保留原始像素，其他变换复用图片插值与页面裁切。

根目录 `ComicInfo.xml`（ASCII 大小写不敏感）最多 1 MiB，拒绝重复和不安全 XML。Title/Writer/Summary/LanguageISO/Publisher 映射为 dcterms 属性；其余直接文本字段保留为 `urn:comicinfo:<原字段名>`。最多 128 值、每值 64 KiB；Pages 等嵌套结构尚未解释。缺省目录顺序不受 ComicInfo/Manga 字段影响；没有自动双页拆分或 EXIF 旋转。书库复用原书保存、元数据编辑、封面设置、精确去重、页进度、固定页书签和备份，schema 仍为 6；未自动选择封面。图片页的文字快照为空，未运行 OCR。

Swift 的 `EXReaderFixedDocument(data: ..., format: .cbz)` 和 Java 的 `new EXReader.FixedDocument(EXReader.FixedFormat.CBZ, bytes)` 复用原有元数据/绘制/文字接口；旧 Swift 缺省 PDF 和 Java `EXReader.Pdf` 构造方式保留。C ABI epoch 1 和版本 0.18.0 不变，无新增运行时依赖。


## ICCBased 配置转换（0.18 开发补充）

默认启用 `EXR_ENABLE_ICC=ON`，静态编入 MIT 许可的 LittleCMS 2.19.1 C 核心。不开启其工具、格式插件、额外图片依赖或单独运行时 DLL。关闭此选项时保留原 Alternate 回退行为。支持 PDF 32000-1 表 68 的 input/display/output/color-space 类及 Gray/RGB/CMYK/Lab 输入，读取 v2/v4 的矩阵、TRC、AToB LUT 和受支持的多过程元素。按当前固定 RelativeColorimetric 策略转换到 sRGB；关闭优化预计算和像素缓存，避免按图像建立大转换表。PDF 自身的范围、颜色状态、图像 Decode、Indexed 调色板、Separation/DeviceN Alternate、填充和描边复用原路径。

Lab 使用真实 L*/a*/b* 单位及文件 Range（通常 [0 100 -128 127 -128 127]）；CMYK 由 PDF 的 0–1 转为 CMS 的百分比；不将 Lab 数值归一到 RGB 单位。XYZ 输入配置不属于 PDF 表 68 的合法输入类型，走 Alternate。配置可用时忽略 Alternate；损坏、不支持或与 N 不匹配的配置按 Alternate 回退。超过处理预算、内存分配失败和取消直接报错，不隐藏为颜色回退。

配置数据最多 4 MiB；每个 CMS context 用私有分配器将全部分配及对齐头开销限制为 16 MiB，实际驻留分配计入原页面颜色缓存。配置最多 512 tags、每个被检查的输入 pipeline 最多 64 stages；逐像素费用按 pipeline 规模计入已有页面/图片工作预算。配置编译的分配点及求值支持取消，失败释放 profile/transform/context；不同 context 使用独立状态。

本步未接入 PDF `ri`/图像 Intent 的动态渲染意图、OutputIntent、软打样、透明组混合色空间、物理印版或套印。因此这是 ICCBased 配置读取与转换的完成批次，完整 PDF 印刷色彩仍有后续工作。公开 C 记录、ABI epoch 1、书库 schema 6 和版本 0.18.0 保持不变。


## PDF CMYK/YCCK JPEG（0.18 开发补充）

DCTDecode 的四分量 JPEG 先保留 C/M/Y/K 样本，再应用 PDF Decode、颜色键 Mask 和 ColorSpace/ICCBased 转换；黑色分量不作为 alpha 使用。支持基线及渐进式、Adobe APP14 transform=0 的 CMYK、transform=2 的 YCCK，以及无 Adobe 标记的直接四分量 JPEG。YCCK 先重建 CMY，K 保持独立；所有样本的反相由 PDF Decode 明确决定，不根据 Adobe 标记额外自动反相。常见 Adobe 数据使用 Decode [1 0 1 0 1 0 1 0]。

XObject 和 BI/ID/EI 内联图片复用该路径，支持已有颜色键、独立图像软遮罩和插值；可用的 ICC 配置继续转换到固定 sRGB，不可用时按既有 Alternate 规则回退。无配置的 DeviceCMYK 沿用已有屏幕近似，不表示印刷级色彩匹配。显式 DecodeParms ColorTransform override、12-bit JPEG、其他 JPEG 编码类型和 CMYK 图像 Matte 仍返回错误。未增加公开 ABI 字段或运行时依赖。

沿用 32 MiB 编码、8192 边长/16 Mi 像素、128 MiB 解码临时分配和图像/遮罩载荷预算，输出转换使用现有页面工作限额。支持解码前后及输出行重建期间的协作取消；熵解码/IDCT 内部沿用 stb 的同步调用。

## PDF 密码认证与读取（0.18 开发补充）

`exr_fixed_open_options` 新增 `pdf_password` / `pdf_password_size`，只在打开调用期间借用，长度最多 1024 字节；NULL/0 尝试空密码。Standard R2/R3 使用 RC4，R4 支持 V2/AESV2，R5/R6 支持 AESV3。R2–R4 密码由宿主提供 PDFDocEncoding 原始字节；R5/R6 接收 UTF-8，经 RFC 4013 / Unicode 3.2 SASLprep 映射、NFKC、禁止字符及双向规则检查后按规范截断为 127 字节。非 ASCII 密码不依赖系统 locale 或新版 Unicode 规则。

缺少/错误密码返回 `EXR_PASSWORD`，输出文档为 NULL；宿主可保留自己的输入、提示密码后重新调用同一打开入口。密码正确后，公开固定页绘制、选文/搜索、元数据和原生标注读取使用同一解密对象树。支持用户及所有者密码，同密码同时匹配时优先识别所有者。核心没有密码 UI，也不保存明文密码。

可在 options 的 `pdf_security` 指向已初始化 `struct_size` 的 `exr_pdf_security_info`；只在成功打开 PDF 后写入。记录含 encrypted、revision、key_bits、owner_authenticated、原始 permissions /P 及 metadata_encrypted。未加密 PDF 的 permissions 为 UINT32_MAX。权限常量对应 ISO 32000 的 /P 位，宿主还须结合 revision 解释旧版本位的含义；所有者认证具有完整权限。权限字段供应用决定提供哪些操作，不能替代应用或文件系统权限控制。

```c
exr_fixed_open_options options = {0};
exr_pdf_security_info security = {0};
exr_fixed_document *document = NULL;
options.struct_size = sizeof(options);
security.struct_size = sizeof(security);
options.pdf_password = password_bytes;
options.pdf_password_size = password_length;
options.pdf_security = &security;
exr_status status = exr_fixed_open(path, &options, &document, &error);
/* EXR_PASSWORD: host may ask again; success: inspect security, then read pages. */
```

解密涵盖间接对象的 literal/hex 字符串、流、压缩对象流、世代号、StrF/StmF/EFF 与显式首位 Crypt filter；Identity 不解密，XRef 流及其 ID 保持明文，ObjStm 内字符串不重复解密，签名字典 Contents 保持明文。EncryptMetadata=false 的 Metadata 流保持明文。AES 严格校验 IV/长度及 PKCS#7，R5/R6 同时验证加密 Perms 与 /P、EncryptMetadata 是否一致。密码错误不提供部分页目录或 metadata；流损坏仍在读取对应页时返回错误且不返回部分结果。

会话仅在内存保留派生文件密钥，用于错误/取消后重新建立延迟解析器；文档释放和临时密钥退出时清零。原书入库逻辑不存储密码或派生密钥。解密流计入现有 128 MiB 缓存/临时载荷与 256 MiB 工作预算，AES/RC4 按 64 KiB、R6 哈希按轮检查取消。

`EXR_ENABLE_PDF_CRYPTO` 默认 ON，使用固定 Mbed TLS 3.6.7 的最小 C 算法子集；OFF 不下载该组件，保留公开符号，`exr_pdf_crypto_available()` 返回 0，加密打开返回 `EXR_UNSUPPORTED`。非 Standard（含证书 PubSec）、EFOpen 专用附件认证及其他 Crypt 方法也返回 `EXR_UNSUPPORTED`。当前编辑接口继续拒绝加密输入，避免在加密 trailer 下写入未加密新对象；没有加密写回或证书认证能力。

Swift 的 `EXReaderFixedDocument(..., password: Data?)` 和 Java 的 password-byte 构造器提供同样的重试错误码与 `pdfSecurity` 快照。旧 C options 前缀、原 Swift 默认调用及 Java 原构造器保持可用，ABI epoch 仍为 1。

## 表格指定列宽（0.18 开发补充）

col、colgroup 和单元格的 CSS width，以及 table/col/colgroup/cell 的 HTML width 属性，参与表格逻辑行内方向的列分配；col/colgroup 的 span 和 colspan 均可提供跨列提示。单位使用现有 px/pt/em/rem/% 解析器。竖排继续按既有逻辑轴映射，以 height 指定行内尺寸；不新增公开字段或宿主专用表格模型。

先收集列和单列单元格提示，再处理由少到多的 colspan。跨列约束优先增加没有单列提示的列。剩余空间先分给完全未指定的列，其次分给只有跨列提示的列；全指定时按比例填满表格。提示总和超过表格时按比例收缩，并为每列保留至少 1px。在显式 fixed 布局且没有提示时等分；默认 auto 布局同时使用下面的内容测量。单元格 width 在列分配时消费，内部布局不再对分配宽度重复计算百分比。单元格内边距和可见边框计入指定宽度提示。

同一组列边界用于测量、绘制、分页、竖排和命中坐标；checkpoint 复制边界，预算包含完整私有状态及行/单元格数组实际分配容量。列数超出 64 或可用空间不足每列 1px 返回 EXR_LIMIT。行组/嵌套等现有限额继续适用。

以上说明宽度提示的分配；默认 auto 布局还使用下面的 min/max-content 测量。当前实线边框子集的 border-collapse 见下文；重复表头和跨页拆分单元格仍待完成。DOCX/RTF 专用 twip 列网格不会自动转换为本步骤的 CSS 宽度提示。

## 表格内容测量与 auto/fixed 布局（0.18 开发补充）

默认 `table-layout:auto`。引擎通过现有字体回退、字素保护、OpenType 塑形、Unicode 断行和软连字符路径测量每个单元格。min-content 在每个合法断点结束一行，不使用应急字素拆行；max-content 保持段内不换行，按塑形段流式累加，保留原有连接上下文及段间 kerning。尾随可折叠空格不计宽度。测量不输出整份字形快照；实际分页仍使用正常断行路径。

单列先收集最小/首选内容宽度和指定宽度，再按跨度处理 colspan；rowspan 不改变列归属。列和单元格的指定宽度作为下界提示。空间介于最小与首选总宽之间时按各列增长需求分配；额外空间优先给未指定列，并按首选宽度分配。auto 宽度表格可收缩至首选总宽，auto 外边距按实际宽度重新定位；显式表格宽度继续填满其可用区域。结果保存为同一组列边界，供最终单元格布局和 checkpoint 使用。

固定尺寸子块参与测量，百分比子块/图片在测量期间视为尺寸未定，实际布局时再依据已分配列宽求值。图片复用现有解码和等比缩放；嵌套表格递归返回对应最小或首选宽度，不为测量再生成一份最终表格。横竖排使用逻辑行内宽度，正交子块通过其物理片段尺寸参与测量。

`table-layout:fixed` 在表格 width 已指定时使用列声明和首行单元格宽度，后续行内容不决定列宽。width:auto 时仍走 auto 算法。需要保留旧版全宽等分表现的 HTML 宿主可设置 `table { table-layout:fixed; width:100% }`；没有 HTML 元素名的宿主构造节点可直接设置同样的 style 属性。支持矩阵内的 auto/fixed 不引入新的公开结构或格式专用参数。

原生分页要求列保持页内：最小总宽超过可用宽时，列会按既有规则收缩至至少 1px，实际文字使用既有应急断行/裁剪规则。它不采用浏览器让整张表格横向溢出的策略。内边距、边框和当前图片缩放规则继续适用；当前实线边框子集的合并模型见下文；复杂百分比约束、更多边框样式、重复表头和跨页拆分单元格仍逐项推进。

测量计入已有文本/塑形工作预算，复用 16 MiB 行队列上限并支持协作取消。测量上下文是临时工作区，不属于返回页的缓存字节预算；最终列边界及游标状态计入缓存/checkpoint 内存。自动列宽需要检查整张表的内容，固定布局可避开这一步。

## 单元格垂直对齐与基线（0.18 开发补充）

单元格支持 CSS `vertical-align:top/middle/bottom/baseline` 及 inherit。CSS 初始值为 baseline；HTML thead/tbody/tfoot 默认 middle，tr/td/th 继承父级对齐。HTML valign 提供大小写不敏感的呈现提示，作者 CSS 可以覆盖。sub/super/text-top/text-bottom/长度/百分比这些合法值用于单元格时按 baseline 处理，遵循 [CSS 2.2 表格规则](https://www.w3.org/TR/CSS22/tables.html)。行内上/下标和其他行内 vertical-align 排版继续单独补齐。

排版器记录首个 in-flow 行盒的基线，ruby 使用所在主行的基线；以嵌套表格开始的内容使用其首行基线。没有行盒或表格行时按内容底边合成，图片单元格与空单元格也可参与对齐。baseline 单元格对齐到其 rowspan 第一行；没有 baseline 单元格的行，其合成基线来自最低内容底边。混合字号、padding/border、跨行单元格共同决定行组所需高度。

top/middle/bottom 在分配的行或 rowspan 行组中定位内容；文字、行盒、图片、子块背景及命中坐标同步移动。单元格自身背景和边框保持整格位置并扩展至分配高度。竖排沿逻辑块轴执行，upright/mixed 使用中央基线，sideways 使用对应方向的字母基线；vertical-rl/lr 转换时转换基线坐标，正交且没有可共享基线时按内容边缘合成。

单元格 height 是内容高度下限，加上可见 padding/border；行 height 提供行高下限。非空表格的明确 height 作为均分到各行的最小高度基准，实际内容或单元格下限可以让总高更大。百分比行/单元格高度按表格明确声明的最小高度求值，基准未定时不强制百分比高度。复杂百分比高度约束、空表格高度和其他块级高度兼容仍随 CSS 矩阵推进。

没有增加公开记录/回调或格式专用选项；宿主构造的语义树和各内置格式共用这套样式/布局路径。按行基线、单元格测量信息和列边界随 checkpoint 一起复制并计入预算。分页仍以相连 rowspan 行组为不可拆单位。


## 表格共享实线边框（0.18 开发补充）

`border-collapse:collapse/separate/inherit` 已接入，初始 separate，此属性可继承到嵌套表格；内表可显式重置为 separate。本步沿用统一四边的 `border` / `border-width/color/style` 模型，支持 solid、none、hidden。逐边声明、多值四边简写、double/dashed/dotted 和立体边框样式仍待补齐。

collapse 为每条行列边界计算一个共享边框。hidden 抑制相同边界的所有候选；none 不参与绘制；其他候选先比较宽度，同宽时按 cell > row > HTML row group > col > colgroup > table 选择。同来源同宽时优先上方，行内方向为 ltr 时优先左侧、rtl 时优先右侧。col span 按列应用；colgroup span 表示整个列组。colspan/rowspan 内部格线移除。行组来源目前识别 HTML thead/tbody/tfoot；CSS 自定义 row-group display 类型继续待补。

每侧共享宽度的一半参与单元格内容留白，并用于自动内容测量、指定宽度、行高和基线计算；跨度一侧宽度不同时以该侧最大半宽预留内容。表格外侧的另一半包含在页内范围。auto 宽度和 auto 外边距包含实际共享轮廓。表格在行组边界分页时，两页各保留该边界；同页连续行组只输出一次共享线。不可拆分行组仍须整组容入一页。collapsed table 的 padding、table-cell 的 margin 按不适用属性忽略；border-spacing 尚未接入。

普通单元格盒保留背景与命中几何，border_width 为零。共享边框以 `EXR_BOX_BLOCK` 矩形暴露，`flags == EXR_BOX_BORDER`，node 指向所属表格，background 是实际颜色，border_width 为零。每页普通盒之后，同一 node 的连续边框矩形构成一个图层：先在透明 RGBA 缓冲中以替换方式绘制该组矩形，再把整个图层按 source-over 合成到页面一次。这样共享线、转角和交叉处的半透明颜色不会重复叠加。随后绘制正文。宿主须保留 flags、node 和组内顺序；使用 positioned 布局重建时，把该组盒子作为连续 EXR_PAINT_BOX 命令提交，即可得到同样的原生像素。

内置栅格器按当前边框图层的可见包围盒临时分配 RGBA 缓冲，单层最多 16M 像素 / 64 MiB，超出返回 EXR_LIMIT；图层间顺序复用，结束立即释放，支持取消与总绘制工作量上限。没有共享边框的页面不分配这块缓冲。网格只在 collapse 表格上分配，当前每条边 12 bytes，总量为 `((rows+1)*columns + rows*(columns+1))*12`，受原有 4096 行/单元格、64 列、8 层嵌套约束。网格、单元格半宽和深拷贝 checkpoint 均计入字节预算。


## 浮动、逐行绕排与分段恢复（0.18 开发补充）

CSS `float:none/left/right/inherit` 和 `clear:none/left/right/both/inherit` 已接入 C 原生排版。float/clear 默认不继承，显式 inherit 可用；浮动行内元素按块处理，table 保留表格排版。图片、普通文本块、表格使用同一避让矩形模型。指定宽度与 max-width 参与尺寸计算，auto 宽度用原生 min/max-content 在当前可用空间中收缩；内容最小宽度在该行放不下时，浮动向下避让。宽度、max-width 和浮动根的百分比 padding 按外侧包含块求值一次，单位内部使用已分配尺寸，避免重复百分比缩小。margin:auto 在浮动定位中按零处理。

左右浮动按逻辑行内轴避让；横排对应左右，竖排对应 line-left/line-right。多个浮动可并排或下移，后来的浮动不抬到先前浮动上方；clear 可用于浮动、普通块和 br。外边距盒参与避让，图片的 padding/border 由外盒绘制，原图片像素保持自身尺寸与比例。普通图片遇到浮动也查找可容纳其整块的空间；普通流块的背景可在浮动后方，而其文字按逐行可用区排版。非浮动表格遇到外部浮动时建立独立 BFC，在旁边放置互不重叠的表格片段；表格声明 float 时使用独立浮动排版上下文，按可分页行组续排。

行内队列根据当前行实际字体度量、混合字号、ruby、字素和最终塑形结果拟合可用区域；没有容纳首簇的空间时下移至可用区域。双向分析跳过浮动子树；浮动插在文本节点之间不会强制结束文字段落。阿拉伯文跨该位置的连字仍由最终行塑形处理。过晚出现的浮动若无法与前方待提交文字同处一行，会先提交前方文字再定位浮动。glyph、line、图片盒和 `clip_left/right` 一起反映实际位置；source advance 可保留尾随空格或不可拆簇的完整宽度，绘制须遵守 clip。

每个表格单元格、浮动单位和正交排版子上下文拥有独立浮动状态。浮动内容不提供父流的首行基线，单元格只有浮动时仍按内容底边合成基线。状态和待提交单位由 checkpoint 拥有或保留，不借用临时栈上的矩形。页边界清除上一页的避让状态，未提交行在新页重新拟合。短浮动保留整块移页；长文本块、浮动表格和嵌套浮动保留独立页级游标，先占用当前剩余空间，后续页先恢复浮动片段，再让正文沿旁边续排。clear 等待对应侧的全部续排，正文先结束也会继续输出浮动。固定/百分比高度的空白与背景分片，顶部 margin 只在首片、底部 margin 只在末片；已有块装饰的底部 padding/border 随片段保留。百分比高度使用初始包含块高度。包含正交书写模式时固定子视口，当前剩余空间容不下则移到下一页，避免改变子内容的行内尺寸。单个不可拆行组、超高字行、无有效内容空间的 margin 仍返回 EXR_LIMIT。原有图片页内缩放规则仍适用。

浮动块与它前面的高字号文字可能分别落在相邻页上，因此 page.start/end 是源文字包络，允许重叠；不能再据此假设所有页面严格分割成相接区间。`exr_layout_page_at` 对有重叠的完整布局扫描实际 glyph 范围，优先包含偏移的较窄范围，避免跨浮动连字的宽范围掩盖浮动自身文字；没有可见匹配时回退到按页起点定位。普通不重叠布局仍走二分查找。重叠查找目前 O(glyph_count)，不另建索引。独立续排还可能让后页 start 小于前页 start。positioned 输入允许重叠及非单调页包络，逐页 glyph/line/box 仍须在所属页包络内；无实际字形匹配时遍历起点回退，不对非单调起点二分。

每上下文最多 128 个存活浮动，整个 pager 树最多 128 个已提交/待提交浮动续排上下文，单元格/浮动/独立图片等通用流单位最多嵌套 8 层，超出返回 EXR_LIMIT。当前 64 位构建的矩形表及计数约 2.6 KiB，包含在上下文/checkpoint 的 sizeof 预算内；字形塑形只借用该表。自动宽度单位在换页或锚点行变化后可重测，图片像素仍复用资源缓存。没有外部浏览器、UI 或新依赖。安装 SDK 的 `examples/books/float-both.epub` 和 `float-long-main.epub` 提供左右图片与长侧栏原始样本；JNI/Swift smoke 检查公开坐标、资源像素、跨页全部正文数量与最终绘制。续排游标和嵌套上下文由 checkpoint 深克隆，计入其字节预算；只保留待提交片段和游标，不缓存整本浮动布局。自动宽度的 min/max-content 测量、当前段落的双向分析和已解析文档仍可能遍历或保留较大的源范围。

完整浮动分片、复杂嵌套浮动的固有宽度约束、shape-outside、浮动的完整 break 规则、完整行内图片与 white-space/CSS 格式化继续待补；以上能力不等同于浏览器完整 CSS。


## 普通表格与外部浮动并排（0.18 开发补充）

同向普通表格不再隐式 clear。指定 width/max-width、padding、border 和 margin
按外侧包含块求值；auto 表格用 min/max-content 选择宽度。margin:auto 可在当前
避让通道中居中或靠右。先用实际首片高度验证整个外盒，短表不会因稍后才开始的
浮动被过早下推。跨到更低浮动的长片段可在提交列宽前收窄，否则下移或换页。
若窄通道让第一个不可拆行组过高，尚未提交的 auto 表格可在下一页重新选宽。

首片提交后列宽保持固定，后续片段在新页重新选择 x 位置，不逐行组横向蛇行，
也不在图片结束后扩大列宽。顶部 margin 只在首片，底部 margin 只在末片；完整
片段装饰和可分页行组复用已有路径。clear:left/right/both 会等待对应侧的长浮动
续排。百分比表格高度沿用初始完整可用页高，不按各页剩余高度重复求值；完整 CSS
确定高度包含块的传播规则仍待补齐。包含正交
子树时保持固定子视口，当前剩余空间不足则换页。无外部浮动的普通表格继续走
原分页器路径；同向未分页的单元格内也支持该 BFC 放置。

BFC 游标由现有 frame/checkpoint 拥有，深克隆和内存预算包含列、行组和待提交
内容。普通表格保持在正文流中并贡献基线，外部浮动不进入单元格的排版上下文。
单个不可拆行组仍须能放入一整页；已提交的窄列不自动加宽来救济后续超高行组。
安装示例 books/float-bfc-stream.epub 由 JNI/Swift 验证长侧栏与普通表格同时续排。


## 可选语言词典与断点查询（0.18 开发补充）

`exr_hyphenator` 是独立、不可变的可选对象。`exr_hyphenator_create` 接宿主 provider；
成功后接管 context，最后释放时调用 release。失败不接管。回调同步执行，使用时
串行化；不可销毁或重入当前对象。它收到规范化的小写 ASCII 语言键、带长度的
原始 UTF-8 单词和 size+1 字节输出区；每个 1 表示该 UTF-8 字节之前允许断词。

`exr_hyphenator_create_patterns` 一次载入 1–64 个语言的纯 UTF-8 加权模式，复制并
压成原生 C trie。每项设置 struct_size，language 为 ASCII BCP47 风格键，NULL/空串
仅匹配无语言输入；语言查找忽略大小写，按 RFC 4647 方式退到父标签，不拿缺省词典
猜测已知语言。重复键拒绝。模式中的 0–9 是边界权重，点号锚定词首/词尾，匹配结果
取最大权重，奇数允许断点、偶数抑制。支持 UTF-8/BOM 头、%/# 注释及
LEFTHYPHENMIN/RIGHTHYPHENMIN；输入 left/right=0 使用文件值或默认 2，非零覆盖。
最小保留量以原文的 Unicode 字素计数，而非折叠后字符数。

`exr_hyphenator_breaks` 输出原文 UTF-8 字节位置，不改原文。原生模式与单词均做
Unicode 17 full case folding，tr/az 用 Turkic I 映射；折叠展开（如 ß→ss）内部断点
不会变成原文字符内部的断点。原生模式和查询使用 Unicode 17 NFC → full case fold →
NFC，兼容预组/组合写法、组合附加符顺序、Hangul 和规范分解排除。它不做 NFKC，
不改文档原文。组合、分解、重排及折叠展开保留原始标量区间；只有能把全部输出
分到原文断点两侧的边界才映射回原始 UTF-8。词典权重若位于合成/重排后的内部、
无法对应原文边界，就不产生该位置的机会；映射到同一模式的权重仍取最大值。
provider 继续收到原始字节，可接自己的规范化、分词和词典实现，须返回原文位置。结果与 UAX #29 字素和 GLUE 保护相交；字素内部
候选清除，非 0/1 或 UTF-8 延续字节候选作为 provider 格式错误拒绝。0/size 始终清零。
有效大小请求的取消、回调错误或校验错误清空全部输出，不返回部分断点。

单词最多 1,024 字节/256 标量，模式最多 128 原始标量；内部 NFC/折叠工作区上限为每个原标量 12 个规范分解标量；
生成器用固定 Unicode 数据验证 NFD 最多 4 倍、folded NFD 相对输入 NFD 最多 3 倍。
原文长度上限不变，ASCII 匹配使用快速路径。
每词典输入最多 8 MiB，全部输入最多 32 MiB；每词典两层合计最多 262,144 个输入模式、一百万 trie
节点（含隐式分隔符层）。原生构造和查询受 64 Mi 工作预算与取消控制；provider 需在回调内响应 control。
构造字节预算 0=32 MiB，最多 128 MiB，
包含语言目录、数组分配容量和 packed edges。`exr_hyphenator_memory_size` 计这些实际
payload，排除分配器开销、借入源字节、临时栈和宿主自有 provider context。

原生 UTF-8 模式已支持 NEXTLEVEL、COMPOUNDLEFTHYPHENMIN、COMPOUNDRIGHTHYPHENMIN
和 NOHYPHEN。两层分别存储、独立取最大权重：第一级的奇数点先拆分复合词，再对
每个词段重复第一级；不能继续拆分的词段才使用第二级。词段拥有独立的词首/词尾
锚点。第一级断点不被第二级的偶数权重覆盖。工作队列最多 256 个不重叠词段，拆分
必须严格缩短词段，避免递归调用栈；匹配、规范化和所有词段共享 64 Mi 工作预算。

LEFT/RIGHT 全词最小值采用第一级设置（0 表示默认 2）；构造输入的非零 left/right
覆盖全词值。COMPOUND 最小值限制词段内部距复合边界的字素数，显式 NEXTLEVEL
文件默认 0，不限制。无 NEXTLEVEL 时，原模式作为普通层，自动加入 `-`、ASCII
撇号、U+2013 和 U+2019 的边界规则及 NOHYPHEN；复合最小值优先使用文件中的
非零 COMPOUND 值，再用文件的非零 LEFT/RIGHT，最后用 3。宿主的全词覆盖值
不改这些词段默认值。格式字段按所在层解析，第二级元信息不覆盖第一级全词过滤。
无 NEXTLEVEL 时输入集属于普通层，其 NOHYPHEN 声明不覆盖自动分隔符层；要自定义
全词 NOHYPHEN，应显式提供 NEXTLEVEL。

NOHYPHEN 是逗号分隔的非空字符或字符序列，最后一次声明替换前值；空声明清空。
匹配采用同一 NFC/折叠形式，最终只去掉匹配序列之前与之后的自动断点，保留序列
内部机会；重叠匹配逐个处理。它不取消文档原有的 UAX 换行。每层最多 64 项，每项
最多 128 原始标量，存储计入词典字节预算。第一级的 NOHYPHEN 作用于整个输入词。
即使某标点两侧受 GLUE 保护，它仍可作为内部词段边界计算最小值；公开断点最终
仍与字素和 GLUE 保护相交。最小值严格执行，包括非常短的词段。

原生格式继续拒绝 TeX 命令，返回 EXR_UNSUPPORTED。非 UTF-8 编码需由宿主先转码；
它不是任意 Hunspell/TeX 文件的完整读取器。词典许可由宿主单独管理，不自动下载。
拼写替换现在通过下面的独立查询返回；原来的位图只返回无需改写拼写的机会。
安装 SDK 的 `examples/hyphen.c` 可输出 `hy-phen-ation`，使用的是原创演示模式。

### 拼写替换查询（0.18 开发补充）

`exr_hyphenator_query` 返回拥有文字的 `exr_hyphenation`。通过
`exr_hyphenation_breaks` 读取按原文字节断点排序的记录，用 `exr_hyphenation_free`
释放；结果独立于输入单词和词典寿命。每条 `exr_hyphen_break` 包含 point、start、end
原文 UTF-8 字节位置，以及带长度的 before/after 文字。选用这个断点时，将原文
[start,end) 换成 before + 显示连字符 + after，after 放到下一行；普通断点的
start=end=point，两个文字串为空。返回文字按词典字面值保留，不自动变换大小写。
查询失败时 *out=NULL，不返回部分结果。`exr_hyphenation_memory_size` 包括结果对象、
记录数组容量与拥有的文字，不计分配器开销；结果 payload 上限 256 KiB。

原生模式支持 `pattern/before=after[,start,cut]`。start 是排除词首锚点后的 1-based
Unicode 标量位置，cut 是移除的标量数；省略两者时替换整个非锚点模式。显式 cut=0
表示插入，不解释为缺省值。替换区域须包含且只包含一个奇数权重点（含两端），
区域外的其他权重点照常参与普通最大权重叠加。before/after 合计最多 128 标量、
512 UTF-8 字节；可以为空，禁止控制字符、NUL、U+2028/U+2029。不带权重的纯词典
替换规则不是断词规则，拒绝。起点、终点和断点都必须能穿过 NFC/折叠映射回到
原文边界；构造时不能映射的模式报 EXR_FORMAT，查询时无法映射到原文字素边界的
候选跳过。不会按折叠后字节长度猜测移除范围。

同一位置取最大权重；相同奇数权重下普通规则优先。两个不同替换在相同最高权重
冲突时抑制该位置，避免依赖规则顺序选择拼写；更高权重可以重新消解冲突。
这些规则也作用于规范化后重合的模式。两级 trie 只有含替换的那层分配可选的节点
索引和替换记录，文字及数组容量计入词典 payload。查询临时工作区有固定上限，
词段仍以原文为基础；尚不按某个假设断点改写拼写后再递归匹配后续词段。

`exr_hyphenator_create_discretionary` 接开放的替换提供器。回调收到原文和同步 emit，
emit 在返回前复制全部文字，不要求宿主保持临时串。每词最多 255 个不同的内部断点，
重复位置、非法范围、UTF-8 或字素切割返回错误；即使提供器忽略 emit 的失败，整个
查询仍失败。point 必须在 [start,end] 内，原文字素及 GLUE 保护继续生效。回调期间
禁止重入或销毁当前词典；成功构造才接管 context，最后释放调用 release。原来的
位图提供器也可由新 query 调用，会得到普通断点记录。

旧 `exr_hyphenator_breaks` 只返回普通机会，跳过需要拼写替换的机会，绝不会把它们
降级成在原词里直接插入连字符。排版器对纯普通词典继续使用位图快速路径；含替换
的原生词典或开放替换提供器使用拥有结果的查询，再映射到文档原文字节位置。
Swift/JNI 的现有 setHyphenation 入口也能实际绘制替换。

`exr_layout_create_hyphenated` 在完整布局中使用可选词典；原来的 create/create_ex
入口保持不启用字典。`exr_pager_set_hyphenator` 在选择访问模式之前调用（包括
set_cache/get/next），持有词典引用。`exr_session_set_hyphenator` 可在空闲时替换，
成功后清空旧章节缓存，已有借用指针失效。调用者随后可释放自己的词典引用；
生成的布局不依赖词典存活。共享同一词典的分页器/会话须由宿主串行使用。

CSS `hyphens` 支持 auto/manual/none/inherit，默认 manual。auto 与已配置词典同时
存在才生成字典机会；manual 保留显式软连字符；none 也禁用软连字符断行。语言从
最近元素的 xml:lang/lang 继承，未声明时使用 EPUB 首个非空 dc:language；显式空
语言阻断继承，非法标签不猜测语言。宿主构造的文档可用相同元素属性。文本单词可
跨内联样式节点和源位置不连续的浮动节点；保留内部撇号、连字符、en dash、U+00B7 中点、组合字符及 ZWJ/ZWNJ，
含数字、非字母起始或超出 1,024 字节/256 标量的词跳过自动查询。当前其他格式的
语言元数据还没有统一映射；普通 HTML 导入仍是正文提取，不能用于完整 CSS 保真。

实际断点从原始标量重塑形，连字符也参与同一字体回退、OpenType 和宽度拟合；
可拆开 provisional fi/阿拉伯连字，在新行重新计算连接形式。可完整放下的最后一行
保持原连字。字素和 GLUE 保护优先，支持 RTL、竖排、table min-content、浮动和
横竖混排上下文。检查点深拷贝并计入单词缓存；取消/provider 错误不返回部分页面，
缓存分页器可在错误修正后重试。无可用断点时保留现有字素紧急换行/裁剪策略。

`EXR_GLYPH_GENERATED` 标记含自动生成文字的字形。普通自动连字符的 start/end 和
cluster_start/end 都指向原文断点，范围为空；替换文字或与正文合成的字体簇可以
拥有非空原文范围。搜索/复制/标注继续使用原文 UTF-8，不从生成字形拼回正文。
公共 glyph 记录和 ABI 不变，private 断词机会位不会出现在公开 boundaries 中。

Swift `EXReaderPager.setHyphenation` 和 JNI `Pager.setHyphenation` 接多语言模式及
字节预算，每个分页器拥有独立编译数据，避免跨分页器隐含共享。空数组关闭，需在
next 之前设置；失败保留已装词典。安装示例和两套 smoke 均覆盖实际断词绘制。
自动下载词典不由引擎隐式执行；词典继续由宿主提供。

规范化内核只供 C 内部调用，不新增宿主必需接口或依赖。它按 Unicode 17 的规范
分解、重排和合成工作，支持源区间合并、取消和共享工作预算；完整官方 NFC 测试
覆盖 20,034 案例及未列出标量的不变性。Unicode 3.2 NFKC/SASLprep 的 PDF 密码
路径保持独立，以遵循密码规范固定的 Unicode 版本。


### 替换文字排版与页级恢复（0.18 开发补充）

实际候选行从原始 glyph 重建：保留 start 前的正文，插入 before 和显示连字符，
一起做字体回退、OpenType 塑形和最终宽度拟合；不按原词宽度猜测替换后的宽度。
若最后一行原词能完整放下，则保留原词及原连字。只有选中且成功提交断点后才
移除显示中的 [start,end)，将 after 接到新行；不会修改文档文本或资源。

before 是覆盖 [start,point) 的单个源簇，after 覆盖 [point,end)。展开后的多个
字形共享该区间，命中只返回原文簇边界，不创造生成串内的字节位置。before 为空
时，由显示连字符保存左侧删除范围；after 为空但删除了右侧原文时，以隐藏生成
字形保存该范围。纯插入的字形源范围为空；右侧插入串与后续原文字素共用起点时，合并其簇范围，
使点击能到达原文字素末端，窄行裁剪也能消费该字素并继续推进。两侧分别继承断点左/右原文字形的样式和方向，
替换字符串仍按字面值使用，不自动推断大小写。字体可以进一步合并这些源簇。

只对当前相关词做有界前读，最多 256 原文标量，避免在替换区尚未读完时提前截断。
流中真正遇到且符合 CSS/语言/字素保护的替换点保存为待用记录；不是把整章全部
词典机会常驻。提交后重塑形 ready carry，保留尚未处理的输入尾部；新页不会丢掉
provisional 连字中未消费的原文。页边界暂停前，候选和选择状态保持完整。

行缓冲的三份字形数组、词缓存、可选替换记录和数组容量合计受 16 MiB 约束。
检查点深拷贝这些记录，按实际保存的紧凑容量计入字节预算；缓存淘汰、向后重放、
浮动/表格/横竖混排上下文使用同一状态。普通词典不构造拥有结果或替换记录数组；
含替换能力的检测在不可变词典中缓存。

每次改写成功后，清除原词的旧词典机会，按实际剩余显示文字重新查询。新机会映射
回原文和未塑形队列，允许同一词连续改写；经过普通换行后同步移动候选索引，已被
消费的左侧改写上下文及其自动机会一起移除。新断点必须推进原文位置，并遵守当前
受保护的源簇/字素边缘。派生词超过 256 标量或 1024 UTF-8 bytes 时使用普通换行。

替换两侧、ready carry 和未塑形输入尾部现在重放 Unicode 17 的字素/换行状态。
组合重音、Prepend、Indic linker、RI 奇偶和 Emoji ZWJ 连接可扩大原文簇范围；
跨 ready/pending 边界的新连接会把完整字素移回待输入区，再测量字体和塑形。
格式控制符和变体选择符按正常文字隐藏；删除占位符使用独立私有标记，不参与
Unicode/词典输入，私有标记不会出现在公开 glyph flags 中。检查点按值保存流状态。

每个生成侧仍是受保护的原文原子簇，不能创造生成串内部的原文字节位置。内部独立
显示换行位置、混合方向子簇、完整段落双向重分析、语言大小写策略及条件复合词
重写继续跟踪。方向当前继承原文字形；字素/换行投影不等于完成跨脚本双向排版。
