# 2a 第 6 步：最小目录面板验收

已实现并通过离屏验收。基线为 main `8ee4bd6b`，包含 PR #67 的封面适配与焦点修复。新行为：顶栏目录按钮打开左侧覆盖面板，章节跳转在新页绘制后收起；正文尺寸与分页不变。

| # | 用户验收 | 实测 |
| --- | --- | --- |
| 1 | 面板几何与令牌 | 宽 **280px**、行高 **34px**、文字 x=**20px**；右侧 **1px** 发丝线。浅/深色各测两书；RGB 误差 **0**。正文打开前后逐像素差异 **0px**。 |
| 2 | 选中态 | 竖条 **2px**；浅 #4553e0 / 深 #7c88ff，行底 #f4f5fd / #262835；RGB 误差 **0**；字重 **600**。选中按下态 #eceefc / #2d2f45 同样色差 **0**。 |
| 3 | 滚动条 | 常态、悬停均 **5px**（x=271–275），半圆端点，透明轨道；常态 #e0e0e2，悬停 #8b8b94。真实 **1,169** 项目录、**90** 次列表绘制，滚动 p95 **2.2448ms**。 |
| 4 | 真书章节点击 | 紅樓夢 **5/5** 不同章节；Pachinko **5/5** 不同行；莎士比亚全集补测 **5/5**，合计 **15/15**。原始 EPUB 保持不变。 |
| 5 | 空状态 | 既有 complex-text.epub 无目录；文案“这本书没有目录”，DirectWrite 实测 **16px / 650**，条目数 **0**。 |
| 6 | 键盘 | 两书分别 ↑、↓、Enter、Esc **4/4**；Tab **4/4**，顺序为目录→设置→列表→正文→目录；Shift+Tab **1/1**。方向键不翻页、不改变章节选中竖条。 |
| 7 | 空白帧与 UIA | 两书各翻 **20** 页；空白帧 **0**（主验收分别呈现 328 / 333 帧）。关闭时真实 UIA 可操作元素恰为 **3**；打开时列表报告完整 **1,169** 项。 |
| 8 | 回归 | 既有 **8/8**；旧控件五态 **30/30**；字号首行锚点 **12/12**；封面/焦点浅深 **4/4** 张与 main 客户区差异 **0px**，旧界面 **8** 张差异 **0px**；self-test **26/26**。 |
| 9 | 出图 | 必需 **4** 张及补充 **6** 张，见 [证据目录](evidence/2a-step6/README.md)。 |

19 个 GUI 验收进程，前台观察数 **0**，窗口位置均为 (-32000,-32000)。抓图前声明 PMv2 DPI 感知，使用 PrintWindow；没有桌面截屏后备路径。整窗 PNG 为 1298×838，实际客户区为 1280×800，client_box=[9,38,1280,800]；取色和几何均按客户区坐标。系统实际 DPI 120，像素规格验收使用宿主支持的 96 DPI 注入。其他 DPI 实测 120/144/192：面板宽 350/420/560，行高 43/51/68，打开时分页构建增量均 **0**。

动画配置 **180ms**、cubic-bezier(.2,.8,.2,1)，仅水平位移，不使用透明度。全程 135 个曲线样本，最大偏移误差 **0.0806px**；完整过渡实测 181.8209–194.1875ms，中途反向通过。关闭系统动画后时长 **0ms**、中间帧 **0**，系统设置在 finally 中恢复。点击外部不翻页，面板外滚轮保持面板打开并翻书；繁忙时的章节点击完成排队跳转。互斥设置面板、Alt+Left 返回旧面板均通过。

固定 34px 行高直接换算 scrollY 与行号。只绘制可见区及缓冲行，在本次 1280×800 下最多 22 行；省略结果按需缓存，位图缓存上限 64 行（96 DPI 约 2.2MiB），宽度/DPI 改变时清空。原生 owner-draw ListBox 保存完整标题和完整条目数，保留 UIA 列表代理及一个 Tab 停靠点。列表采用 GDI 行缓存，头部/空状态沿用既有 DirectWrite；没有新增依赖。

原文件《紅樓夢》的 NCX 只有 Gutenberg 许可证一项，无法直接抽五章。实现按原始解码文本中的回目恢复 **108** 项，并将原文回目匹配到 SDK 规范化内容偏移；EPUB 分割处的重复回目取后一个。没有改写书本、补造章节或生成验收 EPUB。其他有可用目录的书直接沿用原生导航。Pachinko 的章节目录指向作者制作的图片章扉，验收同时核对原 NCX、spine 路径及已呈现的图片位置。

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
cmake -S examples/windows -B examples/windows/.build-msvc -G "Visual Studio 17 2022" -A x64 -DEXR_SDK=C:/Users/Oscar/Documents/Codex/exr-paint-sdk -DEXR_READER_WINDOWS_SHELL=ON
cmake --build examples/windows/.build-msvc --config Release --parallel 4
python -X utf8 docs/ui/acceptance/check_toc_panel.py <EXE> <main基线EXE> <Reader.otf> <紅樓夢.epub> <Pachinko.epub> <原始莎士比亚全集.epub> <输出目录>
python -X utf8 docs/ui/acceptance/check_step6_regression.py <EXE> <main基线EXE> <Reader.otf> <紅樓夢.epub> <真实Malcolm-X.pdf> <Pachinko.epub> <输出目录>
python -X utf8 docs/ui/acceptance/check_step6_motion.py <EXE> <Reader.otf> <原始莎士比亚全集.epub> <输出目录>
python -X utf8 docs/ui/acceptance/check_step6_uia.py <EXE> <Reader.otf> <原始莎士比亚全集.epub> <输出目录>
```

[机器结果、进程记录与原始测量包](evidence/2a-step6/record/)。所有新增改动限于 examples/ 与 docs/ui/；未手动启动 CI，未取消 workflow run。
