# Step 6 真书复核与诊断（2026-11-07）

PR #67 暂不可验收：本轮未复现 owner 报告的封面裁切。`179a429a` 加临时日志的对照构建与当前诊断构建，在指定《紅樓夢》三个尺寸上的完整客户区截图均为 0px 差异。本次提交增加探针和真书验收，没有改变图片绘制行为。

## 原件与探针

指定原件：`C:/Users/Oscar/Documents/Codex/exr-cjk-corpus/hongloumeng-24264.epub`。
SHA-256：`325fef5fb561a258ee4e0ded25821a55d77f7b4b627ae0ecac03410802ea6ec7`。
书库现有条目的 source BLOB 与此原件逐字节同哈希。新导入、现有书库的只读副本、普通启动（不加 `--drive`）、历史 MinGW 运行库均实测：

```json
{"image_count":1,"visible_text":0,"flags":0}
```

当前诊断构建还在已接受帧的 `shell_measure` 中报告 `source_available=1`、`fitted=1`，完整解码源为 1600×2400。《紅樓夢》《Pachinko》《醒世恆言》共 15 组封面都是 `1 / 0 / 0`。

## flags 判断

依据 `include/exr/layout.h:44`、`src/flow.c` 的 `exr_flow_image()`：

| 图片 flags | 语义 | 处理 |
| --- | --- | --- |
| 0 | 正常解码图片 | 保留现有单图条件和等比缩放 |
| 0x1 | 缺少解码图像的占位图 | 保留 SDK 页面绘制 |
| 其余位或其组合 | 未定义的图片标记 | 保留 SDK 页面绘制 |

当前 SDK 没有可加入白名单的非零图片 flags。CSS 居中、边距不写入图片 flags。浮动使用独立的 `exr_style.float_side`（`src/style_internal.h`、`src/pager.c`），不能用图片 flags 判断浮动。本轮保留 `!image->flags`，没有放宽 eligibility；也未声称该条件能区分所有浮动图片。

## 真书实测

96 DPI、深色；全部尺寸核对实际客户区。图片矩形为客户区坐标，居中误差相对实际版心。

| 客户区 | 图片矩形 | 水平偏差 | 垂直偏差 | 比例误差 | 裁切 |
| --- | --- | --- | --- | --- | --- |
| 1242×742 | [427, 96, 815, 678] | 0px | 0px | 0.000000000 | 0 |
| 1280×800 | [427, 96, 853, 735] | 0px | 0.5px | 0.000000000 | 0 |
| 900×600 | [303, 96, 596, 536] | 0.5px | 0px | 0.000757576 | 0 |

另测 120 DPI 的 1242×742、1280×800；三本真书共 15/15 组通过，最大水平/垂直偏差各 0.5px、最大比例误差 0.000757576。120 DPI 下原生最小客户区限制使 900×600 不适用，三个指定尺寸均在 96 DPI 下完成。

`check_step6_real.py` 固定四本原件 SHA-256，核对导入后 source BLOB，并从原始 ZIP 直接解码图片，与 PrintWindow 图中完整目标矩形比较，包括四条源图边缘。15 组整图 RGB 平均误差最大 2.391383/255，四条边平均误差最大 0.522876/255；可区分夹具替代、错误图片和源图裁切。脚本不生成或重写 EPUB。

| 用户本轮六项 | 本机数字 |
| --- | --- |
| 1. 紅樓夢 1242×742 | image=[427,96,815,678]；水平/垂直偏差 0/0px；比例误差 0；裁切 0 |
| 2. 紅樓夢三尺寸 | 3/3；加 120 DPI 后 5/5 |
| 3. 两本不同真书整页图片 | Pachinko、醒世恆言各 5/5；三本合计 15/15 |
| 4. 蓝框及正文 | 四本正文 4/4，与对照完整截图差异 0px；每本版心外 4px 与页面 HWND 外圈 10,032 点，全为 #141416，RGB 误差 0，accent 像素 0；控件焦点 2/2 |
| 5. 既有验收 | 8/8；字号锚点 12/12；额外直接跳字号 10/10；三个无窗口检查 exit=0；P0 复跑通过 |
| 6. 出图 | 紅樓夢封面、Pachinko 正文各 1 张，另有两张控件焦点图，均位于 evidence/2a-step6-fix/ |

既有八项：浅/深 bg、surface 误差 0；五态 30/30；动画 0ms；正文对比度 15.717976/16.455895；深色空白帧 0/152、全程 0/185；字号/主题重启 28→28、1→1，系统模式 2→2；self-test 26/26；旧 UI 8 图 client 差异 0px、负例自检通过。

正文分别取《紅樓夢》part 15、《Pachinko》part 10、《醒世恆言》part 4、《草枕》part 2。封面和正文的新验收只使用原件。既有八项和锚点沿用原有回归输入，其结果不计入真书封面 15 组。

## 改动与复跑

- `examples/reader.c:157`、`:1683` 起：帧内记录 image_count/visible_text/flags/source_available，并经已有可选 EXR_PAINT_TRACE 输出；为原条件补充 flags 语义注释。
- `examples/windows/shell_measure.inc:12`：把已接受帧的判定值及 fitted 写入 JSON，避免仅根据截图猜测走了哪条路径。
- `docs/ui/acceptance/check_step6_real.py`：原件哈希、三尺寸、完整源图像素、两本不同真书、正文及焦点检查。

```powershell
cmake --build docs/ui/acceptance/.build-step6 --config Release --target EXReader check_shell_geometry check_shell_anchor check_shell_epub
python -X utf8 docs/ui/acceptance/check_step6_real.py <EXE> <同SDK的179a429a对照EXE> <FONT> <紅樓夢原件> <Pachinko原件> <醒世恆言原件> <草枕原件> <OUT>
python -X utf8 docs/ui/acceptance/check_step5.py <EXE> <同SDK的main-124dd186-EXE> <FONT> <Long-acceptance.epub> <OUT>
```

本轮纳入进程记录的 GUI 测试共 43 个，全部位于 (-32000,-32000)，前台观察 0；截图使用 PrintWindow。没有手动触发 CI，没有取消 workflow run。

## 尚待定位

需要 owner 实测裁切的 exe 完整路径和相邻 DLL/SDK 路径，核对其二进制哈希、加载的运行库与同一探针输出。当前证据只能确认上述本机构建的真书验收通过，不能确认 owner 所报路径已修复。PR 保持 draft。
