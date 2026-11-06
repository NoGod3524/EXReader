# 2a 第 2 步验收：扁平顶栏与共享绘制层（2026-11-05）

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

## 4. 过程中发现并处理的问题

- **焦点检查必须在前台跑。** 本机桌面在用时，测试窗口两次失去前台，正文还被翻到第 8、11 页（滚轮会作用于光标下的非活动窗口）。
  - 脚本因此在焦点段前加 `activate`。窗口不在前台时，这一步会明确报失败，而不是碰巧通过。
  - 最终一轮全程在前台。
- **`tab` 动作不能用来测焦点。** 原有的 `tab` 动作用 `PostMessage` 投递 `WM_KEYDOWN`，焦点不动；真实 Tab（`SendInput`）能从正文移到“目录”，焦点提示随之显示。
  - 中途试过加 `WM_NEXTDLGCTL` 处理。用真实按键对比过，不加也能移动，所以没有保留。
  - 第 2 步新增 `key_tab`，旧的 `tab` 动作不改。
- **正文焦点框刷新时机。** 正文缓冲必须在 `DefWindowProc` 更新焦点提示状态之后再重画，否则会画出上一个状态的焦点框。已改为先调用 `DefWindowProc` 再重画。

## 5. 未覆盖

- **深色主题**：令牌已在 `shell_tokens.h`，切换入口在第 5 步。
- **其他 DPI**：只测了 100% 缩放，Per-Monitor V2 在第 3 步。
- **MSVC**：MSVC `/W4 /WX` 只能等 CI 验证。本机是 MinGW `-Wall -Wextra -Werror`，0 警告。
- **按钮点击**：目录、设置的点击效果属于第 5、6 步。
