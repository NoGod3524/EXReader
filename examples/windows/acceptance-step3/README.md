2a 第 3 步：物理像素重排与 Per-Monitor V2（2026-11-06）

基线 `4519bd5b`；分支 `codex/ui-2a-step3-20261105`。实现、脚本和证据只改 `examples/`。根目录未提交的 STEP3-PLAN.md / STEP3-PLAN-OUT.txt 保留原状。未运行 CI。

实现文件：

- `examples/reader.c`：UI 线程布局快照；打开书/重排统一配置；原尺寸 DIB 复制与固定页按目标矩形渲染；DPI 消息合并；代次/缓存校验；字号独立于旧 FontPercent；`--offscreen` 和专用驱动动作。
- `examples/windows/shell_geometry.h`、`shell_tokens.h`：DIP→px、34em 上限、可用空间优先、零内边距、1.6 行距、0.8em 段距；竖排沿页高限长并保留 48 DIP 上下空白。
- `examples/windows/shell_screen.inc`：控件按 DPI 换算；150ms 合并；保留最初页首内容锚点直到导航离开其源范围；忙时保留最新请求；恢复旧布局时补足旧工具栏最小窗口；页码合成。
- `examples/windows/shell_d2d.h`、`shell_d2d.cpp`：按宿主 DPI 重建文字资源，HWND/DC target 仍固定 96 dpi；页码样式和 target DPI 查询。
- `examples/windows/shell_measure.inc`：从已接受帧导出源范围、实际 line/glyph 浮点几何、DPI、显示尺寸、比例、布局代次和 pager 构建次数。
- `examples/windows/check_shell_geometry.c`、`check_step3.py`、`summarize_step3.py`：几何断言、离屏驱动、像素负例、矩阵/锚点/选择检查、源字符与基线量测。
- 本目录：结果 JSON、对照组离屏适配补丁、3 张受控中文样本客户区 PNG 和本说明。

实测环境：Windows，浅色，MinGW GCC/G++ 16.2.0，Release，SDK 3.42.0。桌面原生 DPI 为 120（125%）。`SetProcessDpiAwarenessContext(-4)` 返回 1，错误码 0；实际窗口 context 为 PMv2，`GetDpiForWindow=120`。96 / 144 DPI 通过离屏 `WM_DPICHANGED` 注入；120 DPI 场景同时匹配原生窗口 DPI。下表的尺寸均为 GetClientRect 实测物理 px。注入场景不作为真实跨显示器证据。

正文取自固定种子生成的 100000 字中文长段；全部为 Han，按 line 的源 UTF-8 范围解码后计 Unicode 字符，包含符号时按源字符计一次，未数 glyph/字节。有效正文行/列占其行内轴可用长度至少 90%，排除隐藏/生成字形及字号不同的内容；每场景 20 个不同正文页。行距用同 node、同字号相邻行的实际 glyph 基线差 / glyph.size；竖排使用列间 x 差。PNG 仅复核原点、像素尺寸与留白。

| 横排客户区 / 有效 DPI | 页像素 | 有效行 | 字数中位 / p5–p95 | 正文左右最小边距 px | 实测行高比 | scale |
| --- | --- | --- | --- | --- | --- | --- |
| 1280×800 / 96 | 612×624 | 420 | 34 / 34–34 | 334 / 334 | 1.599999 | 1.000 |
| 2560×1440 / 96 | 612×1264 | 860 | 34 / 34–34 | 974 / 974 | 1.599999 | 1.000 |
| 1920×1080 / 120 | 765×860 | 460 | 33 / 33–33 | 577 / 584 | 1.600000 | 1.000 |
| 2560×1440 / 144 | 918×1176 | 540 | 34 / 34–34 | 821 / 821 | 1.600000 | 1.000 |

均显式 f=18 DIP；字号像素依次为 18、18、22.5、27；段距分别为 14.4、14.4、18、21.6 px。margin=0，配置 line_height=1.6；所有样本显示缓存像素尺寸与 SDK bitmap 相同，两个 target 的 x/y DPI 四项全为 96.0。几何左右边距分别为 334/334、974/974、577/578、821/821 px；125% 的满行实际宽 759 px（765 px 版心），因此实际文字右边距为 584 px。

