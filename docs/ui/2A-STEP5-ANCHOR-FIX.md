# 第 5 步：字号内容锚点修复（2026-11-06）

**最终 `check_step5.py` exit=0，pass=true；既有八项全绿。两处非首页六档步进共 12/12，通过指定跳档循环 8/8。**

字号与 resize 共用 `shell_request_layout → shell_pump_layout → JOB_LAYOUT`。document 解析 document 锚点，bounded EPUB 解析章内锚点，TXT 使用规范化内容偏移。定位到包含锚点的 SDK 页面后，将解析所得内容点放到实际可见首行，接入后续 SDK 行带，并同步文字、glyph、命中坐标和进度范围。后续翻页从可见内容末尾继续。

**六档逐档切换**

下表 source_start 为 SDK `exr_line.start`，即章内规范化 UTF-8 内容锚点。初始客户区 1280×800、DPI 96。两处均为 bounded EPUB 第 0 章；前缀分别含唯一编号 `001300`、`010494`，详见 metadata.json。每档同时核对真实首行 glyph 的起点及对应文本前缀。

| 字号 | 100 页附近 source_start | 页号 | 800 页附近 source_start | 页号 |
| --- | --- | --- | --- | --- |
| 17→18 | 154739→154739 | 100→104 | 1248825→1248825 | 800→838 |
| 18→20 | 154739→154739 | 104→115 | 1248825→1248825 | 838→926 |
| 20→22 | 154739→154739 | 115→129 | 1248825→1248825 | 926→1035 |
| 22→24 | 154739→154739 | 129→139 | 1248825→1248825 | 1035→1116 |
| 24→28 | 154739→154739 | 139→176 | 1248825→1248825 | 1116→1413 |
| 28→32 | 154739→154739 | 176→185 | 1248825→1248825 | 1413→1487 |

**指定 17→18→24→32→17 循环**

| 字号 | 100 页附近 source_start | 页号 | 800 页附近 source_start | 页号 |
| --- | --- | --- | --- | --- |
| 17→18 | 154739→154739 | 100→104 | 1248825→1248825 | 800→838 |
| 18→24 | 154739→154739 | 104→139 | 1248825→1248825 | 838→1116 |
| 24→32 | 154739→154739 | 139→185 | 1248825→1248825 | 1116→1487 |
| 32→17 | 154739→154739 | 185→100 | 1248825→1248825 | 1487→800 |

此外，两处从六档末尾 32→17 的准备回切均通过，故完整记录共 22 次字号变化。主脚本原反例也已复测：第 4 页、17→18→20→22→24→28→32，首行均为 **4331**（6/6）。

**既有八项**

| # | 验收项 | 最终结果 |
| --- | --- | --- |
| 1 | 浅/深页面、浮层底色 | #f5f5f2 / #ffffff；#141416 / #1e1e21；RGB 误差 0 |
| 2 | 控件五态 | 30/30；填色、文字、边框、焦点色差 0 |
| 3 | 系统关闭动画 | 展开、收起均 0.000000 ms |
| 4 | 正文对比度 | 15.717976:1 / 16.455895:1 |
| 5 | 空白帧 | 深色 0/141；全程 0/174 |
| 6 | INI 重启保留 | ShellFont 28→28；ShellTheme 1→1；System 2→2；旧 INI 默认 17/2，书架 SHA-256 不变 |
| 7 | self-test | exit=0，checks=26，SDK 3.42.0 |
| 8 | 旧界面 client | 8 张，基线复跑及本次对照均 0 px；负例检出 1 px |

原 phase-a/b/c 本地脚本 exit=0；A 第 115 步、B 第 5 步两个既有失败在基线、复跑、本次完全一致，新增 0。

**固定字号拉丁 Sample**

以修复前 `3096ca7f` 为对照，17/24 号 × 浅/深主题 × 3 页 = **12 张 client 图像，全部 0 px**。输入与 phase 脚本的 Sample.epub 同字节（Long-acceptance.epub）；SHA-256 见 metadata.json。24 张裁剪图存于 pixels/clients.zip，逐图哈希与 client_box 存于 pixels/images.json。

