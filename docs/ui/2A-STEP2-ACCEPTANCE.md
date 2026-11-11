# 2a 第 2 步验收：扁平顶栏与共享绘制层（2026-11-05）

> 2026-11-10 更新：旧 17 控件界面已移除，包含其布局、101–117 消息入口及返回旧面板路径。下文涉及旧控件、phase-a/b/c、旧无障碍证据与 `--debug-ui` 的描述仅为历史；[归档及清单](archive/legacy-17-control/README.md)。当前产品仅使用新界面。

范围：HOST-AUDIT §G5 第 2 步（扁平化重估后 2 人日）。只改 `examples/` 与 `docs/ui/`；宏 `EXR_READER_WINDOWS_SHELL` 默认关闭。规格见 UI-SPEC（扁平化修订）与 WIREFRAMES §2。

本步替代此前按旧令牌做的 48 高原型（owner 决策 8：原型作废）。原型没有提交。

## 1. 做了什么

### 1.1 共享绘制层

- `examples/windows/shell_tokens.h`：UI-SPEC 的令牌。
  - 浅色、深色两套三层底色、文字、强调色、发丝线。
  - 间距 8/16/24/32/48，顶栏 56，圆形按钮 40，焦点描边 2。
  - 叠加色函数 `shell_mix`：hover 6%、pressed 12%。按 UI-SPEC §7 的五层底色逐项核对，结果与规格表完全一致。
- `examples/windows/shell_d2d.{h,cpp}`：Direct2D 和 DirectWrite 绘制层，仍可脱离 `reader.c` 单独编译。
  - 两种文字样式：书名是 17 号、600 字重、左对齐、单行省略；图标是 `Segoe Fluent Icons` 20 号，回退 `Segoe MDL2 Assets`。
  - 自绘圆形图标按钮 `shell_d2d_icon_button`：用 DC 渲染目标画在控件自己的 HDC 上。
  - 字面检查 `shell_d2d_title_faces`：600 字重必须落到真实字面，不能是合成粗体。
  - 两个渲染目标都固定 96 dpi，1 单位 = 1 物理像素；文字抗锯齿固定为灰度，保证截图可复现。

### 1.2 阅读屏

`examples/windows/shell_screen.inc`，由 `reader.c` 包含。

- **顶栏**：高 56，底色 `layer.page`；第 55 行 1 px 发丝线；书名从 x=24 起，到“目录”圆左侧 16 为止。
- **按钮**：两个 40×40 圆形按钮，“设置”距右边 16，“目录”在它左侧 8，两者距顶 8。
  - 按钮保留各自的 `BUTTON` 窗口（`BS_OWNERDRAW`），外观完全自绘，UIA 代理照常提供名称、角色和 Invoke（owner 决策 5）。
  - 窗口尺寸 44×44，给圆外 2 px 的焦点描边留位置。
- **正文区**：去掉 `WS_EX_CLIENTEDGE`，不再有 3D 凹陷边。回旧面板时恢复。
- **五态**：
  - normal：底透明。
  - hover：6% 叠加。悬停用 `TrackMouseEvent` 跟踪。
  - pressed：12% 叠加。
  - focus：2 px 强调色描边，只在焦点提示显示时出现。
  - disabled：图标 `text.disabled`。
- **正文焦点**：阅读屏内正文获得焦点时，画 2 px 内缩强调色框，同样只在焦点提示显示时出现，替代旧的虚线框。
- **Alt+←、Alt+→、`--drive` 默认旧面板**：与原型相同。

### 1.3 驱动脚本新增动作

| 动作 | 作用 |
| --- | --- |
| `shell\|on\|off` | 进入或离开阅读屏 |
| `shell_key\|left\|right` | Alt+← / Alt+→ |
| `shell_hover\|toc\|settings\|none` | 悬停 |
| `shell_press\|<按钮>\|0\|1` | 按下状态 |
| `shell_enable\|<按钮>\|0\|1` | 启用状态 |
| `activate` | 把窗口带到前台 |
| `ui_cues\|hide\|show` | 设置焦点提示状态 |
| `key_tab` | 真实 Tab 键 |

新增检查：`check|shell`、`check|legacy_ids`、`check|shell_fonts`、`check|focus`。

