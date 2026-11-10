# 2a 第 3 步计划：物理像素重排与 Per-Monitor V2

日期：2026-11-05。本轮只读源码、文档和本地 EPUB，唯一写入为本文件；未启动程序、GUI、构建、测试或 CI，未提交。

## 1. 基线与现状

### 1.1 本次实际读到的版本

- 工作区：`codex/ui-2a-step3-20261105`，HEAD 为 `de8087cc`；只读查询远端 `refs/heads/main` 也返回 `de8087cc`。该版本包含第 1 步 merge `5d81eca5`，不含第 2 步，工作区中没有 `docs/ui/2A-STEP2-ACCEPTANCE.md`。
- 第 2 步材料从已有 git 对象读取：`origin/codex/windows-shell-2a-step2-20261105` → `870f85de734981a64c908d781096130d6f9144aa`。读完其 `2A-STEP2-ACCEPTANCE.md` 及相关源码，没有 checkout、fetch 或修改分支。本次无法把用户提到的 `d870...` 对应到已核实的第 2 步合并提交。
- 已读工作区的 `docs/ui/HOST-AUDIT-20261104.md`（尤其 §F、§G）、`2A-STEP1-ACCEPTANCE.md`，并核对 `UI-SPEC-20261104.md` §2–3、`WIREFRAMES-20261104.md` §2。
- **下文默认行号以第 2 步 `870f85de` 为准**，方便在第 2 步之上实现；现状表同时给出当前 HEAD 的行号。实际开工时先确认 main 已含第 2 步，再重新定位，不在本轮同步代码。

### 1.2 页面、字号与显示链

| 计算点 | 第 2 步位置 | 当前 HEAD 位置 | 当前行为 |
| --- | --- | --- | --- |
| 旧字号和窗口尺寸载入 | `examples/reader.c:649` `settings_load` | 同左 | `FontPercent` 默认 150；窗口默认 **外框** 1180×900，恢复下限 900×600 |
| 引擎页尺寸、内边距、字号、行距、段距 | `examples/reader.c:1450` `session_configure` | 同左 | `width=720`、`height=1040`（1455–1456）；margin=36，font=28×百分比/100（默认 42），line_height=1.5，paragraph_spacing=10（1473–1476） |
| 可选旧设置覆盖 | `examples/reader.c:1457` `session_configure` 的 preferences 分支 | 同左 | 可覆盖边距、字号、行距、段距；页宽高仍固定。新 shell 不能意外继承这条路径 |
| 重新排版 | `examples/reader.c:2673` `job_layout` | 同左 | 从 `g.session.config` 复制，2699 只改字号；不会从窗口尺寸计算新的页宽高。分别处理 TXT、bounded EPUB、普通 document 的锚点恢复 |
| 旧面板布局 | `examples/reader.c:3329` `layout_controls` | `:3318` | 顶部 76、底部预留 36，左栏宽为窗口 1/4 并限制在 250–340，3391 设置页面子窗口 |
| 新阅读屏布局 | `examples/windows/shell_screen.inc:86` `shell_layout` | 不存在 | 顶栏固定 56，`g.page` 填满余下客户区；尚无版心、上下留白和页码区 |
| 显示比例和原点 | `examples/reader.c:3412` `compute_view_impl` | `:3398` | 比例为 min((页面客户宽−8)/位图宽, (高−8)/位图高)，居中；3419–3426 与窗口联动的是缩放，不是分页 |
| 显示位图准备 | `examples/reader.c:536` `frame_prepare_display` | 同左 | 539–553 再算相同比例，用 HALFTONE `StretchDIBits` 生成显示缓存 |
| 合成与上屏 | `examples/reader.c:3513` `compose_page_view`；`:3577` `paint_page_view` | `:3499`；`:3559` | 已有页缓冲及 BitBlt，但前面的显示缓存仍经缩放；合成失败回退也会 StretchDIBits，不能把“最后一次 BitBlt”当作 1:1 证据 |
| resize | `examples/reader.c:3662` `page_procedure`；`:6307` `procedure` | `:3644`；`:6109` | 页面 WM_SIZE 仅重绘；主窗口 WM_SIZE（6336）仅记录外框、resize D2D、摆放控件，不提交 JOB_LAYOUT |
| 独立自检 | `examples/reader.c:6124` `st_open_book` | `:5926` | 6148 自己设置 720×1040，6236–6237 断言该尺寸；与 session_configure 分开，必须保留 |

