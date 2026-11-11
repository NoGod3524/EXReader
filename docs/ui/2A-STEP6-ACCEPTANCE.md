# 2a 第 6 步：最小目录面板验收

> 2026-11-10 更新：旧 17 控件界面已移除，包含其布局、101–117 消息入口及返回旧面板路径。下文涉及旧控件、phase-a/b/c、旧无障碍证据与 `--debug-ui` 的描述仅为历史；[归档及清单](archive/legacy-17-control/README.md)。当前产品仅使用新界面。

修复 DirectWrite getter 编译错误后，重新构建并完成以下离屏验收。基线为 main `8ee4bd6b`，包含 PR #67 的封面适配与焦点修复。新行为：顶栏目录按钮打开左侧覆盖面板，章节跳转在新页绘制后收起；正文尺寸与分页不变。

| # | 用户验收 | 实测 |
| --- | --- | --- |
| 1 | 面板几何与令牌 | 宽 **280px**、行高 **34px**、文字 x=**20px**；右侧 **1px** 发丝线。浅/深色各测两书；RGB 误差 **0**。正文打开前后逐像素差异 **0px**。 |
| 2 | 选中态 | 竖条 **2px**；浅 #4553e0 / 深 #7c88ff，行底 #f4f5fd / #262835；RGB 误差 **0**；字重 **600**。选中按下态 #eceefc / #2d2f45 同样色差 **0**。 |
| 3 | 滚动条 | 常态、悬停均 **5px**（x=271–275），半圆端点，透明轨道；常态 #e0e0e2，悬停 #8b8b94。真实 **1,169** 项目录、**90** 次列表绘制，滚动 p95 **2.7404ms**（门槛 ≤4ms）。 |
| 4 | 真书章节点击 | 紅樓夢 **5/5** 不同章节；Pachinko **5/5** 不同行；莎士比亚全集补测 **5/5**，合计 **15/15**。原始 EPUB 保持不变。 |
| 5 | 空状态 | 既有 complex-text.epub 无目录；文案“这本书没有目录”，DirectWrite 实测 **16px / 650**，条目数 **0**。 |
| 6 | 键盘 | 两书分别 ↑、↓、Enter、Esc **4/4**；Tab **4/4**，顺序为目录→设置→列表→正文→目录；Shift+Tab **1/1**。方向键不翻页、不改变章节选中竖条。 |
| 7 | 空白帧与 UIA | 两书各翻 **20** 页；空白帧 **0**（主验收分别呈现 331 / 330 帧）。关闭时真实 UIA 可操作元素恰为 **3**；打开时列表报告完整 **1,169** 项。 |
| 8 | 回归 | 既有 **8/8**；旧控件五态 **30/30**；字号首行锚点 **12/12**；封面/焦点浅深 **4/4** 张与 main 客户区差异 **0px**，旧界面 **8** 张差异 **0px**；self-test **26/26**。 |
| 9 | 出图 | 必需 **4** 张及补充 **6** 张，见 [证据目录](evidence/2a-step6/README.md)。 |

**本次修复与测量来源**

选择 **A**：从创建 layout 时使用的同一个局部 `IDWriteTextFormat *format` 读取 `GetFontSize()` / `GetFontWeight()`。本实现没有 `s->toc_format` 成员；在 `CreateTextLayout` 成功后、`format->Release()` 前记录读数。layout 没有按文本范围覆盖字号或字重，因此无需 B 的位置与输出参数。

修复前同一条 MinGW 命令复现两个 getter 错误；修复后 **MinGW g++ 16.2.0** 的 `-std=c++17 -Wall -Wextra -Werror -c` 返回 **0**，MSVC Release（该文件 `/W4 /WX`）构建返回 **0**。[命令、退出码与输出](evidence/2a-step6/record/build.json)。重测 EXE SHA-256：`6ed28acccddb5b04209cd953d1f4396e8a96c8df891b3202c57da2d6bc42d603`；[元数据](evidence/2a-step6/record/metadata.json) 同时记录被测源码 SHA-256。

