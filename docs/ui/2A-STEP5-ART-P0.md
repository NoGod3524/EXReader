# 第 5 步：已批准美术 P0 六项

本轮只改 `examples/` 与 `docs/ui/`；MSVC 的 `NOMINMAX` 修复保持。`check_art_p0.py`、最终 `check_step5.py`、原 phase-a/b/c 对照及两个无窗口检查均 exit=0。既有八项与字号六档 12/12 无回退。

| P0 | 实测结果（DPI 96） |
| --- | --- |
| 1 中文行高 | 18 px → 32 px；17 px → 30 px；竖排列距 32 px。拉丁 18 px → 28.800001 px。按正文 Unicode 字符判断；反向语言标签的中西文同章测试通过。 |
| 2 顶栏 | 浅 #ffffff、深 #1e1e21；正文 #f5f5f2 / #141416；RGB 误差均 0。高 56 px；1 px 发丝线仍为 --line（叠在 surface 上为 #ededee / #2f2f32）。 |
| 3 图标按钮 | 可见 32×32 px；圆角拟合 9 px；间距 6 px；右边距 12 px；字形宽 18 px。描边绘制值 1.5 px，像素覆盖积分浅 1.503067 / 深 1.496644 px。焦点环宽 2 px、offset 2 px、r11；热区 40×40 px。 |
| 4 书名 | DirectWrite 实际 15 px / 650；绘制原点 x=20；字符间距 −0.15 px，即 −0.01em；单行超长省略。 |
| 5 设置浮层 | 360×172 px，r14；1 px --line 描边，浅 #ededee / 深 #2f2f32；--shadow-lg。内边距上/下/左/右均 20 px。轨道浅 #efeeea / 深 #28282c，r9 / 1px 线 / padding 3；选中底 #ffffff / #1e1e21，r6 + --shadow-sm，RGB 误差 0。分段高 26，左右 padding 12；字号步进 34×34；读数 13/550/tabular；标题 12/550，距控件 8，两节相隔 16 px。 |
| 6 中文段落 | 可见首字缩进 36 px；标题、居中段、引文块之后三例均通过；同章拉丁缩进 0 px。中文段距 9 px，拉丁 14.399981 px。原文已有两枚全角空格时仍为 36 px，原文偏移不变。 |

图标五态实测（底 / 字形；焦点列为浅 / 深）：

| 状态 | 浅色 | 深色 | 焦点环 |
| --- | --- | --- | --- |
| normal | #ffffff / #5c5c65 | #1e1e21 / #b3b3bc | — / — |
| hover | #efeeea / #1b1b1f | #28282c / #f2f2f4 | — / — |
| pressed | #e7e6e1 / #1b1b1f | #313136 / #f2f2f4 | — / — |
| focus | #ffffff / #5c5c65 | #1e1e21 / #b3b3bc | #4553e0 / #7c88ff |
| disabled | #ffffff / #bebec1 | #1e1e21 / #5a5a5f | — / — |

正文截图：

- [紅樓夢横排 1280×800](evidence/2a-step5-art/horizontal-1280.png)，2 个真实段落。
- [紅樓夢横排 2560×1440](evidence/2a-step5-art/horizontal-2560.png)，5 个真实段落；两种横排正文框均宽 612 px。
- [紅樓夢竖排 1280×800](evidence/2a-step5-art/vertical-1280.png)，2 个真实段落；正文框高 592→592 px，有效列高 556→556 px，列距 32 px。竖排只增 writing-mode CSS，正文一致。

指定原件 SHA-256：`325fef5fb561a258ee4e0ded25821a55d77f7b4b627ae0ecac03410802ea6ec7`。出图定位到 part 15，`OEBPS/2878037014660817796_24264-0-16.txt.html`，开头为“接著林之孝家的同著几個老婆子來”。测试 profile 直接定位该正文，不改原 EPUB。原件全文有 。7041、，52580、左双引号“9648、右双引号”6923；**「及」均为 0**。因此三张图保留该版本原有引号，无法提供原件不存在的「」；此处的引号字形条件待 owner 确认。独立夹具中的「」只检验数值，不作为 c 节标点/行末的验收依据。本轮未改 P1 的两端对齐、行末标点、页码、版心或封面规则。