**结论：正文仍硬编码 720×1040。** 第 2 步改变了外壳，没有改变排版输入；字号 18 也还不是现有 shell 的独立正文设置。新路径采用 DIP 字号，默认 17，验收显式设为 18，不能把旧 `FontPercent=150` 解释成 18。

### 1.3 DPI 已有部分与缺口

- `examples/reader.c:6706` `WinMain` 的 6722–6726（当前 HEAD 为 6488、6504–6508）已动态查找 `SetProcessDpiAwarenessContext`，传入 `-4`，不存在该 API 时调用 `SetProcessDPIAware`。`-4` 正是 PMv2 上下文；调用在创建窗口之前，但忽略返回值，也未确认实际生效的上下文。不能沿用审计旧基线“完全 DPI 无感知”的结论。[Microsoft 定义](https://learn.microsoft.com/en-us/windows/win32/hidpi/dpi-awareness-context)
- 两条 examples 构建入口未声明应用 DPI manifest；当前 Windows 宿主代码没有 `WM_DPICHANGED`、`GetDpiForWindow` 或按显示器 DPI 更新几何与字体的处理。现有声明不足以完成 Per-Monitor V2 布局。
- 第 2 步 `examples/windows/shell_d2d.cpp:22` `pixel_properties` 将 HWND/DC 两个 target 固定为 96 dpi；`:54` `make_format` 在 65 行固定书名 17、图标 20。`shell_screen.inc` 也直接把 DIP 令牌当物理 px 使用。因此 125%/150% 下控件、字体和留白尚未正确换算。
- 计划保留 D2D target 的 96 dpi 像素坐标契约，宿主把 DIP 几何与文字字号转换为 px；不要同时提高 target DPI，造成二次缩放。启动时检查 PMv2 设置结果及实际窗口上下文，降级状态必须写证据，不能记作 PMv2 通过。API 必须在 UI 创建前调用，失败可由已设置的进程感知导致，应查询实际状态后判断。[Microsoft API 约定](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext)

## 2. 第 3 步布局方案

### 2.1 单位与目标几何

“1280×800 窗口”按 UI-SPEC 定义为 **1280×800 客户区**，不含标题栏。每条证据同时记录 client 物理 px、DPI 和换算后的 DIP；1000 分档按审计定义的 client 宽记录，不能用外框宽代替。高 DPI 另列可用 DIP 宽，避免把物理宽足够、逻辑宽不足的场景误判为宽窗。

设 s=DPI/96，客户区物理尺寸 Wpx×Hpx，可用宽 W=Wpx/s，字号 f 为 DIP。横排采用 UI-SPEC 的窄窗分支：

- lim=W−96；lim<28f 时版心宽为 lim，否则为 max(28f, min(34f, lim))。无固定 680 上限。
- 引擎页宽为 round(版心宽×s)，页高为 round((Hpx/s−56−32−32−24−32)×s)。引擎 margin=0、font_size=f×s、line_height=1.6、paragraph_spacing=0.8f×s。
- 版心在客户区水平居中；同一剩余宽度分配左右，奇数余量使左右最多差 1 px。正文原点距顶栏下沿 32 DIP；底部依次为 32 DIP 间隔、24 DIP 页码区、32 DIP 下留白。边界先统一舍入，再相减，避免多段独立舍入累积误差。
- 100% / client 1280×800 / f=18 的**计算预期**：引擎页 612×624，左上角为主客户区 (334,88)，正文底 y=712，页码区 y=744..768；左右各 334 px；行距 28.8 px，段距 14.4 px，完整 CJK 行约 34 字。默认 f=17 时页宽 578，左右各 351。
- §F 旧测量的 624×724、每行 32 和左右 352 来自旧版 32em 与引擎 margin，不能作为现行布局的精确期望。它证明过引擎可达目标，没有证明当前宿主可达目标。

字体、页尺寸和留白只换算一次。窗口物理 px 已由 GetClientRect 给出，不能再乘 s。正文显示原点和命中转换使用同一份几何，`g.view.scale=1.000`。

### 2.2 重排与位置保持

1. 在 UI 线程取得客户区、DPI、shell 模式和字号，形成不可变任务快照；JOB_OPEN、JOB_LAYOUT 使用同一份配置生成规则。打开书准备进入 shell 时即按 shell 目标几何排版，避免先排旧尺寸再无条件重排。
2. WM_SIZE、WM_DPICHANGED、shell 进入/退出和字号变化都比较目标几何。resize 使用约 150 ms 防抖；相同页宽高、字号、方向和模式不重复建 pager。达到 34em 上限后只改宽通常只移动版心；窄窗页宽改变、页高或 DPI 改变必须重排。
3. 复用 JOB_LAYOUT 的普通 document 锚点、bounded EPUB 章内锚点和 TXT 内容偏移路径；不按旧页码恢复。保留“请求前页首内容锚点”，避免连续 resize 从中间结果反复取锚点。改尺寸再改回比较页首文本及源范围，不能只比较页号。
4. 任务携带布局代次；只发布与当前书籍、模式、尺寸、DPI 匹配的最新结果。已有 worker 忙时保留最新布局请求，完成后继续，不能因 busy 直接丢掉 resize。沿用单 worker 与提交屏障，不另建线程池。
5. shell 与旧面板切换必须同时切换分页配置，清理对应显示缓存、命中和选区状态；不能仅隐藏控件。旧面板恢复 720×1040 和旧字号映射。旧 `--drive` 默认保持旧配置，只有 `shell|on` 进入新路径。
6. WM_DPICHANGED 先更新 DPI，按系统建议外框 SetWindowPos（不激活窗口），合并其触发的 WM_SIZE，再更新控件/字体并提交一次最终重排；最小化或零客户尺寸不建 pager。该消息的建议矩形和 DPI 参数按 [Microsoft 约定](https://learn.microsoft.com/en-us/windows/win32/hidpi/wm-dpichanged)处理。
7. 固定页 PDF/CBZ 不套用流式页宽高与 CJK 字数判据；按目标显示矩形重新计算渲染 scale，再以实际像素贴图，保留旧面板 zoom 语义。新路径不通过整页拉伸补足尺寸。

## 3. 要改的函数清单（仅 examples/）

本表为后续实现清单，本轮不修改它们。行号均为 `870f85de`；新增辅助函数标在其插入区域，不虚构现有行号。

| 文件:行号 → 函数/区域 | 改什么 |
| --- | --- |
| `examples/windows/shell_tokens.h:29` 令牌枚举 | 补齐正文默认/档位、1.6 行高、0.8em 段距、48/32 留白、24 页码区和客户区尺寸令牌；18 作为显式验收字号，默认仍 17 |
| `examples/windows/shell_screen.inc:77` `shell_button_circle`；`:86` `shell_layout` | 统一 DIP→px；计算顶栏、按钮、正文版心和页码矩形，触发几何变化通知；保留按钮 HWND 与 UIA 代理 |
| `examples/windows/shell_screen.inc:109` `shell_enter`；`:130` `shell_leave`；`:146` `shell_sync` | 进入/退出时请求相应布局配置、保存内容锚点，合并请求，防止 shell_sync 随 job 完成重复重排 |
| `examples/windows/shell_screen.inc:159` `shell_paint`；`:181` `shell_draw_item`；`:205` `shell_page_focus` | 顶栏、五态、描边按 px 几何绘制；新增底部页码绘制辅助放同文件，由页面合成调用；保留先 DefWindowProc 更新 UI state 再读焦点提示的顺序 |
| `examples/windows/shell_d2d.h:21` 文字样式与 `:36` 起 C API；`examples/windows/shell_d2d.cpp:54` `make_format`、`:83` `shell_d2d_create` | 增加页码样式和 DPI/字号资源更新接口，字体大小按 s 重建；仍不引用 SDK、reader.c 或宿主全局状态 |
| `examples/windows/shell_d2d.cpp:109` `shell_d2d_resize`、`:135` `shell_d2d_text`、`:156` `shell_d2d_icon_button` | resize 和 DPI 更新分开，文字及按钮用已换算 px；页码在页面 HDC/合成缓冲绘制时复用 DC target 能力；target 保持 96 dpi |
| `examples/reader.c:997` `host_job`；`:1178` `job_new` | 为 shell 任务快照增加页几何、DPI、字号、模式/布局代次；帧保存相应身份，不让 worker 临时读取变化中的窗口尺寸 |
| `examples/reader.c:1450` `session_configure`；`:2354` `job_open`；`:2673` `job_layout`；`:4045` `change_font` | 只在 shell 布局快照有效时采用物理像素配置；所有重排参数同时更新，复用三类锚点路径；新字号不写回旧 FontPercent；旧宏关闭与旧面板分支维持原行为 |
| `examples/reader.c:1617` `render_fixed` | shell 分支按目标显示尺寸及 DPI 渲染，保留 PDF/CBZ 页比例和旧 zoom；不送入 JOB_LAYOUT 的流式分支 |
| `examples/reader.c:536` `frame_prepare_display`；`:3412` `compute_view_impl`；`:3513` `compose_page_view` | shell 流式页不调用 HALFTONE 缩放；使用位图原尺寸和版心原点，scale=1；合成正文、选区、页码、焦点到已有页缓冲；旧绘制分支保留 |
| `examples/reader.c:3443` `paint_selection`；`:3591` `point_offset`；`:3640` `bounded_mouse` | 核对同一原点/scale 的正逆转换；版心外、留白和页码区不发正文命中；横/竖排均使用引擎实际 glyph 几何 |
| `examples/reader.c:569` `page_cache_clear`、`:570` `page_cache_find`；`:1344` `job_start`；`:4645` `handle_job_complete` | 布局变化时失效缓存，接受结果时检查布局代次，连同预取结果一起拒绝过期配置；复用已有 4 帧容量，避免新旧页尺寸混用 |
| `examples/reader.c:3662` `page_procedure`；`:6307` `procedure` | 接通 resize 防抖、WM_DPICHANGED、字体/资源更新和最小化处理；使用不与既有 timer 冲突的 ID；WM_GETMINMAXINFO（6359）在 shell 路径允许规格最小客户区 720×560 |
| `examples/reader.c:6706` `WinMain`（6722 DPI、6834 创建窗口）；`:649` `settings_load` | 保留既有 PMv2 请求并在 shell 启用路径验证结果；新模式用 AdjustWindowRectExForDpi 类换算确保目标是客户区尺寸；旧外框恢复键及其默认值不被改写成新语义 |
| `examples/reader.c:3853` `update_page_label`；`:5502` `drive_execute` | 将已接受帧的章/页信息交给页码绘制；扩展 shell 专用量测状态输出：客户区、DPI、引擎配置、实际字形/行/列指标、scale、代次、锚点。原有 phase 动作及断言不变 |

第 3 步复用已有构建接线，不新增 manifest/依赖，不改两个 CMakeLists。`st_open_book`、self-test 的 720×1040 和 26 项语义不在修改清单。第 4 步继续负责上屏探针、空白帧和 p95 的完整验收；本步必须提供真实 1:1 数据路径，不能拖到第 4 步才取消缩放。

## 4. 两条判据的测量方法

以下为后续实施后的测量流程，本轮没有执行。量测从引擎实际 layout 的 line/glyph 与帧文本取得，PNG 用于核对上屏原点、边距和像素尺寸。bounded 路径在拥有 layout 的执行点复制所需数值到任务结果，不能从 UI 临时访问已释放的 layout。

通用记录：构建提交、宏/工具链、SDK 与字体 SHA-256、书籍 SHA-256、章节/页/源偏移、原生或受控 CSS、DPI、物理 client 尺寸和 DIP 尺寸、实际字形字号、引擎页大小与显示比例。排除封面、图片、标题、ruby 注音、隐藏/生成字形和段尾短行；有效行/列为占用相应可用行内长度至少 90% 的正文。每场景取至少 20 个正文页，报告有效行/列数、中位数和 p5–p95；不足有效样本不判通过。

### 4.1 横排：每行汉字、左右边距、行高比值

1. **确认方向**：layout 为 `EXR_WRITING_HORIZONTAL_TB`；优先使用长段中文正文、无图片/注音的样本。日文《草枕》不能单独代表中文“每行汉字”。标准计数沿用 §F：每个源文本字符计一次，含标点和空格；另报纯 Han 数及假名数。用源 UTF-8 范围/cluster 去重，不能数 glyph 数、UTF-8 字节或 UTF-16 单元。
2. **每行字数**：按引擎 exr_line 的源范围/所属 glyph 分组，横向占用≥可用行宽 90% 的完整正文行计数。100% / client 1280×800 / f=18 时中位应在 **28–34**，预计接近 34；禁止以 page.width/font_size 的商代替实测。拉丁段另报 65–75 中位及分位数，不与 CJK 混算。
3. **左右边距**：将引擎字形排版框转换到主窗口 client 坐标，L 为完整正文行左沿到 client 左沿，R 为 client 右沿到该行右沿。输出版心几何边距及正文实际边距；PNG 复核墨迹范围时排除顶栏、页码、焦点框。几何版心左右差≤1 px，完整满行的正文左右也应对称；短行、缩进单列报告。各边至少 48 DIP（物理为 48s px，亦满足审计的≥48 px底线）。不要从 PNG 文件外边或页面子窗口左边量起。
4. **行高比值**：同一段、同字号、相邻非 ruby 正文行的基线差 Δy 除以实际 glyph 字号 Fpx，取中位；应为 **1.600±0.005**。f=18、96 DPI 应得到约 28.8/18。排除跨段落的额外 0.8em 间隔。仅靠截图把基线舍入到整数像素不足以验证该容差，应保留引擎浮点坐标；截图只核对没有拉伸。
5. **矩阵**：96 DPI client 宽至少 1280、1000、999、720，字号 14、17、18、24、32；另测 1920×1080@125%、2560×1440@150%，并记录每点物理/DIP宽。≥1000 档查 28–34，<1000 档查≥18及边距优先；高 DPI 若 DIP 宽不满足对应 em 容量，按窄窗公式报告，不能通过压缩字号或缩放截图凑达标。所有点 scale=1.000、版心误差≤1 px，并做尺寸往返页首文本核对。

### 4.2 竖排：每列汉字（沿页高）、上下边距

1. **先证明是真的竖排**：必须记录 layout writing_mode 为 `EXR_WRITING_VERTICAL_RL` 或 `VERTICAL_LR`，及正文的 `EXR_GLYPH_VERTICAL`；vertical-rl 应由右向左换列。文件名、OPF 的阅读方向或截图宽高不能证明竖排。
2. **每列字数**：按引擎 line/物理列分组，沿 y 轴排序，用每列源 cluster 范围去重计数。有效列占用实际行内可用页高至少 90%；含标点/空格，Han、假名另列；ruby、縦中横组合不能因多个 glyph 重复计数。报告每列中位与 p5–p95，同时给出可用页高/实际 Fpx 的容量估算作校验，**绝不拿 page.width/Fpx 或横向列数当每列字数**。
3. **上下边距**：将完整正文列的顶部/底部映射到主 client 坐标；分别报告相对正文容器的上/下留白，以及相对整窗 client 的顶部/底部距离。上方排除 56 DIP 顶栏，下方排除页码区；校验正文距顶栏下沿≥32 DIP、距页码区上沿≥32 DIP，并记录书籍自身 padding 带来的额外空白。f=18、96 DPI 的宿主页高为624，未加书籍样式时理论行内容量约34.7字；真实结果以竖排 layout 为准。
4. **判定边界**：已确认的 28–34 指标在文档中是横排每行；竖排独立报告“每列沿页高”的指标，不用其通过来宣称中文横排达标，也不把 1.6×字号误量为竖向字符步距（竖排 1.6 对应列间距）。如果后续要求竖排也固定28–34/列，应沿 y 轴限制行内长度，不能复用横排612宽来声称已经限制列高。
5. **尺寸/DPI 往返**：同横排记录 scale、页首源范围和文字；抽查同列选区、跨列选择/复制和标注锚点，确认几何转换没有交换 x/y 或重复乘 DPI。

## 5. CJK 本地样本与前置问题

样本只读使用，不复制、不加入仓库：

`C:\Users\Oscar\Documents\Codex\real-books-pass-a-20261105\supplemental-samples\kusamakura-japanese-vertical-writing.epub`

- 本轮确认存在；大小 17,940,673 字节，SHA-256 为 `6d4d4ed5eda3f612e3263c54fa0f74ccfa87260f43e81bb58ea658636e52eeb7`。
- ZIP 内 `OPS/css/vertical.css` 的 html 规则使用 **`-epub-writing-mode: vertical-rl`**，还设 `font-size:14pt`、`margin:auto 1em`、`padding:1em 0`、`max-height:28em`。它可能改变宿主字号与可用列高，不能直接假定实际字号等于18、每列占满624。
- 当前工作区 `src/style.c:357` 的 property 表识别标准 `writing-mode`，未见 `-epub-writing-mode` 别名；第 2 步没有修改引擎。故**原样本是否能在目标 SDK 进入竖排是前置检查项**。本轮只核对源码与 EPUB，没有渲染来确认结果。
- 后续把“原生 CSS 兼容性”和“宿主受控物理排版”分开记录：原生路径保留样式，若方向不成立，记样本未进入竖排；受控路径可通过宿主 `user_css` 显式设置标准 writing-mode、统一正文18及去除干扰的页根尺寸/留白，保留 ruby 与文本方向结构。该结果须标为覆盖样式后的宿主量测，不能当作原生 EPUB 兼容性通过。遇到当前 SDK 无法正确覆盖/排竖版，不在第3步越界修改引擎。
- 中文横排字数与行距门槛另用可重复的长中文段落；《草枕》负责日文竖排、注音与方向兼容性，不能只数日文中的汉字就与28–34比较。

## 6. 旧界面风险与 client 像素零回归

| 风险 | 后续确认方式 |
| --- | --- |
| 新配置泄漏到宏关闭、旧面板或旧 --drive | 宏关闭前后、开宏旧布局都跑同一 phase；旧页仍720×1040、FontPercent语义相同；client像素全等 |
| PMv2 是进程级设置，误改使所有旧目标行为改变 | 复用已存在的启动声明；新增 shell 处理受宏与模式约束。旧路径跨DPI另核对，不用100%截图替代高DPI证据 |
| Alt+← 只恢复控件，仍持有新分页/缩放 | shell进入再返回后，等待旧配置重新接受，检查17个ID101–117可达、原边框恢复、旧页和锚点一致；增加同状态旧界面client比对 |
| 新布局结果或预取迟到，旧尺寸帧覆盖新帧 | 连续resize、改字号、跨屏、切书、shell切换后检查布局代次与位图尺寸；cache命中也须匹配配置，不能只查书/章/页 |
| 新原点破坏选择、复制、标注、UIA几何 | 页内首尾与留白点击、横/竖排跨行列选择、复制源文本、标注跳回逐项检查；新模式仍只有正文和两按钮共3个可操作元素 |
| 页码/页缓冲漏重绘或焦点残留 | 翻页、焦点提示隐藏/显示、窗口恢复、DPI变更后页码与帧同代；沿用第2步先更新UI state再重画的规则 |
| 新最小窗/客户区默认值污染旧WindowWidth/Height | 旧ini恢复与phase resize仍按旧外框语义，新模式几何单独转换；旧界面像素对照能抓到控件位置和尺寸变化 |
| 自检被共享配置顺带改掉 | 后续保留退出码0且报告checks恰好26；自检自己的720×1040断言不改 |

### 6.1 后续比对流程

1. 比较 **第2步基线宏关闭** 两次（off1/off2），再比较基线与第3步宏关闭，以及第3步宏关闭与开宏但保持旧布局。二进制轮流放同一路径，使用同一样本路径、同一已重置数据目录、同一Windows会话、主题、DPI、字体和焦点提示状态。
2. A→B→C连续执行，保留8张：A的00-empty-shelf、01-epub-page1、02-resized、03-pdf-page1、04-stale-final；B的10-restored、11-font-changed；C的20-restored-after-font。不能把两边同时缺失的截图算相等。
3. 同一截图两边取完全相同的**真实client矩形**，比较解码后的RGBA；逐像素任一通道不同即计1，尺寸不同直接失败。无容差、无焦点/正文局部遮罩。100%旧证据使用已确认的第38行起裁切，沿用 `docs/ui/acceptance/compare_shots.py --client-top 38`；125%/150%必须重新用ClientToScreen/GetClientRect定位矩形，不能固定38。既有脚本只按top裁切时仍包含边框，记录裁切范围，扩展测量时应使用完整client矩形。
4. 对照组off1/off2必须8张全部0差异，否则本轮比较无效，先定位环境/焦点状态；不得把偶发虚线框直接忽略后记通过。有效对照后，每组8张 `client_diffpx=0` 才称零回归。
5. 比对工具先通过负例：client内1个像素只改R一级、alpha不变，必须报1且失败；仅改client外标题栏必须报0。逐像素计数，禁止回到RGBA `getbbox()` 判断捷径。保留工具self-test和真实截图负例证据。
6. 保存每张client矩形、尺寸、diffpx、构建SHA-256、DPI、主题和焦点状态。phase本机MinGW已知基线只容许A115、B5两项且不得新增；MSVC官方基线为0。第2步§7最后的像素对照因对照组非0作废，不能引用为有效通过。

### 6.2 执行边界

本轮不运行上述任何项目。第2步验收文档§4要求GUI运行前取得owner明确许可；本轮用户还明确禁止打开任何窗口。未来如执行phase、snapshot、shell验收、DPI跨屏或焦点测试，须另获GUI授权，优先独立Windows桌面。键盘验收走真实SendInput；每次运行最多一次前台激活，失败不重试抢焦点。当前计划没有取得未来运行许可。
