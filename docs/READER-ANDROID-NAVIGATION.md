# Android 原生目录与按页入口

固定宿主起点 `e764f08dea4986f11db183c5b17b41ddb5526bcc`；分支 `codex/reader-android-navigation-ui`。只原样引入 F2 源码 `cbd7832b914bddcf99e06a85962d301a00b47efa` 的 `apps/reader/navigation/`，树 `9395914832e191ad63f18f6188ca5044260d2f12`。不合入其分支历史。SDK 保护树与 Search 模块保持原样。

本宿主的原生目录/按页 UI 已在 API34 x86_64 模拟器通过；[记录](validation/reader-android-navigation.json) 只授予下述可证明目标与生命周期范围。所有编译、测试、语法检查、夹具和工件解析仅在 Actions 执行。

## 同源验收

受测完整源码 **`d68d8e388730f0fbd9e86c70a422388be406391d`**，[run 40115551503](https://github.com/NoGod3524/EXReader/actions/runs/40115551503) attempt1，作业 **120935966789** 成功。原件导出8项、18实际捕获的12组、原宿主17+2、DAV91+4、正式账号/接收16项/4进程、书内搜索15项/2进程均在同源码重新执行通过；新增导航 **18/18**（16+2），真实进程 **6328 / 6542**。

保存 **12** 套真实语义树/PNG；六份原件跨两阶段共12行散列复核。45个根条目以32+13实际分页；EPUB3与NCX的Unicode片段都实际到part1，明确接受PART_ONLY后到part2开头；重复路径明确选择第二章后实际part1；完整CFI再由独立公开对象复核并跳转，surrogate内部、折叠空白与损坏CFI保持原页。PDF实际index2、CBZ实际index1，PDF的作者Outlines标题不在列表。

真实旋转期间取消正在解析的旧任务：View **250287194 → 88006385**，实际viewport **1080×1766 → 2146×637**；原件、SDK notes/progress与产品队列保持，复位旋转后Home/手动重开及真实进程重开后再次导航通过。目标跳转前，第二独立公开对象创建的pager已经按当前reader布局逐块与full-document文本比完全部字节，目标标量边界也核对；不假设两种投影天然相同。

工件 `reader-android-navigation-40115551503-1`，ID **12568127459**，**129689309 B**，SHA-256 **`a964ab12f94d2f6693d4aef35bf1bf55693cc6c37636ff418f42365910cc7214`**，有效期 `2027-01-22T17:18:52Z`。包含原回归、正式16、搜索15和导航18的原始日志/报告/PNG，以及SDK实际cache、安装包、Debug/Release ELF、map、NEEDED和四套runner材料。

Navigation安装归档SHA-256 `25d97e6c103ab6d6baa21859a42d428b84b7b099de9bbc25d2b8e5c62f442cad`。Debug/Release均只有原共享SDK provider，产品DSO不含Navigation/Search/SDK；四个运行库闭包按实际NDK API26公有stub核对。实际SDK cache SHA-256 `e597e6f5e1c0512fbff2be9c761a32c2a579d43db07d7c2d3abb7100b852366b`，AUDIO/MP3/JNI/SHARED为ON、AAC为OFF，仍是原Android共享JNI配置。

首轮 `fd5734a548203da94702af26f558d2595a4898be` / run `40114452672` attempt1 编译、包材料/唯一SDK provider、旧全套、正式16与搜索15通过；新导航前14组通过。实际旋转创建新ReaderView时，探针把尚未装书的空帧直接 `getLong("book")`，抛 `No value for book`。测试改用有界等待当前可见ReaderView和实际book/bitmap就绪；原旋转、取消、帧与存储断言保留。另补上述独立pager投影逐字节证明后，以新source重新整轮验收。

## 宿主行为

阅读页“更多”中的“目录 / 按页入口”打开原生列表，每批 32 个当前层级子项；可进入子层、返回上层或继续下一批。保留原 SDK 顺序、标签和层级，不执行标签 HTML。空作者目录明确显示为空。PDF/CBZ 只显示“按页入口 · 非作者大纲”，不读取或声称 PDF 作者 outline。

点击目标先由已安装 Navigation 模块在新打开的公开 SDK 对象上解析，再打开第二个独立公开 SDK 对象复核 part index/path/id、片段节点、完整 CFI 点或固定 page ID，才产生渲染目标。重复路径列出全部候选，由用户明确选择章节；不取第一个。片段缺失只提示 `PART_ONLY`，只有用户再次明确接受“仅打开章节开头”，并重新解析/核对后才跳转。外链仅提示“未打开”，不启动浏览器或网络。

采用 publication 文档节点 offset 前，第二个独立对象还按当前字号与真实 reader 布局创建公开 bounded pager，把每个流式文本块与已借用的文档投影逐字节比较；长度、全部字节与目标标量边界必须一致。不会另拼整章字符串；投影不能证明一致时明确拒绝，不把 full-document 偏移猜作 pager 偏移。

身份 key 来自 `BookStore.verifySource` 验证后的 `format:原书SHA256@exreader-sdk-公开版本`。快照只含模块复制值，不保留 SDK 指针；页面、目标均复制并释放模块输出。创建、查询、解析与关闭使用现有 SDK worker；没有新增线程池、owner registry、SDK 副本或 SQLite。安装后的 Navigation 只以归档和公开头接入原 `exreader_host` 共享 DSO，SDK 符号继续由同一个 `libexreader.so` 提供。

只有实际选择允许改变阅读位置。浏览、分页、拒绝目标、取消与关闭不修改原件、SDK notes/progress 或产品 revision/outbox。关闭、换书、旋转、后台和销毁立即使 epoch 失效、协作取消并由 SDK owner 释放快照；分组/候选/CFI 对话框的过期点击也有 epoch 检查。

## CFI 的精确映射边界

公开 CFI 使用 raw DOM UTF-16，包含 surrogate 内部位置，不能当作规范化 UTF-8 阅读偏移。元素和子节点边界使用独立 SDK 节点公开范围；文本点只在该节点 raw text 与其公开规范化投影逐字节一致，且 UTF-16 位于完整 scalar 边界时映射。折叠空白或 surrogate 内部位置无法证明精确映射时明确拒绝并保持原页，不以 node.start、旧偏移或页号兜底。

## 云端出口

`.github/workflows/reader-android-navigation.yml` 逐字核对冻结 SDK、Search 与固定 Navigation 子树，检查独占路径。API26 安装 SDK/模块并构建 Debug/Release APK及四套 runner；API34 x86_64 模拟器依次执行原导出、18 捕获/原宿主17+2/DAV、正式账号/接收16项、搜索15项，再执行新导航18项（16+2进程重开）。保存安装归档、实际 cache、ELF/map/NEEDED、SDK provider、PNG/语义树/实际 ReaderView 帧与原始 instrumentation 日志。

新夹具沿用固定 F2 写出器，加入35个真实额外目录根以验证32+13分页。覆盖 EPUB3/NCX、层级/Unicode/纯文本标签、重复 spine、外部/越界/未知目标、PART_ONLY明确确认、正常及不可映射CFI、PDF/CBZ页入口、JNI参数/错线程/身份、实际控制回调取消、关闭/旋转/Home及真实进程重开。PDF含作者Outlines，断言其标题不出现在按页列表中。

性能、真机、TalkBack语音和六平台完整产品均未授予。
