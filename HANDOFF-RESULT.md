# S04 HANDOFF-RESULT — Android 交付 APK 核验

**状态：accepted=false。** 三轮 CI 已用尽；末端 commit 只修掉 last 一个**我方**语法缺陷，**未再执行**（不再刷 run）；模拟器作业三轮都被 static 失败挡住，从未运行。
本包**没有**任何"通过"主张。

## 1. source 表（三种 source 分开）

| 角色 | 值 |
| --- | --- |
| 固定实现起点 | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| 本包分支 / 远端 | `codex/reader-fw-s04`（已 push，未开 PR） |
| 受测（实跑）commit | `d37a9bc6`（run 40214594172）、`69fc2a90`（run 40214931094）、`e7b91fa9`（run 40218466254） |
| 末端 commit（已修语法，**未执行**） | 见分支 tip（本文件所在 commit） |
| docs-only 封存 SHA | **无**（没有 accepted 的 run，不封存） |
| producer source | `4a04a9cc74dde67f755c87e87b278d63a254a3ac`（`codex/reader-android-raw3-candidate`），run `40207467982` / attempt 1 / job `121211376063` |

## 2. 认证过的原工件（ZIP 字节与 digest 实测相等，未过期）

| 角色 | artifact id / name | 字节 | sha256 (GitHub digest) | 到期 |
| --- | --- | --- | --- | --- |
| raw3 | 12604412854 / `reader-android-raw3-40207467982-1` | 113970957 | `c3db2ad1a2e31bc53d01620f2ef90e02a976e3b4f90ac76ed2e179c7c9052805` | 2027-01-23T15:33:00Z |
| sdk-stage | 12604537792 / `reader-android-page-theme-40207467982-1` | 133598571 | `9ea2858145313296d39792d867794db1be687eb70dec38f155dcd1dfe156bf06` | 2027-01-23T15:33:00Z |

## 3. 认证过的真实程序哈希（同一 producer ZIP 内实测）

| 程序 | 路径 | 字节 | sha256 |
| --- | --- | --- | --- |
| 候选 APK（raw3 family debug） | `build/android-raw3/apks/host-debug.apk` | 29721554 | `860927a89eb7ab2e6ffcd93d596e7206a830f15d396be0e0135bf82bedb0b5f3` |
| default-OFF APK | `build/android-raw3/baseline/host-debug.apk` | — | `a4627d562df9c2436a9f91f1371112de5ad6801e4f43544546c412195e1d0c74` |
| raw3 instrumentation APK | `build/android-raw3/apks/raw3-test.apk` | — | `dae5e91a5480d68d69d164efc2ee56abfb7bb9cf4084eb4e2fae80fa94aa13bf` |
| raw3 release-unsigned APK | `build/android-raw3/apks/host-release.apk` | — | `348c8c5bc81ab323ffb12577cd89bdb90bc2cf290bc0dc6511ef97eb755a1416` |
| APK 内 JNI（strip 后） | `lib/x86_64/libexreader_jni.so` | 40392 | `288b0efe39ba577ef923957d24dff3c4e9e70aaab6b92701e25e214717e3818a` |
| 同 run SDK stage JNI 原件 | `build/session-android/sdk-stage/lib/libexreader_jni.so` | 176496 | `88ebe479a3aab9e5bc6ee93e3bb4d8dcc67301fd1e7c310da84118027310dc19` |

## 4. 实际跑出来的检查项（有原 log 支撑，仅这些）

出自 run `40214931094`（source `69fc2a90`，原 log 保留）：

- **工件认证**：run/attempt/job 与 artifact id/name/bytes/digest/expired/expires_at/workflow_run.head_sha 全部与 Actions API 逐项相等；下载 ZIP 的 sha256 == sealed digest（两次独立运行一致）。
- **APK 清单**：ZIP 内 4 个 APK 全部计哈希；候选为 `build/android-raw3/apks/host-debug.apk`。
- **ZIP 结构**：entry 唯一、`testzip` 干净、`classes.dex…classes6.dex`、`lib/` 只有 x86_64（libexreader.so / libexreader_host.so / libexreader_jni.so / libexreader_product.so）。
- **SDK/JNI 身份**：与同 run `sdk-stage` 比对，导出集合（`Java_*`/`JNI_*`）**38 == 38**；18 个同名 ELF section **逐个字节相等**（含 `.text`、`.rodata`），差异只有被 Android 打包剥掉的 `.debug_*`。
- **SDK 版本字符串**：`3.41.0` 出现在出货 `libexreader.so` 中。

## 5. 原失败（逐轮，不改写）

