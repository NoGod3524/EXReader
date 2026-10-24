# 书架整理：有界读取与命令接入

基于已通过产品预集成的交付 `118e628d078a42d918552d6b2797d9aa3a3517eb`，
为原生界面补充独立产品 catalog 的只读接口。SDK 八条受保护路径与冻结 K 相同，
产品 schema1 和同步 wire 不变。

`catalog.h` 新增：

- 子书架／标签／系列的有界双向分页：子书架按父节点及 `(ordinal,id)`，其余按 ID。
- 分组成员有界双向分页：子书架／系列按 `(ordinal,book_key)`，标签按书籍 key。
- 分组及成员精确查找：保留 deleted 依赖状态，供明确恢复及冲突显示；不选择修订 head。
- 已下载过滤、原字节 title／author 子串搜索，复用 1..200 行上限、owner 与回调借用规则。

读取不改变 metadata、历史或 outbox；修改继续使用现有 typed commands。
共享桌面适配层负责完整意图落盘和精确重试，随后由 GTK／Windows 连接原生整理入口。
这部分仍在开发，当前不授予整理 UI 或六平台同步验收。

云端 `reader-desktop-shelf.yml` 保留原 12 项目录与 10 项查询组，新增 15 项组织读取组：
每类 2202 个分组及 2202 本书、父子分类、顺序并列、全部双向遍历、云端／本地过滤、
删除依赖、文字筛选、非法参数与 owner 拒绝、现有索引范围，以及禁止任何写入的 authorizer。
所有构建、夹具生成和测试仅在 Actions。

## 原生接口验收

受测源码 `4bfe09766d6a92445a09d7a66b47fa9eb59ab325`，
[run 40046721924](https://github.com/NoGod3524/EXReader/actions/runs/40046721924)，
attempt1，**3/3 作业成功**。Windows、Linux、macOS 均同次通过原12组、查询10组、
新增组织读取15组；没有跳过、失败或缺项。

| 平台 | 作业 | 工件 | 字节 |
| --- | --- | --- | ---: |
| Linux | `120730038191` | `12540829185` | 496409 |
| Windows | `120730038574` | `12541956025` | 497029 |
| macOS | `120730038421` | `12542090525` | 496841 |

三份工件同 run／source／attempt、未过期；API 的大小和 SHA-256 与上传日志一致。
各报告散列、完整工件 digest 见 [验收记录](validation/reader-organization-native.json)。
只授予原生只读接口，`ui_accepted=false`、`complete_product=false`。

## GTK 原生编辑候选

当前接入书名、作者和收藏，默认书架只增加 Details 入口（Ctrl+E）。弹出的原生表单
显示产品 metadata；旧书在表单可编辑前通过公开 SDK source 重新核验原件，再登记原产品
字段的初始历史。用户 Save 是一条单独的完整 typed 意图及产品事务，Cancel 不提交表单字段。

GTK owner 持有快照；UI 只收到复制字段和操作 token。所有 metadata 操作走提交屏障，
关闭等待结果。提交拒绝时保留完整 pending，界面提供 Retry／Discard uncommitted；
恢复不选择新的 heads，不覆盖并发版本。共同安装的产品 provider 供 catalog、revisions、
commands 与适配层使用；SDK 八条冻结路径保持不变。

候选新增15项实际GTK/X11操作，包括 Unicode／NFC、收藏、取消、提交期间子窗口关闭、真实进程终止后恢复、
完整意图重试、独立原生命令写入后的旧快照拒绝。原UI20、产品5、固定页24、书架14与
保留故障回归均继续执行；共享模块另在同源 Windows/Linux 作业运行29项适配层检查。
本候选尚待本轮云端验收，分类管理界面、Windows 编辑入口及六平台同步仍待接入。
本轮编辑界面夹具为 TXT 原书；保留的 SDK 原件、EPUB 与固定页阅读检查按各自范围登记。

首轮源码 `210403d121d6484a8fff4ea7ffd911efa3163535` 的 run `40048755654`
同源5/5成功，包含实际GTK14项与两平台适配层29项，云端严格汇总 `accepted=true`。
静态复查随后补充子对话框 `delete-event` 屏障和 `destroy` 指针清理，新增持锁期间 WM
关闭的真实操作检查；15项最终候选须以其自身源码完整复验，首轮14项不覆盖这个关闭场景。

后续 `d94848e3`／run `40049360939` 的三个上游成功，GTK 第15项测试失败，严格汇总拒绝。
该驱动使用的 `xdotool windowclose` 直接调用 `XDestroyWindow`，绕过正常 WM 关闭协议，
因此不能用于验证 `delete-event` 屏障；保留失败，驱动改用实际 Alt+F4，生产屏障和断言不变。

最终GTK编辑源码 `19a4bbed98436326264e06bae6470b239bd7201b` 的
[run 40050634471](https://github.com/NoGod3524/EXReader/actions/runs/40050634471)，
attempt1，5/5成功，云端严格 `accepted=true`、`problems=[]`。
GTK实际15项全过，原20/5/24/14及故障回归、Windows原套件、两端适配层29项和前序模块均保留。
四份上游工件未过期，实际ZIP散列／大小由云端汇总实核，API与报告身份再次对照一致；
完整记录见 [GTK编辑验收JSON](validation/reader-gtk-metadata.json)。

随后合入Windows编辑独立交付 `934e01d5`（受测1be8367f/run40050226847/18UI）和
Android原生owner独立交付 `f55735d1`（受测8f7c011a/run40049878764）。
共同候选保留分组读取API和Android canonical/metadata lookup；普通书籍行第10列是deleted，
分组成员第10列是ordinal，合并后分别处理，并在原生组织读取检查验证active book标记。
新的共同源码须重跑Windows18/GTK15和原生模块，独立通过记录不转移为联合验收。
