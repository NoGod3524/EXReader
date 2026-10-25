# Apple 产品阅读记录

固定实现起点 `f5d25b4c71ea39bd22bebea4eedfee16ca178c35`。G03/G04 仅复制共同源码
`ba25961961ae69222bfed4f7a98cb02bb1dc6847` 的已验模块；reading-commands 树
`cf067b8be378d4195817d1106b81f358579e2280`、annotation-view 树
`9d30b6c54f61496010f647695dedd7ea7ab0c7c1`、codec 树
`60127ae75fbac918237b1c8584e0f7ac2e6130a4` 均逐字固定。SDK 保持
`9854061be331fe603a1822d9b2b36ee357154927` / 3.40.0 / ABI1，产品 schema1、wire1、anchor1/2 不变。

## 原生流程

普通阅读页“更多阅读操作”内进入“阅读记录”：保存真实阅读进度、添加点书签、按书分批查看
书签/高亮/批注、编辑正文、删除和查看保留版本。选文面板可把当前实际 UTF-8 范围保存为产品高亮。
技术 selector、CFI 和修订 ID 不作为用户输入字段。

G04 每次返回最多32项、2MiB预算。每个队列调用在同一实际线程打开/使用/关闭原生 history/view；
跨 GCD 调用仅保留 Swift 值和公开纯值 keyset cursor。非 SAFE 记录只显示真实图计数，
不显示正文、head 或位置，也不选择分支。SAFE 删除只显示墓碑。保留历史遍历最多128个节点、
32个可恢复版本、累计2MiB；超过上限明确拒绝，不跳过节点或截断后冒充完整。

产品记录仅提交 G03 与产品修订/outbox；不复制进 SDK notes、不改变当前页。旧 SDK 标注接口和原回归保持。
跳转由用户单独选择：先从第二个 SDK 库实例校验真实原件身份，以公开文档/章节/固定文字快照得到 FOUND；
实际 renderer 候选再独立解析同一 selector，FOUND 后才提交页面。缺失、歧义和 legacy 重复 spine 不按旧偏移兜底。
EPUB v2 同时核对真实 spine 序号和 path；全局 EPUB 与有界章节坐标不混用。

CBZ 使用 SDK 实际提供的非空句柄、空文字快照创建点 selector；不伪造空 selector，也不将宿主限制归因于 SDK。
固定页 ID 与章节 path 按 UTF-8 字节比较：Swift 的规范等价字符串比较不能裁决原件身份。
真实 CBZ 夹具保留 `café.png` / `café.png` 两个规范等价但字节不同的成员，分别公开 capture、
独立 FOUND 和实际 renderer 二次定位；三目标 UI 的漫画示例也使用这份原件。
恢复由用户选择保留版本后独立 FOUND、重新公开 capture，再以 G03 RESTORE 新建版本，当前页面保持不变。
正文编辑提交原观察 head，由 G03 保持原 selector 和 anchor 版本，UI 旧 head 不自动替换为最新 head。

## 私有待完成请求

每个账号目录有独立 `reading-requests`，目录0700、文件0600。线程锁和目录内文件锁覆盖多窗口/多进程。
原请求在产品事务前写同目录私有临时文件、同步文件、原子发布、同步目录，包含稳定 revision/annotation/
bootstrap ID、原件身份、完整观察 heads、原始真实 capture 或空 capture、原操作及正文。

失败或不确定响应保留原请求。重开不自动执行；“重试原请求”沿用同一身份、heads 与 capture，不重捕获，
模块精确重投应为 no-op，包括已 ack 的提交。清理再次核对自身 revision；另一窗口不能清除别人的请求。
“放弃请求”须用户明确确认，已提交版本继续保留。账号或书籍切换不将原请求应用到另一份原件。

## 云端出口与当前状态

`reader-apple-reading-records.yml` 执行冻结 SDK/模块树和路径归属门禁、安装后的实际 Swift 适配器、
19个具名 native 检查，以及 macOS/iPhone/iPad 各7个真实 UI 用例。包含真实进程在私有请求写入后、
产品提交后终止，重开等待显式重试；正常创建、正文编辑、墓碑、保留版本恢复、独立用户跳转和
TXT/有界 EPUB/PDF/CBZ 实际捕获。严格汇总重新下载同次生产者 ZIP，核对大小、散列、有效期、
程序与报告身份；每个实际程序核对安装后 G03/G04、唯一产品 SQLite 和单一动态 SDK。

