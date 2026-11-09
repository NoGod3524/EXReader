MOBI / KF8 / FB2 实现与验收（2026-11-08）

A：PDB record 目录、PalmDOC header、record trailers、PalmDOC LZ77；UTF-8/CP1252；RECINDEX PNG/JPEG/GIF；保留原始字节位置用于 filepos/INDX；按 mbp:pagebreak 分片，无分隔符时在 256 KiB 后的块边界分片。

B：HUFF/CDIC 短/长码、递归短语、循环/深度/内存限制；SKEL/FRAG 重组 section，FDST 解析辅助流，INDX/CNCX 和 guide 提供导航。打开仅建立容器/章节索引；读取时按需扫描记录的解压长度，不生成跳过记录的文本，缓存短语长度，再展开目标记录。只加载当前章节引用的 CSS/SVG。单个位图的 SVG 封面映射到普通图片资源，继续使用共享渲染器。

C：复用现有 XML 树和 ZIP 基础设施，自己映射 FB2 元素与 base64。支持 UTF-8、windows-1251、FB2 ZIP；按 section 分片、合并多行 title 为一个目录项、保留嵌套关系，修正跨 section href，显示封面与正文图片。

D：统一通过 exr_publication_open / open_memory → publication_load → document → pager / layout / renderer；没有格式专用渲染器。直接 document API 保持现有 eager 语义；KF8 渐进读取使用 publication API。没有新增第三方解析库。

| 验收项 | 结果 |
|---|---|
| 1 样本 | MOBI 3、AZW3 5（含 HUFF 2）、FB2 7；全部存放库外 |
| 2 打开/页数/字符/首屏 | 15/15 打开；逐本数据与完整 SHA-256 见下表；首屏全部目视通过；入库截图 3 张 |
| 3 PalmDOC | 3/3 首 section 字节数完全一致：1569、1716、1612；同时对完整解压结果逐字节比较 |
| 4 HUFF/CDIC | 2/2 与 Foliate 完整字节一致：212019、494405；各 record 长度也一致 |
| 5 FB2 | 7/7 打开；3 本主要图片样本均显示封面；另测俄文原书、windows-1251+ZIP+图片 |
| 6 EPUB | 19/19，11116 页；页数变化 0、页面哈希变化 0；同输入/字体/布局/环境 |
| 7 ctest | 210/210 全绿（原 205，新增 5 组）；分层检查 0 反向依赖 |
| 8 错误 | 13 个损坏/空 section/不支持的 SVG 案例均返回明确错误；完整外部书样本解析失败 0 本 |

页数采用 720×1040、Arial、28px、行高 1.5；字符数是各 section 规范化文本的 Unicode 字符数之和。图片为封面或正文资源。目录数量含 KF8 guide landmarks。

| 文件 | 打开 | parts | 页数 | 字符数 | 导航项 | 图片数 | 首屏 | SHA-256 |
|---|---|---:|---:|---:|---:|---:|---|---|
| pg11.mobi | 是 | 20 | 187 | 162213 | 16 | 1 | 正常 | `1b4222ffdf1862a39d0fae6d42c588f28a34c12ad73cc21c2849fe2646cac3e1` |
| pg11.azw3 | 是 | 19 | 200 | 162213 | 17 | 1 | 正常 | `d8211269aed55ded8302f289950936db8368b4d4d384c463b722034152f8f1d2` |
| pg84.mobi | 是 | 35 | 451 | 437723 | 32 | 1 | 正常 | `d907f385b28a2af24f6186a646fd366ede1b84c4c688afe93da3f705862e8e74` |
| pg84.azw3 | 是 | 34 | 475 | 437724 | 33 | 1 | 正常 | `bb23e01816942b03234bc72e94d278217aaf45eba384113ec4b5d73922a66865` |
| pg1661.mobi | 是 | 20 | 618 | 578708 | 18 | 1 | 正常 | `a374b1c7ccd719d6d4d557ee8fcce694f09ed26bc82e2b9a830dba884c994b53` |
| pg1661.azw3 | 是 | 19 | 652 | 578709 | 19 | 1 | 正常 | `f106332c7aa9e36fcf8fa53d1245a2e1c9e0dbe0c48e265f01523550e8216ab7` |
| pg11-huff.azw3 | 是 | 14 | 208 | 161669 | 16 | 0 | 正常 | `3f6c8a50a25a3b3a25385fb8f28f964bae1c5d1c781529704a1d578a623f1f18` |
| pg84-huff.azw3 | 是 | 31 | 489 | 437332 | 32 | 0 | 正常 | `42e99dd5bcac1e3de5f3fd0adc737908ce1cc1245194e1a5bad4935d5e1e6ecf` |
| pg11.fb2 | 是 | 18 | 203 | 162216 | 16 | 1 | 正常 | `3e820e84560529b47f778600b116b5c78cd9f4207a575fe46135dfe7030a8362` |
| pg84.fb2.zip | 是 | 34 | 452 | 437725 | 32 | 1 | 正常 | `9ee3aec4d1b9185b11284380f80e543e2f84e36e962c61b99a880808bb2b79cc` |
| pg1661.fb2 | 是 | 20 | 631 | 578709 | 18 | 1 | 正常 | `1ad086c339cb53ed868aa47cfa22c5bbc4c99e5d3343a33bbc217956452e715f` |
| evgeniy-onegin.fb2 | 是 | 12 | 360 | 158558 | 11 | 0 | 正常 | `d92a1ebd09a1e182eaadd3edf371b8484b7ddcc1a157b30dda4b7d72b8ef5792` |
| kapitanskaya-dochka.fb2 | 是 | 19 | 255 | 211342 | 17 | 0 | 正常 | `e11f5eb900e94ff8a449c5a5d3d30e9a2b2a44ee02c39012854fd02ad2a2dc0b` |
| pikovaya-dama.fb2 | 是 | 8 | 60 | 46142 | 6 | 0 | 正常 | `b90302d4ec699de314fa5376bcf039f5d255b7d15d3255074d8933a4df3122cd` |
| pikovaya-image-1251.fb2.zip | 是 | 9 | 61 | 46142 | 6 | 1 | 正常 | `b5fbe136a6dc990a0ff416fa5226337be73535b684f5b1463b7e72865afc0baa` |