**取状态的方式和原因：**
- **悬停**：截图时光标不在按钮上，系统会立刻发 `WM_MOUSELEAVE`，所以驱动把悬停状态钉住。真实路径是 `WM_MOUSEMOVE` 加 `TrackMouseEvent`，代码同一条。
- **按下、禁用**：走真实的 `BM_SETSTATE` 和 `EnableWindow`。
- **焦点**：用 `SendInput` 发真实 Tab，由消息循环里的 `IsDialogMessage` 移动焦点。

## 2. 验收脚本

位置 `docs/ui/acceptance/`（owner 决策 7）。

- `shell-2a.txt`：驱动脚本。
- `check_shell_2a.py`：判定前 4 条。UIA 读取用 `uiautomation==2.0.29`，与 Windows 无障碍审计同包同版本，只看客户区。
- `compare_shots.py`：判定第 5 条，比客户区（第 38 行起），带 `--self-test` 负例（owner 决策 1）。

```
python docs/ui/acceptance/check_shell_2a.py <开宏的 EXReader.exe> <含 Sample.epub 的目录> <输出目录>
python docs/ui/acceptance/compare_shots.py <证据 a> <证据 b> --client-top 38
python docs/ui/acceptance/compare_shots.py --self-test
```

## 3. 结果（本机 MinGW，Windows 11，100% 缩放，浅色）

- 开宏二进制 `1a4a40d6adce`，不开宏 `1eb139504d3b`。
- `check_shell_2a.py`：退出码 0，40 步无失败。

| # | 验收条 | 结果 |
| --- | --- | --- |
| 1 | 客户区像素零差异（对照组 + 负例） | **通过**：见 §3.1 |
| 2 | UIA 可操作元素恰为 3 | **通过**：`DocumentControl 阅读区域`、`ButtonControl 目录`、`ButtonControl 设置`。客户区元素共 3，无未命名 |
| 3 | 顶栏 56 px | **通过**：x=8 列第 0、54、55、56 行依次为 `#FFFFFF`、`#FFFFFF`、`#F0F0F0`、`#FFFFFF`。书名和按钮以外的顶栏像素 0 个异常；正文左右边缘非底色像素 0 个（无 3D 边）。可见子窗口 3 个，正文上沿 56 |
| 4 | 圆角与间距和规格逐项一致 | **通过**：见 §3.2，23 项 |
| 5 | Alt+← 回旧面板，17 个控件可达 | **通过**：应用内检查两次均为 17（进入前、Alt+← 后）；UIA 中 101–117 全部在场、可操作、不在屏外 |

### 3.1 客户区像素比对

同一数据目录，phase-a/b/c 共 8 张截图。

| 比对 | 整窗差异 | 客户区差异 | 判定 |
| --- | --- | --- | --- |
| 对照组 `off1` / `off2` | 8/8 张不为 0（标题栏） | 8 张均为 0 | 环境稳定 |
| `off1` / `on` | 8/8 张不为 0（标题栏） | 8 张均为 0 | **零回归** |
| 负例：`on` 的 `B/11-font-changed.png` 客户区 (560,300) 的 R 改 1 级 | — | 该张 `client_diffpx 1`，退出码 1 | 能抓到 1 个像素 |
| `--self-test`（合成图：客户区改 1 px RGB，标题栏改 1 px） | — | 客户区报 1，标题栏报 0 | PASS |

phase 结果：三组都是 A 120 步只第 115 步失败、B 29 步只第 5 步失败、C 9/9。失败 2 个，没有新增。自检三组都是退出码 0、`checks` 26。

### 3.2 规格逐项

