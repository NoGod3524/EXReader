# 整页阅读背景：下一 SDK 候选提案

状态：用户已明确选择“允许独立新SDK候选（推荐）”。独立分支 `codex/sdk-page-background` 已实现；原产品共同线仍固定 `9854061be331fe603a1822d9b2b36ee357154927`，3.40.0 / ABI1。新候选尚未授予整产品配色或全SDK发布。

初轮 source `b911815e26a10e7c45f50f56bf7c4e46cbca010b` / run `40164920053` / attempt1 在Linux通过原native164项及新安装消费者535断言；12个样本的三个旧入口输出与独立重建的985冻结版逐字一致。后续三桌面source `edddc463c06ed5731195cdb8f06b2df6dff7699e` / run `40165924012` 和共享模块双版本验证仍在执行；不把初轮Linux结果外推为六平台或宿主授予。

## 当前缺口与源码证据

冻结版 `src/raster.c` 的 `exr_render_page_ex` 分配位图后，以 `memset(...,255,...)` 初始化整张画布。`include/exr/render.h` 的三个公开重排渲染入口均没有画布背景参数。书籍CSS能改变内容与字色，不能控制内容外的整页空白。GTK两项真实配色失败与Android明确未授予的page_colors保留。

公开 `exr_layout_create_positioned` 允许在绘制序列最前放完整背景box，但它不是任意重排页面的无损克隆入口：`src/positioned.c` 会重新验证文字范围、节点/资源、各行glyph顺序及box flags，并重新适配视口、设置SHAPED标志、加载图片。其block flags接受集合也不覆盖公开layout头中的全部border标志。对有界EPUB还缺少对应完整document的廉价借用入口。因此，不能把普通TXT上的背景box成功外推为任意书页、RTL、边框和图片均保持原样。没有修改现有宿主来尝试这条不完整的替代路径。

## 最小新增接口

若用户允许，另开SDK增量候选，建议添加一个C ABI函数，复用原渲染循环：

```c
exr_status exr_render_page_background(
    const exr_layout *layout, exr_font *font, size_t page,
    unsigned channels, uint32_t background_rgba,
    const exr_control *control, exr_bitmap *out, exr_error *error);
```

背景为straight `0xRRGGBBAA`；只改变新画布的初始像素，之后仍按原有绘制次序和混合规则绘制全部书籍背景、边框、文字、彩色字体与图片。channels保持原1或4限制；灰度转换沿用引擎现有规则。预取消、渲染中取消与错误仍清空输出，页位图64MiB上限和所有旧工作区/CPU预算不变。

旧三个入口始终显式传白色，要求旧调用的输出逐字不变；不扩展既有结构体、不改ABI1、不改wire、anchor、产品schema。只加新符号和独立版本记录。旧3.40冻结提交、旧六包与旧证据保持原样；应用只有在新候选通过并明确迁移固定SDK来源后才接入新函数。

## 验收出口

全部检查在Actions执行：保留原SDK渲染、可靠性、安装后消费者与六目标包门禁；旧入口和新增白底入口与原始输出逐字比较。新增浅/深色整页外边距、原书显式白底块、含白色与透明像素的图片、透明/半透明文字、彩色字体、RTL与竖排、表格与多种边框，以及有界EPUB较后页面的实际输出。书籍图片和显式样式不能随页面背景被整体染色。逐取消点验证清空输出并可恢复；原页/节点/文本/锚点与输入位图保持不变。

新SDK证据齐后才跑GTK/Android原有实际控件与截图测试；原两palette失败不删除、不改名、不改成skip。新函数和新平台证据不得回填为旧3.40已具备能力。真正tag/Release仍另行授权。
