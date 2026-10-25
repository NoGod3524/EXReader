# S04 HANDOFF-RESULT — Android 交付 APK 核验

状态：实现已写入，CI 第 1 轮待推送/执行；accepted=false（未跑不得填通过）。

- 固定实现起点：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`；分支：`codex/reader-fw-s04`
- 消费的原 producer：`4a04a9cc74dde67f755c87e87b278d63a254a3ac`（`codex/reader-android-raw3-candidate`）run `40207467982` / attempt 1 / job `121211376063`
- 原 ZIP（认证后才会写入本文件的真实摘要）：
  - `reader-android-raw3-40207467982-1` id 12604412854，113970957 B，sha256 `c3db2ad1a2e31bc53d01620f2ef90e02a976e3b4f90ac76ed2e179c7c9052805`，2027-01-23T15:33:00Z 到期
  - `reader-android-page-theme-40207467982-1` id 12604537792，133598571 B，sha256 `9ea2858145313296d39792d867794db1be687eb70dec38f155dcd1dfe156bf06`，同日到期（同 run 的 `sdk-stage`，用于 JNI 身份比对）
- 候选 APK：`build/android-raw3/apks/host-debug.apk`（debug；商店/签名/真机不在范围）
- 历史失败（保留原样）：run 40214594172 / attempt 1（source d37a9bc6）static job 被我自己的「APK JNI 字节 == sdk-stage 字节」断言拒绝
  （apk 288b0efe… vs stage 88ebe479…）；根因是 Gradle 打包 strip 预置 jniLibs，不是 producer 缺陷；改为导出集合 + ELF section 内容比对，producer 工件与源码未动。
- 第 2 轮失败（保留原样）：run 40214931094 / attempt 1（source 69fc2a90）。JNI 身份改为导出集合+section 内容后**通过**（38==38 导出、18 个 section 全等，
  仅 `.debug_*` 被打包剥掉）；但 static 仍失败于两处**我方**缺陷：期望符号漏了 `Java_` 前缀、aapt2 badging 的 minSdk 行格式未匹配致解析抛错。现已修正。
- 已封存 pin（来自第 2 轮认证工件实测，并与第 1 轮日志交叉一致）：candidate 860927a8…（29721554 B）、apk_jni 288b0efe…、sdk_jni 88ebe479…。
- 未验证：真机、商店/签名、性能预算、dex 逐方法语义审计；第 3 轮（封存 pin + 新模拟器安装/启动/离线重开）尚待执行。