| 项 | 实测 | 规格 |
| --- | --- | --- |
| 书名起点 | 第一处字迹 x=25 | 24（加字形左侧留白 1） |
| 书名终点 | 最后字迹 187 < 1042 | 不越过“目录”圆左侧 16 |
| 圆形直径（hover / pressed 实测） | 40×40、40×40 | 40 |
| 圆角 | 20 | 直径 / 2 |
| “目录”圆位置 | x 1058–1098，y 8–48（客户区宽 1162） | 距顶 8 |
| “设置”到右边 | 16 | `space.2` 16 |
| 两圆间距 | 8 | `space.1` 8 |
| normal 底 / 图标最深像素 | `#FFFFFF` / `#1D1D1F` | `layer.page` / `text` |
| normal 无焦点描边 | 顶栏强调色像素 0 | 焦点提示隐藏时不显示 |
| hover 底 | `#F1F7FE` | 6% 叠加 |
| pressed 底 | `#E4EEFC` | 12% 叠加 |
| focus 描边 | 完全覆盖的像素均为 `#1A73E8`；外缘抗锯齿 `#267AE9`、内缘 `#F3F8FE`；圆内 `#FFFFFF` | 2 px，外扩 2 |
| disabled 底 / 图标最深像素 | `#FFFFFF` / `#AEAEB2` | 无叠加 / `text.disabled` |
| 书名字面 | `Segoe UI Variable Text`；拉丁 simulations 0，CJK（`Microsoft YaHei UI`）simulations 0 | 无伪粗 |

### 3.3 MSVC `/W4 /WX`：证据类型——间接（附配置行号）

CI：PR #50 头 `d76f5333`，run 42158204510，作业 127697311831 `desktop (windows-latest)`，MSVC 19.51.36260.0，作业通过。

推理链：**配置确实对该目标启用 `/W4 /WX` + 该目标编译成功 ⇒ 0 警告**（`/WX` 把任何警告变成错误，有警告就不会生成 `.lib`）。

1. **配置**：`examples/CMakeLists.txt`（`d76f5333`），第 28–30 行：
   ```cmake
   28  add_library(exreader-shell-d2d STATIC windows/shell_d2d.cpp)
   29  target_compile_features(exreader-shell-d2d PRIVATE cxx_std_17)
   30  target_compile_options(exreader-shell-d2d PRIVATE $<IF:$<CXX_COMPILER_ID:MSVC>,/W4 /WX,-Wall -Wextra -Werror>)
   ```
   该作业的这一步执行 `cmake -S stage/examples ...`，`stage/examples` 是本 PR 的 `examples/` 安装后的副本。
2. **编译成功**：日志原文
   ```
   shell_d2d.cpp
   exreader-shell-d2d.vcxproj -> D:\a\EXReader\EXReader\build\sdk-example\Release\exreader-shell-d2d.lib
   ```
3. **警告计数**：日志里没有 MSBuild 的 `Warning(s)` 汇总行（整份日志 0 处），所以无法引用计数原文。改为直接统计：含 `shell_d2d` 或 `exreader-shell-d2d.vcxproj` 的 warning 行 0 条、error 行 0 条；examples 构建这一步的 warning 行 0 条。

**为什么不是直接证据**：日志里没有这个文件的 `cl.exe` 命令行（MSBuild 只打印文件名），没有 `.vcxproj` 的 `WarningLevel` / `TreatWarningAsError`，配置阶段也没打印 `CMAKE_CXX_FLAGS`。没有为此修改 `native.yml`。

**覆盖范围（如实）**：`/W4 /WX` 只作用于独立静态库目标 `exreader-shell-d2d`。从 SDK 安装树构建 `EXReader` 时，`examples/windows/CMakeLists.txt` 用 `target_sources(EXReader PRIVATE shell_d2d.cpp)` 编译同一个文件，**当时不带这两个参数**。因此 §3.3 的“0 警告”只覆盖独立库目标这一条构建路径，不覆盖 `EXReader` 主构建。

**修复**（#50 合并后的单独小 PR）：在 `examples/windows/CMakeLists.txt` 里只对这一个文件设置 `set_source_files_properties(shell_d2d.cpp PROPERTIES COMPILE_OPTIONS ...)`，MSVC 用 `/W4;/WX`，其他编译器用 `-Wall;-Wextra;-Werror`，与独立库目标一致。`EXReader` 的 C 源文件不加 `/WX`。本机 MinGW 验证结果：`shell_d2d.cpp` 的编译命令带 `-Wall -Wextra -Werror`、编译通过；`reader.c` 仍只有 `-O3 -DNDEBUG -std=gnu11`。MSVC 这条路径（`/W4;/WX`）要等 CI 验证。

## 4. 环境限制（先读这节）

