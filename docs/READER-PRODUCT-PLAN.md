# 原生互通阅读器：首版范围

用户于2026-10-23确认：R6收尾后，模块化接入与阅读器产品并行推进；
首版使用用户自有云盘／WebDAV同步，本地优先、离线可读。
Windows、macOS、Linux、Android、iPhone和iPad共用EXReader阅读核心；
保留自有PDF渲染、多格式入口、原生界面、轻量构建及可测性能，不依赖WebView。

## 起点与交付状态

默认分支`codex/framework`已通过PR #3接纳传输修复，提交
`cdfe48231853d6e70fba2c41b42bdd187155901a`。
PR门禁[39972628703](https://github.com/NoGod3524/EXReader/actions/runs/39972628703)
17/17成功、28工件齐全，严格汇总接受；默认分支发布准备
[39975024792](https://github.com/NoGod3524/EXReader/actions/runs/39975024792)
已原样导出此前验收的六份SDK包，`prepared=true`、`published=false`。
默认分支push复验39974986212也在cdfe482本身完成17/17、28工件及严格接受。
完整身份见[收尾记录](validation/reading-release-default-cdfe482.json)。

SDK固定为`9854061be331fe603a1822d9b2b36ee357154927`，SDK3.40.0／ABI1／schema7。
产品模块单独版本化、链接安装后的公开组件；新增书架或同步功能不改SDK私有表。
当前阶段交付导入模块和产品存储基础：c2c75f99的云端run39980923147四作业已通过，
详见[模块记录](validation/reader-modules-c2c75f9.json)。尚未交付新的产品UI或跨设备同步客户端。

### 后续独立候选进度（未合入默认分支）

以上是默认分支起点，不等同于产品分支进度。后续以可独立审阅的草稿 PR 交付：
PR4 模块基础、PR5/6 平台产品目录、PR8/12 导入映射、PR10 桌面目录桥接、
PR11 WebDAV 只读来源、PR13 GTK 固定页、PR14 修订历史/outbox，以及 PR15 Apple
有界书架。各自只授予同源云端证据覆盖的范围，产品尚未完成联合验收。

桌面目录查询 `a1e984315e1399ba96e4ef358030323d44362c81` 的 run `40035762258`
已三平台通过。GTK 实际 2202 书有界界面源码 `dc7e0f6d`、run `40040335713`
已通过十四项真实 UI 和全部保留回归，两作业同源成功。Windows 有界书架源码
`f93ec5cd8154d82be63d8831e14547a27a597eca`、run `40043264202` 已独立通过：
原 UI 158、产品 10、worker 5、有界书架 UI 13，覆盖 2202 本原书、50 行分页和
150 行缓存。详见 [Windows 书架记录](READER-WINDOWS-SHELF.md)。
Android 有界书架源码 `ed0008d680a6838e2834dd2a8973dcf17a5d44d2` 的 run
`40037805014` 已同次通过：目录 12、真实 UI 10、原目录 8、导入映射 14、真实 kill
2、原 45+10+11 及 49 页严格出口、原 48+20 门禁与本包 19 证据探针。工件
`12538856596` 同源、107473231 字节、SHA-256
`891a57848a53baf67bebd7fa1b0cc9a14d5b74c3aab0766e2c5b2a71c23a22c5`，未过期。
仅授予 API34 x86_64 模拟器功能范围；`performance_accepted=false`，观测数据不是
丝滑或真机性能验收。Apple 大书架仍在独立复验。WebDAV 双向同步二期
[PR16](https://github.com/NoGod3524/EXReader/pull/16) 已独立交付：受测源码
`0cb23a13fd23374b61ae7b9744173215aaf04660`，run `40038722770` 两平台同次成功；
Linux 77+59+33、Windows 76+59+33，两个同源工件未过期且 digest 与上传日志一致。
覆盖不可变原件、修订/outbox、真实 TLS/重试/并发/墓碑及 2202 原件全 256 分片；
此包不授予宿主 metadata 投影、同步 UI、移动适配或真实用户云盘互操作。
后续 PR18 的原子 metadata 投影已在源码 `73d80201`、run `40040479157` 两平台
各通过 32 项新增检查；PR20 的具型命令在源码 `32c31768`、run `40042300722`
两平台各通过 33 项新增检查，并保留前序检查。产品 metadata、修订与 outbox 在
同一产品库事务提交，SDK 数据库独立。宿主 UI 和移动调用仍需各自接入验证。
[产品预集成](READER-PRODUCT-INTEGRATION.md)已在共同源码 `bad72dd6`、run
`40045484528` 通过 5/5 作业和云端严格汇总，确认 Windows／Linux 书架与共享同步
模块的同源共存；尚无六目标同步闭环或平台安全凭据 UI 的验收。
详见[桌面有界书架](READER-DESKTOP-SHELF.md)。
Android 产品库从完整 SQL 生成资产，在现有 owner worker 上打开独立
`reader-catalog.db`，拒绝改写 SDK 或未知数据库。导入映射和有界书架的独立结果见上方。
后续原生 owner 源码 `8f7c011aafd4d7f900ef42106fa41e2150a66d58` 已在 run
`40049878764` 完整通过17项桥接、两次中断恢复、原112项功能与87项门禁及新增19项证据门禁；
产品库使用与桌面一致的已安装原生provider。详见 [Android原生owner](READER-ANDROID-NATIVE-OWNER.md)。
WebDAV [实施契约](WEBDAV-PROTOCOL.md)的网络与两端协议结果按各包证据分别登记。
Apple owner 队列负责独立 `reader-catalog.db` 的生命周期，原生包、UI、Model 与
Bounded 消费者使用同一完整 SQL。目录和导入映射的独立结果见
[Apple 导入映射](READER-IMPORT-MAPPING-APPLE.md)；新的有界书架尚未纳入本候选。

### 最新产品候选接续

共同产品metadata候选 `ae584ccf` 已通过Windows/Linux严格预集成及Android原生owner
同源复验。其后的模块和界面按各自固定源码分别验收：

- [真实WebDAV互操作](READER-WEBDAV-COMPAT.md)：Apache与Nextcloud各33项，
  同源原生Windows/Linux回归通过，修复2000条真实目录的XML容量与百分号路径兼容。
- [账号后台会话](READER-SYNC-SESSION.md)：Windows/Linux各20项，
  真实HTTPS、256分片、取消重试和账号独占；尚未接入账号UI或SDK原件导出。
- [阅读状态v2](READER-READING-V2.md)：`818e3629` 的Windows/Linux协议、
  旧端拒收及SDK往返五作业同源严格通过；进度和点书签进入产品修订。
  按书标注keyset分页 `4e59a0b8` 的新增10项与全部保留套件同源五作业严格通过。
- [GTK收藏整理](READER-GTK-COLLECTIONS.md)：`b9124fbd` 的27项新UI与全部保留
  回归同次通过；已正常合入工作候选，支持子书架、标签、系列及显式恢复。
- [SDK原件导出](READER-SOURCE-EXPORT.md)：`745c3483` 两平台各14项、五作业严格
  通过；侧载模块在SDK owner上完成分块读出、取消处理和不覆盖目标的原子发布。
- 平台凭据独立交付 `e2247deb`、run `40057087875` 五平台成功；验证器`32f72ba7`
  的run`40060725476`通过96项拒绝回归并重新散列五ZIP，已正常合入工作候选。
  Windows不可用、iOS锁屏、Android Keystore故障保留未验证范围。
- 阅读状态原生HTTPS联验`f7e911c8`、run`40060616599`同源五作业严格通过：
  四格式原件经SDK导出/上传/下载/第二端实际导入，18个锚点17 FOUND/1预期歧义，
  零误定位。后续`fb30036a`、run`40062187051`同源五作业严格通过：接收端先投影
  四本书的SAFE metadata再导入下载原件，title/author/favorite不被本地默认值覆盖，
  18个阅读捕获仍17 FOUND/1预期歧义、零误定位。

Android收藏整理`3f50a165`的run`40059870895`完整通过，新增8原生/8UI/真实重启及
15门禁与全部原17+2/112/87/19同次通过，已正常合入工作候选。
接收发现/投影公共接口`2cbdd49b`的run`40061634535`两平台各12项、五作业严格通过。
书内搜索包`971e528e`的run`40064018124`两平台各264检查/34场景、严格汇总通过，
包含同长度换书游标拒绝、独立SDK重开、线程归属、完整分页/取消与锚点兼容。
已正常合入工作候选；`8476d6b9`、run`40064505462`同源五作业严格通过，
两平台重跑264搜索检查/34场景及原生同步/metadata/阅读状态/原件传输全部保留套件。
汇总重新校验实际消费者和安装包哈希、原始命名检查及跨平台结果，
`search_package_accepted=true, webdav_roundtrip_accepted=true`。
完整工件身份见[同源联验](validation/reader-search-joint.json)，宿主搜索UI尚未授予。
原生同步macOS接入`a32602be`、run`40065344267`同源四作业严格通过：
macOS ARM64/Linux各283检查、Windows282检查，覆盖HTTPS、修订、同步、metadata、
命令、恢复与账号会话。Apple使用系统随机源/CommonCrypto和系统libcurl/libxml2，
SDK/schema不变。已正常合入工作候选；本包未授予iOS、Android同步或宿主账号UI，
身份见[macOS原生同步](validation/reader-sync-apple.json)。
正常合入macOS接入后的组合源码`867c8650`、run`40065943105`同源五作业严格通过，
再次保留264搜索检查/34场景、全部原生套件及四格式原件/18阅读捕获的HTTPS往返。

阅读设置F3原16组交付保留；root补回归后修复数值语法/有效数字、可空error状态及64 KiB
上限，`1f51b406`、run`40067465230`三平台各20组、严格汇总四作业通过，已正常合入。
Android WebDAV `7c27efec`、run`40066284731`同源三作业通过：API34 x86_64原生91组
及真实重启4组，Linux77/Windows76与各12兼容检查；API26编译、Release扫描与包体增量
单列在[验收记录](validation/reader-webdav-android.json)。已正常合入；尚未授予Android完整
同步会话/SDK原件导出/宿主账号UI。上述两项在后续共同源码复验，不拼接旧结果。

F4文件夹导入原`a85bbc5f`、run`40065922610`三平台668项交付已核实；root独立审查
补出目录预算排队超界、父目录链接替换、并行计数及macOS复制修改观测缺口。
修复源码`67cee469`、run`40068645513`同源四作业成功：三平台各原668+新增4项，
Linux额外8个owner/64次导入的真实TSan通过；严格工件验证另拒绝6种篡改报告。
已正常合入工作候选；原交付、三轮红测及Windows夹具问题均保留在
[独立审查记录](validation/reader-batch-import-review.json)。宿主批量导入UI与组合源码复验待完成。

GTK账号与全库本地准备 `d88ed89d`、run`40068924227` 已通过并正常合入：新增23项，
原105项与4项故障检查同次通过，另保留桌面/产品ctest。包含Secret Service或明确的
仅本次会话凭据、每页50/逐书SDK owner准备、真实多头保留、取消/重试及关闭生命周期。
该扫描会下载校验原书缓存，但尚未把接收历史完整投影为可打开的宿主书籍；
接收投影、SDK导入和缓存缺失后的下载调度继续接续，见
[GTK账号记录](validation/reader-gtk-account.json)。

Apple原生WebDAV传输`5bebae0f`、run`40070706494`四producer与严格汇总五作业通过，
已正常合入。iOS26.2 arm64 iPhone Simulator实际100项，macOS Foundation306项，
Linux295项、Windows294项同源通过；系统TLS验证、流式上传/取消、线程归属及回调保留。
该包只授予传输；完整iOS阅读器会话、SDK导入/导出调度和账号UI继续接续，见
[Apple传输记录](validation/reader-webdav-apple.json)。macOS默认仍为已验系统curl，
iOS默认使用Foundation。上述新包仍需在最终产品共同源码复验。

F5真实文件独立复核仍拒绝：原交付Windows12/18、Linux14/18。
审查源码`80946aa4`、run`40070449808`确认原Windows进程参数已损坏俄文查询；
修复消费者UTF-16→UTF-8入口后，两平台均14/18，SDK源码未改。
RTF两份与CBZ两份仍失败，不更换文件或改成预期拒绝；18份不计入旧1710目标。
该分支未合入工作候选，兼容性与路径策略另行处理，见
[F5审查记录](https://github.com/NoGod3524/EXReader/blob/1ea0e160bc1805619c222bd121028cc1373d50e3/docs/READER-REAL-CORPUS-REVIEW.md)。

Apple有界书架仍等完整云端出口。随后需把已验收包合到同一源码
复验，并把已通过的原生原件/metadata/阅读状态WebDAV往返接入宿主的分批下载、
投影调度、凭据/账号UI及四套原生壳的列表/导航。以上独立结果不转移到尚未测试的组合源码。

## 并行工作包

| 包 | 交付 | 出口 |
| --- | --- | --- |
| P1 产品书库 | 独立metadata数据库；书籍身份、本机SDK映射、子书架、标签、系列顺序、分页索引及离线待同步数据 | 数据约束、事务回滚、幂等、删除记录与数千书分页；不以数据库检查冒充UI流畅性 |
| P2 导入模块 | 独立`extras/sideload`，只使用公开书库API；系统文件、本地文件及云端下载完成后复用同一路径 | 安装后消费、原件回读、精确去重、限额、短读、取消和所有权 |
| P3 WebDAV同步 | 一个账号及专用目录；不可变原书、实体修订、离线outbox、冲突保留与删除墓碑 | 两端往返、离线重连、并发修改、删除、断电重试、HTTPS及凭据隔离 |
| P4 原生产品UI | 复用Windows、GTK、Android、SwiftUI四套壳覆盖六目标；书架、导入、整理、阅读与标注 | 六目标实际流程、生命周期恢复及固定规模书架帧时间／内存预算 |
| P5 联合验收 | 同一产品源码、相同协议与各平台独立证据 | 六目标闭环，至少两设备同步原书、进度、标注和分类；真机及读屏单独登记 |

P1、P2先并行；数据字段固定后P3与各平台P4可并行。共享SDK的变更必须重新冻结，
产品层改动按实际影响复验。所有构建、测试、语法检查、夹具和证据解析仅在GitHub Actions运行。

## 导入与阅读边界

- EPUB/CBZ使用借用的不可变、可随机读source，书库分块复制原件。
- PDF由宿主提供调用期间稳定的私有文件；公开file入口会多次按路径打开，且没有调用内取消参数。
- 其他重排格式首版最多32MiB，分块读取后使用既有memory导入；不声称它们已有有界章解析。
- 精确去重由SDK按格式和原始字节完成。取消不能删除重复命中的旧书；已提交结果必须明确返回。
- 权限、系统选择器、Android URI、安全作用域URL、线程和文件稳定性由宿主管理。
- 有线导入先使用Android系统文件传输和Apple文件共享；桌面使用本地文件／系统云盘入口。

## 产品身份与同步规则

跨设备书籍身份是原书SHA-256加格式，本机SDK行号仅为映射。子书架树、标签和系列分别建模。
同步原书与实体数据，不同步运行中的SQLite文件。全部SDK写入经宿主owner队列，避免其他连接
提交使现有source失效。

EPUB章内锚点、普通重排UTF-8锚点、固定页锚点保持显式模式。远端位置须经公开resolve得到
`FOUND`才可导航；歧义或缺失保留原始记录。当前阅读不被远端进度强制跳转。

首版同步以独立不可变修订保留并发版本，删除同样保留墓碑；设备时钟只供展示，不裁决覆盖。
ETag可用于缓存，具体发现和写入协议由P3实现及互操作验证固定。
原书先验证长度和散列再发布引用。远端暂时缺文件不等于删除；首版不自动回收远端历史和原书。
“移除本机下载”和“从书库删除”使用不同操作，云端书籍支持按需下载及保留离线。

凭据使用平台安全存储：Apple Keychain、Windows Credential Manager、Linux Secret Service、
Android Keystore保护的加密存储；不可用时仅保留当前会话。日志、书库和同步载荷不含凭据。
HTTPS、证书验证、跨源凭据隔离、远端载荷限额和临时文件原子发布进入P3验收。

## 默认界面

首页显示书架、搜索、导入和继续阅读。子书架、分类、系列及批量整理按需进入，
阅读时工具自动收起。逐步覆盖书签、标注增改删、目录、全文搜索、排版设置、主题及常见阅读操作，
以可达的菜单和上下文操作保持默认界面简洁。

书架使用分页、虚拟化及有界缩略图缓存。帧时间、峰值内存和首次可交互预算需在产品实现后
按固定设备／runner及固定书库规模测量并冻结；现有SDK性能结果不替代产品UI预算。
OCR、TTS及商业获取继续作为独立可选模块推进。
