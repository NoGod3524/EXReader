# 2a 第 5 步验收（2026-11-06）

> 2026-11-10 更新：旧 17 控件界面已移除，包含其布局、101–117 消息入口及返回旧面板路径。下文涉及旧控件、phase-a/b/c、旧无障碍证据与 `--debug-ui` 的描述仅为历史；[归档及清单](archive/legacy-17-control/README.md)。当前产品仅使用新界面。

**本轮已通过：字号首行锚点已修复，最终 `check_step5.py` exit=0，八项全绿。100/800 页两处六档 12/12、指定跳档循环 8/8，固定字号拉丁 Sample 12 张 client 图像均 0 px。详见 [本轮修复报告](2A-STEP5-ANCHOR-FIX.md)。**

下文保留 `3096ca7f` 上轮原始记录及失败证据；当前结论以上方本轮报告为准。

浮层、DeckMark 令牌、主题、字号档位和持久化已实现。当前重排沿用原有“定位到包含锚点的页面”逻辑；该页的首行可以早于锚点。首页 offset=0 的测试通过，不能替代非首页测试。

**八项数字验收**

| # | 验收 | 实测 |
| --- | --- | --- |
| 1 | 截图 bg / surface | 浅色 #f5f5f2 / #ffffff；深色 #141416 / #1e1e21；四项 RGB 误差均 0 |
| 2 | 步进器、分段控件五态 | 2 主题 × 3 变体 × 5 状态 = 30 组，填色/文字/描边/焦点与令牌合成值误差均 0；逐项表在下方 |
| 3 | 系统关闭动画 | 展开 0.000000 ms，收起 0.000000 ms；无动画定时器，最终高度在点击处理内同步设置 |
| 4 | 正文 WCAG 对比度 | 浅色 15.717976:1；深色 16.455895:1；均 ≥12:1 |
| 5 | 空白帧 | 深色 presented=144，blank=0；全程 presented=177，blank=0 |
| 6 | 重启设置 | ShellFont 28→28；ShellTheme 1→1；系统模式 2→2；完整 INI 在下方 |
| 7 | --self-test | exit=0，checks=26，SDK 3.42.0 |
| 8 | 旧 UI client 像素 | 原始 phase-a/b/c 的 8 张图：基线自对照 0 px，本次对基线 0 px；负例检出 1 px（alpha 不变），仅标题栏变化的 client 差异 0 |

**首行失败证据**

| 字号 | 首行 UTF-8 偏移 | 与原首行一致 |
| --- | --- | --- |
| 17（第 4 页） | 4331 | 基准 |
| 18 | 2899 | 否 |
| 20 | 3934 | 否 |
| 22 | 3522 | 否 |
| 24 | 3313 | 否 |
| 28 | 3589 | 否 |
| 32 | 4140 | 否 |

6/6 次非首页步进未保持首行。原锚点仍落在新页面范围内；本次没有实现把锚点固定到可见首行的连续视口。第 5 步保持 Draft，不能据首页测试标记完成。

**测量方法**

- 共监测 25 次 GUI 宿主进程；可见顶层窗位置全部为 (-32000,-32000)，每 20 ms 检查前台所属 PID，前台观察数 0。没有执行 SetForegroundWindow、BringWindowToTop、SendInput 或鼠标移动。所有子进程使用 CREATE_NO_WINDOW。
- 图像由 PrintWindow 取得。重叠的浮层 HWND 单独 PrintWindow 后按原坐标合成，避免父窗递归打印时被正文兄弟窗覆盖；没有桌面截屏后备路径。阴影透明区读取宿主自己的正文缓冲。
- normal/hover/pressed/disabled 经 HWND 的驱动消息；focus 的颜色验收直接注入绘制焦点标志。它验证焦点像素，不验证真实键盘焦点取得；全程不激活窗口。
- 关闭系统动画时记录的 0 ms 是有效过渡时长：同步到达最终状态，不把绘制函数的 CPU 用时称为 0。恢复系统动画后配置 180 ms；QPC 测得展开 180.7693 ms、收起 182.8705 ms，包含 Win32 定时器派发延迟。系统原设置在 finally 中恢复。
- 对比度使用截图中出现的正文实心像素与页面背景，按 WCAG sRGB 线性化公式计算。glyph 边缘的抗锯齿像素不作正文主色。
- 原始 phase-a/b/c：基线、基线复跑、本次均仅 A 第 115 步、B 第 5 步两个既有失败（issue #45），C 为 0；新增失败 0。
- 构建：MinGW Release，shell_d2d.cpp 经过 -Wall -Wextra -Werror；基线与本次都开启 SHELL 宏，--drive 保持旧布局。基线取 7b20c5a0，仅补 uiautomationcore 链接库使独立消费者可链接。SDK、字体、样书、二进制 SHA-256 见 metadata.json。

