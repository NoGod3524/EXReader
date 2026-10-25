# 共同 SDK3.41 宿主的 Apple 验收入口准备

准备分支 `codex/reader-apple-common-callers` 从 `b5e49d1753a6b4b88811b03fa904fe9447865247` 开始，普通合并已封存 Apple 七组交付 `8bba2f5328e738b40b3c72050004cbe6157583a7`，合并点 `f7874b3c2b0a33d1e695805551dfedf46512f7fe`。合并无冲突，`apps`、`examples`、`extras` 与两 Apple 生成器相对 b5 没有变化。

本准备没有运行 Actions、构建、测试或本地语法检查，`accepted=false`。原七组只授予受测 source `2c2eabdad62de88bf5e3c337004be37663c61877`，不向本共同源转授。

## 精确生产边界

- `guard.py` 的唯一 `COMMON_BASE` 固定为 `b5e49d1753a6b4b88811b03fa904fe9447865247`。全 `apps`、`examples`、`extras`、`tools` 逐树固定到此点。
- SDK 保护树固定 `edddc463c06ed5731195cdb8f06b2df6dff7699e`；旧 SDK 身份仍为 `9854061be331fe603a1822d9b2b36ee357154927`。SDK3.41.0 / ABI1 / core3.40.0 不变。
- 六个阅读核心模块/schema1 逐树固定 `f680aeaddfb1ecc67ead353554f5b91a5703f72f`。其余已审模块与四个后续模块的显式 SDK CMake 适配按共同 BASE 精确固定。
- Apple 生产、原六消费者/collector、主题 UI 与两项确定性 UI 固定 `902a73bd9984649000d63e96d5056b16daf28c85`；三份 Android Java policy 仍精确 `b1a7b7891cd394671842164a07a86c8e316dace3`。
- `COMMON_BASE..HEAD` 只允许原七个 Apple 工作流、预检、Apple review 调度/guard/summary 与已登记文档。未增加生产路径例外。

Windows 最终交付普通合并后，共同生产必然改变。派发之前必须把 `COMMON_BASE` 显式改成经审核的最终共同生产提交；当前值将拒绝未经登记的生产差异。主题严格汇总从同一个 guard 常量读取这一精确 BASE，不接受运行时传入任意基线。

## 保留的七个完整入口

原六工作流仅把显式 3.41/ON 候选分支改为 `codex/reader-hosts-341-final`；默认 3.40/OFF、原全部业务步骤、消费者、UI、collector、strict、等待与断言保留。guard 仍将六份工作流去掉明确候选注入后逐字比对 `9ee1053b83fcf934e6f0891eb77d468fc394da1e` 的原工作流，并保留原负例。

主题入口保留原37 ON / 10 OFF / 10协议负例、三平台各4场景与新增iPad两场景。两项导入回归仍消费本次同source/run/attempt的实际iOS SDK，核对ZIP、安装身份、原UI观察和实际程序。共同模式以完整共同生产精确pin替代对无关旧producer全apps/extras的比较；旧producer备用路径保留原比较，原两项UI断言未动。

预检入口为 `reader-apple-hosts-preflight.yml`。共同生产固定并通过预检后，在同一 source 派发 `reader-apple-page-theme.yml`、`reader-apple-navigation.yml`、`reader-apple-search.yml`、`reader-apple-reading-records.yml`、`reader-apple-shelf.yml`、`reader-apple-import-mapping.yml`、`wp13-apple.yml`。本准备没有派发其中任何一组。

旧 Apple NUL 发送失败与根节点独立 Android→Apple 实测范围保持各自身份；本准备不授予双向或六平台产品同步。
