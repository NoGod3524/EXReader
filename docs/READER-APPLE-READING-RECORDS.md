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
目前新增完整套件尚未取得云端结果，验收记录为 `accepted:false`。源码、测试、语法检查与工件解析
全部在 Actions，本地仅源码/文档/Git。性能、真机、跨平台产品联合验收继续单列。
