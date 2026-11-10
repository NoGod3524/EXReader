# T1：真实 DOCX 结构往返验收

基线：PR #125 `c04560b784bda182b350b9f6faac33a10ed60509`。30 个原创混合夹具；无修改与只改正文一处分别测量。

**结果：两套矩阵均由 531/540（98.33%）升至 540/540（100%）。无修改 30/30 份所有 OPC 部件字节相同；改字 30/30 份严格等于“只替换目标文字”的独立预期。编辑额外损失 0。**

完整 CTest **391/391**，其中原 #125 当前基线 321 项，新增 70 项；无排除项。19/19 真书、11,318 页、8,648,571 字形，页数和逐页 RGBA SHA-256 变化均为 0。

## 指标口径

#117 实际提供 6 项结构指标；旧报告的 18/18 是 6×3 文档。本任务直接调用原函数，保留原六项，再加入原有文本／图片哈希和十项严格检查，组成每份文档 18 项。原校验器及其断言未修改。

改字路径先独立生成 expected.docx：仅将唯一目标 run 的文字替换并进行 XML 转义。记录 source／expected／actual 三组数值，字符数和文本哈希的有意变化逐项列出；其余部件和目标段落内的结构仍全部比较。每格增加、减少、同数量内容替换都判失败。

## 30 份夹具

| 夹具／结构 | 字节 | 修前 无改／改字 | 修后 无改／改字 | 改字额外损失 |
| --- | ---: | ---: | ---: | ---: |
| [01-table-horizontal · 表格：横向合并](../tests/fixtures/docx-real/01-table-horizontal.docx) | 7,860 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [02-table-vertical · 表格：纵向合并](../tests/fixtures/docx-real/02-table-vertical.docx) | 7,861 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [03-table-nested · 表格：嵌套表](../tests/fixtures/docx-real/03-table-nested.docx) | 7,916 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [04-table-repeat-header · 表格：跨页重复表头](../tests/fixtures/docx-real/04-table-repeat-header.docx) | 8,765 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [05-table-multi-paragraph · 表格：单元格多段](../tests/fixtures/docx-real/05-table-multi-paragraph.docx) | 7,862 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [06-field-page · 域：PAGE](../tests/fixtures/docx-real/06-field-page.docx) | 7,877 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [07-field-numpages · 域：NUMPAGES](../tests/fixtures/docx-real/07-field-numpages.docx) | 7,911 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [08-field-date · 域：DATE](../tests/fixtures/docx-real/08-field-date.docx) | 7,951 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [09-field-ref · 域：REF 交叉引用](../tests/fixtures/docx-real/09-field-ref.docx) | 7,993 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [10-field-toc · 域：TOC](../tests/fixtures/docx-real/10-field-toc.docx) | 7,928 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [11-list-multilevel · 编号：多级](../tests/fixtures/docx-real/11-list-multilevel.docx) | 7,939 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [12-list-restart · 编号：重启](../tests/fixtures/docx-real/12-list-restart.docx) | 7,935 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [13-list-style-bound · 编号：样式绑定](../tests/fixtures/docx-real/13-list-style-bound.docx) | 7,951 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [14-style-inheritance · 样式：三级继承](../tests/fixtures/docx-real/14-style-inheritance.docx) | 7,916 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [15-style-direct-override · 样式：直接格式覆盖](../tests/fixtures/docx-real/15-style-direct-override.docx) | 7,998 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [16-style-theme-fonts · 样式：主题字体与空格式 run](../tests/fixtures/docx-real/16-style-theme-fonts.docx) | 8,037 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [17-section-margins · 节：不同页边距](../tests/fixtures/docx-real/17-section-margins.docx) | 7,995 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [18-section-landscape · 节：横向页混排](../tests/fixtures/docx-real/18-section-landscape.docx) | 8,011 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [19-section-columns · 节：一二三栏混排](../tests/fixtures/docx-real/19-section-columns.docx) | 8,006 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [20-footnote-restart · 脚注：每页重编号](../tests/fixtures/docx-real/20-footnote-restart.docx) | 8,008 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [21-footnote-table · 脚注：带表格](../tests/fixtures/docx-real/21-footnote-table.docx) | 8,070 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [22-image-inline · 图形：内联 PNG](../tests/fixtures/docx-real/22-image-inline.docx) | 7,865 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [23-image-floating · 图形：四周环绕](../tests/fixtures/docx-real/23-image-floating.docx) | 8,066 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [24-shape-group · 图形：组合图形](../tests/fixtures/docx-real/24-shape-group.docx) | 8,322 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [25-textbox · 其他：文本框](../tests/fixtures/docx-real/25-textbox.docx) | 8,015 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [26-comment-anchors · 其他：批注锚点](../tests/fixtures/docx-real/26-comment-anchors.docx) | 7,961 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [27-bookmarks · 其他：跨 run 书签](../tests/fixtures/docx-real/27-bookmarks.docx) | 7,987 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [28-hidden-text · 其他：隐藏文字](../tests/fixtures/docx-real/28-hidden-text.docx) | 7,961 | 17/18 · 17/18 | 18/18 · 18/18 | 0 |
| [29-header-table · 其他：页眉表格](../tests/fixtures/docx-real/29-header-table.docx) | 7,886 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |
| [30-chinese-field-code · 其他：中文域代码](../tests/fixtures/docx-real/30-chinese-field-code.docx) | 8,040 | 18/18 · 18/18 | 18/18 · 18/18 | 0 |

