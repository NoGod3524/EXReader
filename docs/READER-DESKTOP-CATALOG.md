# 桌面产品书库：原生适配器

## 当前交付

受测源码 `cd49a7c3520d7dd6edf799d646ffcb833aca7adb`，分支
`codex/reader-desktop-catalog`，起点为 CPU 基线候选 `220585e8`。
[云端运行 40018932857](https://github.com/NoGod3524/EXReader/actions/runs/40018932857)
attempt 1 三个作业均 success。Windows、Linux、macOS 各执行相同的 12 组原生检查，
各自报告 `accepted=true`、`problems=[]`，实际 SQLite 均为 3.54.0。

这是独立产品 metadata 适配器。八条 SDK 受保护树仍等于
`9854061be331fe603a1822d9b2b36ee357154927`；原产品迁移
`apps/reader/store/001_catalog.sql` 与 `f32bb8aa` 逐字节相同。
没有改变 SDK schema 7、ABI 1 或已冻结的耗时预算。

## 实际行为

- 在独立 EXRP/schema-1 数据库上执行原迁移，拒绝其他应用、非空未登记或未来版本的数据库。
- 用参数绑定在一个事务内登记原件身份和本机 SDK 映射。事务中断回滚产品书籍写入。
- 身份与存储模式冲突时拒绝，不覆盖旧数据；历史重复原件选择最小 SDK ID 及该 ID 的真实模式。
- 重新挂接本机原件保留已有标题、收藏、删除状态、修订和 outbox；移除本机映射保留全球记录。
- 限制为创建连接的宿主 worker，拒绝从其他线程使用或在逐行回调中重入。
- 书架页每次最多 200 条，按 `(sort_title,book_key)` 使用 keyset。续页采用独立 SQL 范围，
  避免可空游标的 OR 条件造成从头扫描。测试从适配器实际执行的 SQL 取查询计划并要求标题索引范围。
- 输入检查 UTF-8、字符长度、格式、散列及字节数；宿主负责提供 NFC `sort_title` 和经公开 SDK 核实的原件身份。

迁移在云端配置阶段嵌入 C 字面量，检查程序逐字节对照仓库原 SQL。
适配器使用独立、按归档 SHA-256 固定的公共 SQLite 3.54.0 依赖，与冻结阅读 SDK
使用相同上游版本和编译限额，不读取 SDK 私有头或链接私有 vendor target。

## 云端检查与工件

| 平台 | 作业 | 检查 | 工件 ID | 字节 | ZIP SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| Windows | 120638126874 | 12/12 | 12529656957 | 80075 | `a230b1b7a55463e3f842cdcf995ffeb843505f221daa4583014d65eaf77f58ef` |
| Linux | 120638127093 | 12/12 | 12528948933 | 80431 | `ac94714a834e2149ace2323453c3e1799b13768735b74bc395ad3ad8f37b19d8` |
| macOS | 120638127189 | 12/12 | 12529292578 | 80172 | `5426d49f5bddc0ff3c7b3807d05ef4dbf43cce0ded5a35bae198c01bf94685d4` |

三份工件的名称、ID、字节、digest 已逐项核对原上传日志与 GitHub API，
均绑定此 run/source、未过期。包含原编译记录、CTest/JUnit、逐组结果、
生成迁移、故障数据库及二进制/源文件身份；没有在本地下载或解析工件。
Linux 同次还执行了原产品 schema 回归。

原生组覆盖：迁移及重开、原外来文件逐字节保留、产品映射事务回滚、
身份/模式拒绝、历史重复模式、旧 metadata/history 保留、本机移除、坏输入、
owner/reentry、真实 writer 锁等待后重试、书架循环拒绝、2,500 条 metadata 的完整有序续页。

## 下一步

Windows/GTK 实际宿主尚未调用这个适配器。本轮没有原件散列、SDK 导入恢复、
桌面 UI、WebDAV 或界面性能验收。

下一步从安装后的公共 SDK 读取原件，以平台原生 SHA-256/NFC 核实全球身份；
把启动补映射和导入发布接到宿主现有 owner worker，再接产品书架分页。
最终消费者必须核 SQLite 的实际链接提供者和编译选项，并复验原宿主流程。
用户原件仍由 SDK 保存，产品 metadata 不复制运行中的 SDK 数据库。
