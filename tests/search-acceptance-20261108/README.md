全文搜索验收 · 2026-11-08

A）引擎在 `include/exr/layout.h` / `src/publication.c` 新增 `exr_publication_search` 和 `exr_publication_search_all`，沿用 SDK 的 status / output / error / control 调用约定。起点是 `{part, offset}`；结果为 `{found, part, offset, length}`，后两项均是 part 内标准化 UTF-8 字节范围。按目录顺序搜索 linear parts，跳过辅助文件，枚举重叠命中；单个匹配不拼接两个文件。未命中 found=0、part/offset=SIZE_MAX。空词、非法 UTF-8、未知 flags 明确报错，失败/取消清空计数。回调可提前停止。

结果可以直接建立 `exr_anchor_create(doc, offset, offset+length, ...)`；定位使用 `exr_target {part,NULL,offset}` → `exr_publication_locate`。现有 `exr_document_locate` 的实参是 fragment 字符串，保持其 ABI，通过 publication 的数字 target 路径接入同一偏移体系。

中文按 Unicode 码点匹配，不分词。分词可以减少子串噪声、支持词级索引，但需要词典，对人名/古文和歧义切分会改变召回；本轮保留可预测的子串语义。全词选项以空白/标点为边界，汉字/kana 为独立单位。竖排沿用逻辑文本顺序，不转换视觉顺序。

默认大小写折叠仅 A–Z、À–Ö、Ø–Þ；其他码点原样比较，包括 ß、希腊字母、土耳其字母，不做 Unicode 规范化。该范围是一对一、UTF-8 字节长度不变的映射，匹配范围可直接落回原文；扩展到完整 Unicode 折叠时，需要处理多码点展开及其源偏移映射。测试包含 Latin-1、补充平面汉字、emoji 和不折叠的反例。

B）顶栏新增 32×32 DIP、r9 放大镜，沿用既有 hover / focus / DPI 绘制。选择顶栏下 48 DIP 的搜索栏，将正文下推，使命中文字不被栏遮挡。原生输入框支持中文输入；200ms 防抖、大小写/全词选项、“第 N / 共 M 个”、Enter 下一个、Shift+Enter 上一个、Esc 关闭、Ctrl+F 打开。当前命中使用 `--accent-soft`（#4553e0 / .10），其余命中使用 `--accent-softer`（.06）；重叠区域去重，字形簇、竖排列和 PDF quad 都使用原文范围。展开栏改变视口高度并触发既有重排；19 本回归固定视口条件比较。

搜索使用独立线程和独立 SQL 原书快照，原有 UI/pager 不参与全文扫描；新输入取消旧请求并丢弃过期结果。缓存标准化文本，不建立分词库或 SQLite FTS。EPUB 搜索快照复用宿主的 presentation 转换，确保其偏移与屏幕正文相同；旧整书导入、MOBI 和 PDF 也已接入。PDF 空白页生成空投影，连续空白保留从搜索投影到原始文本区域的映射。

C）KMP 按码点线性扫描；查询前缀表只建立一次。part 文本首次解析后缓存，publication_free 时释放。缓存是 publication 生命周期内的不可变搜索快照；可变 provider 更新正文后重新打开 publication。

| 验收 | 数字与证据 |
| --- | --- |
| 1. 三书五词 | 15/15：引擎、独立 Python 重叠 find、逐条上下文核对一致，见 [search.json](search.json)。紅樓夢：賈寶玉18、女媧氏1、Gutenberg98、24264两次、2021一次；A Raisin：Brustein4、Nemiroff10、Les Blancs5、1994两次、80744一次；草枕：夏目漱石5、Natsume1、Sadder1、75891一次、0213一次。 |
| 2. 命中位置 | 真书抽样20/20，均通过 publication_locate、锚点往返、目标页范围与实际 glyph 检查；其中6个竖排。额外合成测试20/20（10个竖排）。 |
| 3. flags | 大小写3/3：Cat=1、CAFÉ=1、É=2；全词3/3：cat=4、café=2、2026=1；另验证两个 flags 组合。详见 test_document_search.c / flags 组。 |
| 4. 紅樓夢三轮 | 本轮同配置1,686页。冷查询（新 publication、含正文解析、计数、清理前返回）：“的”88.6829 / 93.1476 / 86.0308ms，中位88.6829ms，13,989命中；“賈寶玉”117.0394 / 92.8251 / 84.8753ms，中位92.8251ms，18命中。缓存查询中位4.4362 / 19.6073ms。均小于200ms；冷指搜索文本缓存为空，不清空操作系统文件缓存。 |
| 5. 连续十字符 | 实际输入“一二三四五六七八九十”，首字输入到结果701.432ms（包含输入间隔、200ms防抖及结果投递）；实际搜索1次、2.870ms；十次输入处理合计41.3885ms、最长4.8961ms。见 [ui.json](ui.json)。 |
| 6. 窗口截图 | [搜索展开/当前1](expanded-current.png)、[当前2与其他命中](next-current.png)、[竖排](vertical-current.png)。全部使用 ops/capture_window.py，120 DPI、物理客户区1280×800。宿主六组6/6，含 PDF 612命中与 MOBI 9命中。 |
| 7. 19本回归 | 19/19，11,296页、8,648,640字形；前后页数和逐页像素 SHA-256 相同，变化页0。见 [比较](realbooks.diff.json)、[基线](realbooks-before.json.gz)、[候选](realbooks-after.json.gz)。 |
| 8. ctest | 203/203，115.22秒；191常规基线 + 7既有 fuzz + 5新增 search 组（basic/unicode/flags/errors/mapping）。新测试还通过 C11 -Wall -Wextra -Wpedantic -Werror 编译。见 [ctest.txt](ctest.txt)。 |

`search.json` 保留15项计数、20项偏移/页/字形及原始三轮计时；`ui-*.txt` 保留六组真实窗口驱动日志；`build.json` 保留基线提交、编译配置、SDK/宿主/字体哈希与实现源码的 Git LF 字节哈希。原书和展开正文不入库。

复现（仓库根目录，MinGW / Windows）：

```powershell
$cfg = (Get-Content tests/search-acceptance-20261108/build.json -Raw | ConvertFrom-Json).configuration
$args1 = @('-S','.', '-B','build/search', '-G','Ninja')
$cfg.PSObject.Properties | ForEach-Object { $args1 += "-D$($_.Name)=$($_.Value)" }
cmake @args1
cmake --build build/search --parallel 6
ctest --test-dir build/search --output-on-failure -j 6
python -X utf8 tests/check_document_search.py build/search/libexreader.dll build/search/search-acceptance.json
# 用任务书中的三条编译命令编译 reader.c/shell_d2d.cpp/shell_epub.cpp，
# 最后链接 -Lbuild/search 及该目录的 expat/miniz，并把 DLL 放在 EXE 旁。
python -X utf8 examples/windows/check_shell_search.py out/EXReader.exe C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Reader.otf build/ui-replay
```

19 本复跑使用 `tools/regress/run_realbooks.py`、`tools/regress/corpus.json`、`tools/regress/layout.json` 与同一 Reader.otf；命令及原件身份见仓库现有 docs/REGRESSION.md 和压缩原始报告。根 CMakeLists.txt 仅新增测试注册；未改 .github/。
