# Step 6：真实 EXE 与 DPI 抓图裁切（2026-11-07）

已用 owner 的 `exr-demo-fix/EXReader-fix.exe` 和《紅樓夢》原件复现，PNG SHA-256 精确等于 `ff3f4377c652f2a94cba58d3328784bcded9115f926aa7ed25bf298a631e7478`。裁切发生在抓图端：125% 缩放下，未声明 DPI 感知的 Python 进程读到 1242×742，而窗口实际为 1552×928。它分配的 1242×742 位图只容纳 PrintWindow 物理像素输出的左上角。

同一原始 EXE、同一窗口，不改绘制代码，仅声明 PMv2 后抓图，封面四边、右上控件和页码均完整。自动检查证明错误 PNG 与完整 PNG 的左上角逐像素相等。此前用完整客户区做的验收未覆盖这个抓图错误。

本轮已完成真实程序验收；PR #67 可按下面的真实尺寸和抓图方式验收。GitHub 状态仍保留 draft。

## 三个高度值

全部来自重编真实程序的 `EXR_PAINT_TRACE`，120 DPI。打开时物理整窗 1552×928，客户端 1534×881。后续对同一窗口改变尺寸。

| 阶段 / 目标 | 打开时 shell geometry.height | 当前 GetClientRect 高 | 单图 fit 使用的版心高 |
| --- | ---: | ---: | ---: |
| 原始复现窗口 | 681 | 881 | 681 |
| 物理整窗 1242×742 | 681 | 695 | 495 |
| 物理整窗 900×600 | 681 | 553 | 353 |
| 物理整窗 1280×800 | 681 | 753 | 553 |
| 精确客户端 1242×711 | 681 | 711 | 511 |

单图高度没有固定常量：`shell_fit_image()` 从当前 page 子窗口客户区重新计算版心；本机 120 DPI 时等于主窗口客户端高减 200。表中第一列固定指首次打开的值，重排后的帧会另有自己的 geometry。日志还分别输出当前帧 geometry、page 子窗口高和最终图片高。

## 真实窗口截图和像素结果

三张新图均包含原生标题栏，PNG 像素尺寸就是物理整窗尺寸。120 DPI 下原生非客户区共占横向 18px、纵向 47px，所以“整窗 1242×742 / 客户端 1242×711”不是这台机器当前的同一组物理尺寸；两种要求分别实测。

| 物理整窗 | 实际客户端 | 图片矩形（客户端坐标） | 水平 / 垂直误差 | 裁切 |
| --- | --- | --- | --- | --- |
| 1242×742 | 1224×695 | [447,120,777,615] | 0 / 0px | 0 |
| 900×600 | 882×553 | [323,120,558,473] | 0.5 / 0px | 0 |
| 1280×800 | 1262×753 | [447,120,815,672] | 0 / 0.5px | 0 |
| 1260×758 | **1242×711** | [451,120,791,630] | 0 / 0.5px | 0 |

原始 owner EXE 与重编 EXE 的四组完整客户区图均为 **0 像素差异**。图片来自 EPUB 原件的 1600×2400 解码源；整图与四条源边均作独立像素比较，结果见 [real-exe-result.json](evidence/2a-step6-fix/real-exe-result.json)。

125% 缩放下交互式最小客户端为 900×700。测试用 SetWindowPos 的 SWP_NOSENDCHANGING 绕过交互最小尺寸限制，令三个指定物理整窗尺寸精确生效；实际 WM_SIZE、重排与绘制仍由真实 EXE 执行。窗口始终在 (-32000,-32000)，使用 NOACTIVATE，前台观察 0。

四张主证据：

- [原脚本错误抓图，精确复现 ff3f4377…](evidence/2a-step6-fix/real-exe-before-1242x742.png)
- [修正抓图：物理整窗 1242×742](evidence/2a-step6-fix/real-exe-1242x742.png)
- [修正抓图：物理整窗 900×600](evidence/2a-step6-fix/real-exe-900x600.png)
- [修正抓图：物理整窗 1280×800](evidence/2a-step6-fix/real-exe-1280x800.png)

