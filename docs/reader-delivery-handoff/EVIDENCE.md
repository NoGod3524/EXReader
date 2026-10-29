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
