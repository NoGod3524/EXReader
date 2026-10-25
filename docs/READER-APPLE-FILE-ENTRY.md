# Apple 文件选择、文件共享与安全作用域入口

`extras/apple-file-entry`是独立的可选Swift组件（macOS 12+、iOS/iPadOS 15+），
把用户选择的文件、文件共享Inbox中的文件变成**应用私有的稳定暂存文件**，并给SDK owner一个
`FileEntryRequest`。组件不依赖阅读SDK、不读写SDK私有存储、不进入默认构建，
SDK、sideload模块与产品schema保持固定起点`f43baf91`的原样。

```text
系统选择器 / 分享 Inbox ──URL──▶ FileEntryStagingArea ──FileEntryRequest──▶ SDK owner
 (安全作用域URL)                  协调读取 + 64 KiB分块复制                 exr_sideload_import_file(stagedPath)
                                  SHA-256、原子提交、私有目录                成功后 area.release(request)
```

## 安装与接入

```text
bash extras/apple-file-entry/install.sh <prefix> macos|iphonesimulator
```

产物：`<prefix>/lib/libEXRFileEntry.a`、`lib/swift/EXRFileEntry.swiftmodule`、
`share/exreader-apple-file-entry/{LICENSE.txt,examples/}`。宿主用`-I <prefix>/lib/swift -L <prefix>/lib -lEXRFileEntry`
链接。`examples/ImportStagedRequest.swift`与`SdkBridge.h`是安装后接入范例：
`importStagedRequest(library:area:request:)`把请求交给已安装的sideload模块并在持久成功后释放暂存。
范例由安装后消费者实际编译、链接公开SDK和sideload后运行（见验收）。

宿主典型流程：

1. 主线程弹出`FileEntryPicker.present(...)`（iOS为`UIDocumentPickerViewController(asCopy:false)`，macOS为`NSOpenPanel`），
   或用`FileEntryInbox.candidates(documentsDirectory:)`枚举Inbox。
2. 立即在选择回调里调用`area.stageInBackground(urls:origin:cancellation:completion:)`；回调在内部串行队列上执行，宿主再切回自己的SDK owner线程。
3. SDK owner线程对每个成功结果调用`exr_sideload_import_file`（或范例函数）；成功后`area.release(request)`。
4. 启动时`area.pendingRequests()`恢复上次未导入完的请求，`area.sweepOrphans()`清理残件。

## 公共接口契约

| 项 | 契约 |
| --- | --- |
| 输入 | `URL`数组（选择器安全作用域URL、Inbox文件URL或任意本地文件URL）；`origin`为`picker/inbox/other`。 |
| 输出 | `FileEntryRequest`：`id`（小写UUID）、`stagedPath`（绝对路径，C侧按UTF-8传入）、`displayName`、`byteCount`、`sha256`、`format`扩展名提示、`origin`。 |
| 暂存目录 | 调用方给定，创建时0700并排除备份；文件0600；数据`<id>.data`、清单`<id>.json`。暂存文件在提交后不再被修改，只由`release`或`sweepOrphans`删除。 |
| 精确字节 | 逐字节复制，不转码、不改换行、不剥离元数据；SHA-256与复制同步计算。`displayName`取URL最后一段原样保留，不做Unicode规范化、不改扩展名；暂存路径不含显示名。 |
| 内存 | 每次复制一个64 KiB缓冲，与文件大小无关；不整书读入内存。 |
| 线程 | `stage(url:)`、`stage(urls:)`阻塞，必须离开主线程（否则`calledOnMainThread`，且未触碰文件）。可并发调用，限额记账有锁。`stageInBackground`用组件内一条串行队列，可在主线程调用，完成回调在该队列上。组件不创建其他线程、不接触主线程。 |
| 重入 | 完成回调可调用除`close()`外的任何方法；`afterChunk`测试钩子内禁止调用`close()`。`close()`幂等。 |
| 安全作用域 | 每次复制前调用一次`startAccessingSecurityScopedResource`，仅当它返回true才在退出（含每条失败/取消路径）调用一次`stop`；返回false的普通URL直接读取。复制完成后作用域已释放，暂存文件与来源无关。 |
| 协调读取 | 经`NSFileCoordinator.coordinate(readingItemAt:)`读取，会等待写入者；取消时调用`coordinator.cancel()`。 |
| iCloud | `.notDownloaded`状态或`.Name.ext.icloud`占位符不读取、不复制，返回`notDownloaded(downloadRequested:)`并（默认）请求系统下载；调用方稍后重试。 |
| 错误 | `FileEntryError`：`closed`、`cancelled`、`calledOnMainThread`、`notFound`、`accessDenied`、`notRegularFile`、`notDownloaded`、`tooLarge(limit:)`、`tooManyPending`、`tooManyFiles(limit:)`、`changedDuringCopy`、`coordination(code:)`、`io(errno:stage:)`。 |
| 取消 | `FileEntryCancellation`单向、线程安全、幂等；每个64 KiB块之前检查，取消后无残留文件。已提交的请求不会被事后撤销。 |
| 提交边界 | 数据文件fsync后原子改名，再写清单并原子改名；清单改名即提交点。之前的失败、取消或进程被杀最多留下`.tmp-*`或无清单的`<id>.data`，由`sweepOrphans`清除（仅限本组件命名模式，外来文件不动，复制进行中不执行）。 |
| 部分复制 | 批量中单个失败不影响其它；失败项无残留。复制期间来源被截断/增长/改mtime→`changedDuringCopy`并清理；复制期间来源被改名不影响（读取的是已打开的描述符）。 |
| 关闭 | `close()`拒绝新工作、取消在途复制并等待它们清理退出；已提交请求保留，重开后`pendingRequests()`恢复（可选`verifyContents`重算SHA-256）。 |
| 删除 | 组件不删除用户来源，包括Inbox。`FileEntryInbox.removeOriginal`仅在宿主显式调用时删除直接位于Documents或Documents/Inbox的普通文件，符号链接、目录和其它路径一律拒绝。 |

