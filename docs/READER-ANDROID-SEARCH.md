# Android 书内搜索

本候选从正式账号/接收已通过的固定源码 `ed9ff5ffc3608971bb19020f1ec07496a79d9710` 建立，分支 `codex/reader-android-search-ui`。安装后的 `EXReaderSearch 0.1.0` 保持原样：最后修订 `523a91f0e8c11e4365e0eab7d3687bf05df2d2c0`，源码树 `2e09cb2945564f25085074a816b95472392df205`。未合入 G01–G16。

这是未验收候选。[验收记录](validation/reader-android-search.json) 在完整 Actions 通过前保持 `accepted:false`。本地未运行构建、语法检查、测试或夹具。

首轮源码 `44bd6d2b` 的 [run 40094753066](https://github.com/NoGod3524/EXReader/actions/runs/40094753066) 完成安装包/依赖审计、原 18/17+2/DAV 与原 16 项，新增搜索在测试种子的偏移 8 处被 SDK 拒绝，因为该 TXT 以中文开头。`85f3add0` 修正为边界 0，并保留原 Debug Rebuild 控件；新组尚未授予。失败及原件保留。

第二轮 `85f3add0` / run `40095203666` 的原有回归与正式 16 项仍通过，新增 provider 项通过；搜索弹窗遮挡底层窗口后，测试无法从窗口列表取得真实 ReaderView 帧而失败。探针增加同一个存活 Activity 上真实 View 的主线程 accessibility extras 读取，保留原像素/页面/存储不变断言。搜索与独立 FOUND 解析同时改为复制当前阅读字号，并以先调到 28 再搜索的有界 EPUB 场景覆盖。

第三轮 `18d5ce81` / run `40109097666` 的前四个新增组通过；歧义选择测试误点了包含同一查询文字的输入框，没有选择结果行。探针现在按真实结果行 ID 与可见性选择，歧义不跳转断言保持。审阅同时修正“更多结果”在纵向容器中误用零宽横向权重的问题；只读查询关闭弹窗后也再次比较真实页面、像素和存储。

第四轮 `e3ff5895` / run `40109992266` 的前九组新增检查通过，包含真实 TXT/EPUB/PDF FOUND 导航、28 字号与重复 spine，以及 CBZ 拒绝。JNI 负例把 selector exact 改成不同字节长度，却仍携带原范围，SDK 正确返回 ARGUMENT。测试保留该拒绝断言，另用同长度不存在的 quote 检查 MISSING 不回退；固定页内嵌 NUL 也保持原 quote 长度。SDK 与生产解析逻辑不变。

第五轮 `369b6d24` / run `40110880624` 的首进程 13 组及重启后存储/无恢复搜索检查通过；最后重开 TXT 时，探针在弹窗退出的窗口过渡瞬间只探测了一次 Shelf 控件，漏过点击后直接等待书架而超时。换书 helper 改为有界等待真实可见 reader/shelf 控件，再操作真实 Shelf；最后重启后搜索断言保留。

## 使用与行为

启用 `-PexrSearch=true` 并提供已安装的 `exrSearchPrefix`。当前验证构建同时保留 `exrSync=true` 和原账号/接收功能。阅读页低频“更多”菜单提供“书内搜索”；没有增加常驻搜索栏。Debug 保留原 Rebuild 按钮、ID 与动作；启用搜索的 Release 隐藏该调试按钮，“更多”占用原位置。

输入查询后显式搜索；文字按 SDK 规范化投影作区分大小写的字面匹配。每次只保留最多 32 条结果，以“更多结果”继续下一批。修改输入清除旧结果和游标；取消、关闭和重新打开不会自动恢复或重启查询。空结果、无效查询、SDK 错误及 CBZ 不支持文字搜索各有状态。

搜索、批次继续、取消与关闭只读源文件和 SDK。它们不改变当前页、SDK notes/progress、产品 history/outbox。只有用户明确选择结果、宿主用独立公开 SDK 对象重新解析为 FOUND 后才通过原 `runPage` 导航。MISSING/AMBIGUOUS/LEGACY 保留列表和原页，不用旧偏移、页提示或百分比兜底。EPUB 的 spine index 与 part path 一起保留；固定页按 page ID 找真实页面，不猜测页号。

TXT 使用公开 document；有界 EPUB 使用 publication/font 和逐 spine 的公开 pager；PDF 逐页文字搜索。无文字 PDF 返回正常空结果，不做 OCR。CBZ 明确不支持文字搜索，不把拒绝伪装成空结果。

搜索创建和独立 FOUND 解析使用发起时的当前阅读字号，沿用宿主原有页面尺寸、页边距与字体；不硬编码为初始 24。

## 所有权与包依赖

所有新 SDK 与 Search 调用、关闭都在原宿主 SDK worker 上；没有新线程池或 owner registry。原件先经现有 `BookStore.verifySource` 核对，source key 绑定全局原件身份及 SDK 版本。Search 原生状态只由该 worker 的私有 Java 对象持有；C 层及模块再次检查创建线程。批次结束即复制 route/selector，再释放模块结果；UI 不接触 SDK 指针。

查询通过已有严格 JNI Unicode 转换和模块校验。exact/prefix/suffix 以显式长度的 `byte[][]` 复制，保留 fixed selector 的内嵌 NUL；路径和 nullable chapter 保留原语义。关闭、换书、宿主操作、后台和销毁立即发出协作取消，SDK worker 随后释放 Search、document/publication/font/fixed；主线程不等待扫描结束。公开 reflow find 内部没有更细取消点。

仅把安装后公开 Search target 的归档和头目录接入 `exreader_host`，所有 SDK 符号仍由原共享 `libexreader.so` 提供。Search 的静态 core 依赖闭包不进入宿主，也不进入产品 DSO；产品保持原独立唯一 SQLite。Actions 保存归档定义/未定义符号、实际 map、Debug/Release ELF NEEDED、包体和运行库字节/散列，以及公开 SDK/provider 的运行时身份。

当前仍是原 Android 共享 SDK 配置，非桌面 reading-core 裁剪 preset。现有冻结 JNI 要求 audio/PDF；新出口记录 SDK 实际 CMakeCache 中 AUDIO/MP3/AAC/JNI/SHARED 值及安装/包内运行库材料，没有改冻结源码或构建选项。

## 云端出口

`reader-android-search.yml` 先核对固定起点、冻结树、Search 树和写入路径；安装真实 SDK/Search 包并构建 API26 x86_64 的 Debug/Release APK。API34 模拟器保留 SDK 原件导出 8 项、18 捕获原生壳 12 组、原宿主 17+2、DAV 91+4，以及原账号/接收 16 项，随后通过独立 instrumentation APK 操作真实搜索控件。

新增场景覆盖 250 个 TXT 命中的八批有界结果、Unicode/空结果/错误、歧义不跳转、显式 FOUND 导航、有界 EPUB 独有与重复 spine、PDF 文字与无文字、CBZ 拒绝、JNI 查询/selector 字节和线程边界、实际控制回调内取消、关闭、后台和进程重开。原件与 SDK notes/progress、产品 revisions/outbox 逐项观察；仅显式导航允许改变阅读位置。Debug 的原生 live 计数不保存句柄，Release 排除探针和测试类。

性能预算、真机、TalkBack 语音和六平台完整产品均不在本包授予范围。
