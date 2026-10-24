# GTK 原生阅读设置

从 `8a7cab996f7b3a876254f16a90dab69bbeb9f15a` 接续。SDK 固定
`9854061be331fe603a1822d9b2b36ee357154927`，复用审查通过的 F3 实现
`1f51b4066cd705a670b3139061336c298e479081`，不修改设置包、SDK、schema或wire。

通过书架 More 中的 Reading settings 或 Ctrl+, 打开低频原生模态面板。默认值来自已安装的
EXReaderPreferences 0.1.0。恢复默认和旧设置导入先显示草稿，用户选择 Save 才保存并应用。
原 `reader.ini` 的字体/缩放不自动导入，也不被新设置悄悄覆盖；书籍位置和书架状态继续按原路径保存。
新设置使用独立 `preferences.json`。加载失败保留当前有效记录，未知版本原件保持，原子保存由现有
SDK owner串行执行；失败不提交候选页面或替换已有设置，关闭等待既有位置保存barrier。

| 字段 | 实际接入 |
| --- | --- |
| 字号、行距、段距、页边距 | 通过公开layout config重建pager；锚点重定位，仍受520×640页的组合几何约束 |
| 主题、四个RGBA颜色 | Light前景通过user CSS应用重排页；四个颜色用于GTK界面，Dark/System只切界面主题 |
| 翻页方向、操作偏好 | 页面的点击/拖动与硬件分页键；LTR/RTL/vertical各有实际轴向规则 |
| 固定页缩放 | 原公开fixed render及原2048像素上限；F5/F6也更新独立设置文件 |

固定页保留PDF/CBZ原作颜色，字号等重排参数不改写固定页内容。重排公开render没有画布背景选项。
run `40091207927`实测Light前景匹配9992像素，而请求的`#FDF4DC`页面背景匹配0，外侧页边距
仍为`(255,255,255)`。背景页像素检查保留失败；页面继续使用可读的Light前景，Dark/System
仅改变原生面板，不将浅字白纸当作可用的Dark阅读页。UI直接说明当前没有阅读页主题。
未采用替换白色像素、全局反色或图像重着色。

System主题观察 `org.freedesktop.portal.Settings` 的appearance/color-scheme（Settings API v1，
实现该键的desktop portal），并观察GTK3的theme-name/application-prefer-dark-theme作为缺省路径。
设置为明确Light或Dark时不跟随平台变化。平台读取异步且有界，不创建常驻轮询。

点击/拖动只作用于渲染页面，不抢占可选择文字和注释输入。Hardware keys模式启用对应方向的箭头键
及PageUp/PageDown；明确的工具栏和F3/F4前后页快捷键始终保留。其它操作模式关闭额外硬件分页键。

工作流 `reader-gtk-preferences.yml` 同源保留F3安装消费者20项、原46+105+4、定向AT-SPI10项，
追加35项真实设置UI检查：每个布局字段的实际分页、页面与原生面板分别采样的颜色像素、真实portal切换、所有翻页操作、固定页
实际bitmap尺寸、重开、显式旧设置导入、损坏/未知记录、实际原子保存失败和父窗口关闭barrier。
全部构建、语法、夹具和证据处理只在Actions。当前迭代已运行，页面背景存在上述真实拒绝，
其余独立检查继续执行；不授予整包通过。

## 最小后续SDK需求

在下一次SDK变更中提供独立页面渲染入口（例如`exr_render_page_with_options`），选项包含
`struct_size`、channels、`0xRRGGBBAA`画布background和现有control。旧`exr_render_page_ex`
继续保持白底和既有ABI/逐字输出。新入口仅改变栅格初始化底色，随后照常绘制原有glyph、box和image，
不重着色作者图形或不透明图片。必须覆盖页边距、透明图片合成、显式作者颜色、取消清空、原64MiB
上限，以及旧入口回归。当前包不修改SDK；该入口与整页Dark主题均未实现或授予。
