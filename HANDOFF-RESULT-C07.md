# HANDOFF-RESULT-C07

结论：同源双向原生记录协议联验 **通过（第 1 轮 CI，无需重跑）**。范围仅限 Android API34 x86_64 模拟器与 macOS 的原生 owner/协议。不授 GUI、六平台、真机、性能、最终产品。

## 固定身份
- 目标源码（固定起点）`e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`；受测提交 `d3f7ec5bb57b372a0b61d13446e7ce8ea2d1ae4f`（与起点只差独占路径）。分支 `codex/reader-next-c07`。
- run [40227524890](https://github.com/NoGod3524/EXReader/actions/runs/40227524890) / attempt 1，5 作业全 success：fixtures 121271966346、mac-send 121272011651、android 121273048017、mac-receive 121274699589、strict 121274955993。
- 严格结果：`accepted=true`，76 项具名检查全过，pending=[]，failed=[]，两个方向 `macos->android`、`android->macos` 均 true。

## 原工件（有效期均 2027-01-23T19:45:22Z）
| 工件 | ID | 字节 | SHA-256 |
| --- | ---: | ---: | --- |
| c07-fixtures | 12611796017 | 9924 | 26614ea8d224d42b94235098de14529ff06113819ee32dbbfcc334fcd06e93a2 |
| c07-mac-sender | 12611641757 | 20679042 | 82a6159bde05342af8311b7e2f5567aa767b182c38a5199e4a9b16fb516f9044 |
| c07-mac-toolchain | 12611980958 | 26187423 | 8297df663ecc6b11722a734db56371abe78b685fcc58c717a4de19b88845e8dc |
| c07-android-evidence | 12611932979 | 53972193 | 104a02d0b67bdbde7bb793d9c0d08996e374028146099115cfffd1044391c91f |
| c07-android-sender | 12612511498 | 23726 | b147128920ccc003d4a1bc5694d93bd4890963463270c8a5b549bf85132f204b |
| c07-mac-receive | 12612267111 | 86257 | 779872124f042100e1403b9f7796652c832b09f788801fe93bb3dd499281ae66 |
| c07-strict | 12612117360 | 3160 | 63a597a75d636734fec48cc5e87d66d538c612a922d535e0f3824578388395f9 |

## 程序与记录集
- macOS 发送端与接收端为同一可执行文件，SHA-256 `9970dcb4880510cca972f9886cf24b669251a607aa239101532ae1160b2130cc`（接收为不同的 6 个新进程）。
- Android APK `967bcd1080c51ed8aa748b4e61432cdb9a75f4b445c665cd1fb8d306256f5fd9`，唯一 SDK DSO `a345ab4c1def2e864a76b9e879da8a372e8821ad09b7991c8fe4e04626b2e8ac`。
- Mac manifest `eae275e0…504243c`，Android manifest `fb5e9889…f64a2`；各 4 原件、11 条真实记录；四格式字节与冻结集一致（PDF 8845B）。
- Mac→Android：同 run 的 Mac ZIP 为对端，Android 新进程经原生 HTTPS 256 分片收取并独立 FOUND/重捕获 11 条；Mac NULL 单独保留、不可导航。
- Android→Mac：新进程公开 receive 与 HostAccountSession HTTPS 256 分片各自 FOUND/重捕获 11 条并重开；Android NULL 单独接收，无 typed 位置、无 FOUND、导航被拒。
- EPUB 章节重建与 transport 分列记录：strict 的 `transport_vs_reconstruction` 中 12 行 route 不同，不计入失败，numbers/selectors 均相等。

## 未验证/保留
- 无失败轮次。未执行：GUI、六平台、真机、性能、最终产品；未复跑原 130 项/18 阶段协议控制（本包不重复，沿用其各自封存）。
- Android NULL 导出、Mac `null-receive` 为本包新增 harness，仅此一轮验证。
- 未开 PR/tag/Release。
