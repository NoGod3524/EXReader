# EPUB 3 固定版式（Fixed Layout）— 支持范围与验证（D1，2026-11-10）

此前覆盖矩阵只验证过 2 本 `rendition:layout=pre-paginated` 真书，而且两本都按流式降级读取：Haruko 在 720×1040 下是 14 页，在 480×800 下变成 15 页。本次补上了固定版式语义，并用 8 本书（2 本真书、6 本合成书）逐项验证六个项目。

## 实现了什么

| 方面 | 行为 |
|---|---|
| OPF 解析 | 包级 `rendition:layout`、`rendition:spread`、`rendition:viewport`（"width=W, height=H"），以及 spine 的 `page-progression-direction`。itemref 的 `rendition:layout-pre-paginated` / `rendition:layout-reflowable` 覆盖包级默认值；`page-spread-left/right`、`rendition:page-spread-left/right/center` 也会读取。没有任何 rendition 声明的书，其 rendition 表为 NULL，流式路径与原来逐字节一致。 |
| 原生视口 | 优先级依次为：内容文档 `<meta name="viewport">` → 包级 `rendition:viewport` → 首图固有尺寸 → 请求页尺寸。来源可通过 `exr_layout_fixed_viewport().source` 查询。 |
| 排版与缩放 | 固定部件在原生视口（CSS px，margin 0，字号 16，行高 1.2，段距 0，强制启用书内 CSS，忽略读者 user CSS）上只排一页，然后用统一比例 `scale=min(W/vw,H/vh)` 居中映射到请求页（等比，留白不裁切）。溢出内容留在该页，pager 恒定只出 1 页。 |
| 绝对定位 | 仅在固定页上生效：`position:absolute/fixed` 加 `top/right/bottom/left`（px/em/%/负值）。包含块是页面；在已定位的祖先内部，包含块是该祖先盒。inset 为 auto 时保留静态位置。元素脱离文档流，不推挤后续静态内容；背景盒覆盖声明的 `width/height`。流式页面完全不读这些属性。 |
| 双页展开 | `exr_publication_spreads()` 按阅读顺序返回物理左/右槽：ltr 下 left 开屏，rtl 下 right 开屏；未声明 side 时与上一页交替，首页为 recto（ltr 在右，rtl 在左）；`center` 页、流式页和 `rendition:spread none` 下的页面一律单屏（`EXR_SPREAD_SINGLE`）。 |
| 新增公共 API | `exr_publication_rendition`、`exr_publication_spreads`、`exr_layout_fixed_viewport` 为增量 ABI；复用已有 `exr_publication_page_progression`，返回解析后的 `exr_direction`（缺省依语言回退，无语言时 LTR），原有签名未改动。 |

已知不支持的部分（本次没有实现，也不计入六项结论）：

- CSS `transform`：杂志样本里 `transform:rotate(-8deg)` 的说明文字按未旋转渲染。旋转文本靠 `writing-mode:vertical-rl` 实现，这部分已验证。
- `z-index`：按文档顺序绘制，背景盒先画、文字后画。
- SVG spine 项：原有限制，spine 只接受 XHTML。
- 整本 `exr_document_open` 流（多章节合排）和有界 chapter reader 视图：仍走流式路径。固定语义只作用于 publication 的单部件文档，也就是阅读器实际使用的路径。

## 语料（8 本，覆盖六种类型）

真书来自 IDPF epub3-samples 20230704，SHA-256 与 `tools/regress/corpus-formats.json` 一致。合成书由 `tools/fixed_layout/make_corpus.py` 确定性生成，内容为本仓库原创，CC0；成品和几何 oracle 存放在 `evidence/fixed-layout-20261110/corpus/`。

