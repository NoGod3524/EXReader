# S10 电脑传书入口与能力证据（契约）

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`；本包只新增
`tests/reader_final_s10/`、`.github/workflows/reader-final-s10.yml`、`docs/reader-final-s10/` 与
`HANDOFF-RESULT.md`。apps/、examples/、extras/、SDK、原 tests/、原 workflow 全部只读，
由 `check_guards.py` 以 `git diff --exit-code 0889 -- apps examples src include cmake CMakeLists.txt
bindings tests/fixtures extras tools docs/validation .github/workflows` 逐步核验。

## 1. 方案边界

- 传书只用操作系统**已有**的文件传输/共享面：Android SAF/分享 Intent 与 USB(MTP) 复制到共享存储、
  Apple Files 文件共享（`UIFileSharingEnabled`）与安全作用域文档选择器、桌面文件选择/拖放/命令行打开。
- 不新增服务器、不新增传输协议、不引入 WebView。`all.no-webview` 与 `all.no-server` 两项静态检查
  逐个扫描 `examples/` 下的宿源码；任何一处出现 WebView 或监听套接字即失败。
- 书进入应用后一律复用既有导入 owner：Android `extras/android-import-entry`（`ImportEntry` +
  `exr_android_import_commit` → `exr_sideload_import_file`），Apple `examples/apple`
  （`HostReaderModel.importFile(url:)` → `HostSession.importBook` → SDK），桌面 `extras/desktop-drop`
  → `extras/sideload`。本包不复制这些实现，也不改它们的断言。

## 2. 六平台入口（静态契约，20 项命名检查 + 13 个具名反例）

| 平台 | 入口 | 检查 ID |
| --- | --- | --- |
| android | `ACTION_VIEW`(content:)、`ACTION_SEND`/`SEND_MULTIPLE`、系统文档选择器 `ACTION_OPEN_DOCUMENT`；只申请 INTERNET，不申请 `MANAGE_EXTERNAL_STORAGE`/`READ_EXTERNAL_STORAGE`/`WRITE_EXTERNAL_STORAGE` | `android.intent.view-content`、`android.intent.send-filters`、`android.intent.no-broad-storage`、`android.owner.saf-picker`、`android.owner.content-only`、`android.owner.no-declared-surface`、`android.owner.sideload-handoff` |
| ios | Files 文件共享 `UIFileSharingEnabled` + `LSSupportsOpeningDocumentsInPlace`；`.fileImporter` → `importFile(url:)`，内部 `startAccessingSecurityScopedResource()`/`stop…` | `apple.files.sharing-keys`、`apple.owner.security-scope`、`apple.picker.document-importer` |
| ipados | 同一 iOS 包声明，另加 CI 生成的验收工程同等钥匙 | `apple.files.review-project-keys` |
| macos | 桌面文档选择器与同一安全作用域 owner 入口 | `macos.picker.document-importer`、`macos.owner.security-scope` |
| windows | 系统打开对话框 `GetOpenFileNameW` → `JOB_IMPORT`；shell 关联/拖到 exe 的路径参数直接导入 | `windows.entry.open-dialog`、`windows.entry.path-argument` |
| linux-gtk | `Import book` 文件选择器、`text/uri-list`/`x-special/gnome-copied-files` 拖放目标、文件夹批量导入 | `gtk.entry.file-chooser`、`gtk.entry.drop-target`、`gtk.entry.folder-batch` |

每个检查都配一个具名变异（`--self-test`）：删掉/改坏对应声明后必须**恰好**只有它（或声明内的
两项）失败，否则本包失败。13 个变异覆盖 Android 权限与选择器、Apple 共享钥匙与安全作用域、
Windows 对话框与路径参数、GTK 选择器与拖放，以及 WebView/监听套接字禁令。

## 3. 用户步骤

### 3.1 Android（SAF + USB/MTP）

1. 用 USB 线连接电脑，在手机上选择「文件传输 / MTP」；把 `.epub/.pdf/.cbz/.txt` 复制到
   `下载(Download)` 或任意共享文件夹。（也可用任意网盘/聊天工具把文件放到共享存储。）
2. 在文件管理器里点开该书 → 选择「用 EXReader 打开」；或在阅读器里点「导入」→ 文档选择器 →
   选中的文件。
3. 应用通过系统授予的 `content:` URI 读取该文件（不需要存储权限），复制到应用私有 staging，
   由导入 owner 校验格式与大小后写入 SDK 书库；随后即可在书架打开。
4. 同一本书重复导入按原字节去重，返回已有记录；导入失败会明确报错且不留临时文件。

限制：单文件 EPUB/CBZ/PDF ≤128 MiB，其余回退格式 ≤32 MiB；一次 Intent 最多 64 个 URI；
不接受 `file:` 等非 `content:` scheme；授权只在接收任务期有效（应用在 finish 前完成提交），
因此不保存长期持久化授权。

### 3.2 Apple（Files 文件共享 + 安全作用域）

1. 电脑上用 Finder（macOS 10.15+ 的「文件共享」面板）或 iTunes（Windows）把书拖入 EXReader 的
   「文件共享」区域；或把书放进 iCloud Drive / 「我的 iPhone」任意位置。
2. iPhone/iPad 上打开 EXReader → 「导入」→ 系统文档选择器 → 选择该书（选择器返回安全作用域 URL）。
3. 应用对 URL 调用 `startAccessingSecurityScopedResource()`，一次性读取为私有 staging 副本并计算
   SHA-256，交给 SDK 导入；完成后 `stopAccessingSecurityScopedResource()`。
4. 也可以通过「文件」App 在 EXReader 的 Documents 目录里直接放书（`UIFileSharingEnabled` 暴露）。

限制：EPUB ≤128 MiB，其余 ≤32 MiB；导入中长度变化会被拒绝；安全作用域之外的 URL 不会被读取。

### 3.3 桌面（Windows / Linux GTK / macOS）

- Windows：菜单「导入」→ 系统打开对话框；或把书拖到 exe/用「打开方式」关联，路径作为命令行参数
  直接导入；产品书库在 `%LOCALAPPDATA%\EXReaderHost`。
- Linux GTK：「Import book」选择器选单本；也接受从文件管理器拖入窗口或粘贴 URI 列表
  （`text/uri-list`、GNOME 复制文件），以及「导入文件夹」批量选择。
- macOS：与 Apple 相同，`.fileImporter` 选择器 → 安全作用域 → 现有 owner。

限制：桌面拖放目标只接受真实本地文件；目录不会递归；远程 URL、远程主机、虚拟/承诺文件会被归类
拒绝并给出原因。空的或不支持的拖放载荷整体失败，不留半成品。

## 4. 实际执行范围（本包 CI）

| 作业 | 真实执行 | 不授予 |
| --- | --- | --- |
| android | API 34 x86_64 模拟器：真实 fixture 经 adb 复制进模拟器 → 本包真实 `DocumentsProvider` 的 `content:` URI 授权 → 既有导入 owner → SDK → 独立 SQLite 读回原件 SHA-256 | 真机、USB 线缆、MTP 复制 |
| apple | iPhone 与 iPad 模拟器：真实 fixture 写入应用 Documents（Files 共享目录）→ 既有 `importFile(url:)`（含安全作用域）→ SDK → owner 自己的原件指纹读回 | 真机、Finder/iTunes 传输、系统选择器 UI |
| desktop | Linux：真实 `text/uri-list` 载荷 → `extras/desktop-drop` → `exr_sideload_import_file` → `exr_sideload_export_original` 导出并与原文件比 SHA-256 | Windows/macOS 可执行、GUI 拖放事件 |
| guards | 20 项真实声明检查 + 13 个具名反例 + 所有权守卫 | — |

CI 里的文件送达只是**模拟**传输（adb 复制、容器内写文件），不得据此声称 USB 真机通过。
Android 与 Apple 都要求"原件回读"：Android 用 `run-as` 取出 SDK 书库后由独立 SQLite 读取器重算
`books.source` 的 SHA-256；Apple 用 owner 的 `HostLibrary.sourceFingerprint` 与交付字节比对。

## 5. 必然 pending 的项目

真机（Android 手机 / iPhone / iPad）、USB 线缆与 MTP 复制、Finder/iTunes 文件共享传输、系统选择器
UI 点击、Windows/macOS 桌面可执行运行。这些只按实际执行授予，本包不预填通过。
