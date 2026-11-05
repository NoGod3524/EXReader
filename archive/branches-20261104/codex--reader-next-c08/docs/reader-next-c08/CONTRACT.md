# C08 原APK数据的独立公开SDK回读（契约）

固定起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`，分支 `codex/reader-next-c08`。只写
`tests/reader_next_c08/`、`.github/workflows/reader-next-c08.yml`、`docs/reader-next-c08/`、`HANDOFF-RESULT-C08.md`；
`guard.py` 对固定起点逐路径校验并带负例自检。全部构建、语法、执行、工件解析仅在 Actions。

## 要补的缺口

S04 已证原 APK 的安装/原生出页/离线重开（`apk_protocol_accepted=true`），但“独立公开 SDK 回读原件/进度值”仍 pending：
其 SQL `book_progress` 与私有副本哈希只是诊断。本包补的是：独立消费者经**公开 C ABI**取回的返回值。

## 输入（只读，不重建）

| 角色 | 身份 |
| --- | --- |
| 原 APK producer | source `4a04a9cc74dde67f755c87e87b278d63a254a3ac`，run `40207467982` attempt 1，job `121211376063` |
| 原 APK | ZIP `12604412854`（`reader-android-raw3-40207467982-1`）内 `build/android-raw3/apks/host-debug.apk`，29,721,554 B，SHA-256 `860927a8…ec`（`authenticate.py` 同时核 ZIP bytes/digest/expiry） |
| SDK 暂存/头 | ZIP `12604537792`（`reader-android-page-theme-40207467982-1`）的 `build/session-android/sdk-stage` |
| S04 协议 | 受测 `49fe49d36b24cd692ec907e07b5cf5c098fa548e`，run `40224699973` attempt 1（仅记录身份，不改其结论） |

APK 原样安装：不重打包、不重签、不改类、不注入偏好、不强制加载。

## 场景

1. 新 API34 default x86_64 模拟器；安装前无包；已安装 `base.apk` 字节须等于原 APK。
2. 把 `tests/fixtures/sample.txt`（10,635 B，SHA-256 `fe0e65a9…3b`）放到 `/sdcard/Download/c08-original.txt`，**点应用的 Import 按钮，在系统文件选择器里点选该文件**（真实 UI 导入）。
3. 点书架行打开，点击右侧翻到 p3；尝试用 UI 选中文字并保存一条批注（失败如实记录，批注期望随之为 0）。
4. HOME 后 `am force-stop` 关闭，由应用自己保存的状态为准。
5. 独立消费者读取（阶段1：首次关闭后）；全新冷启动自动恢复 p3 并关闭，再读（阶段2：fresh reopen）；
   断网（airplane=1、wifi=0、数据=0、ping 失败）冷启动恢复 p3 并关闭，再读（阶段3：离线重开）。

## 独立消费者

`consumer/c08_consumer.c` 是 NDK 编译的原生可执行程序，用 `dlopen` 加载 SDK 的 `libexreader.so`（路径显式给出），
`dlsym` 解析公开 `exr_*` 符号并调用：`exr_library_open`、`exr_library_books`、`exr_library_source`（读全部原件字节并算 SHA-256）、
`exr_library_progress_get`、`exr_library_notes`（并记录 `fixed_notes`/`epub_info` 状态）。它不发 SQL，不自行读库文件。
输出的 JSON 含：已解析符号、逐次调用及状态、`dladdr` 实际加载路径、SDK 版本和 ABI 版本。

两条执行路线均为真实记录，各自要有结果才计入该路线：

- `same_uid_run_as`：`run-as org.exreader.host` 以目标应用自己的 UID 执行（官方调试方式，不提权、不改访问控制），读 `files/library.db`。
- `shell_readonly_copy`：用目标 UID 的 `cat` 取出库文件（含存在的 WAL/SHM/journal）为认证副本（逐字节 SHA-256），`chmod 444`，shell UID 读取；
  不改写副本内路径。库把原件放在 SQLite 里，因此若有路径绑定缺口，会由该路线的 `exr_library_source` 失败如实暴露。

库来源：`<installed base.apk>!/lib/x86_64/libexreader.so`（直接映射）优先，失败则用同一 APK 成员字节的复制品；二者均与已安装 APK 成员比对，
并记录与 SDK 暂存库的对应情况。头文件来自暂存树，缺 `exr/library.h` 时取封存 producer 提交的 `include/`，并在 `consumer-build.json` 写明。
UID/SELinux 上下文与程序/库路径列表写入 `observed.identities`。

## 判定（`validate.py`）

只有真实公开 API 回读才通过：必须解析全部公开符号、记录 open/books/source/progress_get/notes 调用且状态 OK、实际加载的是 `libexreader.so`、
恰一本书、格式 TXT、书名含 `c08-original`、原件字节与大小等于夹具、进度状态 FOUND/LEGACY 且起点>0、笔记与 UI 实际创建的一致。
含 `sql`/`tables`/`db_sha256` 等键、无调用、符号未解析、加载错误对象、原件哈希不符、缺进度、多出笔记、两本书等**负例**在 `--selftest` 中全部必须被拒，正例必须通过。

## 无写与稳定性

每次消费者运行前后对目标应用数据目录全部文件做 stat（大小/mtime）+ 内容 SHA-256 快照，必须逐项相同；认证副本在运行后也须不变。
三个阶段的返回值（书目、原件、进度、笔记）必须逐项相同。SQL 只做 `diagnostic_sql_book_progress` 诊断，不计入通过。

## 不在范围

真机、商店/签名、性能、产品目录库 `reader-catalog.db` 的独立读取（SDK 公开头没有该库的 C 入口；此处的“书目”指 `exr_library_books`）、
iOS/桌面。未跑到的项在 `HANDOFF-RESULT-C08.md` 如实列为未验证。