| 书 | 类型 | 部件 / 720×1040 页数 | 视口 | 要点 |
|---|---|---|---|---|
| page-blanche | 漫画型（真书） | 10 / 10 | content 1200×1577 | 整页 JPEG；`img{position:absolute}` 无 inset；有 nav 目录；ltr 且 side 全部声明 |
| haruko-html-jpeg | 双页展开 rtl + item 级混合（真书） | 13 / 16 | content 600×837 | rtl，`page-spread-left/right`；末项 `rendition:layout-reflowable` |
| fxl-picturebook | 绘本型 | 4 / 4 | content 1024×768（横版） | 出血底图，加 left/top、right/bottom、% 三种绝对定位；`spread none` |
| fxl-magazine | 杂志型 | 4 / 4 | content 1200×1600 | 标题、三栏绝对定位、`vertical-rl` 旋转侧栏、`transform` 说明（不支持） |
| fxl-toc | 固定版式 + 目录 | 5 / 5 | content 800×1100 | nav 指向第 1/3/5 页 |
| fxl-spread-ltr | 双页展开 ltr | 7 / 7 | content 700×1000 | right/left/right/center/left/right/auto |
| fxl-mixed | 混合（item 级 rendition） | 5 / 17 | package `rendition:viewport` 800×1000 | 包级 reflowable；3 个 itemref 为 pre-paginated |
| fxl-noviewport | 缩放：无任何 viewport | 2 / 2 | image 600×900；page 720×1040 | 无 meta，也无 `rendition:viewport` |

## 六项验证方法

验证脚本是 `tools/fixed_layout/verify.py`，经公共 SDK（ctypes）执行；配置为 `tools/regress/layout.json`，字体为 Reader.otf。每个部件都在 720×1040、1040×720 和 480×800 三种尺寸下排版。

1. **页面尺寸**：位图等于请求尺寸；`scale` 等于 min(W/vw,H/vh)（误差 1e-4），偏移等于居中值；所有图片盒都落在映射后的视口内。竖版和横版两种目标都要检查。
2. **整页图完整**：整页图盒应等于映射后的视口（±1px）。合成图四边各有一条红框，渲染后在四边中点采样，必须 4/4 都是红色。真书则按图片固有尺寸和宽高比核对（误差 0.5%）。
3. **绝对定位**：在 layout box 中按元素 id 找到盒，检查声明的 inset 映射后是否吻合（±1px），并在盒内采样像素，颜色应等于声明的背景色。page-blanche 检查无 inset 的绝对定位图片是否处于静态位置；竖排侧栏另外检查是否存在竖排字形。
4. **双页顺序**：`exr_publication_spreads` 的结果与 oracle 逐屏比对左槽、右槽和单屏标志。真书的 oracle 是按 OPF 声明人工推导出来的。
5. **混合版式**：固定部件在三种尺寸下都恰好 1 页，并带 fixed 记录；流式部件没有 fixed 记录，文字右界落在各自页宽内，且 480 宽比 720 宽至少窄 50px（确实发生了重排）。
6. **缩放**：视口来源分别对应 content、package、image、page 四种情况，并检查竖版和横版两种目标下的比例；page 来源时比例应为 1。

## 结果

六项全部通过，在全部 8 本中逐项为 **6/6**（N/A 表示该书没有可测对象）。

| 书 | 1 尺寸 | 2 整页图 | 3 绝对定位 | 4 双页 | 5 混合 | 6 缩放 |
|---|---|---|---|---|---|---|
| page-blanche | PASS | PASS | PASS（静态位置 9/9） | PASS | PASS | PASS |
| haruko-html-jpeg | PASS | PASS | N/A（无定位元素） | PASS | PASS | PASS |
| fxl-picturebook | PASS | PASS（红框 4/4） | PASS（3/3/页） | PASS | PASS | PASS |
| fxl-magazine | PASS | N/A（无整页图） | PASS（6/6/页，含竖排） | PASS | PASS | PASS |
| fxl-toc | PASS | PASS | PASS | PASS | PASS | PASS |
| fxl-spread-ltr | PASS | PASS | PASS | PASS | PASS | PASS |
| fxl-mixed | PASS | PASS | PASS | PASS | PASS | PASS |
| fxl-noviewport | PASS | PASS | PASS（% inset） | PASS | PASS | PASS |

