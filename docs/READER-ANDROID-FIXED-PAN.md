# Android 固定页视口平移

固定起点 `6b43e83537aa6b03bda889d258fe73c0e317acb1`；分支 `codex/reader-android-fixed-pan`。重启前源码检查点 `d199f0dc67ed929ad7c5a3fe8edb855ef50f1f67` 已推送；云端仍在执行，`accepted=false`，尚不授予新增范围。

## 原生页面配色的真实缺口

冻结 `9854061be331fe603a1822d9b2b36ee357154927`：`include/exr/render.h` 的 `exr_render_page_color` 只有 layout/font/page/bitmap/error，选择 RGBA 输出而非主题；`exr_render_page_ex` 也只增加 channels/control。`src/raster.c::render` 公开路径先把整页缓冲设为白色。`layout_config.user_css` 能影响文档盒和文字，但没有整页底色参数，不能可靠覆盖页边与全部作者色。Java 重排页的真实 layout/font 句柄、bounded pager 的窗口文档均未公开，不能借私有字段重建忠实副本。现阶段保留实际 CSS 尝试失败及 `page_colors_accepted=false`；不改变 SDK，不把外围换色或整图反相当成完整阅读主题。

## 平移契约

只改 Android 宿主 `ReaderView`，接在已有 Preferences 真实固定页缩放路径上：实际固定页在原 Canvas 目标上平移，不重绘/重新分页/重新捕获锚点，不改页面位图。超出可用视口一像素以上的方向才允许平移；每个方向都夹紧到距边缘 8 px 的内容边界。无溢出方向保留原翻页规则。拖动在有溢出的主方向被认定后持续消费本次手势，边缘不转化为翻页；点击、硬件和原 forward/back 语义仍负责翻页。选字模式保留原文字拖选优先级。

平移量仅为当前 view 的瞬时状态，换页/重新发布页面复位，尺寸改变时夹紧，重开与旋转不持久化它。取消和多指接触不会制造点击/翻页。相同实际 offset 同时用于 Canvas、文本命中、选区覆盖与虚拟无障碍节点边界；被视口裁掉的行标为不可见。标准四向无障碍滚动动作用于平移，原 forward/back 仍翻页。

## 云端验证出口

新夹具在任何 SDK 读取前登记 600×800 非对称四象限 RGB、四个角落采样点及 PDF 字标；PNG/CBZ 与 PDF 对象图由独立 Python 写出。新 7+1 两进程检查覆盖实际拖到 PDF/CBZ 四角并读取系统截图像素、SDK/product/settings 不变、平移后的真实 PDF 选字/语义边界、四向语义动作、越界/取消/多指、单轴溢出翻页、fit/reflow 原交互、旋转及真正重开。

原 SDK/transport、Host16、Search15、Navigation18、Reading16、Preferences17 与 CBZ10 全部在同一源码保留。构建、语法、夹具生成、测试及工件解析仅 Actions。真机、TalkBack语音、配色、性能与六平台完整产品独立跟踪。

## 重启前检查点（2026-10-25 00:35:15 UTC）

- 工作区 `C:/Users/Oscar/.codex/worktrees/reader-android-sync-session/EXReader`；功能分支 `codex/reader-android-fixed-pan`。源码 HEAD 与 origin 均为 `d199f0dc67ed929ad7c5a3fe8edb855ef50f1f67`，源码、测试、工作流均已提交推送，工作树干净。本次随后仅提交这两份检查点文档，提交信息含 `[skip ci]`，精确文档 HEAD 由交回消息列出。
- [run 40146403326](https://github.com/NoGod3524/EXReader/actions/runs/40146403326)，attempt 1，job `121028566204`，该时刻为 `in_progress`、conclusion 为 null。完整宿主/测试 APK 编译及原生审计已结束，正在 `Actual SDK owner import and public original export in Android private storage`。尚未读取终态逐项结果，不能认定 Pan8 或继承 UI 套件通过。
- 该云端任务保持原样运行；不停止、不重跑，不另开新轮。已有 CBZ 完整交付仍是起点 `6b43e835`，不受本次未验收平移影响。
- 首轮 `e2f177f5` / run `40145782695` 在去掉新四象限清单里无关的旧 PDF 搜索预期后取消，原工件 `12580996162` 保留。`1c7e1634` / run `40145939682` 在 ReaderView 平移条件少一右括号处编译失败，原工件 `12580242735` 保留；`d199f0dc` 已修该语法错误，未改测试断言。完整字节/散列见 [检查点 JSON](validation/reader-android-fixed-pan.json)。

下个真实动作：重启后先只读查上述既有 run/job 的实际终态，再读原始日志/工件。若失败，按真实错误修最小根因并保留旧失败；若 success，逐项确认新 first7 + reopen1 及全旧套件。随后再开独立 `codex/reader-android-fixed-pan-proof` 诊断分支，在 Actions 下载原 ZIP 核对身份并独立解码保存的系统截图，严格复查 9 个角像素、15 份 PNG、14 次原件身份和两个真实进程。可参考此前只读 CBZ proof source `234389f986f8ea8c83d1b8e3c6e0f8174c3469a6`；Pan 报告字段为 `display_pixels`、`pan_frames`，检查名从本包 `run_ui.py` 的 `expected` 读取。诊断必须保持 `diagnostic_only=true, accepted=false`，不得合入 `*-proof`。只有原运行及独立证据完成后才把本包 accepted 改为 true。
