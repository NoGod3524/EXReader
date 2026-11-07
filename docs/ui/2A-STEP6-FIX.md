# 两处窗口视觉修复（2026-11-07）

根因定位以修改前 `124dd186` 为准，先报告定位后修改：

- `examples/reader.c:1680–1684` 把图片在分页位图中的矩形当作图像源，越界时还会清除单图标记；`reader.c:3720–3727` 固定 `scale=1`，只居中平移；`examples/windows/shell_d2d.cpp:429–439` 使用同一宽高创建源位图和目标矩形。该路径依赖 SDK 布局已做完所有适配，没有独立的当前版心高度限制。`reader.c:366` 已把当前版心高传给分页器；`reader.c:1583` 的 1040 是旧界面默认值，不是 shell 的高度来源。
- `examples/windows/shell_screen.inc:319–337` 的 `shell_page_focus()` 在正文 HWND 有焦点且显示焦点提示时，用 accent 连画两层 `FrameRect`。这是 2px 焦点环。`shell_d2d.cpp:438` 的 page-shadow 是独立的暗色阴影绘制，不是该靛蓝边框。

修复让单图页持有完整解码图片，脱离分页裁切矩形；源位图和显示矩形分别传给 D2D。目标尺寸同时受当前版心宽、高约束，短边取整后由原始比例推导长边，居中误差最多半像素。窗口最小时仍保留至少 16px 边距。正文页只绘制页码；目录、设置和设置面板控件继续遵循键盘焦点提示，禁用控件不画图标焦点环。配色、圆角、字号和行高 token 均未改。

验收采用真实 HWND，位置固定为 `(-32000,-32000)`，截图使用 `PrintWindow`。指定尺寸均核对实际客户区。下面为 96 DPI 原件封面；另测 120 DPI 的 1242×742、1280×800。

| 客户区 | 图片矩形（客户区坐标） | 水平偏差 | 垂直偏差 | 长宽比误差 | 裁切 |
| --- | --- | --- | --- | --- | --- |
| 1242×742 | [427,96,815,678] | 0px | 0px | 0 | 0 |
| 1280×800 | [427,96,853,735] | 0px | 0.5px | 0 | 0 |
| 900×600 | [303,96,596,536] | 0.5px | 0px | 0.000758 | 0 |
| 720×560 | [227,96,493,495] | 0px | 0.5px | 0 | 0 |

原件、竖图、横图、方图共 24 组全部通过；最大水平/垂直偏差各 0.5px，最大长宽比误差 0.000758。图片边界从截图像素独立提取，并与应用上报矩形交叉核对；夹具的四条彩色边均完整可见。125% 缩放时原生最小客户区为 900×700，因此 900×600 和 720×560 在 96 DPI 下测。

| 六项验收 | 结果 |
| --- | --- |
| 1. 1242×742 封面 | 双向误差 0px；长宽比误差 0；裁切 0 |
| 2. 三个指定尺寸 | 3/3；加最小窗口、不同图形比例及 DPI 后 24/24 |
| 3. 正文外圈取色 | 版心外 4px 四边及页面 HWND 外圈共 10,032 点，全部 #141416；RGB 误差 0，靛蓝像素 0 |
| 4. 控件焦点 | 目录/设置 2/2，#7c88ff，宽 2px、offset 2px；隐藏焦点提示后 2/2 不画环 |
| 5. 既有验收 | 浅/深底色误差 0；五态 30/30；动画 0ms；正文对比度 15.717976/16.455895；深色空白帧 0/154、全程 0/187；self-test 26；旧界面 8 图 client 差异 0px；字号锚点 12/12 |
| 6. 出图 | [封面](evidence/2a-step6-fix/cover-dark-1242x742.png)、[正文](evidence/2a-step6-fix/body-dark-1242x742.png)、[目录焦点](evidence/2a-step6-fix/keyboard-focus-toc.png)、[设置焦点](evidence/2a-step6-fix/keyboard-focus-settings.png) |

焦点截图在离屏驱动中注入 owner-draw 焦点状态，并分别显示/隐藏 Windows 键盘焦点提示；没有切到前台发送物理键盘输入。生产路径仍检查 `ODS_FOCUS` / `ODS_NOFOCUSRECT`。

本轮以当前源码重建的 main 在《紅樓夢》上未重现 owner 所报的同样裁切；回归夹具可重现独立的长宽比失败（main 误差 0.013793，修复后 0）。本机已有 `exr-demo-main/main-1280.png` 显示裁切和靛蓝边框，保留为历史输入；其配套运行库与本轮消费的 SDK 哈希不同。该历史图不是本轮新抓图。

修复 EXE 另配该历史运行库（SHA-256 `79d5093857385c84c03ea3e7f9000fd44411e712d47c32ab6d63f682efacba66`）补测：单图 24/24、外圈取色 10,032/10,032、目录/设置焦点 2/2 全部通过，截图图片边界与标准 SDK 组合一致。

旧 P0 脚本曾把竖排有效列高写死为 556；P1 已把页高从 592 改为 612，main 和修复构建实际均为 576。本轮把断言改成“实际页高 − 2em”，维持字号、行高、缩进及其余像素断言。

复跑：

```powershell
cmake -S examples/windows -B docs/ui/acceptance/.build-step6 -G "Visual Studio 17 2022" -A x64 -DEXR_SDK=C:/Users/Oscar/Documents/Codex/exr-paint-sdk -DEXR_READER_WINDOWS_SHELL=ON
cmake --build docs/ui/acceptance/.build-step6 --config Release --target EXReader check_shell_geometry check_shell_anchor check_shell_epub
python -X utf8 docs/ui/acceptance/check_step6.py <EXE> <同 SDK 的 main EXE> <FONT> <紅樓夢原件> <OUT>
python -X utf8 docs/ui/acceptance/check_step5.py <EXE> <同 SDK 的 main EXE> <FONT> <Long-acceptance.epub> <OUT>
python -X utf8 docs/ui/acceptance/check_art_p0.py <EXE> <FONT> <紅樓夢原件> <OUT>
```

仅改 `examples/`、`docs/ui/`。未手动触发 CI，未取消任何 workflow run。
