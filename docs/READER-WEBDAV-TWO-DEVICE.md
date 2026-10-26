# 共同源码 WebDAV 双设备互通：证据与缺口

起点 `11042994df180754a11e6d5f828df4277e839c3d`。最终目标见
[进度目录](reader-total-progress/catalog.json) F02–F05：至少两端真实应用上传、下载并打开原件，六端书架组织一致，进度、书签、标注与原始锚点双向互通，以及离线、并发、墓碑与恢复。以上均为 pending；模块成功不授予这些目标。

## 已有证据与本轮入口

- [真实服务验收](READER-WEBDAV-INTEROP.md)在历史源码 `e3dc2386` 上以 Linux 已安装模块和两个独立产品库经 Apache、Nextcloud 各通过 33 项；它的原件和修订由测试生成，不是宿主操作结果。先前 Apache 2000 项上限失败 run `40054114195` 与修复复验均原样保留。
- [Android 记录出口](READER-ANDROID-RECORD-INTEROP.md)文档及验证 JSON 仍写 sender 待执行，但 [run 40181402323](https://github.com/NoGod3524/EXReader/actions/runs/40181402323) 的严格汇总接受了实际 Android API34 x86_64 sender：源码 `b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7`、attempt 1，4 份原件、19 份修订、11 条阅读记录；APK SHA-256 `eea5de2867e147f0a3a9418c0bfbf2e574bdaa18226ffa02340ed94fb549476e`，包工件 `12594712144`（SHA-256 `08ce264db1a6e6083e15ddd20a60f6f088b7d82afe24e4d44aa8681e6551cac3`）。这是历史源码的模拟器结果，跨 Apple 接收仍 pending；包不含书架组织。不得用其协议夹具冒充另一设备。
- [共同源码服务工作流](../.github/workflows/reader-webdav-two-device.yml)重用同一实际服务、已安装公开 API 和原有严格汇总，在本分支重新构建。旧工作流的冻结路径限制不适用于共同源码；此工作流验证当前检出 SHA 是指定起点后代，并保留构建日志、服务原始日志、设备数据库和逐字节结果。历史 harness 的 `start_point` 是其原始测试起点，不是本轮冻结承诺。
- [共同源码 Android 工作流](../.github/workflows/reader-android-composed-record.yml)复用现有真实应用及记录导出探针。工作流沿用原严格汇总核对实际 APK、加载 SDK、源提交和转运包；不继承旧源码的验收结论。

`reader_sync_step` 负责原件与修订传输，明确不执行产品投影或 SDK 阅读状态更新；完整客户端必须在接收后完成原件映射、组织投影和实际锚点 resolve。两独立数据库并不等于两台运行的客户端。

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