| 报告值 | 源码里的值与读取链 | 本轮核验 |
| --- | --- | --- |
| 面板宽 280px | `shell_toc.inc::shell_toc_width()` 的 `shell_px(280,shell_dpi)`，受客户区宽度约束；`shell_measure.inc::shell_toc_measure()` 写入 `width` | 96 DPI、1280×800 两书均为 280；截图 x=279 的边线和 x≥280 的背景另做像素断言。不是 `toc_metrics`。 |
| 行高 34px | `shell_toc.inc::shell_toc_row_h()` 的 `shell_px(34,shell_dpi)`，同时供 `LB_SETITEMHEIGHT`、绘制和测量使用 | 两书均为 34；截图按 34px 行距取选中/悬停/按下态。不是 `toc_metrics`。 |
| 文字 x=20px | `shell_toc_measure()` 输出 `shell_px(20,shell_dpi)`；绘制为 list 左侧 10px 加 `shell_d2d_toc_row()` 内 `round(20*k)-round(10*k)` | 此项是布局起点，不是文字墨迹左缘的截图测量。 |
| 选中行 14px / 600 | `shell_d2d.cpp::shell_d2d_toc_row()` 创建 GDI 字体，选中时 `GetObjectW(...,LOGFONTW)` 取 `-lfHeight/lfWeight`，写 `toc_metrics[2:4]`，再输出 `typography[2:4]` | 两书浅/深四组均断言 `[14,600]`；这条链不经过错误的 layout getter。 |
| 空状态 16px / 650 | `shell_toc.inc::shell_toc_proc()` 的空状态调用参数 `row=-3,size=16,weight=650`；修复后 `format->GetFontSize()/GetFontWeight()` 写 `toc_metrics[0:2]`，再输出 `typography[0:2]` | 新构建的 `empty/empty.json` 为 `[16.000,650,0.000,0]`；脚本断言前两项 `[16,650]`。JSON 的 `empty_font/empty_weight` 是另两个硬编码说明字段，未用作实测依据。 |
| 边线 1px、竖条 2px、滑块 5px、RGB 误差 0 | `check_toc_panel.py` 读取 PrintWindow PNG 的客户区像素；滑块实际列 `[271,272,273,274,275]` | 两书浅深像素断言及长目录常态/悬停断言通过。 |

原提交无法从该源码编译，上轮二进制和报告不能验证这一版本的 getter；本轮以新编译 EXE 的结果替换当前证据。上轮 JSON 保存在 [previous/](evidence/2a-step6/record/previous/)，供逐项对照。

**九项与上轮对照**

| # | 上轮 → 本轮 | 变化说明 |
| --- | --- | --- |
| 1 | 280 / 34 / 20 / 1px，RGB 误差 0，正文差异 0px → 相同 | 无变化；来源见上表。 |
| 2 | 2px / 600、RGB 误差 0 → 相同 | 无变化；增加两书浅深四组 GDI 14/600 断言。 |
| 3 | 5/5px，1,169 项，90 次绘制，p95 2.2448ms → 5/5px，1,169 项，90 次绘制，p95 2.7404ms | p95 增加 0.4956ms，低于 4ms 门槛。此路径使用 GDI，getter 修复只改空状态诊断读数，无法把本次计时差归因于它。 |
| 4 | 5/5 + 5/5 + 5/5 = 15/15 → 相同 | 章节 part、offset 与上轮全部一致。 |
| 5 | 0 项，16/650 → 相同 | 数字不变；本轮由修复后格式对象重新读取并通过断言。 |
| 6 | 两书各键盘 4/4、Tab 4/4、Shift+Tab 1/1 → 相同 | 无变化。 |
| 7 | 各翻 20 页，空白 0，UIA 关闭 3 / 打开 1,169；呈现 328/333 → 同样各翻 20 页、空白 0、UIA 3/1,169；呈现 331/330 | 呈现帧数分别 +3/-3，随消息与动画调度变化；空白帧和可操作元素数不变。 |
| 8 | 8/8、30/30、12/12、4/4、26/26；旧图 8 张/差异 0 → 相同 | 无回退；首行锚点仍为 7977/38339。 |
| 9 | 必需 4 + 补充 6 张 → 相同 | 全部由新 EXE 重出图并重打包。 |

