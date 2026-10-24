# Android 原生阅读设置

固定宿主起点 `5d7da81495e545901f7fc802af00e0b779d1d8c4`；分支 `codex/reader-android-preferences-ui`。
API34 `default` x86_64 模拟器声明范围验收通过。受测源码 `657ea2ccf37087b608155169a2fcecdf28fe8f33`；[run 40138266576](https://github.com/NoGod3524/EXReader/actions/runs/40138266576) attempt 1、job `121004337573` 全部 success。阅读页配色仍未授予。

F3 原交回 `f453af14852ad3d8833d27c0eb6888f804c12050` 相对原受测 `6f33caf83bfb845e27db6382edc5ee100d8db954` 仅两份证据文档。宿主起点已含后续加固；按主线确认保留来源 `ba25961961ae69222bfed4f7a98cb02bb1dc6847` 的 Preferences 树 `a3e53123e861ac7ceb2c5fee4829288822229211`。相对原 F3 树 `bdcddad86ae3898c4cfbfbbb181777f9f55436d4` 仅 `include/reader_preferences.h`、`src/preferences.c`、`src/json.c` 三文件差异：文件上限只可下调、严格数字前导零/有效位处理及独立 parser 状态传递。本轮不改模块。

## 宿主契约

- 仅 `-PexrPreferences=true` 打开；使用安装后的 `EXReaderPreferences 0.1.0`，与公开锚点接线一起启用。
- F3 留在原 SDK host DSO，单一既有 worker；不添加线程、产品表、同步实体、SQLite 或 SDK provider。
- `阅读更多操作 → 阅读设置` 是低频原生面板。字号、行距、段距、页边距传给真实 SDK 布局，固定缩放传给实际固定页 render；翻页方向与点击/滑动/方向键作用于原 ReaderView。
- 修复原固定页 zoom 被 fit-to-window 抵消的问题：同时提高 SDK 栅格采样和实际 Canvas 目标尺寸。使用 draw/settled 后的真实 scale×fit 验证视觉倍率；大于100%时居中放大，平移另行跟踪。
- 方向键模式下阅读视图可在触摸模式持有焦点，关闭设置/点击阅读页后保留实际焦点；首个真实 D-pad 按下应直接翻页，不能被系统仅用于从触摸切换焦点。
- 默认 24 pt / 1.6 / 12 pt / 48 pt / light / ltr / tap / 100%；数值范围由安装的 F3 验证，组合视口由实际 SDK 布局验证。旧 SharedPreferences 中实际存在的 font/zoom 按显式 present 位导入，未列字段保留 F3 默认。
- 应用时先公开 capture 当前页真实点，独立 resolve 必须 FOUND，再以新配置建立候选 pager 并找到含该点的页面。bounded EPUB 保持 spine/path，legacy EPUB 保持 global 投影。旧进度锚点、SDK notes、产品修订/outbox 不因设置而写入。
- 重复 legacy 章节的空范围点可能 AMBIGUOUS；此时只从该页真实 SDK 边界 capture 不超过64KiB的可见范围，再独立 resolve，仍须 FOUND。该范围的真实起点保持页首；若仍歧义则拒绝，不将旧偏移或章节序号当作 FOUND。
- 所有候选渲染与可取消读取完成后，进入短发布边界：F3 写同目录临时文件、flush/fsync、原子 rename；save 成功才接受候选页及新内存值。进入发布后不再取消，符合原子 save 在 rename 成功后返回 OK 的契约。保存失败或此前取消保留旧文件/值/页面。
- 私有位置 `files/reading-settings/preferences.json`；进程内跨 Activity 的静态锁与 owner epoch 防止旧 owner 晚保存。新进程和旋转载入同一个文件；坏格式/未知版本不自动重写原文件。

CBZ 在本包只授予实际固定页缩放。旧阅读记录宿主显式拒绝 CBZ 产品捕获，属于该宿主尚未接线：冻结 SDK 实际有真实空文本 provider，点 capture 与独立 FOUND 需下一轮实测。本轮一并纠正旧阅读文档的错误归因，不把拒绝测试当作 SDK 缺能力。

## 阅读页配色缺口

冻结 SDK 的 `exr_layout_config.page` 只接受几何，`exr_render_page_ex` 接受 channels/control，缺整页背景及全局前景覆盖参数。CSS 可影响文档盒/字形，但不能可靠填充页边及覆盖所有作者颜色。深色选择暂拒绝且不保存；`system` 在系统浅色时可保存，系统变深色时明确提示配色未支持并保留 SDK 原图。不重染位图，不以 chrome 配色宣称阅读主题通过。云端已记录真实 CSS 深色尝试、请求色与原 SDK 输出角像素，阅读页颜色仍不授予。

## 云端出口

工作流 `reader-android-preferences.yml` 在同源码保留原全部回归、正式宿主16、搜索15、导航18及阅读记录16，再运行新增设置正反例和三进程重开/系统主题观察；Debug/Release 均保存安装包、符号/provider/链接证据。所有构建、语法检查、夹具、测试和工件解析仅在 Actions。

新增探针包含实际文字/EPUB 字形及位图、独立点、真实目录只读导致的 save IO、范围/组合几何、取消/旋转、PDF/CBZ native scale、RTL/vertical/swipe/key 输入、未知版本/截断/超限加载与系统深色拒绝。真机、TalkBack语音、产品性能、阅读页配色及六平台完整产品仍单列。

## 实际同源码证据

新增 **17/17**：首进程15、fresh process reopen1、真实系统 night1。PID `7583 / 7783 / 7901`；10份实际语义树/PNG、七份合成原件三个阶段共21次字节/SHA核对。原导出/roundtrip/WebDAV、正式宿主16、搜索15、导航18、阅读记录16与全部 Debug/Release 安装/provider 检查同源保留并通过。

文本实际字号30、行距1.8、段距18、margin40后，真实字形字号30、首x40、首个baseline差54；原公开点559仍在新页 `[352,598)`。legacy EPUB 的歧义空点改由公开可见范围 capture、独立 FOUND；selector/chapter由公开capture原样产生。PDF/CBZ 的真实视觉倍率经 draw/settled 后 `render_scale × fit` 及 Canvas 目标宽度验证，并保留实际PNG。首个真实 D-pad DOWN 日志为 `code=20 action=0 repeat=0 input=4 operation=0 selected=false focus=true`，UP时 operation3，实际下一页已绘制。

最终文件390 B，三个进程/主题阶段的 SHA-256 均为 `a841f7d1a53442253b383608496bda4c05d3194b12e219285bcd4e9afa3309ff`。载入并实际应用 `36 / 2 / 20 / 44 / system / ltr / tap / 150%`；旋转时未发布候选被取消，原文件保留。真实深色 CSS 尝试请求背景 `101010ff`，SDK角像素实际 `ffffffff`，该失败按 `accepted=false` 保留；系统深色重启显示明确配色缺口，文件不改。

原工件 `reader-android-preferences-40138266576-1`：ID `12577914277`、141,737,458 B、SHA-256 `2bd1a2ac79ef6474bcf8cd272057184b435ac29e97dc4d04ed4261b6fc50c71c`，有效至 `2027-01-22T22:22:19Z`。安装 F3 archive 160,656 B / `e3ffee5742820a47b0ddfa9f8ef098e1fe65adc39b1ae4db32ded067dcf39126`；其定义只位于原 SDK host DSO，产品 owner/唯一产品SQLite不变。

独立只读 Actions [40139310222](https://github.com/NoGod3524/EXReader/actions/runs/40139310222)（源码 `9dc28784e28c010307b0bba4de7941fa76dfc325`、job `121007466989`）实际下载原 ZIP，核对完整身份、17逐项报告、10PNG、21原件记录、三份设置文件、真实首键DOWN/UP及安装archive/header，全部通过。诊断自身 `diagnostic_only=true, accepted=false`；`codex/reader-android-preferences-proof` 诊断分支不合入产品。

六次失败及一次取消全部保留在 JSON：legacy重复spine点歧义、对话框关闭后的空semantic root、固定zoom被fit抵消的根因修复及首个D-pad因触摸模式焦点而丢DOWN的实测定位均有原件。取消的中间源码只因进一步要求旋转后真实book bitmap就绪；不授予运行结果。最终纯证据提交仅更新本文件与验收JSON。