**GUI 测试需要 owner 明确许可（2026-11-05 起）。** 驱动脚本、`check_shell_2a.py`、phase-a/b/c 和像素对照组都会在本机桌面打开 EXReader 窗口，焦点段还会把它强制拉到前台。owner 的反馈是窗口“一直在前台疯狂弹出”。

- 今后跑任何 GUI 测试前先申请：说明跑什么、需要几次前台激活、预计多久，等 owner 回复“可以”。
- 未获许可时只做文档、PR 合并和命令行测试（`ctest`、`exreader-check-document`）。
- **焦点类断言以强制前台为前提，和有人同时使用这台机器互斥**：要么占用 owner 的前台，要么在 owner 使用时得到不可靠的结果。真正的出路是独立的 Windows 桌面（见下方待办）。

**有人在用这台机器时，焦点类断言不可靠。** 这一条比修掉它更重要：失败可能来自桌面，不来自代码。

- **实际发生过的两次干扰**：
  - 测试窗口失去前台，`check|focus` 读到 `focus=none` 或 `focus=other`、`foreground=0`。
  - 光标下的非活动窗口照样接收滚轮，正文被翻到第 8 页、第 11 页，连带后面的 `check|page|2` 失败。
  - 两次都出在本机正被使用的时候，代码没有改动。
- **受影响的断言**：所有依赖前台或键盘焦点的断言，即 `check|focus`、`key_tab`、焦点描边截图；以及任何会被滚轮或点击改变的状态，比如页码。
- **不受影响的断言**：像素颜色、几何尺寸、UIA 元素数和名称、旧面板控件可达性。这些不依赖前台。
- **窗口激活规则**（owner 决策，2026-11-05）：
  - 每次运行最多调用 1 次 `SetForegroundWindow`。
  - 调用前在 `drive.log` 记一行 `NOTE ... activating window for focus checks`，`check_shell_2a.py` 原样打印这一行，并在结果里给出 `focus_activations`。
  - 拿不到前台就报“无法获得前台”，这一步失败，**不重试抢焦点**。同一次运行里再次调用 `activate` 直接失败。
- **长期方案（待办，本轮不做）**：在独立的 Windows 桌面上跑焦点类验收，比如专用账号会话、虚拟机或 CI runner，避开人机共用。

## 5. 键盘断言一律用真实按键

**规则：今后所有键盘断言都走真实按键（`SendInput`），不用 `PostMessage` 伪造 `WM_KEYDOWN`。**

- 原有的 `tab` 动作投递伪造的 `WM_KEYDOWN`，焦点不动。真实 Tab 能从正文移到“目录”，焦点提示也随之显示。
- 伪造消息绕过了系统输入队列和按键状态，测到的不是用户实际走的路径，所以不能作为键盘断言的依据。
- 第 2 步新增 `key_tab`（真实按键），旧的 `tab` 动作保持不动。现有 phase 脚本不用它。
- 中途试过为 Tab 加 `WM_NEXTDLGCTL` 处理。用真实按键对比过，不加也能移动焦点，所以没有保留。
- `shell_key`（Alt+←/→）仍是投递消息。它测的是消息循环里的分支，不是焦点；改用真实按键记为待办。

## 6. 已知陷阱

### 6.1 文档里的路径被转义成控制字符

- **现象**：提交 `535cdec1` 写入 §3.3 的日志原文 `D:\a\EXReader\...\build\...` 时，`\a` 和 `\b` 被 Python 字符串字面量解释成 BEL（0x07）和退格（0x08），并已推送。
- **处置**：在 `870f85de` 里用补丁提交修正，没有强推。
- **规则**：写含路径或日志片段的文档时，一律用原始字符串（`r'...'` / `rb'...'`）或直接写文件，不经转义。
- **CI 卫生项（建议，待交给 P）**：仓库内的文本文件不得含 0x00–0x08、0x0B、0x0C、0x0E–0x1F，`\n`、`\t` 除外。`\r` 是否允许按仓库换行约定另定。

### 6.2 焦点提示状态的更新时机

- **现象**：正文改为“只在键盘导航时显示焦点框”后，截图里仍残留焦点框。
- **原因**：正文在收到 `WM_UPDATEUISTATE` 时立即重画缓冲。这时 `DefWindowProc` 还没更新窗口自己的焦点提示状态，`WM_QUERYUISTATE` 读到的是旧值。
- **修法**：先调用 `DefWindowProc`，再重画。
- **规则**：凡是依赖 `WM_QUERYUISTATE` 的绘制，都要在 `DefWindowProc` 处理完 `WM_UPDATEUISTATE` 之后再读状态。后续步骤里的自绘控件同样适用。