初始编译诊断仅编译真实 macOS host，固定 `diagnostic_only=true, accepted=false`。
`96811166` / `40142823496` 的真实完整 macOS app 已编译成功；首次 `f581dec8` 诊断失败因命令
漏带现有 Swift 包装文件，已保留。后续预检复用正式出口相同的 installed-package native 消费者，
先核对当前 kill 边界和19项原生行为，再显式启动一轮正式当前源码 full。两轮尚未执行的旧 G03
full 队列 `40142500507` / `40142823497` 已因实现被替代而取消，严格汇总均拒绝；不改写为通过。
UI 实际看到私有请求落盘/产品提交后的原生观测，再由 UI runner 真正终止应用；native 消费者另在
相同实际边界 `_exit` 并重新启动，分别证明首次提交和精确 no-op 重放。
`3f7bcbed` / `40143531917` 的 app 与 native 消费者均编译成功，19项行为检查实际17通过。
宿主 decoder 把 EPUB 的 `part_path` 章节作用域漏回原生 selector，完整 selector 相等断言拒绝；
修复按公开 record 模式恢复该作用域，保持原相等断言。第一次循环因此未到 CBZ，后续 CBZ 输入缺失
不作为 SDK provider 缺陷。新探针逐格式保留 selector/SDK 状态比较，并独立执行全部四格式。
`72f2ca2f` / `40144185965`、`1b4acf2d` / `40144674393`、`9d9a9dc0` / `40145615101`
均实际编译完整 macOS app 并执行安装后 native19/19；后两轮包含真实 Unicode CBZ 双页分别 FOUND。
这些是直接 swiftc 诊断，不授予 Xcode/UI。`9d9a9dc0` 的 Shelf focused `40145621010` SDK/原生通过，
三目标实际 Xcode batch 编译均因 HostSDK 公共 SDK 枚举不可见失败，真实恢复用例尚未开始。
产品桥头先显式引入公开 `exreader.h`；新的预检使用真实 Xcode app/test bundle build-for-testing，
同时保留同一个 native19 消费者，不再以直接整批 swiftc 替代 Xcode 编译检查。
最终受测源码 `19fde18968e03bb4e87d86b0ed650716ac02c9fa` 的正式 run
[`40163099176`](https://github.com/NoGod3524/EXReader/actions/runs/40163099176) 全7作业 success：
native19/19，macOS/iPhone/iPad 各7个真实 UI 用例，严格汇总 `accepted:true`。
同源旧 WP13 [`40163097702`](https://github.com/NoGod3524/EXReader/actions/runs/40163097702)
全8作业 success；三目标各13/13、67步骤，汇总 `problems=[]`，门禁97项通过。
源码、测试、语法检查与工件解析全部在 Actions，本地仅源码/文档/Git。
此处授予 Apple 产品阅读记录；性能、真机和共同源码联合验收仍独立记录。

## 重启接续点

实现已提交并推送到 `codex/reader-apple-reading-records-ui`，完整实现 SHA 为
`1f2f3cbc4605a008558f2bda74ddfcdcd74ffef8`；后续证据提交 `9c8b47412b410fa1882f330e85efa7dbc15a17cc`
只修改本页和验收 JSON。此次重启 checkpoint 同样只修改两份证据文档。

重启后核对：`40147125432` 的真实 Xcode/native 预检 job `121030738895` 已 success；
同源 Shelf focused recovery `40147139532` 的 SDK/native 与 macOS 已 success，iPhone/iPad 失败。
iPad 原05/07通过，原06重开恢复时 `restoring_layout=true`、`issued_restore_revision=-1`，
目标仍在屏幕外；iPhone 原05的 UI query 超时，原06同样未发真实恢复 scroll，原07通过。
保留失败，不授予恢复或 records UI。

`109dd671bf4a39f44433129e28d1a471a8765eb1` 改为订阅实际 Published restore 请求，
在主线程下一轮读取已赋值 revision 并拒绝过期请求，再执行原生 scroll；只有后续真实几何可确认恢复。
新 recovery `40153506967` 三目标已全部 success，原用例断言未放宽。

旧 `f5d25b4c` 的 Shelf full `40140560610` 保留为失败：macOS/iPhone 完整通过，iPad 原02已遍历
2202份原件并原07通过，原06在进程重开后目标仍在屏幕外，真实 native scroll 未发出。
完整 Shelf 后续在 `25eeb6aaccdc50e670f0aaea73631818bc0551f8` 的
[`40161462179`](https://github.com/NoGod3524/EXReader/actions/runs/40161462179) 全7作业 success，
三目标各原7例通过，包含2202份原件正反遍历及原06旋转、后台与真实进程重开恢复。

## 正式运行中保留的失败与修复

- `eff7ab64` / `40154557074` 的 macOS 6/7 通过，通用按钮辅助器在 TextEditor 的
  AXEnabled 属性处拒绝。后续 `986fca5c` / `40155811151` 的扁平编辑页尝试没有解决问题，已回退。
  `9c58e1c4` 改为操作真实 TextView，并保留实际键入、保存正文、删除和恢复断言，macOS7/7通过。
- `40155811151`、`40156690279`、`40158362929` 的 iOS 用例被 Menu 包装层及内部 Button 的
  XCTest hit-point 属性挡住，未进入阅读记录。最终探针核对已标识 Menu 中实际原生 Button 的正尺寸、
  屏幕内 frame，对测量中心发真实触摸；必须看到真实菜单项并完成原后续结果断言。
  `25eeb6aa` / `40159907949` 仅执行原进度/书签/重开一例，三目标真实通过，明确
  `diagnostic_only=true, accepted=false`；同源正式全套 `40160552435` 随后全绿。
- `25eeb6aa` 的旧 WP13 `40161458572` 保留真实 iPhone 12/13 失败：新增高亮操作挤高原选文
  面板，横屏关闭按钮位于屏幕外，原 test11 的 AXScrollToVisible 失败。`19fde189` 仅在 iOS 将原
  选文内容放入原生 ScrollView；macOS 布局保持原样，旧 tap、选文失效与禁用断言均未修改。
  最终同源 WP13 `40163097702` 三目标各13/13通过，iPhone 原 test11 实际通过。

## 证据归属与集成边界

| 源码 | 工作流 / run | 结果 |
| --- | --- | --- |
| `19fde189…` | records `40163099176`、WP13 `40163097702` | 两轮正式 success，含各自严格汇总 |
| `25eeb6aa…` | Nav `40161454864`、Search `40161456543`、Mapping `40161460346`、Shelf full `40161462179` | 各轮 success，证据只归这个旧源码 |

四份旧回归没有转授 `19fde189`。共同分支合入最终布局后，由联合出口在新的完整 SHA 上执行六套并认证。
最终工件 id、大小、完整 SHA-256、有效期和运行历史见
[reader-apple-reading-records.json](validation/reader-apple-reading-records.json)。
后续证据 HEAD 只改本页与该 JSON；SDK3.40分支不混入 SDK3.41 整页主题或记录迁移声明。