1. run `40214594172` / attempt 1（`d37a9bc6`）：static 被**我方**断言拒绝——我把"APK 内 JNI 字节 == sdk-stage 字节"当作身份；实测 `288b0efe…` ≠ `88ebe479…`。根因是 Gradle 对预置 jniLibs 做 strip，**不是 producer 缺陷**；producer 工件/源码一行未动。
2. run `40214931094` / attempt 1（`69fc2a90`）：改成导出集合 + section 内容后**该项通过**；但 static 又失败于两处我方缺陷：
   （a）期望 JNI 名漏了 `Java_` 前缀（我把 `Java_(org_exreader_…)` 的捕获组当成了完整符号名）；
   （b）`aapt2 dump badging` 的 minSdk 行不是 `sdkVersion:'26'`，`parse_badging` 抛 `AttributeError`，导致版本/权限/资源/签名全部未跑到。
3. run `40218466254` / attempt 1（`e7b91fa9`）：`py_compile` 报 `static_apks.py:307` SyntaxError——我在写文件时把一个换行转义写进了 Python 字符串字面量。**static 与 emulator 均未执行**。

末端 commit 已把 (3) 的打印语句改为逐行输出（不再含转义），并保留 (2) 的两处修复与已封存 pin；**没有**第 4 次 run（遵守"最多三轮"）。

## 6. 明确未验证（pending，不得视为通过）

- `package / versionCode=1 / versionName=0.1.0 / minSdk=26 / targetSdk=35`（aapt2 路径）
- 权限集合恒等于 `{android.permission.INTERNET}`（"权限变化即拒绝"的断言已写，未跑到）
- 资源/资产身份：`assets/reader-catalog-v1.json` 与 `apps/reader/store/001_catalog.sql` 重生成一致、`assets/Reader.otf` == `tools/host_font.py` pin、`assets/OFL.txt`
- apksigner 验签 + 单签名者 + v2/v3 + 调试证书（只 debug 候选）
- default-OFF 与 raw3 候选的差异/同身份对照
- **新模拟器**：安装前干净 profile、`pm path` 字节 == 认证 APK、`dumpsys package` 版本、运行期 `EXReader 3.41.0/<abi> · x86_64`、`/proc/<pid>/maps` 真实加载 JNI、原件导入并保留字节、阅读记录（`book_progress`）落盘、**断网冷启动重开同页码**
- 真机 / 读屏 / 商店签名 / 性能预算 / dex 逐方法语义

## 7. 复跑方法（root 直接用，不需要改代码结构）

```
gh workflow run reader-final-s04.yml --ref codex/reader-fw-s04
```

- workflow：`.github/workflows/reader-final-s04.yml`（只由本分支 `tests/reader_final_s04/**` 与本文件触发，或 workflow_dispatch；jobs：static → emulator → summary，无 matrix）
- 封存 pin 已在 `docs/reader-final-s04/apk-contract.json`（`S04_ALLOW_DERIVE=false`），来自 run `40214931094` 实测并与 run `40214594172` 交叉一致
- 期望值不是手填：由 `expectations.py` 用 `git show 4a04:<path>` 从 producer 源码重推；producer 源码或 blob id 一变即拒绝
- 已知最可能的下一处失败点（按运行顺序）：`parse_badging` 若在真实 badging 文本上仍取不到 minSdk（已兼容 `sdkVersion:'X'`/`minSdkVersion:'X'`/`minSdkVersion='X'` 三种写法，并会把 badging 前 25 行打进日志）；之后是模拟器内 `ImportEntry` 暂存恢复导入与断网重开的时序。

## 8. 结论

只做了"读源码 + 设计并实现 + 3 轮云端实跑"。**已证据化的只有**：原工件 ZIP 认证、APK 清单、ZIP/ABI 结构、APK 内 JNI 与同 run SDK stage 的同源身份（导出+section）。**版本/权限/资源/签名与全部实机项都还是 pending**，`accepted=false`，不授商店/签名/真机，也不构成 Android 交付 APK 的整体通过。

## 9. run / attempt / job / artifact 一览（全部 terminal，无 live run）

| source | run / attempt | static job | summary job | emulator job |
| --- | --- | --- | --- | --- |
| d37a9bc6 | 40214594172 / 1 | 121232886097 (failure) | 121233199903 (failure) | 121233201079 (skipped) |
| 69fc2a90 | 40214931094 / 1 | 121233900496 (failure) | 121234192779 (failure) | 121234193740 (skipped) |
| e7b91fa9 | 40218466254 / 1 | 121244630206 (failure) | 121244683162 (failure) | 121244683703 (skipped) |
| 52cf775f（tip） | 未跑（[skip ci]，轮次上限） | — | — | — |

工作流自身产出的 artifact（均为本包证据，非 producer 原件）：reader-final-s04-static-<run>-1 / reader-final-s04-emulator-<run>-1 / reader-final-s04-summary-<run>-1。
producer 原件见第 2 节。没有开 PR、没有推默认分支、没有 tag/Release。
