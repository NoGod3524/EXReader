# Android navigation cache differential

固定失败来源 `bd8c3638019280bea6496b778339abf04629bd27` / run `40229070687` attempt 1 / Android job `121276697202`。第四项检查找不到 Group；失败画面仍为首批 32 行，不能混同前面成功检查中末批 13 行的画面。

仅 Actions 执行一次受限实验。原 baseline/OFF APK 和原 navigation APK 从已登记工件按 ZIP 字节、SHA-256、来源、有效期认证，先运行原 18 项导航套件。SDK 安装包直接复用，原 APK 不改签。

投影只为原 `result` 查询增加只读目录快照，以及显式 fresh 模式下的 UiAutomation.clearCache；其余断言、30 秒查询等待、900 秒阶段上限和完整 18 项名单不变。对比清理前后同一 window 的标题、行号、可见和启用状态，不强制回顶，不替换 owner 数据。

新 probe 如被系统明确拒绝签名，保留原 APK 对照和拒绝日志，才进入单独标注的“固定 bd8 源码重建 baseline/OFF host + trace probe 同签”范围；记录 APK、证书和 native 库 SHA-256，验证 OFF 标志。只有缺失的小 WebDAV stage 重建，SDK 不重建。该范围不声称使用原 APK。

所有结果恒为 `accepted:false`。一次成功或失败只说明该组执行结果；同一窗口清缓存前后的差分用于检验缓存假设，不授予产品验收，也不代替原公共来源失败。
