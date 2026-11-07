# P1 外壳：页码、留白、单图页

承接 `fd097172` 的第 5 步与 P0。改动集中于 Windows 外壳及验收代码。

| 项目 | 实现与实测 |
| --- | --- |
| P1-3 | 12 px / 500；DirectWrite 启用 `tnum`，并补齐 Segoe UI Semibold 数字 7 的宽度差。当前数值用 `--text-2`，空格、`·` 及后一个数值用 `--text-3`；页码区高 40 px，贴窗底。96 DPI 数字墨迹距底 15 px。 |
| P1-4 | 首行实际墨迹位于发丝线下沿后 40 px；版心下边界距页码区上边界 24 px。1280×800、18 px 横排的分页尺寸由 612×624 改为 612×640。边界分别取整，避免非整数 DPI 累加误差。 |
| P1-5 | SDK 布局中只有一张已解码图片且没有可见文字时，按图片矩形在版心内双向居中。保持 SDK 的等比缩放及高度限制，四周使用已有 `--page-shadow`；深色主题保留黑白图片灰度。CBZ、无文字固定页同样居中。 |

页码数值沿用本分支现有的“章号 · 本章页号”口径。阴影沿用 token 中的 `0 0 0 1 rgba(16,16,28,.05)` 与 `0 2 10 -2 rgba(16,16,28,.12)`。

竖排沿用 34em 长度上限，使用更新后的可用版心空间；1280×800 的分页高度由 592 改为 612，有效列高由 556 改为 576。P0 中文 32 px 列距、缩进、段距及拉丁样式均通过原验收；验收脚本的有效列高改为按实际页面高度核对。

新增验收覆盖浅/深色、96/120/144/150/192 DPI：10 组文字页、32 组单图页、2 组混排负例及 2 组 CBZ。单图页包含带背景及内边距容器的封面。检查实际墨迹、页码颜色和字形宽度、图片位置/比例/高度、四边阴影及灰度保留。三个无窗口检查通过，包括 document/TXT/竖排 21 项字号锚点及继续翻页。

[截图、机器结果与构建哈希](evidence/2a-p1-shell/README.md)。

```powershell
cmake -S examples/windows -B docs/ui/acceptance/.build-p1-final -G "Visual Studio 17 2022" -A x64 -DEXR_SDK=C:/Users/Oscar/Documents/Codex/exr-paint-sdk -DEXR_READER_WINDOWS_SHELL=ON
cmake --build docs/ui/acceptance/.build-p1-final --config Release --target EXReader check_shell_geometry check_shell_anchor check_shell_epub
python -X utf8 docs/ui/acceptance/check_art_p1_shell.py <EXE> <Reader.otf> <OUT>
python -X utf8 docs/ui/acceptance/check_art_p0.py <EXE> <Reader.otf> <hongloumeng-24264.epub> <OUT>
```