全部小于 60 KiB；最小／最大分别为 7860／8765 字节。每份都混合正文、表格、图片、脚注、页眉页脚、域、编号、样式和主题。重复表头夹具有 89 行；每页重编号脚注夹具含两个脚注和显式换页；PNG 为原创 160×96 三条形图。

## ZIP 容器仍有变化

OOXML 部件字节保留与 ZIP 容器原样复制分开统计。[逐夹具 ZIP 审计](docx-real/zip-container.json) 同时记录修前、修后两条路径的容器哈希、条目顺序、时间戳、属性和其它元数据变化。此项保留在明确放弃清单，未计入 18 项通过率。

| 修后路径 | 整包哈希变化 | 条目顺序变化 | 时间戳变化条目 | 文件属性变化条目 |
| --- | ---: | ---: | ---: | ---: |
| noop | 30/30 | 30/30 | 420 | 420 |
| edited | 30/30 | 30/30 | 420 | 420 |

## 18 项 × 30 份总通过率

| 指标 | 修前无改 | 修前改字 | 修后无改 | 修后改字 |
| --- | ---: | ---: | ---: | ---: |
| paragraphs | 30/30 | 30/30 | 30/30 | 30/30 |
| characters | 30/30 | 30/30 | 30/30 | 30/30 |
| tables | 30/30 | 30/30 | 30/30 | 30/30 |
| images | 30/30 | 30/30 | 30/30 | 30/30 |
| footnotes | 30/30 | 30/30 | 30/30 | 30/30 |
| section_margins | 30/30 | 30/30 | 30/30 | 30/30 |
| text_sha256 | 30/30 | 30/30 | 30/30 | 30/30 |
| image_sha256 | 30/30 | 30/30 | 30/30 | 30/30 |
| opc_parts | 30/30 | 30/30 | 30/30 | 30/30 |
| relationships | 30/30 | 30/30 | 30/30 | 30/30 |
| tables_xml | 30/30 | 30/30 | 30/30 | 30/30 |
| fields_xml | 30/30 | 30/30 | 30/30 | 30/30 |
| numbering_styles_theme | 30/30 | 30/30 | 30/30 | 30/30 |
| sections_xml | 30/30 | 30/30 | 30/30 | 30/30 |
| notes_xml | 30/30 | 30/30 | 30/30 | 30/30 |
| drawings_xml | 30/30 | 30/30 | 30/30 | 30/30 |
| annotations_xml | 30/30 | 30/30 | 30/30 | 30/30 |
| main_xml | 21/30 | 21/30 | 30/30 | 30/30 |
| **合计** | **531/540** | **531/540** | **540/540** | **540/540** |

