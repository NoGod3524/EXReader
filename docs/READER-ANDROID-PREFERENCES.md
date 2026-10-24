# Android 原生阅读设置

固定宿主起点 `5d7da81495e545901f7fc802af00e0b779d1d8c4`；分支 `codex/reader-android-preferences-ui`。
本轮仍待 Actions，尚未授予任何新增设置能力。

F3 原交回 `f453af14852ad3d8833d27c0eb6888f804c12050` 相对原受测 `6f33caf83bfb845e27db6382edc5ee100d8db954` 仅两份证据文档。宿主起点已含后续加固；按主线确认保留来源 `ba25961961ae69222bfed4f7a98cb02bb1dc6847` 的 Preferences 树 `a3e53123e861ac7ceb2c5fee4829288822229211`。相对原 F3 树 `bdcddad86ae3898c4cfbfbbb181777f9f55436d4` 仅 `include/reader_preferences.h`、`src/preferences.c`、`src/json.c` 三文件差异：文件上限只可下调、严格数字前导零/有效位处理及独立 parser 状态传递。本轮不改模块。

## 宿主契约

- 仅 `-PexrPreferences=true` 打开；使用安装后的 `EXReaderPreferences 0.1.0`，与公开锚点接线一起启用。
- F3 留在原 SDK host DSO，单一既有 worker；不添加线程、产品表、同步实体、SQLite 或 SDK provider。
- `阅读更多操作 → 阅读设置` 是低频原生面板。字号、行距、段距、页边距传给真实 SDK 布局，固定缩放传给实际固定页 render；翻页方向与点击/滑动/方向键作用于原 ReaderView。
- 默认 24 pt / 1.6 / 12 pt / 48 pt / light / ltr / tap / 100%；数值范围由安装的 F3 验证，组合视口由实际 SDK 布局验证。旧 SharedPreferences 中实际存在的 font/zoom 按显式 present 位导入，未列字段保留 F3 默认。
- 应用时先公开 capture 当前页真实点，独立 resolve 必须 FOUND，再以新配置建立候选 pager 并找到含该点的页面。bounded EPUB 保持 spine/path，legacy EPUB 保持 global 投影。旧进度锚点、SDK notes、产品修订/outbox 不因设置而写入。
- 所有候选渲染与可取消读取完成后，进入短发布边界：F3 写同目录临时文件、flush/fsync、原子 rename；save 成功才接受候选页及新内存值。进入发布后不再取消，符合原子 save 在 rename 成功后返回 OK 的契约。保存失败或此前取消保留旧文件/值/页面。
- 私有位置 `files/reading-settings/preferences.json`；进程内跨 Activity 的静态锁与 owner epoch 防止旧 owner 晚保存。新进程和旋转载入同一个文件；坏格式/未知版本不自动重写原文件。

CBZ 在本包只授予实际固定页缩放。旧阅读记录宿主显式拒绝 CBZ 产品捕获，属于该宿主尚未接线：冻结 SDK 实际有真实空文本 provider，点 capture 与独立 FOUND 需下一轮实测。本轮一并纠正旧阅读文档的错误归因，不把拒绝测试当作 SDK 缺能力。

## 阅读页配色缺口

冻结 SDK 的 `exr_layout_config.page` 只接受几何，`exr_render_page_ex` 接受 channels/control，缺整页背景及全局前景覆盖参数。CSS 可影响文档盒/字形，但不能可靠填充页边及覆盖所有作者颜色。深色选择暂拒绝且不保存；`system` 在系统浅色时可保存，系统变深色时明确提示配色未支持并保留 SDK 原图。不重染位图，不以 chrome 配色宣称阅读主题通过。云端将记录真实 CSS 深色尝试、请求色与原 SDK 输出角像素，阅读页颜色仍不授予。

## 云端出口

工作流 `reader-android-preferences.yml` 在同源码保留原全部回归、正式宿主16、搜索15、导航18及阅读记录16，再运行新增设置正反例和三进程重开/系统主题观察；Debug/Release 均保存安装包、符号/provider/链接证据。所有构建、语法检查、夹具、测试和工件解析仅在 Actions。

新增探针包含实际文字/EPUB 字形及位图、独立点、真实目录只读导致的 save IO、范围/组合几何、取消/旋转、PDF/CBZ native scale、RTL/vertical/swipe/key 输入、未知版本/截断/超限加载与系统深色拒绝。真机、TalkBack语音、产品性能、阅读页配色及六平台完整产品仍单列。
