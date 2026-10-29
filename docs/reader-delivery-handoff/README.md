# F12 交付说明与许可依赖核对（C3 交接包）

分支 `claude/local-c3-delivery-licenses-20261029`，共同基线 `bd28d4946f17a184dd3cd47a584cf49fce34e973`
（`codex/apple-sdk342-full-handoff-20261029`）。本包只新增 `docs/reader-delivery-handoff/`、
`tests/reader_delivery_manifest_handoff/` 与一个专属 workflow；未改 SDK、应用、迁移、Apple 文件。

**本包不等于 F12 全面完成，也不是 F01/F07/F08/F12 或完整产品的通过证据，不改变固定 108 项的验收计数。**

| 文件 | 内容 |
| --- | --- |
| [USER-GUIDE.md](USER-GUIDE.md) | 六端安装 / 启动 / 导入 / 同步 / 原件与标注导出 / 备份与恢复说明（含明确的“未实现”） |
| [LICENSE-DEPENDENCY-MATRIX.md](LICENSE-DEPENDENCY-MATRIX.md) | 依赖、许可、开关、随包路径矩阵；FAAD2 等可选依赖的项目自有记录 |
| [EVIDENCE.md](EVIDENCE.md) | 实际 Actions 运行（run / attempt / job / artifact）与检查结果 |
| `tests/reader_delivery_manifest_handoff/check.py` | Actions 专用的只读检查：源码声明、打包脚本、文档链接、已发布压缩包逐文件核对 |

## 身份与证据边界

- F06 同源 SDK 3.42 成功证据 [run 40678657371](https://github.com/NoGod3524/EXReader/actions/runs/40678657371)（attempt 1，
  “SDK 3.42 same-run aggregate admission”，分支 `codex/sdk342-six-source-20261028`）打包的是源码 `8f8acf3234cba747165f001c0c96efe1b911e6ad`，
  **不是** `bd28d494`。两者之间 `annotation-export`、`annotation-import`、`original-import`、`reading-commands`、`reading-state`、
  `revisions`、`sync`、`store/native`、`extras/opds` 以及 Apple 宿主 Swift 文件有改动，所以这些压缩包**不能**当作 bd28d494 的包。
  本包对它们只做“包里有什么”的读取，并在报告里写明 `NOT EVIDENCE for current source`。
- bd28d494 上唯一已有的运行是 Apple 全量宿主门禁 run 40937997549（attempt 1，结论 failure），由其他代理负责，本包不引用其为通过。
- 没有 tag、Release、PR、默认分支操作；也没有接触凭据或用户资料。

## 做了什么检查（全部在 GitHub Actions 里执行，本机不构建不运行）

1. `guard`：`HEAD == GITHUB_SHA`、基线为祖先、改动路径全部落在本包白名单（以及 `PACKAGING-PATCH.md` 声明的包级补丁）、
   受保护树（`src include cmake CMakeLists.txt CMakePresets.json LICENSE THIRD_PARTY_NOTICES.md licenses apps examples bindings tools`）与基线逐字节相同。
2. `source`：用 `tools/check_reading_licenses.py` 的登记表和 CMake 默认值/预设/构建脚本旗标，推导六端各自应随包的许可文件；
   读取六端打包脚本是否复制 `LICENSE`、`THIRD_PARTY_NOTICES.md`、`licenses/`；核对文档内相对链接；记录 FAAD2 默认关闭且无脚本启用。
3. `artifacts`：只读下载 run 40678657371 的六个 `f06-<target>-…` 工件，核对 GitHub 报告的 digest、`manifest.json` 的逐文件 SHA-256、
   压缩包 SHA-256、构建源与 run/attempt；列出每个压缩包的实际许可路径，与按**压缩包自带 CMakeCache** 推导的期望集合比较，输出缺失与多余项。

## 包级处理

Android 压缩包缺少 `licenses/`（Actions 实测）。本分支对 `tests/android_sdk342_package/run.py` 做了一行补丁，声明与未验证边界见 [PACKAGING-PATCH.md](PACKAGING-PATCH.md)。

## 剩余阻塞与尚未验证

- 没有 bd28d494 同源的六端压缩包；需要由整合分支在同一 SHA 上重跑六个生产者与同轮验证后，才能对新版本下结论。
  `tests/reader_f06_packages/identity.py` 的 `guard` 对改动路径有白名单，本包的路径不在其中，所以**不要**在本分支上直接跑 F06 打包。
- 六端 GUI 步骤未在本包内实操；整库备份/恢复在源码中未实现（见 USER-GUIDE 第 5 节）。
- 签名、公证、商店包、真机、arm64 Android、非 ubuntu-22.04 的 Linux：均未覆盖。
- 法律结论未作；FAAD2 等可选依赖的“能否分发”交由项目许可评审。
