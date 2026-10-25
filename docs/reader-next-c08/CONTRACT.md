# C08 原APK数据的独立公开SDK回读（契约）

固定起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`，原分支 `codex/reader-next-c08`，独立审查分支 `codex/reader-next-c08-root-review`（从原最终 `dddd4fa81e5913cce2dddecc385d20978b3adc72` 建立）。只写
`tests/reader_next_c08/`、`.github/workflows/reader-next-c08.yml`、`docs/reader-next-c08/`、`HANDOFF-RESULT-C08.md`；
`guard.py` 对固定起点逐路径校验并带负例自检。全部构建、语法、执行、工件解析仅在 Actions。

## 要补的缺口

S04 已证原 APK 的安装/原生出页/离线重开（`apk_protocol_accepted=true`），但“独立公开 SDK 回读原件/进度值”仍 pending：
其 SQL `book_progress` 与私有副本哈希只是诊断。本包补的是：独立消费者经**公开 C ABI**取回的返回值。

## 输入（只读，不重建）

| 角色 | 身份 |
| --- | --- |
| 原 APK producer | source `4a04a9cc74dde67f755c87e87b278d63a254a3ac`，run `40207467982` attempt 1，job `121211376063` |
| 原 APK | ZIP `12604412854`（`reader-android-raw3-40207467982-1`）内 `apks/host-debug.apk`，29,721,554 B，SHA-256 `860927a89eb7ab2e6ffcd93d596e7206a830f15d396be0e0135bf82bedb0b5f3`（`authenticate.py` 同时核 ZIP bytes/digest/expiry） |
| SDK 暂存/头 | ZIP `12604537792`（`reader-android-page-theme-40207467982-1`）的 `build/session-android/sdk-stage` |
| S04 协议 | 受测 `49fe49d36b24cd692ec907e07b5cf5c098fa548e`，run `40224699973` attempt 1（仅记录身份，不改其结论） |

APK 原样安装：不重打包、不重签、不改类、不注入偏好、不强制加载。

## 场景

1. 新 API34 default x86_64 模拟器；安装前无包；已安装 `base.apk` 字节须等于原 APK。
2. 把 `tests/fixtures/sample.txt`（10,635 B，SHA-256 `fe0e65a9…3b`）放到 `/sdcard/Download/c08-original.txt`，**点应用的 Import 按钮，在系统文件选择器里点选该文件**（真实 UI 导入）。
3. 点书架行打开，点击右侧翻到 p3；必须用真实 UI 选中文字、输入并保存 `c08note`。笔记按钮计数按大小写无关的 `notes (1)` 结构核对；失败明确拒绝本包，不能把期望改成空列表继续。
4. HOME 后 `am force-stop` 关闭，由应用自己保存的状态为准。
5. 独立消费者读取（阶段1：首次关闭后）；全新冷启动自动恢复 p3 并关闭，再读（阶段2：fresh reopen）；
   断网（airplane=1、wifi=0、数据=0、ping 失败）冷启动恢复 p3 并关闭，再读（阶段3：离线重开）。

## 独立消费者

`consumer/c08_consumer.c` 是 NDK 编译的原生可执行程序，用 `dlopen` 加载 SDK 的 `libexreader.so`（路径显式给出），
`dlsym` 解析公开 `exr_*` 符号并调用：`exr_library_open`、`exr_library_books`、`exr_library_source`（读全部原件字节并算 SHA-256）、
`exr_library_progress_get`、`exr_library_notes`（并记录 `fixed_notes`/`epub_info` 状态）。它不发 SQL，不自行读库文件。
输出的 JSON 含：每个已解析符号的 `dladdr` 对象归属、逐次调用及实际状态、每次 `read_at` 的 offset/requested/returned、消费者 PID/UID/EUID/SELinux/实际程序路径、SDK 版本和 ABI 版本。进度 trace 在释放 anchor 前记录实际返回值；书目、原件、进度和笔记的值都来自这些公开调用。

两条执行路线均为真实记录，各自要有结果才计入该路线：

- `same_uid_run_as`：`run-as org.exreader.host` 以目标应用自己的 UID 执行（官方调试方式，不提权、不改访问控制），读 `files/library.db`。
- `shell_readonly_copy`：用目标 UID 的 `cat` 取出库文件（含存在的 WAL/SHM/journal）为认证副本（逐字节 SHA-256），`chmod 444`，shell UID 读取；
  不改写副本内路径。库把原件放在 SQLite 里，因此若有路径绑定缺口，会由该路线的 `exr_library_source` 失败如实暴露。

库来源：`<installed base.apk>!/lib/x86_64/libexreader.so`（直接映射）优先，失败则用同一 APK 成员字节的复制品；二者均与已安装 APK 成员比对，
并记录与 SDK 暂存库的对应情况。头文件来自暂存树，缺 `exr/library.h` 时取封存 producer 提交的 `include/`，并在 `consumer-build.json` 写明。
UID/SELinux 上下文与程序/库路径列表写入 `observed.identities`。只给测试自有消费者设置可执行、给测试自有认证副本设置只读；不改变目标应用数据或 APK 的权限、SELinux、内容和签名。

## 判定（`validate.py`）

只有真实公开 API 回读才通过：必须解析全部公开符号、记录 open/books/source/progress_get/notes 调用且状态 OK、实际加载的是 `libexreader.so`、
恰一本书且 ID 与实际 UI book ID 一致、格式 TXT、书名含 `c08-original`、原件字节与大小等于夹具、完整 `read_at` 记录、实际 SDK/ABI 符合 producer、进度状态 FOUND/LEGACY 且有正的持久化 offset、笔记必须恰为 UI 创建的 `c08note`。每个符号必须属于消费者实际加载的同一个 SDK 对象，消费者须正常退出。
含 `sql`/`tables`/`db_sha256` 等键、无调用、符号未解析、加载错误对象、原件哈希不符、缺进度、多出笔记、两本书等**负例**在 `--selftest` 中全部必须被拒，正例必须通过。

## 无写与稳定性

每次消费者运行前后对目标应用数据目录全部文件做 stat（大小/mtime）+ 内容 SHA-256 快照，必须逐项相同；读取失败或字节数不完整不能算快照成功。复制的 db/WAL/SHM/journal 文件集合与字节必须匹配该目标快照，副本前后完整文件集合、大小、mtime、权限/UID/GID 与 SHA-256 均须不变。没有写回任何目标文件。
三个阶段的实际返回值（书目、原件、进度、笔记）必须逐项相同。本包不再查询私有 SDK SQL。

## 页码与公开进度的证据边界

UI 初次观察 p1→p2→p3，fresh reopen 与断网 reopen 各重新观察 UI p3，分别绑定相同 book ID。独立 `exr_library_progress_get` 返回的是 normalized-text offset 和 selector，不返回页号。
因此单列 UI 页码、公开 `book.position`／progress start/end/state 及三次冷读稳定性；正 offset 仅证明读到了非零持久化位置，不能宣称它独立、精确解析到了 p3。`independent_exact_page3_resolution_accepted=false`。

## Root 三轮审查入口与原失败保留

新入口保留原全部 UI/回读阶段，最多三轮新的 root CI。summary 重新下载并认证本轮静态/模拟器原 ZIP 的 source/run/attempt、字节数、digest 和有效期，复核 consumer 源码、固定 producer 的完整公开头集合、实际消费者与已安装 APK 的 SDK 成员，再独立重判三个 API 阶段、只读副本绑定和无写快照。

原 `40227150857`、`40227267225`、`40227848141` 三轮失败及取消的 `40227112046` 均保留在原 `HANDOFF-RESULT-C08.md`。原第三轮的 sameUID 消费者被 SELinux 拒绝执行；此项维持 pending，不以提权、改访问控制、重签 APK、注入类或偏好修成通过。认证只读副本是任务原文允许的独立正式路线。
原代理报告过一次本地下载模拟器工件的违规，原记录完整保留；本次 root 审查不在本地执行语法、构建、测试、模拟器或工件下载/解析。

Root 第一轮 `9ad9a768c90ba3d57956335951c6497d8a4e4aec` / run `40232266125` / attempt 1 三作业均 success，三阶段公开 API 实际回读已全量执行。发现报告明细问题：`adb exec-out run-as` 虽返回 0，stdout 明确含 `Permission denied`，driver 已按无 JSON/API 报告正确拒绝 sameUID；summary 的 pending 列表原只筛非零退出，漏了这些已拒绝明细。第二轮按实际 `refusals` 和退出码共同保留完整拒绝上下文，再全轮同源重跑；第一轮的原始 stdout/JSON/日志完整保留，其 sameUID scope 始终为 false。

## 不在范围

真机、商店/签名、性能、产品目录库 `reader-catalog.db` 的独立读取（SDK 公开头没有该库的 C 入口；此处的“书目”指 `exr_library_books`）、
iOS/桌面。未跑到的项在 `HANDOFF-RESULT-C08.md` 如实列为未验证。
