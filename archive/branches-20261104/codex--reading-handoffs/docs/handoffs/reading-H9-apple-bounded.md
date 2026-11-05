# H9：Apple 有界书库阅读接入

执行 [共同约束](reading-extra-index.md#全部包共同约束)。可立即准备；正式开工等待同一固定 SDK
和 H8 Windows 闭环复核。收到完整 SDK SHA 后建 `handoff/reading-h9-apple`；不猜接口。
准备参考 B=`b529513b7e8e8992786f8c679c0ec6c92110b035` 与 [接入地图](../R5-NATIVE-HOST-ADOPTION.md)。

## 所有权与实现

仅 Apple 宿主 `examples/apple/`、`tests/apple_host/`、`.github/workflows/wp13-apple.yml`、
Apple 专用构建/验收工具、`docs/WP13-APPLE.md` 与本包证据。
不改共享 `bindings/swift/EXReader.swift`、引擎、数据库 schema 或其他平台。

- `HostSDK.swift` 为 EPUB 区分 publication/session 与旧 snapshot document；
  `HostPager` 使用 bounded pager，不只是替换构造函数。
- `HostModel.swift` 的 open/rebuild/render/notes/jump 采用稳定 part+path 和章内范围；
  删除 EPUB 全文 Data/slice 依赖，页面只保留有限文字和必要几何。
- 导入接冻结 SDK 的有界入口，不先读整本 Data；fixed-source 保留 PDF/CBZ 行为。
- 保留 SwiftUI token、串行队列、HostCancelBox 与候选提交边界。
  UI 只接自有页面快照；字体/图片/取消 context 生命周期覆盖后台任务。

## 云端验收

macOS/iPhone/iPad 同一源码分别保留既有 12 UI/61 步/46 附件、21 原自检，
保留 SDK21、Model18、package/summary 与证据拒绝回归，不用新增检查替代。
新增跨章、长章缓存逐出后选文与标注、动态字号/旋转、后台与进程重开、取消换书、歧义定位。
记录真实 bounded 路径与内存各组成；不能通过全文回退。

交付固定 SHA、八作业逐项结果及同源工件身份；若原验收结构变化先报主代理。
真机、签名和真人 VoiceOver 不属于本包。准备期仅输出源码映射和计划，不能冒充接入完成。