原 #117 六项在修前、修后各路径均为 180/180。缺陷集中在主文档树／标记顺序，计数相等不能证明无损。额外还逐部件比较原始字节；完整 XML 树保留注释、处理指令、属性、text 与 tail，并验证第二次保存稳定。

## 每项修复：先失败，再修复，转绿

| 步骤 | 失败断言／根因 | 同一断言转绿与指标 |
| --- | --- | --- |
| 文字命令（矩阵前提） | `text-command`：原 DLL 没有 `exr_edit_set_run_text`。旧模型无法通过公开命令替换正文文字。 | 新命令保留 ID、格式、模板及相邻 opaque run；历史、事务、别名、非法输入和逐分配点失败检查通过。结构分数 531→531，没有把新增 API 记为保真分数提升。 |
| T1-01：段落属性前标记，6 份 | `paragraph-markers`：`pPr` 前的注释／PI 被当作 opaque run，却在写出时统一移到属性后。原树位置不等，主部件字节变化。 | 原位置输出前导 opaque run；同一断言通过。两套矩阵 531→537，原始部件精确相等 21→27。 |
| T1-02：最终节尾，3 份 | `section-tail`：body 最后的 `sectPr` 在所有块之后追加，导致原本位于它后面的注释／PI 移到前面；原位节还无故增加命名空间声明。 | 先输出最终节再输出其原 trailer；原段落仍提供命名空间时保持节原字节，移位节继续补足绑定。同一断言通过。两套矩阵 537→540，原始部件精确相等 27→30。 |

修前正文改字使用公开 seed API 深拷贝模型快照，仅改目标 run；原 #125 没有文字命令。补命令阶段改用新公开 API，结果仍为 531/540，证明两种表达方式产生同样的原始损失。中间阶段的 DLL 与报告单独保存，断言未放宽。

| 逐步重放 | 无修改 | 改字 | 精确部件（无改／改字） |
| --- | ---: | ---: | ---: |
| Git 原始 #125 | 531/540 | 531/540 | 21/30 · 21/30 |
| 只加文字命令 | 531/540 | 531/540 | 21/30 · 21/30 |
| 再修段落标记 | 537/540 | 537/540 | 27/30 · 27/30 |
| 再修节尾／最终 | 540/540 | 540/540 | 30/30 · 30/30 |

## 原始证据与复现

- [修前矩阵](docx-real/before.json.gz)、[文字命令阶段](docx-real/text.json.gz)、[段落修复阶段](docx-real/paragraph.json.gz)、[最终两套矩阵](docx-real/after.json.gz)：每格 source／expected／actual、失败路径、部件哈希与编辑额外损失。
- 三个原始失败断言：[文字命令](docx-real/red-text-command.txt)、[段落标记](docx-real/red-paragraph-markers.txt)、[节尾](docx-real/red-section-tail.txt)；[同一断言及新增检查转绿](docx-real/green-regressions.txt)。
- [精确 #125 对照构建](docx-real/control-build.json)、[文字阶段构建](docx-real/stage-text-build.json)、[段落阶段构建](docx-real/stage-paragraph-build.json)：122 个复用产品源文件均核对 Git 原文字节，模型和 IO 重编译，使用原公开头及相同依赖。
- [完整 CTest](docx-real/ctest.txt)、[最终构建](docx-real/build-final.txt)、[配置及测试登记](docx-real/configure-final.txt)、[分层检查](docx-real/layers.txt)。
- [19 本逐页哈希](docx-real/realbooks.json.gz)、[冻结基线差异](docx-real/realbooks.diff.json)。每本输入先核对 manifest SHA-256，再完整渲染各页；原书不入库。
- [生成、矩阵、CTest、对照构建命令](../tests/fixtures/docx-real/README.md)；[明确放弃与保守行为](DOCX-LIMITS.md)。

字节相同指解压后的 OPC 部件。写出会重建 ZIP 容器，其整体 SHA-256 不作为相等条件。保留域、浮动图和组合图形的源数据不代表 core 能重新求值或排版这些 Word 结构。