| 竖排客户区 / 有效 DPI | 页像素 | 有效列 | 每列字符中位 / p5–p95 | 实际上/下最小边距 px | 实际左右最小边距 px |
| --- | --- | --- | --- | --- | --- |
| 1280×800 / 96 | 612×592 | 420 | 32 / 32–32 | 104 / 120 | 341.200 / 334.000 |
| 2560×1440 / 96 | 612×612 | 420 | 34 / 34–34 | 104 / 724 | 981.200 / 974.000 |
| 1920×1080 / 120 | 765×765 | 420 | 33 / 33–33 | 130 / 191 | 586.000 / 578.000 |
| 2560×1440 / 144 | 918×918 | 420 | 34 / 34–34 | 156 / 366 | 831.800 / 821.000 |

受控样本使用标准 `writing-mode:vertical-rl`，实际 SDK mode=1，正文带 `EXR_GLYPH_VERTICAL`，源范围递增时列 x 递减；计数沿页高完成。列间距/字号实测约 1.599999–1.600000，scale 全为 1.000。这里的列距不作为竖向字符步距。

96 DPI 客户区高度 800、每点 20 页的横排诊断矩阵（列为 f DIP，表内为实际源字符中位数）：

| 客户区宽 | 14 | 17 | 18 | 24 | 32 |
| --- | --- | --- | --- | --- | --- |
| 1280 | 34 | 34 | 34 | 34 | 34 |
| 1000 | 34 | 34 | 34 | 34 | 28 |
| 999 | 34 | 34 | 34 | 34 | 28 |
| 720 | 34 | 34 | 34 | 26 | 19 |

20 点均显示 scale=1.000、版心两侧 ≥48 px、行高比在容差内。720 / f=32 的可用宽仅 624 px，按窄窗规则得到 19 字；没有缩小字号。另测拉丁正文 20 页，中位 69、p5–p95=66–72。

布局调度与内容保持：

- 1280→1000 同高且已达 34em 上限，横/竖排 pager 构建次数均 3→3；重复 f=18，均 5→5。
- 请求后保持最初内容锚点，尺寸往返、延迟 700ms 的忙 worker 连续 resize、DPI 往返和 shell 进出后，横排源范围恢复 `[14994,17136)`，竖排 `[14112,16128)`；页首全文逐字节相等。
- 120→144 DPI 每次只增加 1 次 pager 构建；所有最终接受帧 epoch 与目标相等。零尺寸几何不生成任务；最小化保持既有帧；失败布局代次不自动无限重试。
- 回旧面板恢复 720×1040、旧默认字号 42 px（150%），17 个控件可达；1000 px 窄 shell 退出后先补足旧面板最小外框宽 1060，避免 ID117 在客户区外。
- 横/竖排都实测留白点击不产生选区、跨行/列鼠标选择、复制、添加标注后跳回恢复同一源范围。普通 HTML 的源范围与文本往返相等；PDF 原尺寸贴图为 483×624→405×524、scale=1.000，未按流式字符数判定。

旧界面严格像素比对在原生 125% 桌面执行。基线取 4519bd5b、宏关闭，仅应用本目录 baseline-offscreen.patch；同样的离屏适配用于新构建。二进制依次放同一 stable/EXReader.exe 路径，数据目录每组重置到同一路径，A→B→C 连续执行。每张用 GetClientRect/ClientToScreen 的真实完整客户区裁切（本环境 x=9,y=38），无遮罩、无容差、RGBA 任一通道不同即计一像素。8 张图全部存在。

| 比对组 | 8 张 client_diffpx |
| --- | --- |
| 基线 off1 / off2 对照组 | 0,0,0,0,0,0,0,0 |
| 基线 off1 / 本步宏关闭 | 0,0,0,0,0,0,0,0 |
| 基线 off1 / 本步开宏保持旧布局 | 0,0,0,0,0,0,0,0 |
| 真实客户区只改 R 一级，alpha 不变 | 1，比较失败 |
| 只改客户区外一个像素 | 0 |

