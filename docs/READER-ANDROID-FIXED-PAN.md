# Android 固定页视口平移

固定起点 `6b43e83537aa6b03bda889d258fe73c0e317acb1`；分支 `codex/reader-android-fixed-pan`。等待首次 Actions，尚不授予新增范围。

## 原生页面配色的真实缺口

冻结 `9854061be331fe603a1822d9b2b36ee357154927`：`include/exr/render.h` 的 `exr_render_page_color` 只有 layout/font/page/bitmap/error，选择 RGBA 输出而非主题；`exr_render_page_ex` 也只增加 channels/control。`src/raster.c::render` 公开路径先把整页缓冲设为白色。`layout_config.user_css` 能影响文档盒和文字，但没有整页底色参数，不能可靠覆盖页边与全部作者色。Java 重排页的真实 layout/font 句柄、bounded pager 的窗口文档均未公开，不能借私有字段重建忠实副本。现阶段保留实际 CSS 尝试失败及 `page_colors_accepted=false`；不改变 SDK，不把外围换色或整图反相当成完整阅读主题。

## 平移契约

只改 Android 宿主 `ReaderView`：实际固定页在原 Canvas 目标上平移，不重绘/重新分页/重新捕获锚点，不改页面位图。超出可用视口一像素以上的方向才允许平移；每个方向都夹紧到距边缘 8 px 的内容边界。无溢出方向保留原翻页规则。拖动在有溢出的主方向被认定后持续消费本次手势，边缘不转化为翻页；点击、硬件和原 forward/back 语义仍负责翻页。选字模式保留原文字拖选优先级。

平移量仅为当前 view 的瞬时状态，换页/重新发布页面复位，尺寸改变时夹紧，重开与旋转不持久化它。取消和多指接触不会制造点击/翻页。相同实际 offset 同时用于 Canvas、文本命中、选区覆盖与虚拟无障碍节点边界；被视口裁掉的行标为不可见。标准四向无障碍滚动动作用于平移，原 forward/back 仍翻页。

## 云端验证出口

新夹具在任何 SDK 读取前登记 600×800 非对称四象限 RGB、四个角落采样点及 PDF 字标；PNG/CBZ 与 PDF 对象图由独立 Python 写出。新 7+1 两进程检查覆盖实际拖到 PDF/CBZ 四角并读取系统截图像素、SDK/product/settings 不变、平移后的真实 PDF 选字/语义边界、四向语义动作、越界/取消/多指、单轴溢出翻页、fit/reflow 原交互、旋转及真正重开。

原 SDK/transport、Host16、Search15、Navigation18、Reading16、Preferences17 与 CBZ10 全部在同一源码保留。构建、语法、夹具生成、测试及工件解析仅 Actions。真机、TalkBack语音、配色、性能与六平台完整产品独立跟踪。
