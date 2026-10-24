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

候选新增14项实际GTK/X11操作，包括 Unicode／NFC、收藏、取消、真实进程终止后恢复、
完整意图重试、独立原生命令写入后的旧快照拒绝。原UI20、产品5、固定页24、书架14与
保留故障回归均继续执行；共享模块另在同源 Windows/Linux 作业运行29项适配层检查。
本候选尚待本轮云端验收，分类管理界面、Windows 编辑入口及六平台同步仍待接入。
