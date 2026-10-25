# S04 HANDOFF-RESULT — Android 交付 APK 核验

状态：实现已写入，CI 第 1 轮待推送/执行；accepted=false（未跑不得填通过）。

- 固定实现起点：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`；分支：`codex/reader-fw-s04`
- 消费的原 producer：`4a04a9cc74dde67f755c87e87b278d63a254a3ac`（`codex/reader-android-raw3-candidate`）run `40207467982` / attempt 1 / job `121211376063`
- 原 ZIP（认证后才会写入本文件的真实摘要）：
  - `reader-android-raw3-40207467982-1` id 12604412854，113970957 B，sha256 `c3db2ad1a2e31bc53d01620f2ef90e02a976e3b4f90ac76ed2e179c7c9052805`，2027-01-23T15:33:00Z 到期
  - `reader-android-page-theme-40207467982-1` id 12604537792，133598571 B，sha256 `9ea2858145313296d39792d867794db1be687eb70dec38f155dcd1dfe156bf06`，同日到期（同 run 的 `sdk-stage`，用于 JNI 身份比对）
- 候选 APK：`build/android-raw3/apks/host-debug.apk`（debug；商店/签名/真机不在范围）
- 未验证：全部检查（尚无 Actions run）；未做真机、商店签名、性能预算、dex 逐方法语义审计。