## 7. 最后两轮 GUI 运行（如实记录）

- **激活规则修改后的验收**：开宏二进制 `f6c7acd6123c` 跑 `check_shell_2a.py`，退出码 0，40 步无失败，规格 23/23，UIA 3 个，旧面板 17/17。前台激活 1 次，先记录再调用，系统给了前台。
- **随后的像素对照组**（不开宏 `84b547ff2dcf`，开宏 `f6c7acd6123c`）**作废**：
  - 对照组 `off1`/`off2`（同一二进制）在 `A/03-pdf-page1.png` 客户区差 92 px：`off2` 的“打开”按钮上多了一个虚线焦点框，属于焦点状态的偶发差异。
  - 按规则对照组不为 0，本轮开宏比对不作数。仅供参考：`off2`/`on` 8 张均为 0，负例报 `client_diffpx 1`。
  - 重跑的一轮在 owner 要求停止全部 GUI 运行时被中止，没有结果。
- **因此第 5 条（客户区零差异）的有效证据**是 §3.1 那一轮：开宏 `1a4a40d6adce`，对照组 0、`off1`/`on` 0、负例 1。
  - 之后对 `reader.c` 的改动只在 `EXR_READER_WINDOWS_SHELL` 宏内、且只涉及驱动动作（`activate` 的次数限制）。证据链是“源码预处理结果相同 + 编译参数相同 + 工具链相同 → 生成的代码相同”。MinGW 每次链接写入的时间戳不同，所以两次构建的二进制哈希本来就不会相同，这里比的是编译单元，不是二进制。下面是这条链的三个环节：
  - **编译参数与 `1a4a40d6` 那轮一致**：两轮都用同一个本地构建目录（`b-OFF` / `b-ON`），其 `CMakeCache.txt` 写于 17:54，早于 `1a4a40d6` 的构建，之后没有改过；`examples/CMakeLists.txt` 和 `examples/windows/CMakeLists.txt` 在 `aedf8ea7..4de16bd6` 之间也没有改动。reader 的编译参数两轮都是 `-O3 -DNDEBUG -std=gnu11 -isystem <stage>/include`，开宏时再加 `-DEXR_READER_WINDOWS_SHELL=1`。
  - **工具链**：同一个 gcc 16.2.0（MinGW-W64 x86_64-ucrt-posix-seh，WinLibs）。
  - **预处理比对，按尝试顺序如实记录**：
    1. 第 1 次：只加了 `-DNDEBUG` 和包含路径，没有用构建参数。我先判为“无效”：`ls | cut` 把文件大小截成“3985”，看着像只有约 4 KB；grep 又把 `strerror` 声明数成了 493 个 error。随后核对发现两份输出其实都是 4,023,985 字节、96,090 行，并非错误文本，所以“4 KB 错误文本”的说法本身是我看错了。但这次没有用构建参数，作为证据不够，不采用。
    2. 第 2 次：加上构建参数，从两个提交各取一份源码。两份都失败（退出码 1，各 395 字节错误）：临时目录里缺 `apps/reader/desktop/windows_accessibility.inc`。结论无效。
    3. 第 3 次：补上该文件（它在两个提交之间没有变化），参数 `-O3 -DNDEBUG -std=gnu11 -isystem build/reading-library/stage/include`。两份退出码都是 0、错误输出都是 0 字节，输出均为 4,665,678 字节、112,556 行，**逐字节相同**。只采用这一次。
  - 以上都是命令行比对，没有用 GUI 重测。

## 8. 未覆盖

- **深色主题**：令牌已在 `shell_tokens.h`，切换入口在第 5 步。
- **其他 DPI**：只测了 100% 缩放，Per-Monitor V2 在第 3 步。
- **MSVC**：MSVC `/W4 /WX` 只能等 CI 验证。本机是 MinGW `-Wall -Wextra -Werror`，0 警告。
- **按钮点击**：目录、设置的点击效果属于第 5、6 步。