### 硬上限（只能降低，不能提高）

| 项 | 上限 |
| --- | --- |
| 单文件（EPUB/CBZ/PDF及未知扩展名） | 128 MiB（`EXR_SIDELOAD_STREAM_LIMIT`） |
| 单文件（TXT/HTML/FB2/DOCX/RTF/MOBI） | 32 MiB（`EXR_SIDELOAD_MEMORY_LIMIT`），在复制前按扩展名提示拒绝 |
| 一次批量 | 64个，其后各项`tooManyFiles` |
| 暂存未释放 | 1 GiB、256个请求（构造器可降低；重开时按清单重新计数） |
| 复制缓冲 | 64 KiB |
| Inbox枚举 | 256项，仅九种已识别扩展名，跳过隐藏项、目录、符号链接和Documents中的数据库 |

大小在已打开的描述符上`fstat`判定，超限不复制任何字节。扩展名只是提示，格式最终由SDK判断；
`exrFormatRawValue`与`exr_format`枚举值一一对应（TXT=1…CBZ=9）。

## 导入SDK的规则（沿用既有契约）

暂存文件满足`exr_sideload_import_file`对“调用期间保持不变的应用私有路径”的要求，PDF也适用。
精确去重由SDK按格式与原字节完成，命中旧书保留标题、进度和标注（范例消费者验证`created=false`）。
SDK事务失败或取消时暂存请求保留，宿主可重试或`release`；SDK已提交的结果优先于取消。
Inbox原件在暂存成功后是否删除由宿主决定，建议只在SDK导入持久成功后调用`removeOriginal`。

## T04 定向复审（新源码验收待 Actions）

复审固定起点为`3c355b4ea3faab974861f4863893c6018653740c`，独占分支
`codex/dot-apple-file-entry-review`。已用 GitHub API 核实下节原 run 的七个作业确为
同 source/run/attempt 的 completed/success，原交回 HEAD 相对原受测 SHA 只有本页与验收 JSON。
原始运行和失败记录保留；下节绿灯不授予此次修改。

定向修复：关闭排空关闭前入队的后台批次及完成回调（仍禁止从完成回调内调用`close()`）；
已经提交的结果仍优先，关闭后的新调用仍异步收到`.closed`。iOS picker 的 delegate
先消耗一次性回调再执行，旧控制器的重复/重入事件不能重复移交；新增`makeController`供宿主管理呈现。
macOS 系统 completion 同样防重复，但系统面板 UI 仍未驱动。
提交清单与 pending 记账在同一锁内完成；并发 release 幂等，sweep 与新复制互斥；
文件 fsync/close 失败不得作为成功提交。清单发布前再次检查关闭/取消，目录 fsync 仍为尽力操作，
不授予断电耐久性。恢复只接受 version 1、合法摘要、至多64 KiB的普通清单及非符号链接普通数据文件；
已有暂存目录须属于当前用户，收紧至0700且拒绝符号链接。调用方须保持目录及祖先路径稳定，
一个目录只允许一个可变 owner（并非跨进程共享队列）。

新增真实进程在首块复制后`_exit(73)`、另一 invocation 重开并清理实际半成品的回归；
未知/小报长度通过独立 seam 验证一直读至EOF、发现超出声明长度即拒绝，不静默截断。
此 seam 不替代真实 iCloud/File Provider 权限撤销测试。
严格汇总新增真实作业 source/run/attempt 认证、API ZIP大小及SHA-256核对、重复 ZIP成员/报告拒绝、
逐行原始结果与报告一致性以及安装模块摘要绑定，并保留原全部具名用例。

## 原 J05 验收（历史源码）

受测源码`cb0dcfc854ea33caa7b86750279344a6e3515f2d`，
[run40147364965](https://github.com/NoGod3524/EXReader/actions/runs/40147364965)（attempt 1）七作业同次成功：
范围/负例守卫、macOS与iOS模拟器SDK、三个原生目标（macOS、iPhone 11模拟器、iPad Pro模拟器，Xcode 16.4，iOS 26.2）、同源严格汇总。
每个目标运行已安装模块的探针33项加安装后消费者15项，共48项，0失败0跳过；
消费者用公开SDK与已安装sideload模块导入九种格式并回读原字节，另验证去重、取消后重试、坏字节失败保留暂存、重开书库回读。
探针覆盖多文件部分失败、只读/无权限/移动/撤销、复制中截断与增长、取消、close、重开恢复、孤儿清理、篡改检测、限额、Inbox。
汇总核对三份工件的名称、同源SHA、run/attempt、有效期、ZIP内二进制摘要与安装模块，并运行33个证据正反例。
工件ID/字节/SHA-256见[验收记录](validation/reader-apple-file-entry.json)。

保留的失败：run40116197175（编译冲突）、40143622985（FIFO协调挂起）、40145777002（FIFO挂起与Unicode名规范化）、
40146792227（一个测试计数错误）。每次均已修复并在后继源码上重跑。

**仍为pending、未实测**：真实iCloud Drive/第三方File Provider下载（仅经测试接缝验证“未下载”）、系统选择器界面交互（只编译）、
沙盒应用中的真实安全作用域URL（真实启停对普通URL返回false，配对经接缝验证）、Files/Finder文件共享实际投递、真机、macOS App Sandbox。
本记录只授予本包模块；宿主接线、产品界面和六平台互通由root验证。
