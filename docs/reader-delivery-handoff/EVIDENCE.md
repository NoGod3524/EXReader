# Actions 实测证据

## 受测身份

| 项 | 值 |
| --- | --- |
| 受测源码（检查脚本所在） | `b0c6b4778dbca61b5ff41cbd5f04ca29f4b17d2f`（分支 `claude/local-c3-delivery-licenses-20261029`，基线 `bd28d494…`） |
| workflow | `.github/workflows/reader-delivery-manifest-handoff.yml` |
| 终版 run / attempt / job | [40949203489](https://github.com/NoGod3524/EXReader/actions/runs/40949203489) / 1 / `123712499128`，success |
| 输出工件 | `reader-delivery-handoff-40949203489-1`，id `12930681819`，5862 字节，`sha256:96f994a7c265853d9d71b85c0210275a49b1b2d41fe4c8688958952ef1dff89a`（GitHub 自报） |
| 前一轮（保留） | [40948655722](https://github.com/NoGod3524/EXReader/actions/runs/40948655722) / 1 / job `123710582405`，源码 `4c93d633559d4d4e12578a1b5cfe219829bf09eb`，success；工件 `12929139997`。该轮的 `root material` 列误把 `licenses/*/LICENSE` 也算作包根文件（检查脚本缺陷，已在终版修正）；其余数字与终版相同。 |

三步均成功：`guard`（身份与白名单）、`source`（源码声明与打包脚本复制，含“六端脚本都必须复制 LICENSE / 通知 / `licenses/`”的新断言）、
`artifacts`（只读下载并逐文件核对六个已发布压缩包）。本文件的提交带 `[skip ci]`，未触发新的运行。

## 被检查的已发布压缩包（**不是 bd28d494 的包**）

来自 [run 40678657371](https://github.com/NoGod3524/EXReader/actions/runs/40678657371) / attempt 1（“SDK 3.42 same-run aggregate admission”，
分支 `codex/sdk342-six-source-20261028`），打包源码 `8f8acf3234cba747165f001c0c96efe1b911e6ad`。
终版 run 的结论：与受测源码相比，**34 个**打包相关路径已变化 → `NOT EVIDENCE: packaged source differs from current source`。

| 目标 | 工件 id | 工件字节 | 工件 digest（GitHub 自报，下载后复算一致） |
| --- | ---: | ---: | --- |
| windows | 12812276328 | 17,696,295 | `sha256:0206e549…` |
| linux | 12811449234 | 18,545,727 | `sha256:be3a9116…` |
| macos | 12811976629 | 27,507,961 | `sha256:f480b2a8…` |
| android | 12812325830 | 19,702,584 | `sha256:e120fb8a…` |
| iphone | 12813015622 | 27,511,670 | `sha256:c56a913a…` |
| ipad | 12812242328 | 27,511,644 | `sha256:34cb0a2b…` |


逐文件核对：每个压缩包的 SHA-256 与其 `manifest.json` 一致；`manifest.json` 记录的每个文件在压缩包里的字节 SHA-256 一致；
`manifest.source_sha` = `8f8acf32…`、`provenance.run_id/attempt` = `40678657371/1`；`result.json` 的 `passed` 为 true。

## 许可材料实测（压缩包里有没有）

期望集合 = 登记表中、按**该压缩包自带 CMakeCache** 的开关启用的第三方许可文件。

| 目标 | 压缩包字节 | 逐文件已核对 | 随包许可文件 | 期望 | 缺失 | 包根 LICENSE / 通知 | FAAD2 随包 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| windows | 17,684,380 | 36 | 22 | 22 | 0 | 有 | 否 |
| linux | 18,511,581 | 31 | 22 | 22 | 0 | 有 | 否 |
| macos | 27,524,676 | 42 | 23 | 23 | 0 | 有 | 否 |
| android | 19,699,629 | 5 | **0** | 15 | **15** | 有（仅这两个根文件） | 否 |
| iphone | 27,530,694 | 42 | 23 | 23 | 0 | 有 | 否 |
| ipad | 27,530,689 | 42 | 23 | 23 | 0 | 有 | 否 |

- 结论仅限这批旧包：桌面与 Apple 压缩包的许可目录与期望集合一致；**Android 压缩包缺 15 个许可文件**（见 [PACKAGING-PATCH.md](PACKAGING-PATCH.md)）。
- 六个压缩包都没有 `faad2/`；源码侧：`EXR_ENABLE_AAC` 默认 OFF、`reading-library` 预设 OFF，没有任何 F06/sdk342 打包脚本或工作流写入 `EXR_ENABLE_AAC=ON`。
- minimp3：Apple 两端压缩包含 `minimp3/LICENSE`（该构建启用了音频 + MP3，与矩阵第 1 节一致）。
- 这里只检查路径是否存在与压缩包完整性，**没有**再比较许可文本内容与上游的一致性（那是 `tools/check_reading_licenses.py` 在 SDK 安装树上做的事）。

## 缺口与处理

- Android：打包脚本补丁已提交（`tests/android_sdk342_package/run.py` 一行），本分支 Actions 只验证了它能编译、且 `source` 步骤看到它复制 `licenses/`；
  **未在真实 Android 打包流水线里运行**，所以 Android 压缩包是否真的出现 `licenses/` 仍未验证。
- 没有 bd28d494 的六端压缩包；整合分支需在同一 SHA 上重跑后才能对新版本下结论。
- 本包不改变固定 108 项的验收计数，也不是 F01/F07/F08/F12 的通过证据。

---

# 追加：Android SDK 3.42 实际打包验证与检查加固（源码 `9bced259710edff4bb98c730121ca09295500d73`）

以上内容保留为 b0c6 轮的记录（只读旧包 + 源码复制行）。下面是用户退回后补做的真实验证。

## 受测身份

| 项 | 值 |
| --- | --- |
| 受测源码 | `9bced259710edff4bb98c730121ca09295500d73`（基线 `bd28d494…`；`android_admission.py guard` 通过：改动路径只在 C3 声明范围内，`run.py` = 基线 + 声明的 8 行） |
| Android 打包验证 run / attempt / job | [40950703390](https://github.com/NoGod3524/EXReader/actions/runs/40950703390) / 1 / `123717743311`，workflow “C3 Android SDK 3.42 package licence binding”，**success**（全部步骤 success，含 API 34 x86_64 模拟器安装） |
| Android 输出工件 | `c3-android-sdk342-licenses-40950703390-1`，id `12931817204`，19,778,654 字节，`sha256:f6f164d07ad081785d8a10cb95e52f8a4a8784e5ad3630fee3e506113906b368`（GitHub 自报） |
| 清单检查加固 run / attempt / job | [40950703274](https://github.com/NoGod3524/EXReader/actions/runs/40950703274) / 1 / `123717742993`，**success**；工件 `12931870627`，`sha256:5479c7859d8993acdfe06539b804028c5040ca9a80a5671fc65333008a587194` |
| 归档 | `EXReader-android-9bced259710e.zip`，sha256 `b4baebfabbd9d05c243aade3765143335f00d5d856a8a29332fb0d8149e963f2`；归档内 APK 与模拟器装入的 APK 同为 `df7defce60b99ca6eb3ad50450671518a69c256256a6f6e3eb6642fa6f849dbd` |

流程（全部在 Actions）：C3 身份准入 → 安装规范 OPDSHash 前缀（`EXREADER_ORIGINAL_HASH_PREFIX`，复用 C1 的 `hash_stage` 做法，
不使用私有回退，没有删除任何 provider 检查）→ **原** `tests/android_sdk342_package/run.py build`（同一份 composition 配方，原断言与预算未改，
原冻结 guard 未改）→ 原 `identity.py package` → `android_verify.py verify` → **原** `identity.py android` 模拟器安装 → `finalize`。

## 归档 `licenses/` 与安装树的逐字节核对

- 归档 `licenses/` 15 个文件；`build/wave3/sdk-stage/share/exreader/licenses` 安装树 15 个文件；**闭集相等、逐字节相同：是**。
- 按该构建自己的 CMakeCache 开关，登记表期望 15 个，缺失 0，安装但不在期望内 0。启用的登记组件：
  freetype、expat、miniz、stb、openjpeg、lcms、sqlite、minimp3、unicode、argyll-cmyk、adobe-glyph-list、pdfjs-data、pdf-calculator-names、noto-test-fonts。
  （FAAD2、libwebp、libtiff、libavif/libaom、Mbed TLS 在该构建中关闭，归档里也没有。）
- 实际安装的 vendor 归档：expat、exr_jpx、exr_lcms、exr_sqlite、freetype、miniz；与登记缺失 0、未登记 0。

## 产品前缀（`build/wave3/stage`）

- 安装的产品包 20 个：AnnotationExport/Import/View 0.2.0、Commands 0.2.0、FontLibrary 0.1.0、JumpHistory 0.2.0、Navigation 0.1.0、OriginalExport 0.1.0、
  Preferences 0.1.0、ProductCatalog 0.1.0、ReadingCommands 0.2.0、ReadingState 0.2.0、Revisions 0.4.0、Search 0.1.0、Session 0.2.0、Sideload（无版本文件）、
  Sync 0.2.0、SyncView 0.2.0、WebDAV 0.2.0、WebDAVObserved 0.1.0。
- 产品前缀里的许可类文件 2 个，均已随包到 `product-licenses/` 并与安装文件逐字节相同：
  `exreader-product/sqlite-public-domain.txt`（**产品目录自带 SQLite 的声明**，与仓库 `licenses/sqlite-public-domain.txt` 逐字节相同）、`exreader-webdav/LICENSE.txt`。
- SDK 的 SQLite 声明 `licenses/sqlite/sqlite-public-domain.txt` 同在归档中。

## APK 实际依赖的原生库

`libexreader.so`（APK 自带的第一方库）与 `libOpenSLES.so`（Android 系统提供的 OpenSL ES）之外，APK 只需要 libc/libm/libdl/liblog/libandroid/libz/libjnigraphics 一类系统库。
`libOpenSLES.so` 未在检查脚本的系统库名单里，所以被列为“非系统”；这是名单不全而不是额外第三方依赖。

## 清单检查加固（同一 run 40950703274）

`check.py artifacts` 现在：下载的 ZIP 逐成员拒绝重复（含大小写折叠）、绝对路径、`..`、反斜杠、盘符、符号链接/非常规成员、加密成员，
不再使用 `extractall`；GitHub 工件 digest **必须存在且等于下载字节的 SHA-256**，`size_in_bytes` 必须等于下载大小；
工件 id、`workflow_run.id/head_sha`、`manifest/result/configuration` 的 `source_sha/run_id/attempt/target`、归档 SHA-256 与字节数全部强制核对；
归档成员集合必须**恰等于** `manifest.files ∪ manifest.metadata_files`，每个文件的字节与 SHA-256 一致，归档内的 `manifest.json` 必须等于工件 manifest（去掉 `archive`），
`SHA256SUMS` 必须等于由 manifest 重算的内容。对六个旧包的结果与前一轮相同（Android 仍缺 15 个，其余缺 0）——这是旧包的真实状态。

## 仍然不能授予的

- 这次验证的是 **SDK 3.42 + bd28 同源（加 C3 声明补丁）的 Android 单包**，不是六端：Windows/Linux/macOS/iPhone/iPad 在 bd28 上没有新包，仍只有 8f8acf32 的旧包证据。
- 编译产物内部是否确含某第三方代码只是由 CMake 开关与已安装归档推断；NDK `c++_static` 与系统库不由 EXReader 随包许可；
  没有逐字对比上游许可文本（那是 `tools/check_reading_licenses.py` 的职责）；没有法律结论。
- 模拟器步骤是原 `identity.py android` 的安装与启动检查，不是 GUI 回归，也不是真机/arm64/商店包。
- 不授予 F12；不改变固定 108 项计数；不是 F01/F07/F08 的通过证据。补丁仍需主代理核验后再决定是否并入共同分支。
