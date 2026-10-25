# Windows raw3 宿主候选

当前阶段只完成源码组合，宿主 raw3 尚未实现，未授予运行或互通验收。

普通 merge 将 Windows 简洁版封存 `f355525b74ae261db536c56200e46643919ef323`
与已通过的 raw selector/伴随模块 `56793e7c` 组合为
`3561c9a9a2c1d209c66931c080e5f0267d0fe653`。
Windows 实际 owner、默认界面与原回归保持简洁版原件，七个可选 raw 模块保持各自交付原件。
SDK 仍为批准的3.41候选 `edddc463c06ed5731195cdb8f06b2df6dff7699e`。
源码前置检查通过也不代表宿主支持了 anchor3。

第一处实际接入缺口是桌面metadata包原先只能寻找commands0.1。
现增加默认关闭的raw0.2配置，显式 `reader_metadata_open_raw_v3` 打开raw revisions，
book/group/membership及heads/get/identity均使用对应raw API；旧配置仍为0.1。
raw包的旧open入口拒绝且不创建数据库，安装配置拒绝混用legacy/raw依赖。
正在Windows/Linux分别构建安装两配置，再原样复用全部29项metadata消费者检查，
包括真实进程终止、私有pending重放、错误线程与单一产品SQLite来源。
这些结果只覆盖metadata包，不替代实际Windows宿主、网络或记录验收。

后续实现必须覆盖实际宿主的以下入口：

| 入口 | 需要完成 |
| --- | --- |
| `windows_records_owner.cpp` | 显式 raw store/codec/commands/view；固定页新捕获使用3，源1/2恢复保留原版本 |
| `windows_records.inc` | SDK公开捕获与独立FOUND；NULL不可跳转/编辑，显式字节长度与空值保留 |
| 本地 pending | 旧EXRRD001始终writer2；新版本显式writer/source，原请求不迁移、不改ID/父图 |
| `windows_accounts.inc`、`windows_accounts_ui.inc` | 实际会话、收发、投影走匹配raw家族；TLS、256分片、原件与wire身份验证 |
| metadata/目录与导入 | 审查全部revision/command调用者，不能仅替换记录owner而遗漏实际宿主入口 |
| 安装与构建 | 默认OFF；七个raw家族、单一产品SQLite和单一批准SDK的真实安装来源核对 |
| 原有功能 | 同轮完整默认OFF/F3/atomic13与简洁UI回归全部保留 |
| 新证据 | 同一8845B NUL PDF点/非空范围，编辑/删除/恢复、真实终止与重开，真实Mac原件/父图/NULL网络接收 |

此分支不修改旧3.40冻结版、产品schema1或旧wire，也不作为共同25bc运行的替代项。