宿主给实际 CJK 段落加阅读样式类，有界分页器不变。独立 XML/ZIP 核对：38 个条目中 30 个仅添加样式类；正文、节点及其他属性变化 0，ZIP CRC 错误 0。拉丁段落按自身字符恢复 1.6 / 0.8em；测试特意反置 lang 标签。

| 既有验收 | 本轮最终结果 |
| --- | --- |
| 浅/深正文与 surface | #f5f5f2 / #ffffff；#141416 / #1e1e21；色差 0 |
| 控件五态 | 30/30；采用本轮批准的分段控件色值；填色、文字、边框、焦点色差 0 |
| 系统关闭动画 | 展开/收起 0.000000 ms |
| 正文对比度 | 15.717976:1 / 16.455895:1 |
| 空白帧 | 深色 0/153，全程 0/186 |
| INI | 字号 28→28；主题 1→1；跟随系统 2→2；旧 INI 默认 17/2，书架 SHA-256 不变 |
| self-test | exit=0，checks=26，SDK 3.42.0 |
| 旧界面 client | 原 phase-a/b/c 的 8 张图：基线复跑 0 px、本轮对照 0 px；负例检出 1 px |

原 phase-a/b/c 的 A-115、B-5 两个既有失败在基线、复跑、本轮一致，新增失败 0。快捷旧界面 8 图对照同样为 0 px；其重启截图先 wait_idle，消除启动恢复未结束就抓图的时序差异。

字号锚点六档 **12/12**（另指定跳档循环 8/8、准备回切 2/2）：

| 字号 | 100 页处 source_start | 页号 | 800 页处 source_start | 页号 |
| --- | --- | --- | --- | --- |
| 17->18 | 154739→154739 | 100→104 | 1248825→1248825 | 800→838 |
| 18->20 | 154739→154739 | 104→115 | 1248825→1248825 | 838→926 |
| 20->22 | 154739→154739 | 115→129 | 1248825→1248825 | 926→1035 |
| 22->24 | 154739→154739 | 129→139 | 1248825→1248825 | 1035→1116 |
| 24->28 | 154739→154739 | 139→176 | 1248825→1248825 | 1116→1413 |
| 28->32 | 154739→154739 | 176→185 | 1248825→1248825 | 1413→1487 |

无 HWND 的 document / TXT / document-vertical 实际 JOB_LAYOUT 共 21/21，锚定后续读 3/3。最终证据中 32 个 GUI 子进程均在 (-32000,-32000)，前台观察 0，截图均用 PrintWindow。未手动运行 CI 或取消 workflow。

[逐项机器结果、40 张状态图、INI、构建/输入哈希与压缩原始测量](evidence/2a-step5-art/README.md)。

复跑（独立 MSVC consumer 构建）：

```powershell
cmake -S examples/windows -B docs/ui/acceptance/.build-art-release -G "Visual Studio 17 2022" -A x64 -DEXR_SDK=C:/Users/Oscar/Documents/Codex/exr-paint-sdk -DEXR_READER_WINDOWS_SHELL=ON
cmake --build docs/ui/acceptance/.build-art-release --config Release --target EXReader check_shell_epub check_shell_anchor
python docs/ui/acceptance/check_art_p0.py <EXE> <Reader.otf> <hongloumeng-24264.epub> <OUT>
python docs/ui/acceptance/check_step5.py <EXE> <7b20c5a0基线EXE> <Reader.otf> <Long-acceptance.epub> <OUT>
python docs/ui/acceptance/check_step5_legacy.py <EXE> <3096ca7f基线EXE> <Reader.otf> <Long-acceptance.epub> <OUT>
```
