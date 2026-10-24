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