三本主要 FB2 由安装的 Calibre 使用 `ebook-convert --sectionize toc` 从完整 Gutenberg MOBI 独立生成；pg84 另用 ZIP 包装。三本俄文 FB2 直接下载自 Tolkomedia，原书没有图片；另一个测试变体在完整《黑桃皇后》中加入 Gutenberg 公版封面，并转为 windows-1251、ZIP。所有派生过程、源 URL、源哈希及成品哈希在 [samples.json](samples.json)。

两本 HUFF 样本由 Gutenberg 完整 EPUB 经 KindleGen 2.9 `-c2` 生成，再由 KindleUnpack `-s` 提取独立 AZW3。工具仅用于库外样本准备与验证，不是引擎依赖。

| HUFF 样本 | PalmDOC 声明/FDST 正文 | 辅助流 | 完整解压 | 与长度吻合 |
|---|---:|---:|---:|---|
| pg11-huff.azw3 | 207816 | 4203 | 212019 | 正文匹配 PalmDOC 声明；总量匹配 FDST 末端 |
| pg84-huff.azw3 | 490176 | 4229 | 494405 | 正文匹配 PalmDOC 声明；总量匹配 FDST 末端 |

参考比对直接在库外加载 [Foliate mobi.js](https://github.com/johnfactotum/foliate-js/blob/78914aef4466eb960965702401634c2cb348e9b1/mobi.js)，固定 revision 与文件 SHA-256 见 samples.json。测试包装器只调用参考 codec；没有将参考解析代码复制进仓库。

错误语义：返回非 EXR_OK、输出 document/publication 为 NULL，并设置 error.code 和 error.message。EXR_FORMAT=5 表示无效表、越界、截断、重组 XML 错误或无可读内容；EXR_ENCODING=4 表示无效编码；EXR_LIMIT=6 表示短语深度/展开量/资源上限；EXR_UNSUPPORTED=11 表示 DRM 或不支持的结构。不能索引的大型无 SKEL KF8 返回 KF8_NO_SKELETON；空 section 返回 KF8_EMPTY_SECTION；组合/变换/背景 SVG 位图返回 EXR_UNSUPPORTED / KF8_SVG_BITMAP。详见 [errors.json](errors.json)。

渐进验证：合成两章 HUFF 样本只截短后一章的最后一个 record。open 与 section 0 均成功，section 1 返回 KF8_RECORD_LENGTH，证明打开与首章加载没有展开整本。原始 MOBI 允许先解压文本建立 pagebreak 目录；每次 publication_load 只返回一个 section 文档。

EPUB 基线说明：旧的 19 项混合清单实际包含 17 本 EPUB、1 本 PDF、1 本 MOBI，已原样保留在 historical-mixed-before.json。本次使用 17 本原 EPUB 加 Gutenberg Alice/Frankenstein 两本 EPUB；用保存的 b7bad7f 原始 DLL 对这 19 本重新运行基线，不将两本非 EPUB 计入 EPUB 回归。基线 DLL SHA-256 为 7bc6bf94e43e035af6acba6b5fc070cb2efc294bde7a0567642c0249fffd3cdf。

复现命令（样本参数指向库外目录）：

```powershell
cmake --build build -j 6
ctest --test-dir build --output-on-failure -j 6
python tools/check_layers.py build
python tests/book_acceptance.py --samples <external-samples> --output <evidence> --library build/libexreader.dll --probe build/exreader-book-codec-probe.exe --font C:/Windows/Fonts/arial.ttf
python tools/regress/run_realbooks.py --manifest <epub-path-manifest> --dll build/libexreader.dll --font <Reader.otf> --layout tools/regress/layout.json --output <epub-after.json> --baseline <epub-before.json> --workers 3 --source-revision <measured-revision>
```

截图：[MOBI](mobi-first.png) · [AZW3](azw3-first.png) · [FB2](fb2-first.png)。

受保护树及源文件身份记录见 protected-trees.json。examples/ 和 .github/ 未改；src/book.c 已登记 tools/layers.json；没有新增 src/*.h。

实现提交：`84d59833620b57bb31e3e7739e3cfb8996b2d5ef`。Draft PR：[NoGod3524/EXReader#96](https://github.com/NoGod3524/EXReader/pull/96)。
