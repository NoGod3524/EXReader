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
macOS 的 `hasFocus`、匿名控件计数、窗口框、文本样式点值）；`audit_collect.py` 在 Actions 里把记录
与契约逐项比对，产出 `report.json`；`audit_gate.py` 汇总三目标并给出两个独立结论。

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
| `reader.large_type` | `UICTContentSizeCategoryAccessibilityExtraExtraExtraLarge` 下的阅读器 | iPhone/iPad |
| `library.large_type` | 同上的书架 | iPhone/iPad |
| `reader.landscape` | 旋转到横屏后的阅读器 | iPhone/iPad |
| `reader.portrait` | 恢复竖屏后的阅读器 | iPhone/iPad |
| `reader.window_min` | macOS 最小窗口（宿主自声明 380×460 下限） | macOS |
| `reader.window_default` | 恢复窗口尺寸 | macOS |
| `reader.keyboard` | Tab 遍历开始前的阅读器 + 键盘遍历记录 | macOS |

## 3. 判据与阻断规则

每个判据产出一条 item，`verdict` ∈ {`pass`, `fail`, `blocked`, `uncovered`, `gap`, `stale`}：

- **名称/角色**：声明元素必须出现；角色必须匹配；可访问名称（label，其次 value）不得为空。
- **状态可见**：`enabled` 必须与声明一致（忙时禁用、取消后恢复）；禁用状态必须能被辅助技术观察到。
- **可达性与截断**：可交互控件的布局框必须完整落在窗口内（容差 2 pt）、必须 `isHittable`、
  最小边不小于 24 pt（WCAG 2.5.8，阻断）；iOS 上小于 44 pt 记 HIG 建议项（不阻断）。
- **重叠**：同一步骤内可交互控件的布局框不得互相覆盖超过较小控件的 50%。
- **阅读顺序**：声明的阅读序列必须与视觉纵向顺序一致（容差 20 pt）。
- **Dynamic Type**：`reader.epub` → `reader.large_type` 同名元素高度必须增长（≥0.5 pt），
  否则说明固定 frame/lineLimit 压制了字号缩放。
- **键盘路径**：macOS 全键盘访问（`AppleKeyboardUIMode=3`）下 14 次 Tab 的焦点序列必须覆盖可交互控件；
  若 XCUITest 完全观察不到 `AXFocused`，该项记为 `uncovered` 而不是伪造通过。

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
4. `summary`：合流三份 `report.json`，用 `gh api` 核对工件身份（名称含 run/attempt、字节非零、
   `sha256:` 摘要、未过期），再输出 `reader-a11y-apple-summary.json` 与
   `reader-a11y-apple-validation-<run>-<attempt>` 工件。

## 7. 结果

本节与 `docs/validation/reader-a11y-apple.json` 记录同一次 source/run/attempt 的实际结果。
首次云端执行后由运行证据回填；未执行前不声称任何目标通过。

## 8. 限制

- 自动 XCUI 只证明控件在语义树里的名称、角色、状态、位置与顺序，不证明朗读质量。
- 夹具路径（`-EXRUITestFixtures 1`）用于让导入/选文/标注可重复；不接真实 iCloud 账号或用户文件。
- 门槛值（24 pt / 44 pt / 50% 重叠 / 20 pt 顺序容差 / 0.5 pt 缩放）写在契约 `policy` 里，
  改动契约即改动判据，必须与新证据同源。
