# J22：真实跨操作系统修订与原书往返验收

**可立即独立开工 · P0 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-cross-os-relay`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

新增真正由不同操作系统先后生产/消费的同源码验收：Windows↔Linux、macOS↔Linux，交换四格式实际原件、metadata/组织修订与18类阅读捕获。

依赖只读：公开 SDK、reader_revisions/reading-state/sync/WebDAV API。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

仅交换线上不可变原书与修订字节；禁止拷贝SDK/产品数据库或用发送端报告代替接收端真实SDK回读。

只在Actions以工件中继真实服务目录和传输记录；接收端重新启动原生HTTPS服务并执行其公开原生客户端/SDK。明确这是制品中继跨OS兼容，不冒充实时六设备用户云盘。输入、预期和hash在消费者运行前固定。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `tests/reader_cross_os_relay/**`
- `.github/workflows/reader-cross-os-relay.yml`
- `docs/READER-CROSS-OS-RELAY.md`
- `docs/validation/reader-cross-os-relay.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

发送、接收、返回确认与严格汇总同一source/run/attempt；独立原书SHA、17 FOUND/1 planted ambiguity零误定位、NFC/NFD/俄文/emoji、冲突/待父/墓碑、重试/重开；缺一个方向或身份不符必须拒绝。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

测试包只能写自己的 tests/workflow/docs；不修改共享代码，不借旧run的通过或虚构公开 API，不授予宿主UI或真机。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

