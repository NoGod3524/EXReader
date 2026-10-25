# Windows raw3 宿主候选

桌面metadata的可选raw配置已完成独立验收；Windows实际记录/同步宿主raw3尚未实现，未授予宿主或互通验收。

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
Windows/Linux已分别构建安装两配置，再原样复用全部29项metadata消费者检查，
包括真实进程终止、私有pending重放、错误线程与单一产品SQLite来源。
这些结果只覆盖metadata包，不替代实际Windows宿主、网络或记录验收。

实际宿主接入现已写入独立默认OFF raw选项、所有账号/记录/metadata入口及EXRRD002私有native capture。
旧EXRRD001保持writer2/source0，不迁移；新请求显式writer/source，restore必须相同。
真实READ/RESTORE/NOTE_TEXT只接受明确支持parser，NULL不导航/编辑/进入恢复列表，DELETE只传mode。
source编译检查不授运行；实际SDK/安装包/Win32完整配置编译与原消费者正在新增验证。
批量整理还依赖metadata0.1，现增加同样默认OFF的bulk0.2显式open配置，避免raw宿主丢失该原有功能；
原bulk实现和全部原检查分别在legacy/raw配置运行后才授予该包结果。

## Metadata独立验收

受测源码 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，
[run40209325599](https://github.com/NoGod3524/EXReader/actions/runs/40209325599)，attempt1，四作业全success。
Windows/Linux分别执行legacy/raw两配置各29项原检查、真实C/C++消费者及显式open验证，两个混配configure均拒绝。
严格汇总实际下载本轮三个原ZIP，核对source/run/attempt、字节/digest/有效期，
两平台每配置的29项完整名字，以及四个真实程序SHA-256（包括原消费者报告自己的程序SHA）。

| 工件 | ID | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Windows | 12604173715 | 22463059 | `5e9057311636460c2c38463bcb59ab83042e94be6402f2a108c70029bc357d03` |
| Linux | 12604774056 | 18344581 | `c765225c86e83cf1f7b31028e487456086a81138d4a52980f294f24f18c06514` |
| source | 12604133762 | 473 | `a7b31592635e86121026845fcfd4e1afb6872e3367e2e4d9093967b35f0407a6` |
| summary | 12604303499 | 710 | `56274c57e5df447c3d8ff43513866dd864d05743199a76782ee5e342fbc8e896` |

有效期均到 `2027-01-23T15:56:48Z`。作业ID：source121216980957、Linux121217017638、
Windows121217017686、strict121217386170。
首轮 `f8b4ea7d` / `40208744954` 两平台已过；新增汇总的 `7f678011` / `40209259006`
因漏计原检查中动态命名的两个真实kill检查而拒绝。修正仅汇总契约，模块未改，失败保留。

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

## 断网期间的待验收改动

Windows host 工作流已接入实际 `windows_records_owner.cpp` 消费者，分别链接安装后的
legacy/raw 模块；同轮覆盖真实 NUL PDF 捕获、独立重开，以及提交前/提交后由外部驱动
终止真实进程后的重试。旧 pending 由 legacy 可执行程序实际生成，再交 raw 程序接续。
驱动核对标记 PID、落盘 pending 的长度和 SHA-256，并在终止后及跨配置拒绝写入后核对原字节。
报告必须对应本轮源码、实际 owner 源码、SDK 3.41.0 及实际可执行程序散列。

这些改动尚未运行；当前不授予 owner 恢复或宿主运行结果。首次完整 host 运行
`40214712302` 在源码检查阶段因 Windows 默认 cp1252 解码失败；现已显式使用 UTF-8，
原失败保留，修复仍待云端验证。Claude 三个任务与 DeepSeek 十二个任务按用户断网请求暂停，
须在用户确认恢复后续接。
