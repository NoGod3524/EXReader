# Step 5 art P0 evidence

[完整六项实测、五态色值、八项回归与字号锚点](../../2A-STEP5-ART-P0.md)。

真实原件正文的 c 节验收截图：[1280 横排](horizontal-1280.png)、[2560 横排](horizontal-2560.png)、[1280 竖排](vertical-1280.png)。指定 EPUB 没有「」字符；保留原有引号，未替换标点。

- [P0 像素与 SDK 坐标](record/p0-result.json)
- [焦点环 2px / offset 2px / r11 的像素拟合](record/focus-measurement.json)
- [八项与六档 12/12 汇总](record/step5-result.json)
- [原 phase-a/b/c 对照](record/legacy-result.json)
- [100/800 页六档与跳档记录](record/font-anchors.json)
- [独立源内容一致性核对](record/source-identity.json)
- [无 HWND 检查](record/native-checks.json)
- [最终 GUI 进程位置与前台观察](record/processes.json)
- [编译器、二进制、源码及输入哈希](record/metadata.json)
- [原始 SDK glyph/line 数组、驱动、日志、INI、原 phase 像素图](record/measurements.tar.gz)

settings/ 为浅深设置图，icon-states/ 为图标 10 态，control-states/ 为三类控件 30 态，均在 record/ 下。这些夹具截图只检验控件与排版数值，不作为 c 节标点/行末证据。