首轮有一张状态栏尾部差 470 px，未记作通过；离屏截图前双方统一 RedrawWindow 全量重绘后，上表的完整四组重跑得到 0。首次离屏尺寸测试受系统默认最大跟踪尺寸限制，未用于最终 2560×1440 数据；离屏模式放开上限后重新读取真实 client 并重测。

四个构建组的 phase-a/b/c 都是 A 119/120（只 A115 失败）、B 28/29（只 B5 失败）、C 9/9，共 2 个既有失败，无新增。自检退出码 0、checks 恰好 26。独立几何断言退出码 0；shell_d2d.cpp 本机 `-std=c++17 -Wall -Wextra -Werror` 编译退出码 0。

未达标或未覆盖：

- **原生 150% 与真实跨显示器 DPI 变化未验证**；144 DPI 结果是受控消息路径，原生窗口仍报告 120 DPI。96 DPI 同样为受控路径。没有改变用户桌面缩放设置。
- 原版《草枕》SHA-256 为 `6d4d4ed5eda3f612e3263c54fa0f74ccfa87260f43e81bb58ea658636e52eeb7`，当前 SDK 实测 mode=0、vertical glyphs=0；其 `-epub-writing-mode` 别名兼容性未通过。本步只改宿主，受控标准 CSS 竖排通过；没有复制、修改或提交原书。
- 本机未构建 MSVC、TXT 产品专用宏组合；未做真实前台键盘/焦点验收，未运行 CI。

所有运行窗口均创建于 (-32000,-32000)，WS_EX_NOACTIVATE + SW_SHOWNOACTIVATE；离屏模式阻止 SetFocus 激活、拒绝 activate/key_tab/probe_resize，禁止截图失败后截桌面。截图只用 PrintWindow。运行器持续检查进程是否成为 foreground，累计观察值 0。**是否出现过前台窗口：否。**

复跑入口（输出目录必须新建）：

```powershell
gcc -std=c11 -Wall -Wextra -Werror examples/windows/check_shell_geometry.c -o examples/windows/build/check_shell_geometry.exe
examples/windows/build/check_shell_geometry.exe
python examples/windows/check_step3.py EXE FONT NEW_OUTPUT
python examples/windows/summarize_step3.py NEW_OUTPUT
python examples/windows/check_step3.py --stress EXE FONT NEW_OUTPUT
python examples/windows/check_step3.py --selection EXE FONT NEW_OUTPUT
python examples/windows/check_step3.py --matrix EXE FONT NEW_OUTPUT
python examples/windows/check_step3.py --phases BASELINE_OFF STEP3_OFF STEP3_ON FONT SAMPLE_DIR NEW_OUTPUT
```

构建沿用 examples/windows/CMakeLists.txt，`-DEXR_SDK=<prefix> -DEXR_READER_WINDOWS_SHELL=ON -DCMAKE_BUILD_TYPE=Release`。本地旧 SDK 的导出链接集缺 UIA，基线和新构建均额外使用 C/CXX_STANDARD_LIBRARIES 中的 `-luiautomationcore -lole32 -loleaut32 -luuid` 和既有 Win32 库；没有修改 CMake 文件。基线离屏补丁用 `git apply --unidiff-zero` 应用到 4519bd5b 源码副本，必须沿用其 windows_accessibility.inc。详细原始日志、逐页 line/glyph、客户区矩形与截图在本工作区 `examples/windows/build/`，提交的 results.json 保存汇总、样本/SDK/字体/各阶段二进制 SHA-256。

`results.json` 的 layout_exe 是主矩阵和 phase 像素组所用构建，release_exe 另外验证了窄 shell 返回旧面板的最小尺寸修复；该最后修复只在 shell_leave 执行，phase 保持旧布局不会调用。两阶段均保留其二进制哈希。固定页和最新锚点往返用 release_exe 验证。
