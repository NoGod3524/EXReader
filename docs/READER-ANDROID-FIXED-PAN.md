# Android 固定页视口平移

固定起点 `6b43e83537aa6b03bda889d258fe73c0e317acb1`；分支 `codex/reader-android-fixed-pan`。受测源码 `b25975b45f021bdf1bd086088634cfc2a4b4d2d4` / [run 40156615296](https://github.com/NoGod3524/EXReader/actions/runs/40156615296) attempt1 / Android job `121059247720` 已完整 success：新 Pan8 与原92项 UI 同源通过，共100项。仅授予 API34 default x86_64 模拟器上的本宿主范围。

原工件 `12585631849`，147551041 B，SHA-256 `1826428c4f0c35075d620f496b5a3ccef4a6e121bf9e797dd74ad881599b28b4`，有效期 `2027-01-23T03:00:46Z`。Pan first7/reopen1 的真实进程分别9124/9370；23张系统截图、9个四角RGB观测、22次原件回读、8组四旋转×显式Select/650ms长按拖动原文与视口严格检查均由本次真实驱动核对。后续独立ZIP/PNG只读proof仍单独记录，不把诊断运行当生产验收。

## 原生页面配色的真实缺口

冻结 `9854061be331fe603a1822d9b2b36ee357154927`：`include/exr/render.h` 的 `exr_render_page_color` 只有 layout/font/page/bitmap/error，选择 RGBA 输出而非主题；`exr_render_page_ex` 也只增加 channels/control。`src/raster.c::render` 公开路径先把整页缓冲设为白色。`layout_config.user_css` 能影响文档盒和文字，但没有整页底色参数，不能可靠覆盖页边与全部作者色。Java 重排页的真实 layout/font 句柄、bounded pager 的窗口文档均未公开，不能借私有字段重建忠实副本。现阶段保留实际 CSS 尝试失败及 `page_colors_accepted=false`；不改变 SDK，不把外围换色或整图反相当成完整阅读主题。

## 平移契约

Android 宿主 `ReaderView` 接在已有 Preferences 真实固定页缩放路径上，另修正 app-private PDF viewport 几何与共享选择工具条布局：实际固定页在原 Canvas 目标上平移，不重绘/重新分页/重新捕获锚点，不改页面位图。超出可用视口一像素以上的方向才允许平移；每个方向都夹紧到距边缘 8 px 的内容边界。无溢出方向保留原翻页规则。拖动在有溢出的主方向被认定后持续消费本次手势，边缘不转化为翻页；点击、硬件和原 forward/back 语义仍负责翻页。选字模式保留原文字拖选优先级。

平移量仅为当前 view 的瞬时状态，换页/重新发布页面复位，尺寸改变时夹紧，重开与旋转不持久化它。取消和多指接触不会制造点击/翻页。相同实际 offset 同时用于 Canvas、文本命中、选区覆盖与虚拟无障碍节点边界；被视口裁掉的行标为不可见。标准四向无障碍滚动动作用于平移，原 forward/back 仍翻页。

## 云端验证出口

新夹具在任何 SDK 读取前登记 600×800 非对称四象限 RGB、四个角落采样点及 PDF 字标；PNG/CBZ 与 PDF 对象图由独立 Python 写出。新 7+1 两进程检查覆盖实际拖到 PDF/CBZ 四角并读取系统截图像素、SDK/product/settings 不变、平移后的真实 PDF 选字/语义边界、四向语义动作、越界/取消/多指、单轴溢出翻页、fit/reflow 原交互、旋转及真正重开。

原 SDK/transport、Host16、Search15、Navigation18、Reading16、Preferences17 与 CBZ10 全部在同一源码保留。构建、语法、夹具生成、测试及工件解析仅 Actions。真机、TalkBack语音、配色、性能与六平台完整产品独立跟踪。

## 重启前检查点（2026-10-25 00:40:57 UTC）

- 工作区 `C:/Users/Oscar/.codex/worktrees/reader-android-sync-session/EXReader`；功能分支 `codex/reader-android-fixed-pan`。源码、测试、工作流已提交推送。受测源码是 `d199f0dc67ed929ad7c5a3fe8edb855ef50f1f67`；上一次纯文档检查点 `5e1d839c55615ad44a5d92461637804098ef67bc` 已用 `git ls-remote` 确认在远端，工作树当时干净。本次随后提交最小诊断留存修正与这两份文档，信息含 `[skip ci]`，精确最终 HEAD 由交回消息列出。
- [run 40146403326](https://github.com/NoGod3524/EXReader/actions/runs/40146403326)，attempt 1，job `121028566204`，已自然 `completed/failure`。完整宿主/测试 APK 编译及原生审计通过；Host16、Search15、Navigation18、Reading16、Preferences17、CBZ10 共 92 项 UI 同源通过。新 Pan 首阶段在 `json.loads(private('fixed-pan-ui-first.json'))` 报 `JSONDecodeError`，新授予检查为 0；尚未定位仪器化根因，不能据此断言 SDK 或平移实现故障。
- 原工件 `12580498901`，146190324 B，SHA-256 `51d6ea82c9ccc4f9ca0f7fc960826d986c924b544cdc303ed7f66848adfaceda`，有效期 `2027-01-23T00:21:56Z`，保留未改。已保存原 `first-instrumentation.txt`；旧驱动在解析报告前未保存 raw report/logcat，故当前日志不足定位。最小留存修正现先保存原报告字节与 logcat，解码失败时打印原仪器化与原字节；所有验收断言保留。该修正尚未执行，不为它新开运行。
- 运行未被停止或重跑，没有另开新轮。已有 CBZ 完整交付仍是起点 `6b43e835`，不受本次未验收平移影响。
- 首轮 `e2f177f5` / run `40145782695` 在去掉新四象限清单里无关的旧 PDF 搜索预期后取消，原工件 `12580996162` 保留。`1c7e1634` / run `40145939682` 在 ReaderView 平移条件少一右括号处编译失败，原工件 `12580242735` 保留；`d199f0dc` 已修该语法错误，未改测试断言。完整字节/散列见 [检查点 JSON](validation/reader-android-fixed-pan.json)。

下个真实动作：重启后在 Actions 只读下载上述原 ZIP，核对完整身份后读取 `android-fixed-pan/ui/first-instrumentation.txt` 及实际留存文件，定位原仪器化/报告生成根因；本地不下载或解析 ZIP。随后按真实错误做最小修正，以包含诊断留存修正的源码跑完整同源整轮，保留所有旧断言与失败原件。只有新 first7 + reopen1 和全旧套件真实成功后，再开独立 `codex/reader-android-fixed-pan-proof`，在 Actions 独立解码保存的系统截图并严格复查 9 个角像素、15 份 PNG、14 次原件身份和两个真实进程。可参考此前只读 CBZ proof source `234389f986f8ea8c83d1b8e3c6e0f8174c3469a6`；Pan 报告字段为 `display_pixels`、`pan_frames`，检查名从本包 `run_ui.py` 的 `expected` 读取。诊断保持 `diagnostic_only=true, accepted=false`，不得合入 `*-proof`。本次不启动上述后续云端工作。

## 重启后的原件诊断

只读诊断 source `7d8a9913962517ec581220e00b383bb0951307ea` / run `40153537765` / job `121049911211` 在 Actions 内核对原失败 run、attempt、artifact 完整大小和 ZIP SHA-256 后成功读取 `first-instrumentation.txt`。原输出明确显示第一项四角像素检查 status 0；第二项 `panned_pdf_selection_and_clipped_semantic_bounds_match_actual_page` 开始后报 `INSTRUMENTATION_RESULT: shortMsg=Process crashed.`、`INSTRUMENTATION_CODE: 0`。因此后续空报告 JSON 解码错误不是最初故障；原 ZIP 不含 raw report 或 logcat，尚不能判定崩溃根因。

诊断 source `d82f008c` / run `40153716101` / job `121050442774` 仅在 Actions 内恢复同一 ZIP 的原宿主 APK、原 Pan instrumentation APK 和七份原件，以原 API34 default x86_64 pixel_6 配置重放 Pan first 阶段并保存 main/crash/system logcat 与 raw report；不重编译、不替代原92项回归，不授予验收。该诊断由 `workflow_dispatch replay_saved_failure=true` 显式启用，完整工作流作业被排除。真实 crash log 明确为主线程 `AssertionError: panned real marker semantic node visible`，出自本包 `selectBottomRight`，不是 native 崩溃。主线程测试断言原来会直接杀进程，现转回 instrumentation 线程生成原失败报告，原断言保留。

宿主 `FixedSession` 原把公开 PDF text 的原生坐标直接当 Canvas 左上坐标。修正只在 app-private JNI 使用原 PDF、公开 `exr_fixed_pages` 的 geometry 和公开 `exr_viewport_create(scale=1)`，读取与 `exr_fixed_render` 相同的 crop/rotation/y-axis 矩阵，再统一转换宿主选区和语义几何；不改冻结 SDK 或 Java bindings。矩阵目录限制 10,000 页，原件仍限 32 MiB。旋转后语义行沿实际文字基线聚合，避免 90/270 度文字逐字拆行。

新 Pan 夹具另加四份 `/CropBox [100 200 700 1000]`、`/Rotate 0/90/180/270` 的真实 PDF，SDK 读取前手写声明每个旋转的可见/裁剪角标及 600×800 或 800×600 视口；没有复制另一套 viewport 矩阵。原第二项检查内逐一用真实宿主控件打开、缩放和平移，验证渲染尺寸、语义裁剪、实际指针选择的精确原文，以及 SDK/product/settings 不变。Pan 仍是 first7+reopen1，现有原件为11份，原92项夹具和断言不变。新源码尚待完整云端整轮，`accepted=false`。

source `094d475e2d8860c30ffcc2fb903d5aa9747706e9` / run `40154163799` / job `121051820296` 完整轮中原92项全部同源通过，新四角 RGB 检查通过。第二项在新增的 crop270 精确选字处失败，完整报告正常留存。只读诊断 run `40155347245` / job `121055463655` 在 Actions 内核对该原 ZIP 后确认 crop0/BRA、crop90/TRA、crop180/TLA 均通过；crop270 只选出 `B`，同时 ReaderView 高度由1766降到1618。真实宿主首次选字才把底部工具条从 GONE 改为 VISIBLE，使活动指针下的视口在拖选中途改变。修正在显式 Select 模式开启时先预留空工具条（INVISIBLE），选字仅揭示操作而不重新布局；清除选区时保留此空间直到退出模式。原精确 `BLA` 断言不变，并增加拖选前后实际视口尺寸、offset完全不变的检查。此修正需要新同源完整轮。

source `d509751501ac3d12b9a5bbb4b5388712a45be1e6` / run `40155515246` / job `121055966707` 已自然 failure：旧92项全部通过，Pan 前六项（包括四个裁剪旋转的精确选字、语义平移、取消、多指、单轴翻页及固定页/重排原交互）通过；第七项旋转重建时探针对临时无页面的 frame 直接 `getLong("book")`，报 `JSONException: No value for book`。等待条件改为先用 `optLong` 等待真实目标 book 和新 view，保留原超时及最终页面/zoom/pan/原件断言，不把临时空 frame 当成功。

显式 Select 预留空间方案不能覆盖长按同帧进入选择模式，因此最终共享修复改为原生 `FrameLayout` 叠放上下文工具条：没有选区时完全隐藏，有选区时沿已有 viewport 转换判断位置，显示在选区另一侧。显示、隐藏及移动工具条都不参与 ReaderView 的尺寸分配，显式 Select 和真实450ms长按均走同一回调，无常驻空工具条。四个裁剪旋转各执行显式 Select 与真实650ms长按再拖动两条路径，精确选出同一声明角标，逐次保存 `before_mode/before_down/held/after` 实际 frame，严格要求宽高/offset/token不变，并核对工具条不盖住所选角标。新源码仍需完整同源整轮，不继承 d509 的通过数。

## b259 同源验收与静态后续

本节之后的状态覆盖以上历史候选的“待运行”说明。b259整轮实际通过：Host16、Search15、Navigation18、Reading16、Preferences17、CBZ10，以及Pan first7/reopen1。四个非零CropBox的0/90/180/270旋转均由显式Select和真实长按650ms后拖动精确选中BRA/TRA/TLA/BLA；八组进入模式、按下、长按保持、结束观测严格保持实际视口宽高、offset及页面token，工具条不遮住所选角标。真实旋转重建与force-stop后重开也通过。配色、真机、TalkBack语音、性能、完整六平台产品仍未授予。

独立只读proof分支 `codex/reader-android-fixed-pan-proof` 不合入主线。首次proof `40158522030` 对原驱动未要求的 `before_down.selection_mode` 加了额外前提而拒绝；公开无障碍extras可能保留前一次模式位。checker已回到原受测契约：保留几何/token/原文严格比较及held/after真正已进入选择模式的检查，移除额外缓存前提，不改b259生产或原断言。修正proof仍待终态，不能称独立proof已通过。

静态自审：10,000页矩阵目录上限与冻结SDK `src/pdf_pages.c` 的原PDF页数/Count上限一致，不是新增更窄的PDF限制。`nativeViewports` 的二次PDF打开及逐页矩阵读取确实只在Java调用前后执行HostTask.check；没有把HostTask传给公开open options.control，这是新增native段的协作取消缺口。当前100项不验证该新增段内部取消，也不验证10,000页边界。最小后续是复用现有host_task_control给打开过程传control，并在逐页循环调用现有host_cancelled；原件释放与未发布结果屏障保持。该后续须新共同源码验证，不能沿用b259证据授予。
