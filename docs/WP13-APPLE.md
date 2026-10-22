# WP13 Apple 宿主闭环

分支 `codex/wp13-apple`，实现基线 `a2552d7feb786cd2345d2b0b3eb894777b3254db`。本包只改 Apple 宿主与验收资产，不触碰迁移、OPDS、Android、Linux 包或引擎接口。

## 交付范围

| 路径 | 内容 |
| --- | --- |
| `examples/apple/ReaderApp.swift` | SwiftUI 入口与自检画面 |
| `examples/apple/HostSDK.swift` | 公开 C SDK 的局部桥接：书库、进度锚点、标注、固定页 |
| `examples/apple/HostModel.swift` | 串行工作队列、会话、真实进度、取消与恢复 |
| `examples/apple/HostViews.swift` | 书架、阅读器、选文、标注列表与编辑 |
| `examples/apple/SelectableText.swift` | iOS `UITextView` / macOS `NSTextView` 真实文字选择 |
| `examples/apple/LegacySelfTest.swift` | 原有 21 项宿主自检，检查名与口径保持不变 |
| `tests/apple_host/EXReaderHostUITests.swift` | macOS、iPhone、iPad 的 XCUITest 交互与生命周期验收 |
| `tests/apple_host/make_xcodeproj.rb` | 仅用于验收的 Xcode 工程生成 |
| `tests/apple_host/prepare_fixtures.py` | 确定性 EPUB/PDF/损坏文件/字体夹具 |
| `tests/apple_host/collect_evidence.py` | 逐 case、逐步骤、元素树、截图与数据库散列归档 |
| `.github/workflows/wp13-apple.yml` | 云端三平台验收与独立打包 |
| `docs/validation/wp13-apple-*.json` | 云端逐平台结果 |

共享 `bindings/swift/EXReader.swift` 保持只读；书库与锚点包装放在 app 目录，公开 SDK 所有权不变。

## 功能闭环

1. **导入、书架、重复书**：`exr_library_import_file_unique()` 按格式与原字节精确去重；原书字节写入 SQLite 的 `books.source`，宿主不保留外部文件路径，重启后仍从书库打开。
2. **阅读与排版**：EPUB/TXT 等重排文档经 `exr_library_document()` 打开，PDF/CBZ 经 `exr_library_fixed()`；页宽/页高跟随窗口与旋转，字号 18–48pt 触发重新分页，位置用锚点保持。
3. **真实选择与标注**：本页文字来自 SDK 文本快照，选择范围由原生文本视图产生；重排书用 `exr_library_note()` 由书库从存储源捕获 TextQuoteSelector（exact/prefix/suffix/chapter），固定版式用 `exr_library_fixed_note()` 捕获 page_id + 引文。列表显示锚点解析状态（精确/歧义/旧式/未找到）。
4. **持久化**：每次翻页写入点锚点（`exr_library_progress()`）与数值位置；固定版式写页位置。后台、视图重建、进程重启均从书库恢复。`Documents/host-state.json` 与 `library.sqlite` 快照作为 artifacts。
5. **异步与取消**：所有 SDK 工作在一个串行队列执行；每次操作带 token 与取消盒，旧结果不能覆盖当前书；视图销毁触发取消并持久化当前位置；取消返回 `已取消`，随后可继续打开其他书。
6. **可访问性**：稳定 identifier、中文 label、从上到下的阅读顺序，动态字号下控件仍可达；完整 VoiceOver 真人验收留给 WP14。

## 持久化与权限

- 书库：`Application Support/EXReader/library.sqlite`（iOS 位于 app 容器 `Library/Application Support`）。原始 EPUB/PDF 字节在 SQLite 中，无外部 sidecar。
- 状态快照：`Documents/host-state.json`（iOS 通过 `UIFileSharingEnabled` 暴露 Documents）。
- 系统文件选择器使用 security-scoped URL，读完即释放；文件内容随后进入书库，不再依赖原路径。
- 单文件上限 32 MiB；超限或格式不支持在导入/打开时给出可恢复错误。

## 锚点策略

- 进度：页起点作为空引文点锚点，附带最多 32 个 Unicode 标量的前后文；解析失败时使用书库保存的数值位置，并在 UI 中保留真实页码/百分比。
- 标注：书库从存储源重新捕获选择器；列表解析返回 `FOUND/AMBIGUOUS/LEGACY/MISSING`。只有 `FOUND` 才允许“定位”，歧义或未找到会显示状态并拒绝跳转，不按页码猜测。
- 固定版式：`page_id + 引文 + 前后文`；解析复用页面文本快照，同样拒绝猜测。
- 重新分页/旋转/字号变化：旧页起点锚点在新分页器中解析，再定位到包含该偏移的页。

## 云端验收

工作流 `.github/workflows/wp13-apple.yml` 在 `macos-15` 上：

- `sdk`：构建并安装 macOS、iphonesimulator、iphoneos 三套 SDK。
- `uitest`（matrix: macos / iphone / ipad）：生成只用于验收的 Xcode 工程，运行 XCUITest。每个平台至少 20 条具名步骤，覆盖导入、去重、书架、翻页、字号、旋转/窗口、选文、复制、标注增改删与导航、后台/前台、进程重开、取消与错误恢复。UI 测试使用真实点击/触摸、硬件键盘选择与复制，并断言持久化后的 UI 状态。
- `package`：用 `tools/build_apple_host.py` 消费安装后的 SDK，独立打包 macOS、模拟器与未签名设备包，并运行原有 21 项自检（macOS/iPhone/iPad 各 21 项）。

产物：xcresult、逐 case 与步骤 JSON、元素树、截图、xcodebuild 原始日志、SQLite 快照与 SHA-256、字体/SDK/Xcode/模拟器身份。设备包保留但不声明真机通过：`physical_device_execution=false`。

## 结果

| 平台 | 用例 | 步骤 | 21 项自检 | 结论 |
| --- | --- | --- | --- | --- |
| macOS | 待云端 | 待云端 | 21/21 | 待云端 |
| iPhone 模拟器 | 待云端 | 待云端 | 21/21 | 待云端 |
| iPad 模拟器 | 待云端 | 待云端 | 21/21 | 待云端 |

## 未满足项与边界

- 真机安装按用户要求暂缓；产物为未签名包，`physical_device_execution=false`。
- 系统文件选择器的实际点选不在自动 UI 用例内（系统进程 UI 不稳定）；宿主侧 security-scoped 导入路径由 in-app 夹具按钮覆盖同一 `importFile` 代码路径。
- 大章节/分段按需加载仍走公开 `exr_library_document()` 全文档路径，受 32 MiB 上限约束；本次不引入 bounded chapter 接口。
- VoiceOver 真人走查不在本包。