**其他锚点路径与 resize**

无 HWND 的真实 `JOB_LAYOUT` 检查：document、TXT、document 竖排各 7 次，共 **21/21**；首行分别为 9639、9639、13597。三条路径的锚定后续读也均通过，3/3。旧 resize 压力脚本横/竖两组均 exit=0，四条返回路径的内容范围与文本一致；新远页测试的缩小、返回也均保持首行。

本轮 **36 个 GUI 宿主验收进程，前台观察总数 0**；截图使用 PrintWindow。C 单测不创建 HWND。未手动启动或取消 workflow；PR 保持 Draft。

**文件与行号**

| 文件 | 本轮修改位置与作用 |
| --- | --- |
| examples/reader.c | 152：锚定视口标记；1193：TXT 内容位置；1754：首行章内锚点；2052：复用 TXT 帧投影；2767、2777：视口拼接与续读；2941 / 2986 / 3041：三个 JOB_LAYOUT 分支；5922：离屏远页驱动 |
| examples/windows/shell_screen.inc | 43、58、86：字号/resize 共用首行锚点与 TXT 位置传递 |
| examples/windows/shell_anchor.inc | 1：实际像素、行/glyph、命中与文字范围的锚定视口 |
| examples/windows/check_shell_anchor.c | 1：无窗口 document / TXT / 竖排与续读检查 |
| docs/ui/acceptance/check_font_anchors.py | 1：100/800 页、六档、跳档、首行 glyph / 文本、bounded 存储、resize 检查 |
| docs/ui/acceptance/check_font_pixels.py | 1：固定字号拉丁 Sample client 像素比较 |
| docs/ui/acceptance/check_step5.py | 36、53：远页运行时限参数；230、231：最终汇总纳入严格锚点检查 |
| docs/ui/2A-STEP5-ANCHOR-FIX.md | 1：本报告 |
| docs/ui/2A-STEP5-ACCEPTANCE.md | 3：更新当前验收结论，保留上轮原始失败记录 |
| docs/ui/evidence/2a-step5-20261106/README.md | 3：本轮证据入口 |
| docs/ui/evidence/2a-step5-20261106/anchor-fix/ | 本轮数字、原始测量、截图、哈希、INI、脚本日志与 fixture |

**复跑**

```powershell
cmake -S examples/windows -B docs/ui/acceptance/.anchor-build -G "MinGW Makefiles" -DEXR_SDK=C:/Users/Oscar/Documents/Codex/exr-paint-sdk -DEXR_READER_WINDOWS_SHELL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build docs/ui/acceptance/.anchor-build --parallel 4
python docs/ui/acceptance/check_step5.py <最终EXE> <7b20c5a0基线EXE> <Reader.otf> docs/ui/evidence/2a-step5-20261106/record/Long-acceptance.epub <新输出目录>
python docs/ui/acceptance/check_font_pixels.py <最终EXE> <3096ca7f修复前EXE> <Reader.otf> docs/ui/evidence/2a-step5-20261106/record/Long-acceptance.epub <新输出目录>
python docs/ui/acceptance/check_step5_legacy.py <最终EXE> <3096ca7f修复前EXE> <Reader.otf> docs/ui/evidence/2a-step5-20261106/record/Long-acceptance.epub <新输出目录>
```

C 检查复用宿主的 C++ 对象及链接库，编译 `examples/windows/check_shell_anchor.c` 时开启 `EXR_READER_WINDOWS_SHELL=1`，保留 assert（不加 NDEBUG），链接 shell_d2d.cpp 对象和 SDK；运行参数为 `<Reader.otf> <可写TXT临时路径>`。预期 exit=0，输出 21 条字号记录，含 3 条续读断言。

[机器结果与完整证据](evidence/2a-step5-20261106/anchor-fix/README.md)。