fxl-toc 的目录由 `exr_publication_toc` 得到，3 条目录分别指向部件 0、2、4，三者都是 pre-paginated。

逐页数值（scale、offset、盒几何、来源）见 `evidence/fixed-layout-20261110/results.json`，截图见同目录 `screenshots/`：每本 ≥2 张，另有双页合成图。

### 双页展开顺序

- haruko（rtl）：`[p01]`，然后 `(右 p02 | 左 p03)`、`(p04|p05)`、`(p06|p07)`、`(p08|p09)`、`(p10|p11)`，然后 `[p12 右]`，最后 `[About 单屏]`。截图 `haruko-html-jpeg-spread-2-1.png` 中左槽是 p03，右槽是 p02，读者先读右页。
- page-blanche（ltr）：`[cover 右]`、`(000|001)`、`(002|003)`、`(004|005)`、`(006|007)`、`[008 左]`。
- fxl-spread-ltr：`[1 右]`、`(2|3)`、`[4 center 单屏]`、`(5|6)`、`[7 auto→左]`。

### 混合版式判定

fxl-mixed：包级默认 reflowable，fixed 由 itemref 声明，共 5 个部件、17 页（720×1040）。

| 部件 | 判定 | 页数 720×1040 / 1040×720 / 480×800 | 依据 |
|---|---|---|---|
| 1 cover | 固定 | 1 / 1 / 1 | itemref `rendition:layout-pre-paginated`；视口来源 package 800×1000，scale 0.9 |
| 2 ch1 | 流式 | 7 / 8 / 14 | 无 fixed 记录；文字右界 675.4 → 441.3 |
| 3 plate | 固定 | 1 / 1 / 1 | 同 1；right/bottom 说明框的位置正确 |
| 4 ch2 | 流式（继承包级默认） | 7 / 8 / 14 | itemref 没有 rendition 属性 |
| 5 end | 固定 | 1 / 1 / 1 | `rendition:layout-pre-paginated page-spread-left` |

整书 720×1040 的第 1、9、17 页为固定页，第 2–8 页和第 10–16 页为流式页。

haruko 的判定：p01–p12 共 12 页是固定页（各 1 页，600×837，scale 1.2）；AboutThisDocument 是流式，在 720×1040 下 4 页，文字右界 665.3，到 480×800 时收窄为 425.3。

## 回归与测试

- **19 本流式真书**（`tools/regress/run_realbooks.py`，基线为未改动的 3076d3dd，从独立源码快照构建）：19/19，共 11,426 页、8,648,571 字形。页数变化 0 本，字形数变化 0 本，逐页像素哈希变化 0 页（`regress-19books.diff.json`）。
- **新增 ctest 4 组**（`native-fixed-layout-{rendition,viewport,absolute,mixed}`，`tests/test_fixed_layout.c`，EPUB 在内存中构造）：
  - rendition：包级/项级覆盖、ltr/rtl/center/auto/none 的展开顺序、无 rendition 的书。
  - viewport：四种来源、竖版/横版比例、像素级验证不裁切与留白、溢出时仍只出 1 页。
  - absolute：各种 inset、百分比、嵌套包含块、静态位置不推挤、像素颜色。
  - mixed：固定部件 1 页；流式部件与无 rendition 的同书字形逐一相等；流式页忽略 `position:absolute`。
- **负对照**：屏蔽绝对定位分支后，absolute 组在第 198 行失败。

## 复现

```sh
python tools/fixed_layout/make_corpus.py --output build/fxl-corpus
python tools/fixed_layout/verify.py --dll <libexreader.dll> --font <Reader.otf> \
  --layout tools/regress/layout.json --corpus evidence/fixed-layout-20261110/corpus.json --output build/fxl-verify
```

`corpus.json` 中真书的路径指向本机样本目录，校验用的 SHA-256 记录在 `results.json` 里。
