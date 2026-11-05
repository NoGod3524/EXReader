# G16：macOS／iPhone／iPad 可访问性审计

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-a11y-apple`。
类型：审计；优先级：P1；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_a11y_apple/**`
- `.github/workflows/reader-a11y-apple.yml`
- `docs/READER-A11Y-APPLE.md`
- `docs/validation/reader-a11y-apple.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

只新增独立XCTest/UI测试和Actions侧项目生成配置，读取基线Apple宿主文件；不改HostModel/HostViews/HostCatalog/HostSDK、原项目生成器或现有Apple工作流。
分别在macOS、iPhone/iPad Simulator审计名称/角色/状态、焦点和键盘路径（适用处）、Dynamic Type/大字体、旋转/尺寸变化、导入/阅读/书架/标注的可达性与截断。
不存在功能记缺口；输出元素路径、实际/预期、截图与最小修复建议交Apple owner/root。自动XCUI不等于VoiceOver/真机通过。
不接真实iCloud账号或用户文件，不为报告全绿放宽原UI判定。

## 云端出口

三目标实际应用和独立UI测试，固定source、模拟器runtime、窗口/字体设置和程序SHA。原件/语义树/步骤逐项对照；audit_completed与accessibility_accepted分开。
测试不能执行的目标保持未覆盖；有阻断缺陷则不授予无障碍。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `tests/apple_host/make_xcodeproj.rb`
- `tests/apple_host/EXReaderHostUITests.swift`
- `examples/apple/HostViews.swift`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

