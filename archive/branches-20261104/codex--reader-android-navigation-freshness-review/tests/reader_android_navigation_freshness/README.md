# Android navigation cache differential

固定失败来源 `bd8c3638019280bea6496b778339abf04629bd27` / run `40229070687` attempt 1 / Android job `121276697202`。第四项检查找不到 Group；失败画面仍为首批 32 行，不能混同前面成功检查中末批 13 行的画面。

仅 Actions 执行一次受限实验。原 baseline/OFF APK 和原 navigation APK 从已登记工件按 ZIP 字节、SHA-256、来源、有效期认证，先运行原 18 项导航套件。SDK 安装包直接复用，原 APK 不改签。

投影只为原 `result` 查询增加只读目录快照，以及显式 fresh 模式下的 UiAutomation.clearCache；其余断言、30 秒查询等待、900 秒阶段上限和完整 18 项名单不变。对比清理前后同一 window 的标题、行号、可见和启用状态，不强制回顶，不替换 owner 数据。

新 probe 如被系统明确拒绝签名，保留原 APK 对照和拒绝日志，才进入单独标注的“固定 bd8 源码重建 baseline/OFF host + trace probe 同签”范围；记录 APK、证书和 native 库 SHA-256，验证 OFF 标志。只有缺失的小 WebDAV stage 重建，SDK 不重建。该范围不声称使用原 APK。

所有结果恒为 `accepted:false`。一次成功或失败只说明该组执行结果；同一窗口清缓存前后的差分用于检验缓存假设，不授予产品验收，也不代替原公共来源失败。

## 已封存结果

受测诊断源码 `798a96c52932ab67635023b8a2623c7297d281b7`，run [40233907741](https://github.com/NoGod3524/EXReader/actions/runs/40233907741) attempt 1 成功。

| 组 | 实际结果 |
| --- | --- |
| 封存原 baseline APK + 原 navigation APK | 原套件 16 + 2 = 18 项通过 |
| 封存原 baseline APK + 新 trace probe | Android 明确拒绝签名；0 项，保持失败 |
| bd8 baseline/OFF 同签重建 host + trace probe，trace 模式 | 原套件 18 项通过 |
| 同一重建组，fresh 模式 | 原套件 18 项通过 |

fresh 第三项 `hierarchy_unicode_fragment_selects_independently_verified_part` 的同一 window 181，标题前后均为“目录 · 45 项 · 本批 32 项”、native_live 均为 1。事件 1 的 rows 为空；clearCache 返回 true 后，事件 2 出现可见启用的 row0 `First & chapter`、row1 `Group` 等五行。第四项真正查 `Group` 时，window187 在清缓存前后都有同一个可见启用 row1，未观察到差分。因此证据支持“探针缓存可以陈旧”，尚不能直接归因先前第四项 Group 失败。

重建组的 APK 和证书均不同于封存原件；SDK、host、JNI 三个 native DSO 字节与原件一致，product DSO 不同，不能把同签重建组写成原 APK 执行。357 个复用 SDK/产品 stage 文件在该次实验前后哈希不变，owner BuildConfig false 和 native cache OFF 守卫通过。

最终工件 `12613604629`，22,249,008 B，SHA-256 `86489765d5b7fd4a2f9de75c5c5b9e9d1d815c4e8af4662d9946cd2387bc6b29`，有效期 `2027-01-23T21:06:28Z`。无模拟器检查 run [40234679542](https://github.com/NoGod3524/EXReader/actions/runs/40234679542) 在云端重新认证 ZIP 后打印了配置、证书、完整 native hash 和上述原始缓存事件。本地未下载或解析工件。

历史诊断失败保留：run `40232637095` 的新 probe 编译成功，但原 host 拒绝其签名；缺失 report 的 adb exit0 被收集器误当 JSON，finally 再解析错误掩盖原错误。无模拟器检查 `40233119316`、`40233225167` 认证了真实日志。run `40233313404` 修正收集后再次取得原 18/18，但错误地要求 host 与 androidTest 的 BuildConfig 总数为 1；随后只按 owner package 与目标标志筛选唯一配置，保留 false 校验与全部原配置。两次失败不作通过证据。
