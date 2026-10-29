# EXReader 六端用户说明（安装 / 启动 / 导入 / 同步 / 导出 / 备份与恢复）

**适用范围与诚实声明**

- 六端 = Windows x86_64、Linux x86_64 (GTK3)、macOS (arm64)、Android x86_64 模拟器 (API 34)、iPhone 模拟器、iPad 模拟器。
  这是 F06 打包线（[tests/reader_f06_packages](../../tests/reader_f06_packages/README.md)）目前产出的六个**开发期**压缩包，不是商店版或签名安装器。
- 菜单、按钮名称取自当前源码里的字符串（`apps/reader/desktop/windows_*.inc`、`examples/linux/*.inc`、
  `examples/android/.../MainActivity.java`、`examples/apple/*.swift`）。**本文没有在真机或真实窗口里逐步实操过**；
  各端 GUI 行为的验收证据在各自的 Actions 记录里，不由本文提供。
- 本文写的是**当前源码**能做的事。F06 的六个压缩包构建于较早的源码（见 [README](README.md)），
  不能当作当前源码的包。
- 凡标注“未实现”或“未验证”的条目，不要当作可用功能。

## 1. 各端取得与启动

压缩包内都带 `安装说明-中文.md`、`SHA256SUMS`、`manifest.json`（逐文件字节数与 SHA-256）。启动前先校验：

- Linux / macOS：在解压目录执行 `sha256sum -c SHA256SUMS`（macOS 可用 `shasum -a 256 -c SHA256SUMS`）。
- Windows：`certutil -hashfile <文件> SHA256`，与 `SHA256SUMS` 逐个比对。

| 端 | 入口（取自 `tools/reader_wave3_package/delivery.py`） | 首次运行注意 |
| --- | --- | --- |
| Windows | 解压后运行 `EXReader\EXReader.exe`（Windows 10/11 x64；无安装程序，无注册表写入，无开机自启） | 未做代码签名，SmartScreen 可能提示 |
| Linux | 解压后运行 `EXReader-Linux/Start-EXReader.sh`；需要系统自带 GTK3 与基础 X11 库 | 只在 ubuntu-22.04 构建与检查，其他发行版未声称；不是 deb/rpm |
| macOS | 双击 `EXReader.app`，或 `open EXReader.app` | 仅 ad-hoc 签名，未公证；Gatekeeper 可能要求手动放行 |
| Android | `adb install -r artifacts/app-debug.apk`，然后启动 `org.exreader.host` | 只授予 x86_64 API 34 模拟器；debug 签名；真机/arm64 未验证 |
| iPhone | `xcrun simctl install <udid> EXReader.app`，然后 `xcrun simctl launch <udid> org.exreader.host` | 仅 arm64 模拟器；不能装到真机，未做 App Store 提交 |
| iPad | 同 iPhone（同一个 universal 应用，另有独立的 iPad 模拟器安装记录） | 同上 |

Linux 命令行（`examples/linux/reader.c` 的 `main`）：`exreader-linux --version` 打印 SDK 版本和 ABI；
`exreader-linux FONT STATE_DIRECTORY [OBSERVATION_FILE]` 用指定字体和状态目录运行（观察文件用于自动化，普通用户不需要）；
无参数时状态目录是 `$XDG_DATA_HOME/exreader`（通常 `~/.local/share/exreader`）。其它参数个数会打印用法并返回 2。
Windows 与 Android 的宿主没有面向用户的命令行开关；`examples/windows/README.md` 提到旧宿主 `--data` 可改数据目录，
未对 F06 的 Wave3 宿主核对。

数据位置（升级前必须知道，见第 6 节）：

