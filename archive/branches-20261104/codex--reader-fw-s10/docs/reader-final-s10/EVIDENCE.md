# S10 实际证据（同一 source / run / attempt）

- 受测源码：`9f49b736ecee0baeee8d9524e7e75a40592ae5d0`（分支 `codex/reader-fw-s10`）
- 运行：[run 40218271618](https://github.com/NoGod3524/EXReader/actions/runs/40218271618) / attempt 1，5/5 作业 success
- 固定实现起点：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`；SDK 3.41.0 / ABI 1（`src include cmake CMakeLists.txt` 相对起点逐字节不变）
- 本包只新增：`tests/reader_final_s10/`、`.github/workflows/reader-final-s10.yml`、`docs/reader-final-s10/`、`HANDOFF-RESULT.md`

## 1. 作业与工件（同一 attempt，均由 summary 重新认证）

| 作业 | job id | 结论 | 工件 | 字节 | ZIP SHA-256 | 有效期 |
| --- | --- | --- | --- | ---: | --- | --- |
| guards | 121244044679 | success | 12608745043 | 4064 | `61da68730017ded8195d8059dfdf1dd06caf2ec0b605e1c092a6d53cb47369cb` | 2027-01-23T17:48:56Z |
| android | 121244044649 | success | 12608329499 | 7686 | `b89adf8a8d179571f7818fdbf5b8d70867717e988cea992eaf60e23824818c0a` | 2027-01-23T17:48:56Z |
| apple | 121244044513 | success | 12609011496 | 53650661 | `d121579d68ebad9935b3c5509bb5c3fa900bb11dd743f232c6ab8ad56faf9e29` | 2027-01-23T17:48:56Z |
| desktop | 121244044692 | success | 12608640524 | 20847 | `0338489b09eab5940a0fe3090083588cb4a36ac2af164d4e3efea3f7874926ed` | 2027-01-23T17:48:56Z |
| summary | 121247475395 | success | 12608596187 | 7624 | `17b45691ed01e5d80c5b61ad6ce8147577e6180415a35d40ad9c09deb193c9fb` | 2027-01-23T17:48:56Z |

summary 在 Actions 内按 `gh api` 重新读取本 attempt 的 4 个上游 job（名称、`head_sha`、`conclusion=success`）、
每个工件 ZIP 的 id/字节/`digest`/未过期，并把下载到的原始字节重新散列后与 `digest` 比对，随后才解析内容；
输出 `checks: 21, problems: []`（本 attempt 的 `validation.json`/`summary.json`/
`authenticated-artifacts.json` 在 12608596187 内）。

## 2. guards（静态契约 + 反例）

- 所有权 7 项：`HEAD==GITHUB_SHA`、起点为祖先、改动只在四个自有路径、受保护树（含原 workflow，排除本包
  workflow）逐字节不变、接受/拒绝两类路径分类反例、workflow 只触发 `codex/reader-fw-s10`。
- 入口契约 20 项（真实文件，只读）：Android VIEW/SEND 过滤与无 `MANAGE_EXTERNAL_STORAGE`/读写外存权限、
  owner 库 manifest 为空、`ACTION_OPEN_DOCUMENT` 选择器、只接受 `content:`、交给 `exr_sideload_import_file`；
  Apple 交付 bundle 与 CI 验收工程的 `UIFileSharingEnabled`/`LSSupportsOpeningDocumentsInPlace`、
  `importFile(url:)` 内的 `startAccessingSecurityScopedResource`/`stop…`、`.fileImporter` → `model.importFile`；
  macOS 同两项；Windows `GetOpenFileNameW`→`JOB_IMPORT` 与 shell 路径参数导入；GTK `Import book` 选择器、
  `text/uri-list`/`x-special/gnome-copied-files` 拖放目标、文件夹批量；全库禁 WebView、禁监听套接字。
- 13 个具名反例：每个变异必须**恰好**让声明的检查失败（例如删掉 `UIFileSharingEnabled` 只让
  `apple.files.sharing-keys` 失败，加入 `listen(` 只让 `all.no-server` 失败），多失败或少失败都判失败。

## 3. android（API 34 x86_64 模拟器，9 项检查）

交付：CI 生成 `S10-Transfer.epub` → `adb push` 到 `/data/local/tmp` → `run-as` 复制进发送器应用私有 inbox →
在模拟器内用 `sha256sum` 复核与 fixture 一致。入口：本包真实的 `DocumentsProvider`
（`content://org.exreader.s10docs.docs/document/S10-Transfer.epub`）+ `ACTION_VIEW`
+ `FLAG_GRANT_READ_URI_PERMISSION`，落到**未改动**的导入 owner 宿主 `org.exreader.importprobe`
（`extras/android-import-entry` + 安装版 SDK）。owner 证据：`ready.id` 等于 `<fixture sha256>.epub`、
`size`/`format=EPUB` 相符；`commit` `status=0, created=1, bookId>0`；`readback.equal=true`；
`released.fileExists=false`。回读：`am force-stop` 后取出 `files/probe.exrlib`，用独立 SQLite 读者
重算 `books.source` 的 SHA-256 并与交付字节比对（`sdk.stored-source-matches-fixture`）。

## 4. apple（iPhone 与 iPad 模拟器各 14 项检查）

CI 用无改动的 `examples/apple` owner 源码（`HostSDK/HostModel/HostCatalog/HostAccount/HostSearch/
HostNavigation/HostReadingRecords/SelectableText` + `bindings/swift/EXReader.swift`）与安装版
iphonesimulator SDK 编出驱动 bundle，Info.plist 声明 `UIFileSharingEnabled=true` 与
`LSSupportsOpeningDocumentsInPlace=true`。fixture 由 CI 复制进应用 `Documents/Inbox`（即 Files.app 在
设备上写入的同一共享目录），以 `-S10Inbox <name>` 启动后驱动真实入口
`HostReaderModel.importFile(url:)`（含 security-scoped 进入/退出）；随后用 owner 自己的
`HostLibrary.sourceFingerprint` 回读存储原件 SHA-256 并与交付字节比对。两个模拟器均
`checks: 14, problems: []`。

## 5. desktop（Linux，9 项检查）

载荷是真实 `text/uri-list` 框架：一个真实文件 URI、一个真实目录、`mtp://` 虚拟项、`https://` 远程项、
`file://other-host.invalid` 远程主机项。经**未改动**的 `extras/desktop-drop` 解析：文件项必须唯一且路径等于
被投放文件，目录项不得递归，其余三类必须按类别拒绝。随后 `exr_sideload_import_file` 导入安装版 SDK，
`exr_sideload_export_original` 导出原件，Python 端对导出文件与原文件比 SHA-256 与字节数。

## 6. 首轮真实失败与根因（保留，不合并成功片段）

[run 40214657202](https://github.com/NoGod3524/EXReader/actions/runs/40214657202)（source
`1dfdd4a019d815a719bc12e1cb64a721f6289bbc`）：guards 与 desktop 失败，android（121233078504，9 项）与
apple（121233078315，14×2）已成功，summary 因缺上游被 skip（121237159297）。工件保留：
guards 12607400235 / android 12606623967 / apple 12608185207 / desktop 12606484332，有效期
2027-01-23T17:04:01Z。

1. guards：`mutation mutate.gtk.drop-target failed  instead of gtk.entry.drop-target` —— 自测只替换首个
   出现处，而 `examples/linux/drop_import_ui.inc` 两次出现 `x-special/gnome-copied-files`。修复：变异对
   所有出现处生效（未放宽任何断言）。
2. desktop：`json.decoder.JSONDecodeError: Expecting value: line 15 column 3 (char 681)` —— 本包
   `entry_check.c` 在序列化 drop items 时多写了一个尾逗号。修复：改为前置逗号的分项写出，并让
   `run_desktop.py` 在解析失败时保留原始字节再判失败。

两处都是本包工具缺陷，未触及任何 owner 文件或断言；原失败与工件留在记录中。

## 7. 未执行 / pending（不预填通过）

真机（Android 手机、iPhone、iPad）、USB 线缆与 MTP 复制、Finder/iTunes 或 iCloud 的 Files 传输、
系统 SAF/Files 选择器的 UI 点击、Windows 可执行运行、macOS 应用运行、性能与商店分发结论。
CI 内的文件送达是模拟传输（adb 复制、容器内写文件），**不得**据此声称 USB 真机通过。
