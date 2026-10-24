# G16：macOS / iPhone / iPad 可访问性审计

审计包，不是功能包。本包只新增独立 XCTest/UI 用例、Actions 侧项目生成配置与本文件；
基线 Apple 宿主（`examples/apple/HostViews.swift`、`HostModel.swift`、`HostCatalog.swift`、
`HostSDK.swift`）、原项目生成器 `tests/apple_host/make_xcodeproj.rb` 与既有 Apple 工作流逐字未改。

- 实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`
- 分支：`codex/reader-a11y-apple`
- 工作流：`.github/workflows/reader-a11y-apple.yml`
- 证据：`docs/validation/reader-a11y-apple.json`（逐目标计数、run/attempt、工件身份）
- 唯一可改路径：`tests/reader_a11y_apple/**`、`.github/workflows/reader-a11y-apple.yml`、
  `docs/READER-A11Y-APPLE.md`、`docs/validation/reader-a11y-apple.json`

## 1. 审计什么

三目标真实应用 + 独立 UI 测试：

| 目标 | 目的地 | 受测程序 |
| --- | --- | --- |
| macOS | `platform=macOS`，宿主窗口 | `EXReaderHost.app/Contents/MacOS/EXReaderHost` |
| iPhone | `platform=iOS Simulator,id=<UDID>` | `EXReaderHost.app/EXReaderHost`（iphonesimulator） |
| iPad | 同上（iPad 设备族） | 同上 |

每个目标都在同一次运行里固定并记录：完整 source（`GITHUB_SHA`，同时写入受测程序 Info.plist 的
`EXRSourceSHA`）、模拟器 runtime 标识符与版本、设备名/UDID、窗口布局框、内容尺寸类别点值
（`caption1/body/headline`）、macOS 键盘访问设置（`AppleKeyboardUIMode`）、夹具清单摘要、
安装后 `libexreader.dylib` 的 SHA-256、受测可执行文件的 SHA-256 与字节数。

## 2. 方法：契约驱动，逐项对照

`tests/reader_a11y_apple/a11y_contract.json` 是本包的对照表，包含三类声明：

1. **语义树期望**（`states`）：每个受审步骤里应出现的元素标识、角色（XCUITest `elementType`）、
   可访问名称/值、启用状态、可交互控件集合、阅读顺序序列、状态暴露规则。
2. **内容规则**（`content_rules`）：对辅助技术暴露的内容做正则/子串判定（内部哈希、符号命名、
   调试追踪串、下标式标识）。
3. **源码审计**（`feature_gaps`）：把“不存在的能力”按 `文件:行` 固定下来，并在 CI 里回读源码校验
   （`contains` / `absent` / `absent_in_lines`）；源码一旦漂移，缺口条目变为 `stale` 并让证据无效。

运行侧只做观察：`A11yAuditSupport.swift` 遍历 `XCUIApplication.snapshot()`，为每个步骤输出一条
`EXR_A11Y_STATE {json}` 记录（元素路径、角色、名称、值、布局框、启用状态、`isHittable`、
匿名控件计数、窗口框、文本样式点值）；键盘另发一条 `EXR_A11Y_KEYBOARD` 记录（见下文键盘判据）；`audit_collect.py` 在 Actions 里把记录
与契约逐项比对，产出 `report.json`；`audit_gate.py` 汇总三目标并给出两个独立结论。

### 实测到的平台差异（写进判据，避免把装置差异当成产品缺陷）

1. **平台身份**：iPad 模拟器上的测试进程把 `userInterfaceIdiom` 报成 `.unspecified`（`model` 仍是
   "iPad"），所以平台优先取 `TEST_RUNNER_EXR_A11Y_PLATFORM`（工作流注入），其次按 idiom/model 判断；
   采集端再用 `simctl` 目的地（设备名/UDID）复核：iOS 设备族与目的地一致时记 `pass` 并留下
   `记录=… 目的地=…` 的实际值，只有族别与目的地矛盾才记 `blocked`。
2. **文本暴露**：macOS 上 SwiftUI `Text` 的元素是 `label=""`、`value="<字符串>"`。名称判定与内容规则
   都走同一个 fallback（label 为空则用 value），否则规则会在空串上“通过”。
3. **阅读面 value**：`reader.page` 在 macOS 上不桥接 AX value，页号只能从 AT 名称读（名称本身是
   `第 N 页：正文前 60 字`）。所以页号判据看名称，不看 value。
4. **大字体装置**：`-UIPreferredContentSizeCategoryName` 启动参数在当前 runtime 上会把应用重置回默认
   类别，不能当夹具用；必须用 `xcrun simctl ui <udid> content_size` 改设备设置，并且判定前先确认
   测试进程的 `caption1_pt` 确实变大，否则输出 `blocked`。
5. **懒加载书架**：大字体下 `LazyVStack` 只构建可见行，按书名找行的探针会落空，所以大字体用例
   只要求“有书可开”，不绑定具体书名。

### 受审步骤（18）

| 步骤 | 覆盖 | 平台 |
| --- | --- | --- |
| `library.empty` | 空书架：标题、空状态、8 个导入按钮 | 三目标 |
| `library.populated` | 两本夹具入架：列表容器、书架行名称/角色 | 三目标 |
| `library.busy` | 长导入进行中：忙文本、取消按钮、竞争控件禁用状态 | 三目标 |
| `library.after_cancel` | 取消后恢复：状态文本、导入控件恢复可用 | 三目标 |
| `reader.epub` | 阅读器首页：书名、阅读面替身、位置/进度/状态、翻页、字号、选文、标注 | 三目标 |
| `reader.second_page` | 翻页后：位置与阅读面同步更新 | 三目标 |
| `selection.sheet` | 选文面板：可选文本视图、提示、五个按钮 | 三目标 |
| `selection.selected` | 全选后：摘录发布、复制/标注所选可用 | 三目标 |
| `reader.with_note` | 标注保存后：标注计数与状态 | 三目标 |
| `notes.sheet` | 标注列表：摘录、评论、状态、定位/编辑/删除 | 三目标 |
| `notes.editor` | 编辑标注：输入框、保存、取消 | 三目标 |
| `reader.large_type` | 设备内容尺寸类别为 `accessibility-extra-extra-extra-large` 时的阅读器 | iPhone/iPad |
| `library.large_type` | 同上的书架 | iPhone/iPad |
| `reader.landscape` | 旋转到横屏后的阅读器 | iPhone/iPad |
| `reader.portrait` | 恢复竖屏后的阅读器 | iPhone/iPad |
| `reader.window_min` | macOS 最小窗口（宿主自声明 380×460 下限） | macOS |
| `reader.window_default` | 恢复窗口尺寸 | macOS |
| `reader.keyboard` | Tab 遍历开始前的阅读器 + 键盘遍历记录 | macOS |

## 3. 判据与阻断规则

每个判据产出一条 item，`verdict` ∈ {`pass`, `fail`, `blocked`, `uncovered`, `advisory`, `gap`, `stale`}：

- **名称/角色**：声明元素必须出现；角色（映射后的 `XCUIElementType` 名称，见下）必须匹配；
  可访问名称（label，其次 value）不得为空。`XCTest` 会把类型打印成 `XCUIElementType(rawValue: 48)`，
  所以判据用固定映射表转成 `Button`/`StaticText`/`TextField`/`ScrollView`/`Other` 等稳定名称再比对。
- **状态可见**：`enabled` 必须与声明一致（忙时禁用、取消后恢复）；禁用状态必须能被辅助技术观察到。
- **可达性与截断**：可交互控件的布局框必须完整落在窗口内（容差 2 pt）、必须 `isHittable`；
  最小边不小于 24 pt（WCAG 2.5.8）在**触控平台（iPhone/iPad）阻断**。
- **建议项（`advisory`，不阻断、不计入 finding）**：iOS 上 24–44 pt 的 HIG 触控建议，
  以及 macOS 上小于 20 pt 的指针目标。门槛写在契约 `policy.minimum_target_pt`，
  避免用 Web 的 24 pt 去误判 AppKit 控件。
- **重叠**：同一步骤内可交互控件的布局框不得互相覆盖超过较小控件的 50%；位于 `ScrollView` 内的行
  与外部控件的几何重叠会被滚动视口裁剪，这类组合记为 `uncovered` 而不是遮挡缺陷。
- **阅读顺序**：声明的阅读序列必须与视觉纵向顺序一致（容差 20 pt）。
- **内容区占位**：大字体状态下书架列表 `library.list` 与阅读面 `reader.page` 至少保留窗口高度的 25%
  （作者设定的设计下限，不是 WCAG 判据，因此不阻断），把“控制区把正文/书架挤没”这件事量化出来。
- **书架行**：书架顺序属于产品决定，所以按**行名称**核对书名（`book_row_names`），不把书名绑到下标。
- **Dynamic Type**：`reader.epub` → `reader.large_type` 同名元素高度必须增长（≥0.5 pt）。
  判定前先校验装置是否生效：两个状态里 `caption1_pt` 必须变大；否则输出 `blocked`（装置未生效），
  不拿它评判产品。
- **键盘可操作性**：macOS 全键盘访问（`AppleKeyboardUIMode=3`）下按 16 次 Tab、每第 4 次追加 Space，
  阅读器的可观察状态（位置/字号/状态/面板）必须出现变化；全程无变化即判 `fail`。
- **焦点顺序**：本次 Xcode 的 `XCUIElement` 既不暴露 `hasFocus` 也没有等价焦点 API，
  逐控件焦点顺序记为 `uncovered`，不伪造通过。

结论分两步，互不冒充：

- `audit_completed`：三目标是否都产出了可解析、同 source/run/attempt、契约步骤齐全、
  工件名含 run/attempt 且字节/摘要非空的证据。
- `accessibility_accepted`：在 `audit_completed` 之上，是否没有任何 **阻断** 判据失败。

“报告生成成功”不等于“无障碍通过”：有阻断缺陷时 `accessibility_accepted=false`，
工作流仍以 0 退出（审计已按契约完成），证据无效才返回 1。

## 4. 源码审计缺口（不存在的能力）

以下条目由契约声明、在 CI 中回读源码校验，输出为 `gap` 而不是通过：

| 缺口 | 位置 | 实际 | 最小修复 |
| --- | --- | --- | --- |
| 无控件提示 | `HostViews.swift`（全文无 `accessibilityHint`） | 翻页/导入/删除标注只有名称 | 关键控件补 `.accessibilityHint`，或记录“不需要”的理由 |
| 无标题语义 | 全文无 `isHeader` | 书架/选文/标注标题不参与按标题导航 | 四处标题加 `.accessibilityAddTraits(.isHeader)` |
| 无排序优先级 | 全文无 `accessibilitySortPriority` | 依赖默认容器顺序 | 阅读面与底部控制栏显式声明优先级 |
| 状态不播报 | 全文无 `UIAccessibility.post` | 导入完成/失败、翻页、标注保存都静默 | 状态变化处 post `.announcement` 或加 `.updatesFrequently` |
| 阅读器无滚动回退 | `HostViews.swift:183-267` | 固定 `VStack`，大字体/最小窗口会裁切控制器 | 控制区包 `ScrollView` 或大字体折叠为单行工具条 |
| 未选文即可复制 | `HostViews.swift:317-322` | `.disabled(!isCurrent)`，未选文时按钮可用、按下才提示 | `.disabled(!isCurrent || quote.isEmpty)` |
| 装饰图像未隐藏 | `HostViews.swift:103` | `chevron.right` 未 `accessibilityHidden` | 装饰图加 `.accessibilityHidden(true)` |
| 阅读面替身只 60 字 | `HostModel.swift:428-431` | `pageLabel` 取 `prefix(60)`，其余正文对辅助技术不可见 | 正文放 `accessibilityValue` 或提供逐段 rotor |

## 5. 未覆盖（保持未授予）

- **AX traits**：XCUITest 公共 API 不暴露 `isHeader`/`updatesFrequently` 等 traits，需 Accessibility Inspector。
- **VoiceOver 实际朗读、转子、提示音**：自动 XCUI 不等于 VoiceOver 通过。
- **Reduce Motion / Bold Text / Increase Contrast / Differentiate Without Color**：runner 上无脚本化开关。
- **iOS/iPadOS 全键盘访问路径**：模拟器未启用 Full Keyboard Access。
- **macOS 逐控件焦点顺序**：`XCUIElement` 在本 Xcode 中不暴露焦点，只测到“键盘能否驱动阅读器”。
- **macOS 大字体**：macOS 无系统 Dynamic Type 缩放，只有最小窗口压力证据。
- **真机**：本包只在 Actions 的 macOS 宿主与模拟器执行。
- **系统文件选择器面板**：不属于宿主 AX 树，且不接真实用户文件。
- **输入法/软键盘路径**：只审计 `notes.editor` 的可达性与名称。

## 6. 云端出口

工作流 `Reader Apple accessibility audit` 四个 job：

1. `frozen`：`HEAD == GITHUB_SHA`、实现起点是祖先、SDK 保护树等于
   `9854061be331fe603a1822d9b2b36ee357154927`、产品 SQL 与实现起点相等、
   `git diff --name-only <start> HEAD` 全在本包白名单内。
2. `sdk`：在 `macos-15` 上构建并安装 `macos` 与 `iphonesimulator` 两套 SDK（本包自己的工作流，不改 `wp13-apple.yml`）。
3. `audit`（`macos`/`iphone`/`ipad` 三路并行）：生成独立审计工程（`make_a11y_xcodeproj.rb`，
   不带 `EXR_APPLE_HOST_REVIEW`/`EXR_APPLE_IMPORT_REVIEW`，受测的是普通宿主）、跑独立 UI 用例、
   导出截图附件、采集逐项证据，工件名 `reader-a11y-apple-audit-<platform>-<run>-<attempt>`。
   iPhone/iPad 各跑两次：默认内容尺寸一次（跳过 `test07DynamicTypeAudit`），
   再用 `xcrun simctl ui <udid> content_size accessibility-extra-extra-extra-large` 改设备字号后
   只跑该用例一次（`-only-testing:`），最后复位为 `medium`。`simctl ui ... content_size` 的读数
   作为“字体设置”写入证据；`-UIPreferredContentSizeCategoryName` 启动参数在当前 runtime 上不生效，
   所以大字体必须由设备级设置给。
4. `summary`：合流三份 `report.json`，用 `gh api` 核对工件身份（名称含 run/attempt、字节非零、
   `sha256:` 摘要、未过期），再输出 `reader-a11y-apple-summary.json` 与
   `reader-a11y-apple-validation-<run>-<attempt>` 工件。

## 7. 结果

本节与 `docs/validation/reader-a11y-apple.json` 来自同一次运行，不拼接其它 run/attempt。

- 受测 source：`a8756cd196a18a050acb47967948b631df4313f7`（GITHUB_SHA，同时写入受测程序 Info.plist 的 EXRSourceSHA）
- 运行：`40083042946` attempt `1`，工作流 Reader Apple accessibility audit
- 契约：`tests/reader_a11y_apple/a11y_contract.json`，`sha256:28c0e7e88d4f8e370606e863aaa8263bda71918d95268d4d9856f68d5ab93dcb`
- SDK 保护树：`9854061be331fe603a1822d9b2b36ee357154927`（frozen job 校验通过）；实现起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`

### 7.1 逐目标证据

| 目标 | 设备 / runtime | 窗口 | 字体/键盘装置 | 受测程序 SHA-256 | 步骤 | pass | fail | 其中阻断 | blocked | 缺口 | 未覆盖 | 建议项 | 截图 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| macos | macOS host / macOS | 900×488 | keyboard=3 | `849ec1d899e4fc15760034228aff48f47374a6589c92527d385fcd7fafff1863` | 14 | 403 | 4 | 0 | 0 | 8 | 7 | 0 | 28 |
| iphone | iPhone SE (3rd generation) / com.apple.CoreSimulator.SimRuntime.iOS-26-2 | 375×667 | content_size=accessibility-extra-extra-extra-large | `6e6ff64712addcee93283ffe23b391ca1982990b8c53a4b327848eb0d09b7c6f` | 15 | 433 | 13 | 9 | 0 | 8 | 7 | 47 | 30 |
| ipad | iPad mini (A17 Pro) / com.apple.CoreSimulator.SimRuntime.iOS-26-2 | 744×1133 | content_size=accessibility-extra-extra-extra-large | `6e6ff64712addcee93283ffe23b391ca1982990b8c53a4b327848eb0d09b7c6f` | 15 | 440 | 8 | 4 | 0 | 8 | 7 | 47 | 30 |

### 7.2 结论

| 结论 | 值 | 依据 |
| --- | --- | --- |
| audit_completed | `true` | 三目标契约步骤齐全、无 blocked、审计用例无失败、工件名含 run/attempt 且字节/摘要非空 |
| accessibility_accepted | `false` | 三目标共 9 类阻断判据失败（见 7.3），按约定不授予无障碍 |

### 7.3 阻断缺陷（不授予无障碍）

| 目标 | 步骤 | 元素路径 | 实际 | 预期 | 截图（导出文件名） | 最小修复 |
| --- | --- | --- | --- | --- | --- | --- |
| iphone | library.busy | `Application>Window>Button[library.cancel]` | 最小边 20.5 pt | 控件不小于 24 pt（WCAG 2.5.8） | CEA30726-A4BD-45D1-858A-501E0D5E2702.png | 扩大点击区域（.contentShape / padding / frame(minWidth:minHeight:)） |
| iphone | library.large_type | `library.book.0|library.import.epub` | 重叠面积占较小控件 91% | 可交互控件的布局框不互相重叠 | CB8A57CE-EDB4-4ADE-88AC-D39D0D190544.png | 在压缩布局中重新分配间距，避免控件互相覆盖 |
| iphone | reader.epub, reader.landscape, reader.portrait | `Application>Window>Button[reader.back]` | 最小边 20.5 pt | 控件不小于 24 pt（WCAG 2.5.8） | 1E5B136F-4D12-4E32-ABC2-AA96FE24E49A.png | 扩大点击区域（.contentShape / padding / frame(minWidth:minHeight:)） |
| iphone | reader.landscape | `Application>Window>Button[reader.back]` | isHittable=false（可能被遮挡或在窗口外） | 启用中的控件可被命中 | BC14A28F-837D-47B2-900D-FE80F7E9650F.png | — |
| iphone | reader.landscape | `Application>Window>Button[reader.back]` | frame={"height": 20.5, "width": 34.0, "x": 16.0, "y": -34.5} window={"height": 375.0, "width": 667.0, "x": 0.0, "y": 0.0} | 控件完整落在窗口内 | BC14A28F-837D-47B2-900D-FE80F7E9650F.png | 为大字体/小窗口加滚动回退或压缩行距，避免控件溢出窗口 |
| iphone | reader.landscape | `Application>Window>Button[reader.select]` | frame={"height": 34.5, "width": 58.0, "x": 264.5, "y": 362.5} window={"height": 375.0, "width": 667.0, "x": 0.0, "y": 0.0} | 控件完整落在窗口内 | BC14A28F-837D-47B2-900D-FE80F7E9650F.png | 为大字体/小窗口加滚动回退或压缩行距，避免控件溢出窗口 |
| iphone | reader.landscape | `Application>Window>Button[reader.notes]` | frame={"height": 34.5, "width": 70.0, "x": 332.5, "y": 362.5} window={"height": 375.0, "width": 667.0, "x": 0.0, "y": 0.0} | 控件完整落在窗口内 | BC14A28F-837D-47B2-900D-FE80F7E9650F.png | 为大字体/小窗口加滚动回退或压缩行距，避免控件溢出窗口 |
| ipad | library.busy | `Application>Window>Button[library.cancel]` | 最小边 20.5 pt | 控件不小于 24 pt（WCAG 2.5.8） | 2FABAE0B-A164-4AB5-8659-FC7CC3B0642A.png | 扩大点击区域（.contentShape / padding / frame(minWidth:minHeight:)） |
| ipad | reader.epub, reader.landscape, reader.portrait | `Application>Window>Button[reader.back]` | 最小边 20.5 pt | 控件不小于 24 pt（WCAG 2.5.8） | BF1270CA-3242-47E1-B666-4D4DAE28B5B3.png | 扩大点击区域（.contentShape / padding / frame(minWidth:minHeight:)） |

### 7.4 非阻断发现（内容规则）

| 目标 | 步骤 | 元素 | 判据 | 实际 | 最小修复 |
| --- | --- | --- | --- | --- | --- |
| macos | reader.epub | `reader.state` | content-rule:reader-state-internal-hash | 匹配禁止模式 ^#[0-9A-Za-z]{4,}$ / #41996943 | 生产构建隐藏该调试行，或对其加 .accessibilityHidden(true) |
| macos | reader.epub | `reader.font.decrease` | content-rule:font-button-symbol-only | 匹配禁止模式 ^A[-+±]$ / A- | 补 .accessibilityLabel("减小字号")/"增大字号" |
| macos | library.empty | `library.title` | content-rule:library-title-trace | 包含 token= / 1:token=0,busy=false,started=false:scene=background / 2:token=0,busy=false,started=false:startup-request / 3:token=0,busy=true,started=tru | 仅在 -EXRUITestFixtures 下挂载该调试值，或加 .accessibilityHidden(true) |
| macos | library.populated | `library.book.0` | content-rule:library-book-index-identifier | 命中需改进模式 ^library\.book\.\d+$ / library.book.0 | 改用 library.book.<bookID>；同时保留 AX 名称中的书名以便人工脚本稳定 |
| iphone | reader.epub | `reader.state` | content-rule:reader-state-internal-hash | 匹配禁止模式 ^#[0-9A-Za-z]{4,}$ / #41996943 | 生产构建隐藏该调试行，或对其加 .accessibilityHidden(true) |
| iphone | reader.epub | `reader.font.decrease` | content-rule:font-button-symbol-only | 匹配禁止模式 ^A[-+±]$ / A- | 补 .accessibilityLabel("减小字号")/"增大字号" |
| iphone | library.empty | `library.title` | content-rule:library-title-trace | 包含 token= / 1:token=0,busy=false,started=false:scene=inactive / 2:token=0,busy=false,started=false:startup-request / 3:token=0,busy=true,started=true: | 仅在 -EXRUITestFixtures 下挂载该调试值，或加 .accessibilityHidden(true) |
| iphone | library.populated | `library.book.0` | content-rule:library-book-index-identifier | 命中需改进模式 ^library\.book\.\d+$ / library.book.0 | 改用 library.book.<bookID>；同时保留 AX 名称中的书名以便人工脚本稳定 |
| ipad | reader.epub | `reader.state` | content-rule:reader-state-internal-hash | 匹配禁止模式 ^#[0-9A-Za-z]{4,}$ / #41996943 | 生产构建隐藏该调试行，或对其加 .accessibilityHidden(true) |
| ipad | reader.epub | `reader.font.decrease` | content-rule:font-button-symbol-only | 匹配禁止模式 ^A[-+±]$ / A- | 补 .accessibilityLabel("减小字号")/"增大字号" |
| ipad | library.empty | `library.title` | content-rule:library-title-trace | 包含 token= / 1:token=0,busy=false,started=false:scene=inactive / 2:token=0,busy=false,started=false:startup-request / 3:token=0,busy=true,started=true: | 仅在 -EXRUITestFixtures 下挂载该调试值，或加 .accessibilityHidden(true) |
| ipad | library.populated | `library.book.0` | content-rule:library-book-index-identifier | 命中需改进模式 ^library\.book\.\d+$ / library.book.0 | 改用 library.book.<bookID>；同时保留 AX 名称中的书名以便人工脚本稳定 |

### 7.5 建议项、缺口与未覆盖

- 建议项（advisory，不阻断、不计入 finding）：macos 0 条，iphone 47 条，ipad 47 条；主要是 iOS 上 .bordered 按钮 34.5 pt 触控高度低于 HIG 44 pt 建议。
- 源码缺口（gap，CI 回读源码校验）：`hint-absent`、`header-traits-absent`、`sort-priority-absent`、`status-not-announced`、`reader-not-scrollable`、`copy-annotate-enabled-without-selection`、`named-icons-not-hidden`、`page-label-60-chars`。
- 未覆盖（uncovered）：`ax-traits`、`voiceover-speech`、`appearance-adaptations`、`macos-dynamic-type`、`physical-device`、`system-picker`、`ime-input`。

### 7.6 工件身份

| 工件 | id | 字节 | sha256 | 有效期 |
| --- | --- | --- | --- | --- |
| `reader-a11y-apple-audit-ipad-40083042946-1` | 12557085807 | 13343992 | `sha256:4a0fc9a029096d7b47188e8999a646540ee5b8e4a14a1771edbdb4b502c911f9` | 2026-11-23T10:19:11Z |
| `reader-a11y-apple-validation-40083042946-1` | 12556359831 | 6081 | `sha256:752e62ee044c1940905e98902e8e5e273ad79ad7fc7a2ec598a0dd7c1e0fe43d` | 2026-11-23T10:21:47Z |
| `reader-a11y-apple-audit-iphone-40083042946-1` | 12556119011 | 7815251 | `sha256:2f8d2468cf30470da86e0c1837eff3c4fe795832ffadf473094a25bd52560f67` | 2026-11-23T10:21:15Z |
| `reader-a11y-apple-audit-macos-40083042946-1` | 12555909373 | 5550194 | `sha256:c34f4b34b8e864af1282fb61884eb1243a76da3bf0aeaee869b497802aea50ec` | 2026-11-23T10:11:58Z |

### 7.7 交给 Apple owner 的最小修复建议

按修复代价排序。前两项同时消掉阻断判据与 reader-not-scrollable 缺口：

| 优先级 | 问题 | 位置 | 最小修复 |
| --- | --- | --- | --- |
| P1 | 阅读器横屏/大字体下控件被挤出窗口（reader.back y=-34.5、reader.select/reader.notes 越界） | HostViews.swift:183-267（ReaderScreen 固定 VStack(spacing: 6)） | 把控制区包进 ScrollView，或在 verticalSizeClass == .compact 时折叠成单行工具条 |
| P1 | reader.back / library.cancel 触控高度 20.5 pt（< 24 pt，WCAG 2.5.8） | HostViews.swift:185、:78 | 两个按钮补 .frame(minHeight: 44).contentShape(Rectangle())，或统一 .buttonStyle(.bordered).controlSize(.large) |
| P2 | 阅读面替身只 60 字（pageLabel 的 prefix(60)） | HostModel.swift:428-431 | 整页正文放 accessibilityValue，名称保留页号；或提供逐段自定义 rotor |
| P2 | 状态变化不播报（导入完成/失败、翻页、标注保存） | HostViews.swift:150、:261 | 状态变化处 UIAccessibility.post(notification: .announcement, argument:)，或给状态 Text 加 .accessibilityAddTraits(.updatesFrequently) |
| P3 | 字号按钮只有 A- / A+ | HostViews.swift:242、:246 | 补 .accessibilityLabel(减小字号) / .accessibilityLabel(增大字号) |
| P3 | reader.state 暴露内部状态哈希 #41996943 | HostViews.swift:226 | 生产构建隐藏该调试行，或 .accessibilityHidden(true) |
| P3 | 缺标题语义与控件提示 | HostViews.swift:71、:187、:300、:414 | 四个标题加 .accessibilityAddTraits(.isHeader)；翻页/导入/删除标注补 .accessibilityHint |
| P3 | 书架行标识按枚举下标（library.book.<index>） | HostViews.swift:111 | 改为 library.book.<bookID>；AX 名称继续带书名 |
| P3 | 装饰性 chevron.right 未隐藏 | HostViews.swift:103 | 加 .accessibilityHidden(true) |
| P3 | iOS 上 .bordered 按钮 34.5 pt（HIG 建议 44 pt） | 全部 .buttonStyle(.bordered) 行 | 只记为建议项；若按 HIG 收敛，统一 controlSize(.large) |

以上修复都不需要改本包的测试或契约：契约只声明期望，修复后重跑同一工作流即可重新取证。

## 8. 限制

- 自动 XCUI 只证明控件在语义树里的名称、角色、状态、位置与顺序，不证明朗读质量。
- 夹具路径（`-EXRUITestFixtures 1`）用于让导入/选文/标注可重复；不接真实 iCloud 账号或用户文件。
- 门槛值（24 pt / 44 pt / 50% 重叠 / 20 pt 顺序容差 / 0.5 pt 缩放）写在契约 `policy` 里，
  改动契约即改动判据，必须与新证据同源。
