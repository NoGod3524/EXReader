# 2a 第 4 步宿主复测

实现基线：`7b20c5a0`。分支：`codex/ui-2a-step4-20261106`。

**六项中 5 项通过；第 2 项时延未通过，第 4 步尚未验收通过。** 最终运行器退出 1；自检子进程退出 0。结果已回写 [HOST-AUDIT §F](../../HOST-AUDIT-20261104.md#f5-第-4-步宿主复测2026-11-06)。

| 硬判据 | 1280×800 新屏 | 2560×1440 新屏 | 旧面板对照 |
| --- | --- | --- | --- |
| 空白帧 / 实际提交帧 | **0 / 183** | **0 / 182** | **0 / 74** |
| 未命中排版 + 渲染 p95（本 PR 自测） | 25.1427 ms | 47.9864 ms | 不设本项门槛 |
| **独立复核（2026-11-06，verifier 会话）** | **22.46 / 23.88 ms（两轮，均 ≤ 25 ✅）** | **51.81 / 54.54 ms（两轮，均 > 35 ❌）** | 1280 档原报"超标"属噪声；2560 档超标稳定且更严重 |

> 复核说明：1280×800 的 25.1427 ms 未被复现（两轮均低于门槛），不应据此判 1280 档超标；
> 2560×1440 超标成立且实测更差。空白帧计数是宿主自埋计数器的定义，暂缓绘制（每轮 7–8 次）
> 与系统擦除背景不计入其中。
| 未命中样本数 | 59 | 59 | — |
| 缓存命中次数 | 20 | 20 | 20 |
| 命中排版增量 / 渲染增量 | **0 / 0**（20 次各自均为 0） | **0 / 0**（20 次各自均为 0） | **0 / 0** |
| 尺寸恢复 / 忙时恢复正文像素差 | **0 / 0** | **0 / 0** | — |
| 旧尺寸提交 / 提交失败 | **0 / 0** | **0 / 0** | **0 / 0** |
| 位图→缓冲 BitBlt 次数 | 173 | 172 | 74 |
| StretchDIBits 次数（含显示缓存准备） | **0** | **0** | 53（保留原缩放路径） |
| 等待新尺寸帧而暂缓提交 | 8 | 7 | 0 |

第 6 项：`selftest/report.json` 为 `passed=true, checks=26, engine_version=3.42.0`，`selftest/process.json` 为 `exit=0`。

实现沿用四帧缓存、原预取策略和已合入的后备缓冲。缓存帧保留已准备的 display bitmap；新屏 1:1 数据复制后用 BitBlt 合成和提交，移除直接 DIB 提交的回退。新屏排版几何与实时窗口不符时暂缓绘制，任务完成后重新合成；后备缓冲尺寸也在 WM_PAINT 入口复核。探针的 `has_page` 来自实际合成成功结果，提交使用缓冲自己的 generation，避免把正在生产的帧当作已显示帧。

机器为 Core Ultra 7 256V / 16 GB / Windows 11。宿主与 SDK 均为 MinGW GCC/G++ 16.2.0 Release；SDK 构建源码 `e3dc6099` 的 `src/`、`include/` 与基线相同，未修改 SDK。SDK 可选图像/加密功能的开关保留在 `build.json`；本输入无图、无加密。字体来自交付包 Reader.otf。完整二进制、字体和输入哈希见 [result.json](result.json)。

原生桌面 DPI=120，离屏发送 WM_DPICHANGED 注入 96 DPI，字号 18 DIP；客户区为物理 1280×800、2560×1440，页面为 612×624、612×1264。使用默认进程优先级，未设置 CPU 亲和性或改变桌面设置。

三个场景均发送 PageDown 20 次、滚轮 100 格。测试书沿用 PR #43 的 `make_epub(path,3,163840,single_paragraph=True)`，生成的原文件为 [Long-acceptance.epub](Long-acceptance.epub)。新屏另连续发送 60 次单页请求，不关闭预取；只对实际光栅化且无 frame-cache hit 的任务采样。首个请求命中预取，余下各 59 个样本全部保留，包含章节切换及长尾。每个任务先相加 `stage_anchor_pager_ms + stage_raster_ms`，再按 `ceil(n*0.95)-1` 取 p95。没有以两个阶段的 p95 相加代替联合 p95。

排版总调用数分别为 **8→304 / 8→343 / 2→87**；渲染为 **5→162 / 5→155 / 2→55**。这些是整个区间的累计值；各次缓存命中都单独记录 `cache_layout_delta=0, cache_render_delta=0`。排版调用包括宿主的 pager_get 和 positioned-layout 创建，TXT / 固定页的渲染入口也接入渲染计数器。

每次成功提交均记录客户区与缓冲宽高，以及页面与目标排版宽高，运行器逐帧比较。尺寸往返为原尺寸→720×560→2560×1440→原尺寸；另在 delay=700 ms 的忙任务中连续改尺寸再恢复。首行、源范围和正文像素均恢复。原始 `before/restored/busy-restored.json` 保留文字和 line/glyph 数据；对应 PNG 由 PrintWindow 取得，比较范围是实际正文位图。两档源范围分别保持 `[95637,97084)`、`[163185,163840)`。

所有主窗口均创建于 **(-32000,-32000)**，带 WS_EX_NOACTIVATE；运行器以 PMv2 读取物理窗口坐标，每 20 ms 检查前台 PID。三组及自检的前台观察均为 **0**。没有调用 SetForegroundWindow、BringWindowToTop 或移动鼠标，所有子进程使用 CREATE_NO_WINDOW。重排等待期的暂缓绘制不计为已提交帧；系统 blit 前的背景擦除仍按 §G5 留给第 5 步的窗口类背景色处理。

复跑入口（Windows，输出目录必须不存在）：

```powershell
python docs/ui/acceptance/check_step4.py EXReader.exe Reader.otf SAMPLE_DIR NEW_OUTPUT
```

`SAMPLE_DIR` 须包含自检原样使用的 Sample.epub、Sample.pdf。宿主由 `examples/windows/CMakeLists.txt` 开宏构建；MinGW 的 UIA 链接补充见 `build.json`。运行器只使用 --offscreen 和 PrintWindow；超出时延门槛时仍完成其他项目，然后以非零退出。

`shell-1280/`、`shell-2560/`、`legacy/` 保存未裁减的 paint.csv、drive.tsv、驱动脚本、进程记录及结果。每组还用真实日志构造四个负例，分别把 total_presented 改为 0、total_blank 改为 1、cache_layout_delta 改为 1、缓冲宽改为 -1；四种均被判定器拒绝，结果保存在各组 JSON。没有手动运行 CI。

<!-- required checks rerun 2026-11-06 -->

