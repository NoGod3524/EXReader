# A3 RTL 段落级验证（2026-11-09 任务）

三本自造书与带受控附录的希伯来真书派生版均 **6/6**；未修改的真书单独保留 **210 页**及截图，不给不存在的拉丁混排场景编造结论。修复前同一组受控样本均 4/6，失败项为末行对齐和书籍翻页方向。

## 语料与页数

[Gutenberg 阿拉伯语目录](https://www.gutenberg.org/browse/languages/ar)仅列出 Tribute to Michael Hart。尝试下载 Hindawi 的[كليلة ودِمنة](https://www.hindawi.org/books/29061736/)与[الأيام](https://www.hindawi.org/books/62042949/)的 EPUB，均返回 Cloudflare 验证页。按任务允许的后备方案，生成两本阿拉伯语、一本希伯来语原创测试书。它们有完整 EPUB3 包、两章 spine、导航及跨页段落，使用自造文本，**不等于已出版真书**。

另外下载 [Knut Hamsun《Hunger: Book One》，Elhanan Segal 希伯来译本，PG #18291](https://www.gutenberg.org/ebooks/18291)。原书没有 RTL 段内拉丁词组；`hunger-probed` 在其末尾添加明确标题“EXReader ORIGINAL CONTROLLED TEST APPENDIX”的自造测试章，用于可复现的六项检查。原书内容成员字节不变，只改 OPF 并增补一个 XHTML。原版与派生版 SHA256 及差异见 corpus.json / hunger-probed.provenance.json。

已逐页核对：派生版前210页与未改原书的210页像素SHA256完全相同，新增附录3页。

固定测量：720×720，页边距36，Arial 26px，行高1.3，书内CSS开启、嵌入字体关闭。**仅计 `in_reading_order` 的 spine 页面**；导航及非线性封面不计。每本页数均为完整分页结果。19 本历史回归继续使用原脚本既有口径，不更改基线。

| 书籍 | 性质 | 页数 | 至少两张实际渲染截图 |
|---|---|---:|---|
| arabic-journey | original test book | 4 | [PNG 1](arabic-journey-000.png), [PNG 2](arabic-journey-001.png) |
| arabic-library | original test book | 4 | [PNG 1](arabic-library-000.png), [PNG 2](arabic-library-001.png) |
| hebrew-journey | original test book | 4 | [PNG 1](hebrew-journey-000.png), [PNG 2](hebrew-journey-001.png) |
| hunger | real book | 210 | [PNG 1](hunger-011.png), [PNG 2](hunger-012.png) |
| hunger-probed | real book + original controlled appendix | 213 | [PNG 1](hunger-probed-011.png), [PNG 2](hunger-probed-012.png) |

派生版附录另有 [PNG](hunger-probed-appendix.png)。本次提供11张最终截图。

## 六项逐本结论及证据

第5项按 [CSS Text 3 text-align-last:auto](https://www.w3.org/TR/css-text-3/#text-align-last-property)判定：普通行两端贴齐，RTL短末行及强制换行前一行向右起始端对齐，**左侧留白**。不会把 RTL 末行改成向左对齐。第3项按 [Unicode 17 UAX #9 L4](https://www.unicode.org/reports/tr9/tr9-51.html#L4)：`()`、`[]`、`«»` 在奇数级别选择镜像字形；直引号及 `“”` 没有 Bidi_Mirroring_Glyph，不人为交换。

| 书籍/版本 | 1 段落方向 | 2 数字嵌入 | 3 标点镜像 | 4 双向混排 | 5 行末对齐 | 6 默认下一页在左 | 合计 |
|---|---|---|---|---|---|---|---:|
| arabic-journey | 通过 | 通过 | 通过 | 通过 | 通过 | 通过 | 6/6 |
| arabic-library | 通过 | 通过 | 通过 | 通过 | 通过 | 通过 | 6/6 |
| hebrew-journey | 通过 | 通过 | 通过 | 通过 | 通过 | 通过 | 6/6 |
| hunger-probed | 通过 | 通过 | 通过 | 通过 | 通过 | 通过 | 6/6 |

未改原书 `hunger` 用于真实内容分页及视觉验证；没有把原书中不存在的第4项当作已测。表内 `hunger-probed` 的六项位置来自标记附录，正文来源仍是真书。三本自造书已独立满足后备方案，派生真书作为额外验证。

`assessment-after.json` 每项记录页号、行号、源偏移、字形级别及实际x坐标；`render-after.json.gz` 保留全部行/字形与逐页像素SHA256，页号从0开始。判定不只检查码点覆盖：

1. 纯 RTL 段的可见字母源偏移随物理x递增而递减；右边界=684px。
2. `0123456789`、`2026`、`12.34` 的字形x单调增加、级别为偶数，内部顺序不反转。
3. 对每枚括号、引号检查实际 glyph ID；独立 HarfBuzz 14.6.0 的同字体 cmap 提供期望字形。硬编码期望镜像对独立于引擎的镜像表。
4. `OpenAI Reader ABC xyz` 在 RTL 段内保持从左向右的词组顺序；另测 RTL 书内显式LTR整段。
5. 第一行24px右缩进时右边界=660px；普通两端对齐行左右=36/684px；短末行右边界=684px。阿拉伯样本1末行由 x=36,width=67 改为 x=617,width=67，边界误差为 684-(36+67)=581px，修后0px。
6. OPF显式RTL/LTR优先；缺省/default按主语言子标签决定（本次原书he→RTL），不倒置spine数组。原生 Windows 实际 WM_KEYDOWN：三个RTL样本 左→第2页/右→第1页；显式LTR对照 右→第2页/左→第1页。见 host-after*.txt；修复前相同检查三个RTL全失败、LTR通过。用户已保存的翻页偏好仍可覆盖默认。

独立cmap对照和完整双向算法的分工不同：cmap核对镜像输出，原有 Unicode 17 bidi conformance 验证段落算法；本次没有以cmap命中替代坐标、顺序及翻页验证。

## 失败定位与修复

| 修复前失败 | 层/具体函数 | 根因与修复 | 定量结果 |
|---|---|---|---|
| #5 RTL两端对齐短末行 | 布局/绘制前定位：`src/flow.c:exr_flow_emit_line()` | `align==3` 在 final/forced 行停止拉伸后仍从左边缘放置；仅对RTL的这些行及语义标题回到start/right。整形及bidi重排不改。 | ar1边界误差581px→0；ar2 588px→0；he 360px→0 |
| #6 EPUB默认翻页 | 格式元数据：`src/formats.c:package_start()/epub_metadata()/exr_epub_load()`；传递：`src/publication.c:publication_index()`、`chapter_window.c`/`chapter_reader.c`；宿主：`examples/reader.c:page_procedure()` | 原代码未读取OPF spine方向，公共API无法查询；默认左右键恒定LTR。保留独立书籍方向，新增document/publication查询，传到普通及有界章视图，宿主物理左右键消费该值。PageUp/PageDown及逻辑next仍按阅读顺序。 | 三个RTL宿主反例FAIL→PASS；显式LTR保持PASS |

没有未解决的六项失败。#1–#4 原本通过，保留算法，以新测试锁定实际输出。无新增 `src/*.h`；现有内部头新增字段，层检查119对象/1354符号引用、0新逆向依赖。

## 回归与测试

- 修复前基线 `03ccf53e`，独立冻结的DLL；相同19本书、Reader.otf、tools/regress/layout.json。
- **19/19、11,318页、8,648,571字形；页数/字形数/逐页像素SHA256变化全部为0**。见 books-before/after.json.gz、books.diff.json。
- **MSVC Release + fuzz完整ctest 262/262全绿，79.74秒**，包括sdk-release。见 ctest-msvc.txt。
- 新增5组、225检查：native-rtl-paragraph(54)、numbers(39)、punctuation(36)、mixed(56)、progression(40)。原有native-bidi另通过861,948个Unicode17用例、24,401,500次检查。见rtl-focused.txt。
- MinGW完整测试261/262；唯一sdk-release以MSVC README命令链接MinGW包的 .dll.a，缺少exreader.lib（LNK1181）。未修改断言或包装工具来掩盖它；另用完整MSVC构建验证Windows发行包及全部262项通过。RTL测量、19书哈希和宿主按键使用同一MinGW候选DLL。
- 原生宿主测试使用当前源码；修复前反例使用03ccf53e的宿主，仅注入同样的probe_key参数支持，未注入方向修复。
- 新C测试起初用了旧EXR_HTML文本解析器，发现其按既有设计丢弃CSS/属性；测试夹具改为真实EPUB DOM加载，没有放宽任何坐标/顺序断言。

## 复跑

```powershell
python tests/rtl_verify.py generate tests/fixtures/rtl
# 以项目CMake正常构建；本次两个构建均启用EXR_BUILD_FUZZ=ON。完整配置、工具链与依赖缓存记录在provenance.json。
cmake --build build --parallel 6
ctest --test-dir build-msvc --output-on-failure -j 4
Invoke-WebRequest https://www.gutenberg.org/ebooks/18291.epub3.images -OutFile build/rtl-corpus/hunger.epub
python tests/rtl_verify.py probe build/rtl-corpus/hunger.epub tests/fixtures/rtl/hebrew-journey.epub build/rtl-corpus/hunger-probed.epub
python tests/rtl_verify.py render --dll build/libexreader.dll --font C:/Windows/Fonts/arial.ttf --output build/rtl-after --source-revision YOUR_REVISION tests/fixtures/rtl/arabic-journey.epub tests/fixtures/rtl/arabic-library.epub tests/fixtures/rtl/hebrew-journey.epub build/rtl-corpus/hunger.epub build/rtl-corpus/hunger-probed.epub
python tests/rtl_verify.py assess build/rtl-after/render.json C:/Windows/Fonts/arial.ttf build/rtl-after/assessment.json
python tests/check_rtl_host.py --binary build/rtl-reader.exe --output build/rtl-host-final
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/libexreader.dll --font C:/Users/Oscar/exr-deps/reader-font/Reader.otf --layout tools/regress/layout.json --output build/books-after.json --baseline build/books-before.json --source-revision YOUR_REVISION --workers 4
```

原生Windows宿主按项目examples目标构建，或本次使用的MinGW直连命令：`gcc -O2 -mwindows examples/reader.c -Iinclude -Ibuild/generated/include -Lbuild -lexreader -lcomdlg32 -lgdi32 -luiautomationcore -lshell32 -lole32 -loleaut32 -luuid -lm -o build/rtl-reader.exe`。宿主脚本自带90秒超时并将窗口放在屏外。

Python评估使用已安装的uharfbuzz，仅作独立验收oracle；引擎没有新增依赖。真书、第三方字体、DLL不入库；原始与派生EPUB哈希、字体/DLL哈希和逐文件证据哈希见provenance.json。