**五态逐项取色**

表中“实测/期望”两值相同；期望由权威令牌的 RGB/alpha 在所在 surface 上合成，逐通道四舍五入。primary 是选中主题段；ghost 是未选主题段。pressed 保持 hover 填色并下移 .5px，disabled 整体 opacity .4。

| 主题 | 控件 | 状态 | 填色（实测/期望） | 文字（实测/期望） | 描边（实测/期望） | 焦点（实测/期望） |
| --- | --- | --- | --- | --- | --- | --- |
| light | stepper | normal | #ffffff / #ffffff | #1b1b1f / #1b1b1f | #e0e0e2 / #e0e0e2 | — |
| light | stepper | hover | #efeeea / #efeeea | #1b1b1f / #1b1b1f | #d3d2d0 / #d3d2d0 | — |
| light | stepper | pressed | #efeeea / #efeeea | #1b1b1f / #1b1b1f | #d3d2d0 / #d3d2d0 | — |
| light | stepper | focus | #ffffff / #ffffff | #1b1b1f / #1b1b1f | #e0e0e2 / #e0e0e2 | #4553e0 / #4553e0 |
| light | stepper | disabled | #ffffff / #ffffff | #a4a4a5 / #a4a4a5 | #f3f3f3 / #f3f3f3 | — |
| light | ghost | normal | #ffffff / #ffffff | #5c5c65 / #5c5c65 | — | — |
| light | ghost | hover | #efeeea / #efeeea | #5c5c65 / #5c5c65 | — | — |
| light | ghost | pressed | #efeeea / #efeeea | #5c5c65 / #5c5c65 | — | — |
| light | ghost | focus | #ffffff / #ffffff | #5c5c65 / #5c5c65 | — | #4553e0 / #4553e0 |
| light | ghost | disabled | #ffffff / #ffffff | #bebec1 / #bebec1 | — | — |
| light | primary | normal | #4553e0 / #4553e0 | #ffffff / #ffffff | — | — |
| light | primary | hover | #3946cc / #3946cc | #ffffff / #ffffff | — | — |
| light | primary | pressed | #3946cc / #3946cc | #ffffff / #ffffff | — | — |
| light | primary | focus | #4553e0 / #4553e0 | #ffffff / #ffffff | — | #4553e0 / #4553e0 |
| light | primary | disabled | #b5baf3 / #b5baf3 | #ffffff / #ffffff | — | — |
| dark | stepper | normal | #1e1e21 / #1e1e21 | #f2f2f4 / #f2f2f4 | #3b3b3e / #3b3b3e | — |
| dark | stepper | hover | #28282c / #28282c | #f2f2f4 / #f2f2f4 | #444447 / #444447 | — |
| dark | stepper | pressed | #28282c / #28282c | #f2f2f4 / #f2f2f4 | #444447 / #444447 | — |
| dark | stepper | focus | #1e1e21 / #1e1e21 | #f2f2f4 / #f2f2f4 | #3b3b3e / #3b3b3e | #7c88ff / #7c88ff |
| dark | stepper | disabled | #1e1e21 / #1e1e21 | #737375 / #737375 | #2a2a2d / #2a2a2d | — |
| dark | ghost | normal | #1e1e21 / #1e1e21 | #b3b3bc / #b3b3bc | — | — |
| dark | ghost | hover | #28282c / #28282c | #b3b3bc / #b3b3bc | — | — |
| dark | ghost | pressed | #28282c / #28282c | #b3b3bc / #b3b3bc | — | — |
| dark | ghost | focus | #1e1e21 / #1e1e21 | #b3b3bc / #b3b3bc | — | #7c88ff / #7c88ff |
| dark | ghost | disabled | #1e1e21 / #1e1e21 | #5a5a5f / #5a5a5f | — | — |
| dark | primary | normal | #7c88ff / #7c88ff | #ffffff / #ffffff | — | — |
| dark | primary | hover | #929cff / #929cff | #ffffff / #ffffff | — | — |
| dark | primary | pressed | #929cff / #929cff | #ffffff / #ffffff | — | — |
| dark | primary | focus | #7c88ff / #7c88ff | #ffffff / #ffffff | — | #7c88ff / #7c88ff |
| dark | primary | disabled | #44487a / #44487a | #78787a / #78787a | — | — |

**host.ini 重启前**

```ini
[Host]
ShellTheme=1
ShellFont=28
FontPercent=150
ZoomPercent=100
WindowWidth=1298
WindowHeight=847
ActiveBook=1
```

**host.ini 重启后**

```ini
[Host]
ShellTheme=1
ShellFont=28
FontPercent=150
ZoomPercent=100
WindowWidth=1298
WindowHeight=847
ActiveBook=1
```

**旧 INI 兼容**

