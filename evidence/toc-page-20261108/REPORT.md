# 卷首目录页验收 · 2026-11-08

基线 `d1395059`（main，已含 #76）；分支 `codex/engine-toc-page-20261108`。固定 720×1040、margin 36、字号 28、line-height 1.5、段间距 10，同一 Reader.otf（SHA-256 见 body-hash-compare.json）。

## 实现

| 规格 | 做法 |
|---|---|
| 合成页机制 | `exr_page_kind { EXR_PAGE_BODY, EXR_PAGE_TOC }` + `exr_layout_page_kind()`；`exr_toc_pages_create()` 产出独立的 positioned `exr_layout`，不属于任何 publication part |
| 位置 | `exr_publication_toc_insert_before()` 返回目录页应排在其前的阅读顺序 part：首个阅读 part 若 id/path 含 cover/表紙/表纸/封面，或是无文字的纯图 part，则排在它之后，否则排在最前。拼接由宿主按此下标做 |
| 内容 | `exr_publication_toc()`（nav / NCX / 正文恢复），标题与层级原样 |
| 版式 | 目录项、页码、标题、点线先作为普通段落交给现有 `exr_layout_create_ex`（同字体、同视口、同用户 CSS、同对齐规则）排版；只有行装配（点线、右对齐页码、分页、续页表头）在 `src/toc_page.c`。行内样式 `text-indent:0; line-height:1; margin-left:(level-1)em`，并为页码区预留右边距，使长标题在页码前换行 |
| 点线 | 重复的 `·`（U+00B7）字形；字体里 `·` 宽于 0.6em（CJK 全角点）时退用 `.`。理由：纯字形，宿主不需要新的绘制命令，也不需要 box/dash 支持；点按"从页码往左的固定格线"排布，各行点列对齐、间距恒等于字宽，不会断 |
| 超链接 | `exr_toc_pages_entry_at()`（行几何）与 `exr_toc_pages_entry_for_offset()`（接 `exr_layout_hit_test` 返回的偏移）得到条目序号 → `exr_publication_toc()[i].target` → `exr_publication_locate`（内部即 `exr_document_locate`）。整行宽度都是点击目标 |
| 分页 | 条目不跨页；续页顶部重复"目录（续）"/"Contents (continued)"（有 CJK 标题用中文，宿主可经 `exr_toc_page_options` 传入本地化文案） |
| 无目录 | `*out == NULL` 且 `EXR_OK`，不生成空页 |
| 搜索/复制 | 目录页是独立 layout，不在 publication 任何 part 的文本里；`exr_layout_page_kind()` 供宿主在混排页列表时跳过。引擎没有"复制全书"入口，全书文本即各 part 的 `exr_document_text`，已验证不含目录合成文字 |

## 页码编号的选择：罗马数字 i、ii、iii…，不占正文页号

1. 目录条目的页码必须等于读者在正文里看到的页号。若目录页占用正文页号，目录自身页数会反过来改变所有条目的页码（循环依赖）。
2. 正文页序、书签、阅读进度、CFI→页映射和现有逐页哈希都保持不变，宿主只需在封面后插入若干页。
3. 与印刷惯例一致（前言用罗马数字）。每页用 `exr_toc_pages_label()` 取 `i`、`ii`…。

## 验收

| # | 项 | 结果 |
|---|---|---|
| 1 | 紅樓夢（108 项，正文恢复） | 目录页 **11** 页；每页项数 16,10,10,10,10,10,10,10,10,10,2；最大层级缩进 **0 px**（单层）。表头"目录"，续页"目录（续）" |
| 2 | 醒世恆言（40 项，正文恢复） | **2** 页，21 + 19；缩进 0 px |
| 2 | Pachinko（70 项，ncx，2 层） | **4** 页，21,21,20,8；二级缩进 **28 px**（=1em） |
| 2 | 另：Born a Crime（nav，22 项，2 层） | 2 页，14 + 8；缩进 28 px |
| 3 | 点击正确性 | 三本指定书各抽 10 项，**30/30**：命中序号 = 目标序号（行几何与 `exr_layout_hit_test` 偏移两条路都对），定位后与原 EPUB XML 独立匹配的标题行 Δ行 = 0（±1 内）。全部 17 本带目录 EPUB 共 **161/161** 命中序号正确 |
| 4 | 点线与页码 | 17 本共 **全部有标签的行**（逐行从布局几何核对）点线等间距连续、页码右端 = W−margin（容差 0.02px）。截图 `screenshots/` |
| 5 | 无目录书 | `tests/fixtures/toc-pages-none.epub`：`exr_toc_pages_create` 返回 NULL，不生成页；该书改前/改后 DLL 均 1 页、逐页哈希相同 |
| 6 | 搜索 | `exr_document_find` 在全部阅读 part 搜"目录（续）"（紅樓夢，仅出现在目录页）命中 **0**，同一串在目录页字形中存在；Latin 书同理搜 "Contents (continued)" 命中 0。C 测试里 "Zyxwv"（仅出现在 nav 标题）命中 0，对照词 "Body paragraph" 命中 >0 |
| 7 | 正文 | 19 本 **11,296 → 11,296 页，逐页像素哈希改变 0**，内容指纹一致（body-hash-compare.json） |
| 8 | ctest | 基线 **196/196**（本机配置：audio/library/text-index/pdf-edit 开，与任务写的 191 配置不同），新增 `native-toc-page`（22,029 项断言），共 **197/197** |

## 说明与限制

- **单倍行距**：已设 `line-height:1`，但引擎行盒高度是 `max(leading, 上升+下降)`。Reader.otf 自然高度 42px，所以目录行距为 42px，与正文（28×1.5=42）相同；其他字体（测试里的 primary.ttf 15px vs 21px）则确实更紧。这是引擎既有规则，改动会影响正文哈希，未动。
- 仅横排、从左到右的行；竖排书的目录页也是横排。
- 目录页码标签由宿主传入（宿主已知全书分页）；harness 用真实 pager 分页计算。
- 封面识别是启发式（命名或纯图首 part），非 OPF guide 解析。
- 构建注册：`CMakeLists.txt` 一个测试、`tools/layers.json` 一个源文件登记；未改 `examples/`、workflow。
- 本地构建因 TLS 校验失败无法下载依赖，改用本机已有的依赖源码（`FETCHCONTENT_SOURCE_DIR_*`），未关闭证书校验。
