# EPUB 引擎目录与内部链接验收 · 2026-11-07

基线 `c9dfc6c14a0c3d2372da4e8a6f02dc348309610f`；分支 `codex/engine-toc-links-20261107`。测试 DLL、完整引擎源码清单、Git blob 身份与构建参数见 [BUILD.json](BUILD.json)。

## A–C 实现

| 范围 | 文件与关键函数 | 行为 |
|---|---|---|
| A：目录解析 | `src/navigation.c`：`resource`、`walk`、`item`、`exr_epub_navigation_details` | EPUB3 manifest 的 nav 属性 → NCX navMap；解析嵌套树与 NCX playOrder |
| A：统一目录与恢复 | `src/publication.c`：`exr_publication_toc`、`recover_toc`、`recover_part` | 输出 title、level、target、source、play_order；level 从 1 开始 |
| B：href → part | `src/publication.c`：`exr_publication_resolve_href` | 复用 `exr_resolve_path` / `exr_uri_decode`，处理相对路径、点段、fragment 与 URL 编码；路径精确匹配优先，再做唯一 Unicode 大小写匹配 |
| B：fragment → offset | `src/document.c`：`exr_document_locate`、`exr_link_case_equal` | id/xml:id/a@name → part 内归一化 UTF-8 字节偏移；重复精确 id 取 DOM 首项，大小写回退要求唯一 |
| C：跳转与诊断 | `src/publication.c`：`exr_publication_locate`、`exr_publication_missing_targets` | 缺失 fragment 返回该 part 的 offset=0、ANCHOR_MISSING；按 part+fragment 去重保存请求；缺失 part 单独返回 PART_MISSING |
| C：当前章节 | `src/publication.c`：`exr_publication_target_at` | 输入 part+offset，返回最近的前置目录项索引；同位置取更深层项，首次缓存目录位置 |

公共声明位于 `include/exr/document.h`、`include/exr/layout.h`。`exr_target` 含 part、已解码 fragment 和 offset；URI 目标 offset=SIZE_MAX，正文恢复目标直接携带偏移。返回的目录与字符串借用至 publication_free。

恢复条件：nav 中没有可跳转的章节目录或只有许可证时先尝试 NCX；NCX 也没有章节目录或所有链接项均为许可证时扫描线性正文。优先识别原始正文行中的“第＋数字＋回/章/卷/节/節”，否则使用 h1–h6。正文引用中的“第四回中……”不会成为回目，重复的拆分文件标题保留后一个落点。恢复只增加目录元数据。

`toc_continuations` 处理真实拆分书：原目标无正文、下一线性 part 重复同一锚点且含标题时，将目录目标规范到下一 part。Pachinko 的章节先链接装饰图 part，再进入含标题的 continuation，属于此情况。普通 href 解析仍返回原资源。

## 五组验收数字

| 书 | 目录项 | 深度 | 来源 | 标题行定位 | 反向目录匹配 | 缺失锚点 |
|---|---:|---:|---|---:|---:|---:|
| 紅樓夢 | 108 | 1 | 正文恢复 | 10/10 | 10/10 | 0 |
| 醒世恆言 | 40 | 1 | 正文恢复 | 10/10 | 10/10 | 0 |
| Pachinko | 70 | 2 | ncx | 10/10 | 10/10 | 0 |

本次语料中的《醒世恆言》NCX 同样只有 1 项许可证，因此 40 项来自正文恢复。另有真实 EPUB3 nav 验证：Born a Crime 为 22 项、2 级、来源 nav。所有书籍仍使用原语料 SHA-256。原包目录清单见 [SOURCE-INVENTORY.json](SOURCE-INVENTORY.json)。

3. 锚点收集：17 本 EPUB 共 1,774 次内部 fragment 请求，缺失唯一目标 **1** 个。Crying in H Mart：`OEBPS/toc.ncx` 请求 `Text/p000_cover.xhtml#cover`，定位状态 ANCHOR_MISSING，part=0、offset=0；公开 missing_targets 查询返回该记录。三本指定书缺失数均为 0。

4. `tools/regress/run_realbooks.py`：19/19 本成功，**11,061 → 11,061 页**；页数变化 0 本、增加/删除页 0、逐页像素 SHA-256 差异 **0/11,061**，glyph count 差异 0。完整内容指纹前后一致。

