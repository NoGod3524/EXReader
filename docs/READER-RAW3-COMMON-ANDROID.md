# Android 共同源码完整原链投影

准备起点：`1a6d98ed613c61ffea4267f01f83e2c49b1c02f6`。
分支：`codex/reader-raw3-common-android`。当前只准备源码，未推送、未运行，`accepted=false`。

## 保留原链

新工作流投影到 `caa84411ae79c866c28cf982243b6cb80b4bbe49` 的
`.github/workflows/reader-android-raw3.yml` 后必须逐字相等。保留 android / protocol / summary 三个 job、
原超时、API34 default x86_64 模拟器、所有 SDK/模块构建参数、工件成员和原执行步骤。
原 130 项、默认 sender 8 项、raw 19 项、protocol 18 阶段及 Java20 均不删减。

仅允许以下投影差异：工作流名与分支；两处独占旧 guard 入口替换为 common guard 和拒绝负例；
summary 增加完整 checkout 并改用附加严格入口；每个 producer 增加 common 来源报告上传，
summary 另上传补充严格来源报告。旧文件一行不改。

## common guard 与旧 guard 分开

旧 guard 的独占路径约束在共同树上会正当拒绝，所以不执行、修改或伪装其成功。
新 guard 验证实际 `HEAD == GITHUB_SHA`、基线祖先和干净 checkout；所有基线旧文件的 blob/mode 固定，
新文件只限自身目录、新工作流及两份专用文档，拒绝 symlink 与 executable mode。
明确验证批准 SDK3.41、raw 七包、既有 Android 家族、原 Android owner/全部旧 suite、metadata/schema
及批准 WebDAV 修复树。两处 guard 从实际树得到相同的模块/SDK/suite 布尔结果。

兼容位置 `build/android-raw3/guard.json` 保存的是明确标注
`guard_kind=common`、`legacy_guard_executed=false`、`source_guard_only=true` 的新报告。
它的 `accepted=true` 只说明共同源码约束通过，不声称旧 guard 被执行或 runtime 通过。
附加 strict 实际认证两个 producer 的原 ZIP，并将旧 raw strict 真正读取的 guard 对象与认证的新报告逐字字段比较。

## 原 strict 不变

新 strict 先执行原 `reader_android_record_interop/check_evidence.py`，再用 `runpy` 完整执行未修改的
`reader_android_raw3/strict.py`。后者全部原断言照常执行；仅保留其返回的 globals，取得它实际从
认证 raw ZIP 读取的 guard 对象。没有拦截 assert、重设 `GITHUB_SHA`、改源文件或替换结果。
随后新增来源认证：同 run/attempt/source 的 android/protocol 已成功；两个 common guard 原 ZIP
字节、digest、有效期、成员与负例名单正确；guard 来源为 common 且不是 legacy；fresh 检查完全相等。

负例仅 Actions 执行：实际临时 index mutation tree 验证 SDK、raw、owner、旧 strict/guard/business 不可改，
并检查 scope/mode、workflow 的 raw flag/API/超时/原业务/peer/工件/strict/guard 变更均拒绝。
真实 HEAD、index 和事件环境保持原样。

## 范围

固定 incoming Mac peer 仍是独立来源 `15dab6b2…`、run `40196978163/1` 的原工件；
本包不会将其改称共同源码 Apple 发送方，不授予共同源码双向互通。
运行通过时只授予本次同源 Android 完整 leaf；`complete_product=false`、`physical_device=false`、
`bidirectional_interoperability_accepted=false`。最终 root 将与其他包装器一起明确更新允许路径和 pin，
并在同一最终 source 运行全部 leaf；不同源码结果不能拼接。

机器状态见 [验证记录](validation/reader-raw3-common-android.json)。
