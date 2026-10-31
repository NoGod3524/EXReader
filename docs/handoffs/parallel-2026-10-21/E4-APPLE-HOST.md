# E4：WP13 Apple 原生宿主闭环

你统一负责macOS、iPhone和iPad，避免三个智能体同时修改同一SwiftUI宿主。先读同目录`README.md`，复用现有SwiftUI与公开SDK，完成实际阅读、标注和恢复闭环。

## 起点

- 分支`codex/wp13-apple`，实现基线`a2552d7feb786cd2345d2b0b3eb894777b3254db`。
- 现有`examples/apple/ReaderApp.swift`、`tools/build_apple_host.py`、`tools/check_apple_host.py`。三类Apple宿主原自动检查各21项，保留已有结果口径。
- 当前书架由宿主JSON等状态保存；启动时确认现状，不把现有元数据列表当作完整SDK书库/标注接入。
- 用户明确暂缓真机安装；本包只进行macOS与iPhone/iPad模拟器验收。无签名证书、账号或设备授权依赖。

## 必做功能

1. 文件导入、书架与重复书籍处理；明确文档权限和原书持久化位置，重启后原书仍可访问。
2. 保留重排/固定页阅读、翻页、字号/缩放、旋转和多尺寸布局。显示真实进度与状态，错误和取消可恢复。
3. 真实文字选择、复制、标注增改删与列表导航；使用公开锚点和书库能力，不能只保存截图坐标或页码猜测。
4. 关闭重开、后台/前台、视图重建后恢复进度与标注；iPhone与iPad各验证，macOS生命周期另验。
5. SDK工作串行执行、取消与view销毁正确回收；状态更新回到正确UI上下文，旧异步结果不能覆盖当前书籍。
6. 稳定的accessibility identifiers、labels、reading order和动态字号基础语义，为WP14留可测接口；完整VoiceOver真人验收不在本包。

## 文件所有权

拥有`examples/apple/**`、`tools/build_apple_host.py`、`tools/check_apple_host.py`、`tests/apple_host/**`、`.github/workflows/wp13-apple.yml`、`docs/WP13-APPLE.md`、`docs/validation/wp13-apple*.json`。

共享`bindings/swift/EXReader.swift`先只读；缺书库/锚点包装优先在app目录添加局部桥接文件，并保持公开SDK所有权。构建脚本允许接入app目录新增源，不修改顶层CMake和既有native/reliability工作流。

## 云端验收

- macOS应用和iPhone/iPad模拟器实际运行，原21/21/21检查不得丢失。
- 每个平台至少20条具名交互/生命周期步骤，覆盖导入、书架、翻页、旋转/窗口/字号、选文、标注导航、后台/恢复、进程重开、取消与错误恢复。三平台分别报告，不能用iPhone替代iPad。
- UI测试通过真实控件/触摸/键盘事件与持久化结果断言；编译、Swift typecheck或模型函数自检不能算交互验收。
- EPUB/PDF已有能力保持；其他格式及大章路径按实际公开SDK与预算声明。锚点歧义明确呈现，不生成伪精确恢复结果。
- 截图、可访问元素树检查、状态/数据库散列、SDK/应用/字体/输入身份、逐case结果及原日志作为云端artifact保留。
- unsigned设备包可延续既有构建用于后续安装，但`physical_device_execution=false`；不声明真机通过。

## 最终交付

代码、三平台云端工作流、独立打包消费、各平台验收表和JSON。提交推送自己的分支，不合并。回复SHA、路径、云端run及三平台结果、持久化/锚点策略和未满足项。不要改迁移/OPDS/Android/Linux包或引擎接口。
