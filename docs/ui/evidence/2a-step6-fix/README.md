# Step 6 窗口视觉修复证据

[根因、六项验收及复跑命令](../../2A-STEP6-FIX.md)。

- [封面：深色 1242×742](cover-dark-1242x742.png)
- [正文：深色 1242×742](body-dark-1242x742.png)
- [目录键盘焦点绘制](keyboard-focus-toc.png)、[设置键盘焦点绘制](keyboard-focus-settings.png)
- [24 组图片像素边界、三尺寸与取色结果](result.json)
- [既有验收：五态、动画、空白帧、self-test、旧界面和字号](record/step5-result.json)
- [100/800 页字号锚点 12/12](record/font-anchors.json)
- [P0 排版、颜色及图标](record/p0-result.json)
- [历史 main 配套运行库 24 组补测](record/historical-runtime-result.json)
- [三个无窗口检查](record/native-checks.json)
- [44 个 GUI 进程的位置与前台观察](record/processes.json)
- [源码、EXE、两个运行库及原件哈希](record/metadata.json)
- [历史 main 既有截图](record/historical-main-existing.png)：本轮开始前已有的输入，显示裁切及靛蓝边框。
- [原始驱动、PNG、SDK 坐标、取色、paint trace、INI 和对照记录](record/measurements.tar.gz)

本轮新截图均来自 `(-32000,-32000)` 的真实窗口及 PrintWindow，前台观察为 0。焦点验证采用离屏绘制状态注入，显示/隐藏键盘焦点提示分别验收，没有前台物理按键测试。

压缩包中的 `step6/`、`step5/`、`art/`、`historical-runtime/` 分别对应新缺陷验收、既有验收、P0 和历史运行库补测。导入 profile 及原件副本未打包；夹具生成代码在 `check_step6.py` 中。