5. ctest：基线 **169/169**，最终 **173/173**，失败 0。新增 4 组、234 项断言：nav 30、NCX 45、恢复 81、fragment 78。测试涵盖 nav 优先级、仅许可证 nav → NCX、page-list → NCX、嵌套、playOrder、正文恢复、误识别排除、拆分 continuation、Unicode 大小写、id/name 定位、重复 id、空/未投影锚点、缺失锚点记录去重、路径歧义与非法输入。见 [CTEST-TOC.txt](CTEST-TOC.txt)、[CTEST.txt](CTEST.txt)。

## 30 项逐项跳转结果

抽样固定为章节项首尾及等距位置。《紅樓夢》与《醒世恆言》从全部恢复项选取；Pachinko 从 Capítulo 章节项选取。先调用 publication_locate，再用原 EPUB XML 中标题/锚点后的 64 字符上下文做独立且唯一的文本匹配，随后通过真实 pager 的 layout_lines 比较行号。每项还调用 target_at 核对反向索引。脚本：[check_toc_realbooks.py](../../tests/check_toc_realbooks.py)。

目录序号、part 和行号均为 0 基；offset 为 part 内 UTF-8 字节偏移。Δ行全部为 0，满足 ±1 行。

### 紅樓夢

| 目录项 | 标题 | part | offset | 原始标题匹配 offset | 实际/预期行 | Δ行 | 反向索引 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | 第一回 甄士隱夢幻識通靈 賈雨村風塵怀閨秀 | 1 | 762 | 762 | 23/23 | 0 | 0 |
| 12 | 第十三回 秦可卿死封龍禁尉 王熙鳳協理宁國府 | 3 | 61997 | 61997 | 945/945 | 0 | 12 |
| 24 | 第三十一回 撕扇子作千金一笑 因麒麟伏白首雙星 話 | 7 | 42544 | 42544 | 649/649 | 0 | 24 |
| 36 | 第四十九回 琉璃世界白雪紅梅 脂粉香娃割腥啖膻 | 11 | 4551 | 4551 | 70/70 | 0 | 36 |
| 48 | 第六十一回 投鼠忌器寶玉瞞贓 判冤決獄平儿行權 | 14 | 37221 | 37221 | 566/566 | 0 | 48 |
| 59 | 第七十二回 王熙鳳恃強羞說病 來旺婦倚勢霸成親 | 17 | 79273 | 79273 | 1214/1214 | 0 | 59 |
| 71 | 第八十四回 試文字寶玉始提親 探惊風賈環重結怨 | 21 | 48442 | 48442 | 735/735 | 0 | 71 |
| 83 | 第九十六回 瞞消息鳳姐設奇謀 泄机關顰儿迷本性 | 24 | 18797 | 18797 | 286/286 | 0 | 83 |
| 95 | 第一零八回 強歡笑蘅蕪慶生辰 死纏綿瀟湘聞鬼哭 | 26 | 69640 | 69640 | 1059/1059 | 0 | 95 |
| 107 | 第一二零回 甄士隱詳說太虛情 賈雨村歸結紅樓夢 | 29 | 50341 | 50341 | 765/765 | 0 | 107 |

### 醒世恆言

| 目录项 | 标题 | part | offset | 原始标题匹配 offset | 实际/预期行 | Δ行 | 反向索引 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | 第一卷 | 1 | 778 | 778 | 23/23 | 0 | 0 |
| 4 | 第五卷 | 3 | 40089 | 40089 | 637/637 | 0 | 4 |
| 9 | 第十卷 | 5 | 32969 | 32969 | 514/514 | 0 | 9 |
| 13 | 第十四卷 | 6 | 56442 | 56442 | 929/929 | 0 | 13 |
| 17 | 第十八卷 | 8 | 47898 | 47898 | 762/762 | 0 | 17 |
| 22 | 第二十三卷 | 11 | 45690 | 45690 | 728/728 | 0 | 22 |
| 26 | 第二十七卷 | 13 | 83853 | 83853 | 1337/1337 | 0 | 26 |
| 30 | 第三十一卷 | 16 | 21988 | 21988 | 352/352 | 0 | 30 |
| 35 | 第三十六卷 | 18 | 37992 | 37992 | 603/603 | 0 | 35 |
| 39 | 第四十卷 | 20 | 27064 | 27064 | 441/441 | 0 | 39 |