补充测量变化：动画样本 **135→134**，最大曲线误差 **0.0806→0.0563px**，完整过渡范围 **181.8209–194.1875→181.8328–196.5403ms**。回归套件呈现帧仍为 **93**。成功套件仍 **19** 个 GUI 进程，含首次动画失败尝试共 **20** 个。计时/帧数为各次采样结果；本次修复没有改变绘制格式、动画或分页参数。首次动画失败和复测记录均在原始测量包中。

成功验收包含 19 个 GUI 进程；加上首次动画断言失败的 1 个进程，本轮共 **20** 个，前台观察数均为 **0**，窗口位置均为 (-32000,-32000)。抓图前声明 PMv2 DPI 感知，使用 PrintWindow；没有桌面截屏后备路径。整窗 PNG 为 1298×838，实际客户区为 1280×800，client_box=[9,38,1280,800]；取色和几何均按客户区坐标。系统实际 DPI 120，像素规格验收使用宿主支持的 96 DPI 注入。其他 DPI 实测 120/144/192：面板宽 350/420/560，行高 43/51/68，打开时分页构建增量均 **0**。

动画配置 **180ms**、cubic-bezier(.2,.8,.2,1)，仅水平位移，不使用透明度。复测全程 **134** 个曲线样本，最大偏移误差 **0.0563px**；完整过渡实测 **181.8328–196.5403ms**，中途反向通过。首次有一条 180ms 过渡实测 **197.897ms**，超过现有 ±17ms 断言 **0.897ms**；保留该次原始 CSV、日志和断言，未改阈值，完整复测通过。关闭系统动画后时长 **0ms**、中间帧 **0**，系统设置在 finally 中恢复。点击外部不翻页，面板外滚轮保持面板打开并翻书；繁忙时的章节点击完成排队跳转。互斥设置面板、Alt+Left 返回旧面板均通过。

固定 34px 行高直接换算 scrollY 与行号。只绘制可见区及缓冲行，在本次 1280×800 下最多 22 行；省略结果按需缓存，位图缓存上限 64 行（96 DPI 约 2.2MiB），宽度/DPI 改变时清空。原生 owner-draw ListBox 保存完整标题和完整条目数，保留 UIA 列表代理及一个 Tab 停靠点。列表采用 GDI 行缓存，头部/空状态沿用既有 DirectWrite；没有新增依赖。

原文件《紅樓夢》的 NCX 只有 Gutenberg 许可证一项，无法直接抽五章。实现按原始解码文本中的回目恢复 **108** 项，并将原文回目匹配到 SDK 规范化内容偏移；EPUB 分割处的重复回目取后一个。没有改写书本、补造章节或生成验收 EPUB。其他有可用目录的书直接沿用原生导航。Pachinko 的章节目录指向作者制作的图片章扉，验收同时核对原 NCX、spine 路径及已呈现的图片位置。

**原文回目恢复的判定规则**

对应 `examples/windows/shell_toc.inc` 的 `shell_toc_load()` / `shell_toc_recover_chapters()`：

1. 原生导航读取成功后，统计 `role == "toc"` 的项。仅当项数为 **0 或 1** 且 `g.session.bounded` 为真（分章 publication）才尝试恢复；多于 1 项直接使用原生导航。当前代码按数量判定，不按许可证关键词判定；因此单个正常导航项也会进入尝试。
2. 按 publication 顺序扫描 `in_reading_order` 的 part，只检查有有效 `start` 偏移的 `EXR_NODE_TEXT`。按换行分行，跳过行首 ASCII 空白/控制字符（字节值 ≤32）和全角空格 U+3000。
3. 候选行至少 **9 个 UTF-8 字节**，必须以“第”开头；在距开头 **40 字节以内**寻找“回”。“回”之后必须是行尾、ASCII 空白/控制字符或全角空格。当前实现不额外校验“第…回”之间是否为中文数字，也不以 HTML heading 标签或文件名推断章节。
4. 必须在该文本节点的 SDK 规范化内容范围内匹配到从“第”至“回”的完整前缀，才记录 `part + offset`；失败即跳过。若该行只有回次（可带 CR），可追加下一行不足 **180 字节**的标题，中间跳过空白、`-` 和 `—`；标签中的 ASCII 空白和横线归并为空格，保留 UTF-8 字符边界。
5. 相同“第…回”前缀重复出现时删除较早一项，保留较晚落点，以处理 EPUB 分割处重复回目。累计至少 **5 项**才整体替换导航；不足 5 项释放候选并保留原生结果。导航读取失败显示“目录无法读取”，不进入恢复；零项且恢复不足时显示空状态。

