# Apple 原生目录导航

固定起点 `356c57a4c641f05e10cff13850e24bd94336454e`；本包在 Search 已验源码之后接入 F2。

F2 源码仅复制受测提交 `cbd7832b914bddcf99e06a85962d301a00b47efa` 的 `apps/reader/navigation`，树身份固定为 `9395914832e191ad63f18f6188ca5044260d2f12`。其 Linux/Windows 包级证据见 [固定验收记录](https://github.com/NoGod3524/EXReader/blob/13fd6dc1408fba0e71f5bc5a919e225a97c972c3/docs/validation/reader-navigation.json)。

原生 SwiftUI 目录面板每次最多显示 32 个同级项，保留作者顺序、父子关系及重复标签。子目录、上一级、前后批由显式按钮触发。PDF/CBZ 明示“按页入口 · 非作者目录”。CFI 放在可展开的次级入口中。

每次队列调用在同一实际线程内打开并释放 F2 快照，跨调用仅传递独立 Swift 值。目录和目标均绑定原件格式、SHA-256、字节及解析版本；显示前重新读取原件核验。路径重复只展示候选 spine，不自动选首项。片段不存在必须由用户确认章首，不静默降级。

跳转在第二个独立 SDK 库实例中直接调用公开 `document_resolve` / `publication_cfi_resolve` / 固定页数组，核对章节索引、path、id、node 或 CFI 点；不重复调用 F2 充当独立校验。CFI TEXT 节点只在 raw 与 normalized 范围逐字节一致时按 Unicode scalar 累加 UTF-16 单位，拒绝代理项内部与空白折叠；元素只使用公开子节点边界。实际布局 pager 的整个 projection 与独立文档逐块比较，原生 anchor 必须 FOUND 且位置精确相等后才渲染与保存。固定页没有文字 FOUND 声明，仅授予独立页面身份核验。

关闭、取消、换书通过 generation 和当前书身份丢弃迟到结果；候选渲染以前不改变旧 session。提交沿用既有 `HostCancelBox.commit` 取消边界。应用重开重新读取目录，不持久化快照指针或未经核验的目标。

Apple 构建只显式链接安装后的 `libreader_navigation.a` 与既有动态 SDK；不传递模块 CMake 的静态 SDK。实际宿主二进制和 `dladdr` 检查共同核实单一 SDK 提供者。冻结 SDK `9854061b…`、3.40.0/ABI1、产品 schema1 均不变。

容器观测改为 collector 与 always-trace 各自独立报告。定位工具在发出命令前独占创建报告路径，拒绝覆盖已存在文件；每条命令的参数、原始输出、退出码和原有超时保存。当前不添加重试、不改变 collector 断言和测试期限。

首次专项云端运行尚未完成。源码、12 项 native 适配检查、5 个真实 UI 用例（macOS / iPhone / iPad）及同源工件汇总由 `reader-apple-navigation.yml` 执行。原有完整回归只在最终稳定源码上执行，旧源码通过记录保持原归属。