### Pachinko

| 目录项 | 标题 | part | offset | 原始标题匹配 offset | 实际/预期行 | Δ行 | 反向索引 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 6 | Capítulo 1: Yeongdo, Busan, Coreia | 10 | 0 | 0 | 0/0 | 0 | 6 |
| 12 | Capítulo 7 | 22 | 0 | 0 | 0/0 | 0 | 12 |
| 19 | Capítulo 14 | 36 | 0 | 0 | 0/0 | 0 | 19 |
| 26 | Capítulo 3: Abril de 1940 | 50 | 0 | 0 | 0/0 | 0 | 26 |
| 32 | Capítulo 9: Osaka, 1949 | 62 | 0 | 0 | 0/0 | 0 | 32 |
| 39 | Capítulo 16: Osaka, abril de 1960 | 76 | 0 | 0 | 0/0 | 0 | 39 |
| 46 | Capítulo 2: Osaka, abril de 1965 | 90 | 0 | 0 | 0/0 | 0 | 46 |
| 52 | Capítulo 8: Nagano, agosto de 1978 | 102 | 0 | 0 | 0/0 | 0 | 52 |
| 59 | Capítulo 15: Nova York, 1985 | 116 | 0 | 0 | 0/0 | 0 | 59 |
| 65 | Capítulo 21: Tóquio, 1989 | 128 | 0 | 0 | 0/0 | 0 | 65 |

## 19 本分页回归

| 书籍 ID | 基线页数 | 最终页数 | 哈希变化页 |
|---|---:|---:|---:|
| a-raisin-in-the-sun | 354 | 354 | 0 |
| between-the-world-and-me | 228 | 228 | 0 |
| black-boy | 1011 | 1011 | 0 |
| born-a-crime | 501 | 501 | 0 |
| crying-in-h-mart | 506 | 506 | 0 |
| hongloumeng-24264 | 1586 | 1586 | 0 |
| how-does-it-feel-to-be-a-problem-being-young-and-arab-in-america | 492 | 492 | 0 |
| i-know-why-the-caged-bird-sings | 625 | 625 | 0 |
| kusamakura-japanese-vertical-writing | 462 | 462 | 0 |
| pachinko | 1214 | 1214 | 0 |
| tangshi300-52323 | 83 | 83 | 0 |
| the-absolutely-true-diary-of-a-part-time-indian | 560 | 560 | 0 |
| the-autobiography-of-malcolm-x. | 279 | 279 | 0 |
| the-distance-between-us-a-memoir | 702 | 702 | 0 |
| the-fire-next-time | 187 | 187 | 0 |
| the-fire-this-time-a-new-generation-speaks-about-race | 314 | 314 | 0 |
| the-house-on-mango-street | 181 | 181 | 0 |
| xingshihengyan-24239 | 1152 | 1152 | 0 |
| zami-a-new-spelling-of-my-name---a-biomythography | 624 | 624 | 0 |

内容指纹：`5e1e09169287f5767ee5a7d71fc37ef472bd1c0327c802cf4226573751e8c78c`。

逐页哈希原件：[基线 JSON.gz](pagination-baseline.json.gz)、[最终 JSON.gz](pagination-candidate.json.gz)；比较报告：[pagination.diff.json](pagination.diff.json)。原件仅含计数、时间和哈希。两份 gzip 解压后可以交给原 `run_realbooks.py --baseline ... --candidate ... --output ...` 复核。

## 本地复现

```powershell
python tests/make_toc_fixtures.py
cmake --build build/w -j 4
ctest --test-dir build/w -j 4 --output-on-failure
python tests/check_toc_realbooks.py --manifest tools/regress/corpus.json --dll build/final/libexreader.dll --font <Reader.otf> --layout tools/regress/layout.json --output <toc.json>
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll <libexreader.dll> --font <Reader.otf> --layout tools/regress/layout.json --source-revision <source> --baseline <baseline.json> --output <candidate.json> --workers 4
```

受保护树已登记在 [R-PROTECTED-TREES.md](../ci-packaging-20261103/R-PROTECTED-TREES.md)。本轮未改 examples/、排版/渲染函数或工作流；未合成卷首目录页。未手动触发 CI，未取消 workflow run。
