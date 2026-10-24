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
全部构建、语法、夹具和证据处理只在Actions。最终同源检查已完成：新UI 33通过、2拒绝，
原套件全部通过；页面背景和Dark阅读页仍未实现，不授予整包通过。

## 最终同源证据

受测源码 `ce912f8c149e30cf3843e39258ae6889235495a0`，
[run 40110581923](https://github.com/NoGod3524/EXReader/actions/runs/40110581923)，attempt1，
实际GTK作业 `120921266256`。工作流为failure，唯一失败步骤是新设置UI中的两项阅读页配色检查；
全部35项均执行，`accepted=false`。实际程序SHA-256为
`4923e07c7790b5fec1fca7c2680a1aa3c2c14b30892b0a26bbec25d788c6b115`。

| 同源范围 | 结果 |
| --- | --- |
| 原F3安装消费 | 20/20 |
| 原账号/接收 | 46/46 |
| 原GTK UI | 105/105（20+5+24+14+15+27） |
| 原故障回归 | 4/4（含真实26项标注故障恢复及字体恢复mutant） |
| 定向AT-SPI | 10/10 |
| 新原生设置UI | 33/35；仅Light整页底色和Dark阅读页配色拒绝 |

原固定页后端11组82断言、私有快照/取消53断言、公开SDK九项与产品十二项消费者及两次真实
进程终止恢复同次通过。字号30使本页结束偏移432→280，行距2.5为432→257，段距48为432→395，
页边距85为432→280；25.5浮点字号实际应用并保存。固定页100%→125%使实际SDK位图
600×800→750×1000；F5更新为150%，真实重开恢复。三方向与四种输入模式的真实点击/拖动/硬件键、
旧设置显式导入、损坏/未知文件、权限导致的真实保存失败及重试、观察到SDK owner后关闭并重开全部通过。
System真实portal事件下原生面板匹配背景像素为Dark45208、Light47319；两种状态的Light阅读页前景均9992。

工件 `12566797535` 为41,212,307字节，SHA-256
`ddc331bedd4b8a4ba1e316531c7d2d7563bdde4a727a53a11fd870f8337636a7`，
有效期2027-01-22T16:13:49Z，同run/source、未过期；ID/字节/digest与原上传日志和API逐项一致。
本最终轮没有独立重新下载ZIP散列。逐项具名结果与全部前轮拒绝见[验证记录](validation/reader-gtk-preferences.json)。

原账号测试及原固定页断言均未修改。本包wrapper加强真实输入就绪：52本逐一核对公开chooser选中文件的
路径散列及按钮敏感状态，每本仅一次Return，等chooser消失、新导入generation及保存结束，仍使用原30秒预算。
原固定页驱动仅等待F3/F4/F5/F6/F8/F10的实际新generation，不重送键。关闭临时凭据bus后先用系统
fusermount卸载严格限于RUNNER_TEMP/gtk-account-*/run/doc的挂载，再执行原清理；清理失败仍拒绝。

保留的后期失败：`40095211918`原46检查已过，但Python3.10清理死portal FUSE挂载抛
ConnectionAbortedError；`40096404519`在第39次原生选择器输入前停住；`40109606798`已完成
52次单次导入，但新wrapper漏掉原脚本同级模块路径，无法导入receive_checks。最终轮逐项重新执行。
只读诊断`40109319296`在Actions重新散列旧ZIP后读取实际host和应用日志，始终`diagnostic_only=true`。

## 最小后续SDK需求

在下一次SDK变更中提供独立页面渲染入口（例如`exr_render_page_with_options`），选项包含
`struct_size`、channels、`0xRRGGBBAA`画布background和现有control。旧`exr_render_page_ex`
继续保持白底和既有ABI/逐字输出。新入口仅改变栅格初始化底色，随后照常绘制原有glyph、box和image，
不重着色作者图形或不透明图片。必须覆盖页边距、透明图片合成、显式作者颜色、取消清空、原64MiB
上限，以及旧入口回归。当前包不修改SDK；该入口与整页Dark主题均未实现或授予。
