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
| 主题、四个RGBA颜色 | 重排前景与内容背景通过user CSS；GTK外观和选择文字层通过原生CSS |
| 翻页方向、操作偏好 | 页面的点击/拖动与硬件分页键；LTR/RTL/vertical各有实际轴向规则 |
| 固定页缩放 | 原公开fixed render及原2048像素上限；F5/F6也更新独立设置文件 |

固定页保留PDF/CBZ原作颜色，字号等重排参数不改写固定页内容。重排公开render没有画布背景选项，
其外侧页边距可能仍是白色；工作流记录实际像素，未采用替换白色像素、全局反色或图像重着色。

System主题观察 `org.freedesktop.portal.Settings` 的appearance/color-scheme（Settings API v1，
实现该键的desktop portal），并观察GTK3的theme-name/application-prefer-dark-theme作为缺省路径。
设置为明确Light或Dark时不跟随平台变化。平台读取异步且有界，不创建常驻轮询。

点击/拖动只作用于渲染页面，不抢占可选择文字和注释输入。Hardware keys模式启用对应方向的箭头键
及PageUp/PageDown；明确的工具栏和F3/F4前后页快捷键始终保留。其它操作模式关闭额外硬件分页键。

工作流 `reader-gtk-preferences.yml` 同源保留F3安装消费者20项、原46+105+4、定向AT-SPI10项，
追加35项真实设置UI检查：每个布局字段的实际分页、颜色像素、真实portal切换、所有翻页操作、固定页
实际bitmap尺寸、重开、显式旧设置导入、损坏/未知记录、实际原子保存失败和父窗口关闭barrier。
全部构建、语法、夹具和证据处理只在Actions。当前尚未执行，不授予验收。