初始完整图、精确客户端 1242×711 图、对照图和原始高度日志位于 [real-exe-measurements.tar.gz](evidence/2a-step6-fix/record/real-exe-measurements.tar.gz)。

## 构建、修改与复跑

真实程序由 MinGW GCC 16.2.0 编译 `examples/reader.c`、`examples/windows/shell_d2d.cpp`、`examples/windows/shell_epub.cpp`，宏 `EXR_READER_WINDOWS_SHELL=1`，动态链接指定 `cjk-justify-20261106/build/libexreader.dll`；不是 harness。DLL 与 owner exe 相邻 DLL 哈希相同：`79d5093857385c84c03ea3e7f9000fd44411e712d47c32ab6d63f682efacba66`。实际进程加载路径见 [real-exe-loaded-dll.json](evidence/2a-step6-fix/record/real-exe-loaded-dll.json)。

- `examples/reader.c:1591`、`:1594`：输出打开时 shell 几何高与实际配置页高。
- `examples/reader.c:1659`：输出单图判定前的几何高。
- `examples/reader.c:3755` 起：输出当前主 / 子客户区高、帧几何高、适配使用的版心高和图片高。仅增加可选 trace。
- `docs/ui/acceptance/capture_window.py:17`：获取任何窗口几何前声明 PMv2；按物理整窗尺寸分配位图，并正确使用 64 位 GDI 句柄、释放资源。
- `build_real_exe.ps1`：保留指定 DLL 的三源文件构建命令。
- `check_real_exe.py`：普通书籍命令行启动，不使用 `--drive`；原脚本哈希复现、错误图与完整图左上裁切相等、三种整窗及精确客户端尺寸、原 EXE 对照、源图四边与居中检查。

工作区根目录的用户抓图脚本保持原件。请改用已提交的 PID 抓图脚本：

```powershell
python -X utf8 docs/ui/acceptance/capture_window.py <pid> <输出png>
```

完整复跑：

```powershell
./docs/ui/acceptance/build_real_exe.ps1
python -X utf8 docs/ui/acceptance/check_real_exe.py docs/ui/acceptance/.build-real-exe/EXReader-fix.exe C:/Users/Oscar/Documents/Codex/exr-demo-fix/EXReader-fix.exe C:/Users/Oscar/Documents/Codex/exr-cjk-corpus/hongloumeng-24264.epub C:/Users/Oscar/Documents/Codex/exr-demo-fix/Reader.otf tools_capture_window.py docs/ui/acceptance/.run-real-exe-native
python -X utf8 docs/ui/acceptance/check_step5.py docs/ui/acceptance/.build-real-exe/EXReader-fix.exe C:/Users/Oscar/Documents/Codex/exr-demo-main/EXReader-main.exe C:/Users/Oscar/Documents/Codex/exr-demo-fix/Reader.otf docs/ui/evidence/2a-step4-20261106/Long-acceptance.epub docs/ui/acceptance/.run-real-exe-regression
```

## 既有回归

同一真实构建、指定 DLL 运行 `check_step5.py`，退出码 0，既有八项全部通过：

| 既有项 | 本轮结果 |
| --- | --- |
| 浅 / 深 bg、surface | RGB 误差 0 |
| 五态 | 30/30 |
| 关闭系统动画 | 动画 0ms |
| 正文对比度 | 15.717976 / 16.455895 |
| 深色 / 全程空白帧 | 0/154；全程 0/187 |
| 字号与主题重启 | 28→28、1→1；系统模式 2→2 |
| self-test | 26/26 |
| 旧 UI | 8 张客户区差异 0px，负例自检通过 |

第 100 / 800 页六档字号递增锚点 **12/12**，另有直接跳字号 **10/10**；双向翻页及窗口缩小后恢复均保留页首。非零首行位置 4529 在六次递增中保持不变。

[完整回归 JSON](evidence/2a-step6-fix/record/real-exe-regression.json)、[进程记录](evidence/2a-step6-fix/record/real-exe-processes.json)、[原始回归测量](evidence/2a-step6-fix/record/real-exe-regression-measurements.tar.gz)。

只修改 examples/ 与 docs/ui/。未手动触发 CI，未取消任何 workflow run。