本次指定紅樓夢满足“1 个原生 toc 项 + 分章 publication”，最终恢复 **108 项**；章节点击另对照未改写 EPUB 中的原文回目核验。

字号锚点使用原始紅樓夢的两处非首页正文（页 5 / 20），六档 18/20/22/24/28/32 的首行内容偏移分别保持 **7977 / 38339**，同时核对实际 glyph 与文本前缀。原 26 项 self-test 要求第一页必须有文字，故用 Project Gutenberg 完整原始 TXT 版紅樓夢及真实 Malcolm X PDF；源 URL 与 SHA-256 写入机器报告。除用户明确允许的空状态已有夹具外，全部输入均为真书。

**章节落点（零基行号，精确内容偏移）**

| 书 | 行 | part | 偏移 | 结果 |
| --- | ---: | ---: | ---: | --- |
| 紅樓夢 | 0 | 1 | 762 | 通过 |
| 紅樓夢 | 2 | 1 | 42749 | 通过 |
| 紅樓夢 | 8 | 2 | 86298 | 通过 |
| 紅樓夢 | 20 | 6 | 27746 | 通过 |
| 紅樓夢 | 1 | 1 | 24608 | 通过 |
| Pachinko | 6 | 9 | 0 | 通过 |
| Pachinko | 17 | 31 | 0 | 通过 |
| Pachinko | 28 | 53 | 0 | 通过 |
| Pachinko | 42 | 81 | 0 | 通过 |
| Pachinko | 7 | 11 | 0 | 通过 |
| Shakespeare | 10 | 6 | 10499 | 通过 |
| Shakespeare | 250 | 49 | 6 | 通过 |
| Shakespeare | 550 | 115 | 14636 | 通过 |
| Shakespeare | 900 | 193 | 6393 | 通过 |
| Shakespeare | 1100 | 240 | 10925 | 通过 |

**建议同步规格**

1. §1.7 的表、§6 线框/汇总、§7 第 6 项仍写 4/8px，与用户明确决策及该节开头的 DeckMark 实测冲突；统一为常态/悬停 **5px**、x=271–275，取消加宽动画，只改颜色。
2. 补充“目录缺失或只有版权导航时，从原文明确回目恢复目录”的规则；指定紅樓夢正是此例。当前实现保留原文顺序，以规范化内容锚点定位。

**复跑**

```powershell
g++ -std=c++17 -Wall -Wextra -Werror -c examples/windows/shell_d2d.cpp -o examples/windows/.build-msvc/shell_d2d-mingw.o
cmake -S examples/windows -B examples/windows/.build-msvc -G "Visual Studio 17 2022" -A x64 -DEXR_SDK=C:/Users/Oscar/Documents/Codex/exr-paint-sdk -DEXR_READER_WINDOWS_SHELL=ON
cmake --build examples/windows/.build-msvc --config Release --parallel 4
python -X utf8 docs/ui/acceptance/check_toc_panel.py <EXE> <main基线EXE> <Reader.otf> <紅樓夢.epub> <Pachinko.epub> <原始莎士比亚全集.epub> <输出目录>
python -X utf8 docs/ui/acceptance/check_step6_regression.py <EXE> <main基线EXE> <Reader.otf> <紅樓夢.epub> <真实Malcolm-X.pdf> <Pachinko.epub> <输出目录>
python -X utf8 docs/ui/acceptance/check_step6_motion.py <EXE> <Reader.otf> <原始莎士比亚全集.epub> <输出目录>
python -X utf8 docs/ui/acceptance/check_step6_uia.py <EXE> <Reader.otf> <原始莎士比亚全集.epub> <输出目录>
```

[机器结果、进程记录与原始测量包](evidence/2a-step6/record/)。所有新增改动限于 examples/ 与 docs/ui/；未手动启动 CI，未取消 workflow run。
