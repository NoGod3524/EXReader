# 共同源码 WebDAV 双设备互通：证据与缺口

起点 `11042994df180754a11e6d5f828df4277e839c3d`。最终目标见
[进度目录](reader-total-progress/catalog.json) F02–F05：至少两端真实应用上传、下载并打开原件，六端书架组织一致，进度、书签、标注与原始锚点双向互通，以及离线、并发、墓碑与恢复。以上均为 pending；模块成功不授予这些目标。

## 已有证据与本轮入口

- [真实服务验收](READER-WEBDAV-INTEROP.md)在历史源码 `e3dc2386` 上以 Linux 已安装模块和两个独立产品库经 Apache、Nextcloud 各通过 33 项；它的原件和修订由测试生成，不是宿主操作结果。先前 Apache 2000 项上限失败 run `40054114195` 与修复复验均原样保留。
- [Android 记录出口](READER-ANDROID-RECORD-INTEROP.md)文档及验证 JSON 仍写 sender 待执行，但 [run 40181402323](https://github.com/NoGod3524/EXReader/actions/runs/40181402323) 的严格汇总接受了实际 Android API34 x86_64 sender：源码 `b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7`、attempt 1，4 份原件、19 份修订、11 条阅读记录；APK SHA-256 `eea5de2867e147f0a3a9418c0bfbf2e574bdaa18226ffa02340ed94fb549476e`，包工件 `12594712144`（SHA-256 `08ce264db1a6e6083e15ddd20a60f6f088b7d82afe24e4d44aa8681e6551cac3`）。这是历史源码的模拟器结果，跨 Apple 接收仍 pending；包不含书架组织。不得用其协议夹具冒充另一设备。
- [共同源码服务工作流](../.github/workflows/reader-webdav-two-device.yml)重用同一实际服务、已安装公开 API 和原有严格汇总，在本分支重新构建。旧工作流的冻结路径限制不适用于共同源码；此工作流验证当前检出 SHA 是指定起点后代，并保留构建日志、服务原始日志、设备数据库和逐字节结果。历史 harness 的 `start_point` 是其原始测试起点，不是本轮冻结承诺。
- [共同源码 Android 工作流](../.github/workflows/reader-android-composed-record.yml)复用现有真实应用及记录导出探针。工作流沿用原严格汇总核对实际 APK、加载 SDK、源提交和转运包；不继承旧源码的验收结论。

`reader_sync_step` 负责原件与修订传输，明确不执行产品投影或 SDK 阅读状态更新；完整客户端必须在接收后完成原件映射、组织投影和实际锚点 resolve。两独立数据库并不等于两台运行的客户端。

## 共同源码复验结果

[run 40381289997](https://github.com/NoGod3524/EXReader/actions/runs/40381289997)，attempt 1，源码 `d84f0071808f6669f4def22846c5759a486e03e0`：Apache job `121777892436` 和 Nextcloud job `121777892798` 均成功，原服务场景各 33/33；summary job `121781546688` 下载并核对两份工件的 SHA-256、源码/运行身份及原服务 access log。各服务工件同时保存本轮真实 Android 包重放的调用、产品库、服务日志和结果：Apache 工件 `12678778986`，SHA-256 `0d5ccada25f3a24527bd8d818c2f729a881334fd0a6372e0ced34371f9162e8b`；Nextcloud 工件 `12679451399`，SHA-256 `2bc34b43a1283cba68baf8da0e6cfa5421859b83c9ef56c9305b07c3036eec55`。

重放先核对历史真实 Android sender 的 run、源码、原 ZIP 散列和 manifest，再以公开 revision 接口按祖先顺序写入独立产品库，通过当前源码的公开 sync/WebDAV 接口上传并由另一库拉取。两服务均核对 4 份原件、19 份原始 revision 与服务端和接收库字节一致，发送和接收库均为 19 条历史、0 条待发。该测试的发送端和接收端均是模块驱动；它没有在宿主中触发同步、投影组织或定位，也没有反向写入。sender 使用历史源码而非本次源码。原有 summary 校验整个工件 ZIP 的身份和原服务测试，不独立复核新增重放结果的语义；新增步骤结果及原始证据保存在同一已认证工件内。
[Android run 40381154018](https://github.com/NoGod3524/EXReader/actions/runs/40381154018)，attempt 1，源码 `2b34566f3ef0eed20ebc1970262f2a2d9e253ed9`：实际 Android API34 x86_64 sender 及严格 summary 均成功，共 138 项；sender 包含 4 份原件、19 份 revision、11 条阅读记录，另以独立进程核验缺父时 PENDING、祖先齐备后 FOUND。原安装 APK SHA-256 `cbadbdfabac6a069c3315bcc274d9fba50dd933c27d3eedc747a4ae43bd20e78`，实际加载 SDK SHA-256 `b3fc325f187a612d0fc809565faba6e9fa1d5ece2a7f7ba8158210b52db46310`；sender 包工件 `12679821614`，SHA-256 `399b8ff46bc1d34c53496bea17c67e9e749745299b621b1feb80f99eb72ed94b`。该 Android 源码与上述 WebDAV 重放源码 SHA 不同，而且 WebDAV 重放使用的是更早的历史 sender 包，不能合并为同源端到端结果；Apple incoming 仍 pending，双向互通为 false。
## 六端缺口

以下是指定起点目录的独立宿主功能状态，并非同源跨设备结论：

| 目标 | 云原件接收 | 组织 | 进度/标注 | 同步状态及失败/取消/重试 | 跨设备剩余 |
| --- | --- | --- | --- | --- | --- |
| Windows | verified | partial | verified | partial | 共同源码实际程序的双向同步、组织投影及原始锚点定位 |
| Linux GTK | verified | verified | verified | partial | 共同源码实际程序的双向同步与原件打开、远端记录定位 |
| macOS | partial | partial | verified | partial | 云原件接收、组织及真实双向宿主闭环 |
| Android | verified | verified | verified | partial | 同源真实 sender/receiver、WebDAV 往返及远端锚点定位 |
| iPhone | partial | partial | verified | partial | 云原件、组织、实际应用双向链路与真机证据 |
| iPad | partial | partial | verified | partial | 云原件、组织、实际应用双向链路与真机证据 |

这些 verified 只代表目录所引用的独立功能范围，不表示同一最终源码或共同验收。

## 可接受的下一步证据

在同一源码、同一运行中启动两个实际程序，核对实际安装包/执行程序及加载 SDK 的散列；各端通过真实公开操作导入并打开原件、建立组织和捕获进度/标注。各端通过自己的同步会话向同一真实 WebDAV 目录写入并从对方读回，保留原始网络日志、原件散列、原始 revision 字节与完整祖先。接收端实际打开原件、检查组织投影，并由 SDK 对原始锚点返回 FOUND 后核对位置；反向重复。删除、恢复、离线及冲突另留真实操作和结果。禁止手工生成记录、替换 parser、重编码原始 wire 或把两个测试数据库当作两个宿主。

各平台和每项缺口单独登记源码、run/attempt、真实程序与工件身份、原始失败及作用范围；云盘身份校验由其专责团队处理。本分支不改其宿主或云导入代码。

## 实际 Android→GTK 联合运行

在独立测试包中新增同一作业内的真实 Android 同步界面、固定镜像 Apache 与实际 GTK 接收驱动。服务端验证 Android 原件和 revision 原字节后，GTK 从同一服务扫描并通过实际宿主入口接收书籍及检查记录定位；整个链路以运行中的 APK、GTK 可执行文件与服务镜像身份绑定。组织及反向路径仍未覆盖。

初次 [run 40384258547](https://github.com/NoGod3524/EXReader/actions/runs/40384258547)（源码 `442604ab67972a1db94b61c663a563d42ce54ab0`）实际 sender 六项成功，但同步 UI 准备报 `UI target did not become ready`；原始 Apache access log 只有独立检查的 PROPFIND，没有 Android 请求。[run 40385748498](https://github.com/NoGod3524/EXReader/actions/runs/40385748498) 在 Actions 中读取原失败工件确认上述现象。该轮没有实际上传，不计互通。后续测试将启动和回书架、打开同步、账号设置、同步分别记录，不改生产宿主。GTK 独立构建诊断 [run 40384592342](https://github.com/NoGod3524/EXReader/actions/runs/40384592342) 成功，仅证明构建。

[run 40385936562](https://github.com/NoGod3524/EXReader/actions/runs/40385936562)（源码 `e478b5e07ab89a633bf00fbca58c08ff25cab19d`）完成 sender 后，在 `open_sync_panel` 失败。Actions 内 [run 40388218100](https://github.com/NoGod3524/EXReader/actions/runs/40388218100) 读取失败时的实际无障碍树，显示阅读页仍可见；先前的就绪谓词误识别后台隐藏的书架控件。已收紧为可见且可操作后重跑；该失败不得计入 WebDAV 上传通过。

共同源码接线审查：`examples/android/app/src/main/cpp/sync_jni.cpp` 的远端投影调用与 `examples/linux/received.inc` 的接收投影都限定 `book`；两处未接入 shelf、tag、series 或 membership 的远端投影。现有修订 API 支持这些实体，但现有宿主接收入口没有将其串起来；仅同步到 history 不等于书架组织已显示。修订/账户不属于本包可改宿主范围，应作为后续接入任务。

[run 40388334083](https://github.com/NoGod3524/EXReader/actions/runs/40388334083)，attempt 1，源码 `034a4a38d3818f1b24889aeeb04d6f3167ef4095`：Android 实际应用经同步界面向 Apache 发送；同一作业构建的 GTK 程序经自己的同步界面接收，并实际打开 TXT、EPUB、PDF、CBZ，11 条选定进度/书签/高亮以 SDK 返回 FOUND 且范围与原始记录一致。APK SHA-256 `b9ee945d9ae871d48603378b2cec5c9d7e487ae6b278aa4dec66c34246451bdf`，加载 SDK SHA-256 `b3fc325f187a612d0fc809565faba6e9fa1d5ece2a7f7ba8158210b52db46310`；GTK 实际运行程序 SHA-256 `1c9eaa35dc15d163ff3d3671a7610940df03ad6b1bdb00e374ee7db3d5db4323`；原工件 `12681039806`，SHA-256 `98a216c7203c2965218449ac26deae046cfa9452f7683960cdddb76367bb9cb7`。

独立认证 [run 40390426526](https://github.com/NoGod3524/EXReader/actions/runs/40390426526) 在 Actions 下载并散列原 ZIP，复核源码/作业、APK 与实际加载 SDK、GTK 程序、转运包 4 份原件、接收库中 19 份精确原 revision、4 个 SDK 本地映射、11 条 FOUND 数值和 682 条应用侧服务请求。报告中的 `desktop_receiver=false` 是初始化遗留值，实际 `actual_desktop_receive=true` 及接收原始结果经上述复核；它不应被改写成历史原报告。此结果只授予 Android→GTK 单向、模拟器与 Linux、所列格式和记录，不授予组织或反向。

四原件另由 [run 40391241316](https://github.com/NoGod3524/EXReader/actions/runs/40391241316) 独立回读：Actions 认证原 ZIP 后，以精确受测源码 `034a4a38d3818f1b24889aeeb04d6f3167ef4095` 构建公开 SDK inspector，从实际 GTK 接收库逐字节导出 TXT 4109、EPUB 13853、PDF 1892、CBZ 43936 字节，均与 Android 原件一致。认证工件 `12683890627`，SHA-256 `f22802647b2382ca2bc02533da185f82b9a26ce8ffb6bf88c434550e0a0d9a39`。

## 已认证的限定双向结果

[运行 40390699668](https://github.com/NoGod3524/EXReader/actions/runs/40390699668)，attempt 1，受测源码 `9ea6d1d56d6d38942cc996734776f865d0a18681`；[独立认证 40392496386](https://github.com/NoGod3524/EXReader/actions/runs/40392496386) 成功。实际 Android API34 x86_64 模拟器安装 APK SHA-256 `6b35db356ac76703c0a9a56a455eeb7e27300740930d03910f09f192e9c62d1b`，实际加载 SDK SHA-256 `b3fc325f187a612d0fc809565faba6e9fa1d5ece2a7f7ba8158210b52db46310`；实际 Linux GTK 执行程序 SHA-256 `1c9eaa35dc15d163ff3d3671a7610940df03ad6b1bdb00e374ee7db3d5db4323`。两端使用同一固定 Apache WebDAV 服务。

- Android→GTK：TXT、EPUB、PDF、CBZ 四份原件经实际应用发送与接收；独立 SDK inspector 从 GTK 库读取的 4109、13853、1892、43936 字节分别与 Android 原件逐字节相同。19 份原始 revision 逐字节核对，11 条所选进度、书签、高亮由 GTK 实际 SDK 返回 FOUND，范围和原始记录一致。
- GTK→Android：GTK 实际界面新建 TXT 进度和书签，经服务上传，Android 实际界面同步并读取精确 wire；两条均由 Android 实际 SDK 返回 FOUND，范围均为 `0..0` 点锚。反向高亮、其他格式、书架组织、并发和真机未由此轮接受。

原始工件 `12685855227` SHA-256 `5083ece4c791a4bff28bb218e89f8d27ef248ee615727805189076180f8369b4`；认证工件 `12686025698` SHA-256 `0736793d2da263baaac2115ab1df5e986be7382e0fe477019108c65d940c0416`。认证核对原 ZIP、程序与 SDK 身份、双向原始 wire、11+2 条定位、1258 条非独立检查服务请求和四份 GTK SDK 原件回读。仅授予上述两端和范围，不授予六平台完整互通。
