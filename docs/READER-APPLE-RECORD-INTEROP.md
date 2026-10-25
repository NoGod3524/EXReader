# 实际 Apple 阅读记录互通出口

固定起点 `b1a7b7891cd394671842164a07a86c8e316dace3`。全部生产 owner、SDK、
模块、wire 与原兼容测试保持该提交的原样内容。本分支只增加测试、独立工作流与本文。

实际 `HostSession` 导入 TXT、有界 EPUB、PDF、CBZ，使用实际捕获与
`HostReadingWorker.submit` 生成每格式进度和书签，另对前三格式生成真实范围高亮。
从公开 outbox 导出原始完整 wire、book 修订及全部祖先，通过已有公开 SDK 流式出口
导出原件。manifest schema1 的 originals/revisions/reading_records 与 Android 对接约定一致。

Apple 的 sender 声明真实裸版本 `3.41.0`，不替换成 Android 前缀。
实际 executable、唯一 dyld SDK DSO、原始 wire 和原件均保留并散列绑定。
新的接收进程用公开 receive 存入原字节，完整唯一 reading graph 接纳后调用实际宿主
位置解析与重新捕获，检查 SDK 状态与产品 outbox 不变；第三进程重开后再解析同一 bundle。
每次运行同时保留原 18 个兼容进程阶段、两 SDK 各 19 项原 owner 测试及 Java20 策略检查。

当前验收：**未通过**。`aa561e86773935805d35150ad0bd2adc9cf4a7ff` 的
[40180582614](https://github.com/NoGod3524/EXReader/actions/runs/40180582614) 中两 SDK、
18 个原兼容进程阶段和新发送程序均已构建/执行；实际发送在 PDF 进度提交被拒绝。
只读诊断 [40181690876](https://github.com/NoGod3524/EXReader/actions/runs/40181690876)
认证原工件 `12593897613`，15,263,131 字节，SHA-256
`20d5747479aebe7ef6d0ca2c6223b2bd1170e1d24af4c1cbd9fd81e2b93c777a`。
原待完成请求保留原件 `pdf:5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc`
（8,845 字节）、`kind=progress`、固定页 `page-1` 的 0..0 点捕获。
实际 suffix 原始 Base64 为 `QWZp5LiAAEFBQfCfmIA=`，包含真实 NUL。
现有 `reader_rs_encode_v2` 对固定页 exact/prefix/suffix 的 NUL 明确返回
`NOT_REPRESENTABLE / GAP_NUL`，所以不是 parser 标签差异。原请求和原件均未删改。

**实际 Android 双向互通仍 pending**。新增独立 `android-to-apple` 运行路径，
认证 Android 源码 `b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7` 的
[40181402323](https://github.com/NoGod3524/EXReader/actions/runs/40181402323) attempt1：
实际 producer 与 strict 均 success，138 项原检查；固定工件 `12594712144`
（16,615 字节，SHA-256 `08ce264db1a6e6083e15ddd20a60f6f088b7d82afe24e4d44aa8681e6551cac3`）。
原 strict summary 工件 `12593694660` 的摘要也独立固定并认证。

Apple 两个实际接收进程分别首次接收与重开相同原字节，覆盖四原件、19 原始修订和
11 个真实点/范围。原保留记录通过公开 decoder 与 manifest 比较；新 SDK 捕获则与
实际宿主对原 wire 的重建比较，保留 EPUB `part_path` 与隐式 chapter 的真实区别。
同时核对实际加载 DSO、安装来源、完整唯一父图及只读状态不变。
这条新路径已通过下面的独立运行，只授予 Android→Apple 原生 owner 单向范围，
不能授予 Apple→Android、双向互通或完整产品。原 `apple-loopback` 发送路径仍可显式运行，
仍使用上述真实 NUL PDF，不因方向接收而宣称其失败已修复。
本包不授予宿主 UI、真机、六平台同步或完整产品验收。

## Android→Apple 已封存单向证据

受测 Apple 源码 `9ce130cf79020ec9ca15e3e03b7ec148ac451188`，
[run 40184339801](https://github.com/NoGod3524/EXReader/actions/runs/40184339801) attempt1，
native `121141831952` 与 strict `121143544084` 均 success。
Android 发送源与本次 Apple 接收源分别记录，不声称共同源码。

- 两个真实 macOS 进程 PID 56564 / 56566，分别首次接收和原 profile 重开；
  各自 11 条记录全部 FOUND、复捕获一致、完整唯一父图接纳、SDK 状态与 outbox 不变。
- 原 18 个兼容阶段、两版 SDK 各 19 项原 owner 测试与 Java20 策略检查同次重跑；
  strict 另拒绝 7 项错误身份/范围/进程/manifest 协议。
- 实际程序 SHA-256 `8c09d3e7c129f0b11dfad505e3f6e771f0bceff3071d28806bcd1b4971bd2d56`；
  两进程实际加载 `libexreader.3.41.0.dylib`，SHA-256
  `64fa27c57d88eebd0e348908c3f8831d900363a3220af7a24c80db00ee3f37e0`，
  与同 producer 原兼容安装库逐字相符。产品审计确认动态 SDK 与安装后的命令模块。

| 工件 | ID | 字节 | SHA-256 |
| --- | ---: | ---: | --- |
| 原始接收、原兼容控制与已认证发送包 | 12595851323 | 68,572,246 | `8949f0b81f62e0fe680a5c4639bb5e84f6c7436ed49118fbeedbf2a92045e553` |
| strict summary | 12595856266 | 892 | `e6156a298bcac31ab3491255b33506c484142ae61b061191d81e11b5088c63b9` |

有效期均为 `2027-01-23T10:20:07Z`。ZIP 下载、摘要认证、解包和原始证据解析均在 Actions；
本地仅阅读运行日志与 API 元数据。本节之后的证据提交不改变受测源码。
`android_to_apple_accepted=true`；`apple_to_android_accepted=false`，
`actual_apple_sender_accepted=false`，`bidirectional_interoperability_accepted=false`。

## 独立可选的选择器字节候选

当前失败必须继续保留，不能用删除 NUL、改偏移、改变原件或另选容易通过的 PDF
当作修复。本分支仍固定现有生产树和 wire v2。

下一候选只扩展应用模块，SDK/产品 schema1/旧 wire 不改：为固定页原始选择器增加
显式 anchor v3 与独立 encode/decode/command 入口，默认继续使用原 v2。
v3 的 exact/prefix/suffix 用严格 Base64 与明确字节长度表示；page ID 和其余标识仍为
原有严格 UTF-8。实际 start/end、NUL、空与 NULL 的区别、原件身份及父图均须无损保留。
旧接收器明确拒绝 v3，不能将其当 v2 读取；新候选读旧记录时保留原始 wire/版本。

候选验收须覆盖这个真实 PDF 的点/范围、跨进程原样重开、两端真实生成/接收/FOUND/
复捕获，以及原全部 v1/v2 正反例；另拒绝坏 Base64、长度不符、超额、未知版本与缺父。
原 v2 失败在旧入口继续作为负对照。候选的实现、云端证据与主线采用分开记录，
目前尚未改任何已冻结模块或授予新格式。