| 端 | 数据位置 | 依据 |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%\EXReaderHost`（`library.sqlite`、`host.ini` 等）；账号/云导入在该宿主的 `account.ini`、`cloud-import`、`sync-originals` 子路径 | `examples/windows/README.md`；Wave3 宿主的子路径取自源码字符串，**目录根是否相同未逐项核对** |
| Linux | `~/.local/share/exreader`（或启动命令传入的 `STATE_DIRECTORY`），含 `reader.ini` | `examples/linux/reader.c` |
| macOS / iOS / iPadOS | 应用的 Application Support 目录；iOS 的 `Info.plist` 打开了 `UIFileSharingEnabled` 与 `LSSupportsOpeningDocumentsInPlace` | `examples/apple/HostModel.swift`、`tools/build_apple_host.py` |
| Android | 应用私有目录；清单中 `android:allowBackup="false"` | `examples/android/app/src/main/AndroidManifest.xml` |

## 2. 导入书籍

支持的文件类型以书架导入实际接受的为准；Windows 宿主源码里出现的格式有 epub、pdf、cbz、txt、mobi、fb2、docx、rtf、html 等，
**TXT 在 Windows 宿主中仍有限制**（源码字符串：“TXT 目前仅支持第一页；此功能尚未实现。”“TXT 阅读设置尚未实现。”）。
某一格式能否导入、能否阅读，以该端实际提示为准。

| 端 | 本地导入 | 备注 |
| --- | --- | --- |
| Windows | 菜单“导入书籍…”（Ctrl+O）；“从已配置云盘导入…”用于云端原书。拖放导入有独立模块，但其文档写明“未接生产宿主”，不要依赖拖放 | 导入结果提示“新提交 / 重复 / 共提交”。云端原书校验失败时不导入，已下载文件保留 |
| Linux | 菜单“Import file…”、“Import folder…”（批量）。拖放导入同样以独立模块形式存在，未确认接入该宿主，不要依赖 | 批量导入前有选择与预览步骤，细节见 `docs/READER-GTK-BATCH-IMPORT.md` |
| Android | 书架导入按钮（系统文件选择器，`ACTION_OPEN_DOCUMENT`）；也可从其他应用“打开方式 / 分享”交给 EXReader | 复制期间可取消，状态栏显示“Import canceled” |
| iPhone / iPad / macOS | 书架内的文件导入（系统文件选择器）；内置若干示例导入按钮仅用于验收样本 | 导入流程细节见 `docs/READER-APPLE-SHELF.md` |

重复导入同一本书不会产生第二份原件（按内容校验和判重）；导入只新增，不会改动你的源文件。

## 3. 同步（WebDAV 云盘）

同步目标是用户自备的 WebDAV 云盘（`EXReaderWebDAV` 模块，TLS 由系统库提供，见 [LICENSE-DEPENDENCY-MATRIX](LICENSE-DEPENDENCY-MATRIX.md)）。
你需要：云盘地址、用户名、密码或令牌。EXReader 不提供也不托管服务器。

| 端 | 入口 | 步骤 |
| --- | --- | --- |
| Windows | 菜单“同步账号…”（账号与同步）；“同步状态…” | 填地址与凭据 → 选择是否“保存到系统安全存储（取消勾选则仅本次会话）” → 应用 → “立即同步(&S)”。同步中可取消，已完成部分保留，之后可“重试” |
| Linux | 菜单“Account / Sync…”、“Sync status…” | 同上思路；凭据存系统钥匙串（libsecret）依赖桌面会话 |
| Android | 书架“More” → “同步” | 同步面板内填写与启动；状态文案含“同步中 / 同步失败，可重试” |
| Apple | “书库账号”（账号）、“同步详情”（含“取消同步”） | 同步状态是只读快照 |

必须知道的语义（来自源码提示与 `docs/READER-SYNC-RESILIENCE.md`、`docs/READER-SYNC-STATUS-VIEW.md`）：

- “一轮扫描完成不等于整库已同步”；状态“未知”也不等于已同步。
- 状态页是只读的：不重试、不确认、不修改任何记录。
- 原件必须先下载并校验才加入书架；校验失败不会替换本机书籍。
- 冲突、墓碑（删除标记）、保留版本会原样保留为显式状态，不会静默合并。
- 未配置账号或没有网络时，同步会提示不可用，本机阅读不受影响。

**未验证**：与真实第三方 WebDAV 服务（具体厂商）的互通、长时间弱网、大库同步耗时，本文均未验证。

## 4. 原件导出与标注导出/导入

### 原件导出（导出的是导入时保存的原始文件）

| 端 | 入口 | 行为 |
| --- | --- | --- |
| Windows | 菜单“导出原件…”：在书架多选（Ctrl/Shift）→ 选择目录 | 不覆盖已有文件；可取消，已发布的文件不会回滚；仅云端、本机没有原件的书会提示“所选书籍尚未下载到本机，无法导出原件” |
| Linux | 菜单“Export original…” | 同上思路 |
| Android | 书架长按某本书 → “导出原件”（系统“创建文件”选择器） | 保存失败时私有原件保留 |
| Apple | “导出与分享” → “分享导出文件”；“验证原件” | 具体按钮路径以实机为准（未实操） |

### 标注导出 / 导入（可移植 JSONL + Markdown）

| 端 | 入口 | 先决条件 |
| --- | --- | --- |
| Windows | 菜单“标注导入与导出…”（也有“导出标注…”） | 先打开一本书；导出的是当前书全部标注 |
| Linux | 菜单“Export annotations…”、“Import annotations…” | 同上 |
| Android | 阅读中“阅读更多操作” → “标注导入 / 导出” | 先打开目标书 |
| Apple | “标注导入与导出”、“导出标注” | 同上 |

- 导出结果提示形如“标注 N · 当前 · 已删除 · 冲突 · JSONL · Markdown”；取消导出不留下半个文件，原有导出保持不变。
- **导入先预览**：显示冲突、未解析位置、NULL 位置，必须明确点击“确认导入”才会写入；导入只新增共享历史版本，
  不修改原书，重复项不会再次入队。位置无法解析的标注原样保留但不能跳转。
- 格式细节见 [docs/READER-ANNOTATION-EXPORT.md](../READER-ANNOTATION-EXPORT.md)。

## 5. 备份与恢复

**应用内的“整库备份 / 恢复”功能：当前源码里没有找到面向用户的入口，请不要把它当作可用功能。**

核对结果：

- 四类宿主的菜单与按钮字符串中，没有“备份整个书库”“从备份恢复书库”的入口；字符串里的“恢复”都是**未完成操作的恢复**
  （导入映射、字体库提交、书籍编辑、已删除阅读记录的“保留版本恢复”）。
- SDK C 接口有 `exr_library_backup`（`include/exr/library.h`），Apple 宿主 `HostSDK.swift` 有 `backup(to:)` 封装，
  但没有找到界面调用它；Android 清单设置了 `allowBackup="false"`，所以系统自动备份也不包含应用数据。
- 因此：**可恢复的备份 = 你自己保存好的原书文件 + 你导出的原件/标注文件**（第 4 节），再加云盘同步的副本（第 3 节，行为边界见上）。

如果你一定要做本机整目录冷备份（**非受支持流程，未验证恢复结果**）：

1. 完全退出应用，确认没有其他进程在使用该库。
2. 复制整个数据目录（第 1 节表格），包括 SQLite 主文件以及同目录的 `-wal` / `-shm` 文件和产品目录库、原件、账号文件。
   不要只复制 `library.sqlite`，也不要在应用运行时复制。
3. 恢复时同样先退出应用，再整目录放回；之后是否一致没有被验收。

SDK 书库与产品目录是**两个独立的库**，须作为一组备份（见 [docs/READER-UPGRADE-DELIVERY.md](../READER-UPGRADE-DELIVERY.md)）。

## 6. 升级与旧库

- 目前没有对六端都验证过的最终原生安装包；[升级与交付状态](../READER-UPGRADE-DELIVERY.md) 明确写着：
  就地迁移在存在其他写入进程时**不具备发布条件**（已有失败记录），请勿对可能被其他进程打开的库运行迁移工具。
- 升级前保留旧安装目录和一份第 5 节所述的冷备份；确认新版本能打开你的书后再清理。
- 旧版 IndexedDB / 备份迁移是单独的命令行工具，不是应用里的按钮，说明在 [WP12-LEGACY-MIGRATION](../WP12-LEGACY-MIGRATION.md)。

## 7. 本文没有验证的内容

- 任何一端在**当前源码**上的完整安装/启动/导入/同步/导出流程（F06 压缩包来自更早的源码）。
- 真机（Android arm64、iPhone/iPad 真机、Apple Silicon 之外的 Mac）、签名、公证、商店分发。
- 上述所有菜单路径的逐步 GUI 实操；各端 GUI 的自动验收在各自 Actions 记录中，不在本文范围。
- 整库备份/恢复（未实现）；跨设备恢复一致性。
- 与具体 WebDAV 服务商的互通。