输入只有 FontPercent、ZoomPercent、WindowWidth、WindowHeight、ActiveBook，没有新键；启动 exit=0，默认字号 17、主题 2。

书架数据库启动前后 SHA-256 同为 `eaf6a3fb1657743aa0adc6908a40d520a09fa236468d03fc230a8e96160642f6`；SQLite 完整逻辑导出也一致。输入/输出分别为 record/legacy-before.ini、record/legacy-after.ini。

**令牌替换对照**

| 项 | 旧值 | DeckMark 新值 |
| --- | --- | --- |
| 浅色 page / side / float | #FFFFFF / #F7F7F8 / #FFFFFF | #f5f5f2 / #ffffff / #ffffff |
| 深色 page / side / float | #121316 / #191A1D / #222327 | #141416 / #1e1e21 / #1e1e21 |
| text（浅/深） | #1D1D1F / #E8E8EA | #1b1b1f / #f2f2f4 |
| text-2（浅/深） | #6E6E73 / #A1A1A6 | #5c5c65 / #b3b3bc |
| text-3（浅/深） | #AEAEB2 / #5C5D63 | #8b8b94 / #7d7d87；disabled 另按 opacity .4 |
| accent（浅/深） | #1A73E8 / #1A73E8 | #4553e0 / #7c88ff |
| hover | accent 6% 叠加 | surface-2 #efeeea / #28282c；primary #3946cc / #929cff |
| pressed | accent 12% 叠加 | hover 填色 + translateY(.5px) |
| 顶栏线（浅/深） | #F0F0F0 / #202124 | line .075，bg 上合成 #e4e4e2 / #262627 |
| 控件描边 | 无 | line-strong .13，surface 上合成 #e0e0e2 / #3b3b3e |
| 控件 / 面板 / 大容器圆角 | 8 / 14 / 10（旧集合 8/10/14） | 9 / 14 / 18 |
| 控件高 / 内边距 / 字重 | 32 / 16 / 400 | 34 / 14 / 550 |
| 阴影 | 0 2px 8px rgba(0,0,0,.08) | shadow-sm / md / lg / page-shadow 逐值见快照与 shell_tokens.h |
| 曲线 | cubic-bezier(0,0,.2,1) | cubic-bezier(.2,.8,.2,1) |
| 界面字体 | Segoe UI Variable / Segoe UI | SF Pro Text / Segoe UI Variable Text / Segoe UI / PingFang SC / Microsoft YaHei UI / Microsoft YaHei |

新增 surface-2、surface-3、desk、accent-hover、accent-soft、accent-softer 及四组阴影均逐值定义于 shell_tokens.h；权威文件字节快照与 SHA-256 在 record/DECKMARK-TOKENS.md 和 metadata.json。

**改动文件**

- examples/reader.c：设置读取/写入、主题显示映射、类背景画刷、命令与驱动消息、PrintWindow 浮层合成、帧探针。
- examples/windows/shell_tokens.h：集中 DeckMark 色值、alpha、字体栈、圆角、阴影、曲线、控件尺寸与字号档位。
- examples/windows/shell_d2d.cpp、shell_d2d.h：控件与面板绘制、缓存模糊阴影、原生 surface 背景合成。
- examples/windows/shell_screen.inc、新增 shell_settings.inc：浮层 HWND、命中/悬停/焦点、动画、主题与字号入口。
- examples/windows/shell_measure.inc：设置、控件坐标、类背景、动画与窗口位置证据。
- examples/CMakeLists.txt、examples/windows/CMakeLists.txt：advapi32 与 uiautomationcore 链接。
- docs/ui/UI-SPEC-20261104.md、HOST-AUDIT-20261104.md：DeckMark 覆盖规格；本验收文档、acceptance/check_step5.py、check_step5_legacy.py 与 evidence/2a-step5-20261106/。

**复跑**

```powershell
cmake -S examples/windows -B docs/ui/acceptance/.build-step5 -G "MinGW Makefiles" -DEXR_SDK=C:/Users/Oscar/Documents/Codex/exr-paint-sdk -DEXR_READER_WINDOWS_SHELL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build docs/ui/acceptance/.build-step5 --parallel 4
python docs/ui/acceptance/check_step5.py <新 EXReader.exe> <7b20c5a0 基线 EXReader.exe> <Reader.otf> docs/ui/evidence/2a-step5-20261106/record/Long-acceptance.epub <输出目录>
python docs/ui/acceptance/check_step5_legacy.py <新 EXReader.exe> <同一基线> <Reader.otf> docs/ui/evidence/2a-step5-20261106/record/Long-acceptance.epub <输出目录>
```

第一条验收脚本预期整体 exit=1，原因是保存的非首页首行反例。第二条整体 exit=0，要求原有 phase 失败集合完全一致且 8 张 client 图像差异为 0。未手动启动 CI；没有取消 workflow run。
