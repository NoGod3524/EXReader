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

## 公开 SDK 桥接与 GTK 后继候选

`apps/reader/desktop` 从安装后的公开 SDK 读取原件，在现有宿主 worker 上以
64 KiB 分块计算平台 SHA-256，用平台 NFC 规范化排序标题。原件仍只由 SDK 保存。
EPUB 模式来自公开 `epub_info_get`，不根据扩展名猜测旧式/章节模式。
目录写入失败不回滚已发布的 SDK 书籍；启动修复重用一次公开 `books()` 数组。
取消在每本书发布前后检查；在途 SQL 事务可完成并保留提交行，已有 writer 等待上限为 5 秒。

首轮源码 `b059d9d451e26ffcb28df708386be49a3dccac51`，
[run 40022079594](https://github.com/NoGod3524/EXReader/actions/runs/40022079594)
Windows/Linux 两作业通过：各 8 组公开 SDK 检查、原 12 组 catalog 检查，
并在 SDK 提交后未映射、产品事务已插书但未插映射两处杀死真实进程，在新进程恢复。
两份原件已按上传日志与 API 核对：

| 平台 | 工件 ID | 字节 | ZIP SHA-256 |
| --- | --- | ---: | --- |
| Linux | 12530782947 | 231257 | `1ea44d6cab59dd76da18a5a9f664494b86e27da90fd8509ee1c2df14600e8a94` |
| Windows | 12531860201 | 688092 | `1766e382599d0d6d086463cfc78dcf95526331617513f0b1f8c4b440c07c0161` |

首轮的跨块夹具全为同一字符，Linux map 检查也仅检查符号存在；这两处证据不足已在后继收紧。
后继使用随偏移变化的数据独立重算 SHA、固定全部具名检查，
以 GNU linker 的 definition trace 或 MSVC map 精确符号行确认实际 archive/object。
第 9 组公开 SDK 检查还在 COMMIT 时触发取消，要求保留提交且返回 CANCELLED。

源码 `5da02c64fb60cc9afe19cfdd6390d412718fe1ea` 的
[run 40022745042](https://github.com/NoGod3524/EXReader/actions/runs/40022745042)
两作业通过上述 9+12+2 检查；两平台实际使用产品公开 SQLite archive，
版本/source ID 和编译限额一致。Linux 实际 GTK 宿主还执行了原 20 项 UI 操作及 3 项目录检查。
该轮产品测试复用了原 UI 目录且未覆盖拒绝实例的正常关闭，保留原结果，
不能据此授予封存证据和跨实例设置保护。

GTK 接受点 `6a22858cf98ea55d2bed079f651cbf96d462412c`，
[run 40023076532](https://github.com/NoGod3524/EXReader/actions/runs/40023076532)
attempt 1 两作业均 success，9+12+2 检查在 Windows/Linux 各自同次通过。
Linux 原 20 项 UI 与新增 5 项产品检查同次通过，两个报告的原 UI 报告 SHA 完全一致。
Windows job `120652304263`、Linux job `120652303918` 的原日志确认上述计数，
GNU/MSVC 均确认 SQLite 来自 `reader_catalog_sqlite` 的 `sqlite3.c` 对象。
两份工件名称、ID、大小、digest 均与各自原 upload 日志/API/source 对齐，未过期：

| 平台 | 工件 ID | 字节 | ZIP SHA-256 |
| --- | --- | ---: | --- |
| Linux | 12531806837 | 371481 | `c1bb24f8758273de05758c73150b43f737c0065f77b73f61cd480162fb1e4ce2` |
| Windows | 12532135764 | 688874 | `1fe1dc72a22ed3ae30191548bff999091700afca6117ba8cce2993eb002444b1` |

GTK 在原 worker、最终导入补偿之后补映射；本地 profile 使用生命周期文件锁。
拒绝实例在成功打开前不保存 profile 设置。新增测试正常关闭第二实例，
在第一实例关闭前逐字节核对设置，再重启第一实例核对阅读恢复。
产品测试使用已正常关闭的 profile 副本及独立证据目录，原 20 项 UI 原件保持封存。
新增 5 项具名结果：启动补映射、保留用户 metadata、第二实例拒绝且不干扰原实例、
拒绝实例正常关闭不覆盖设置、第一实例再正常重启保留当前书。

## Windows 实际宿主与最终双平台复验

受测源码 `5d97e5a08f938b7807d8201d3cb26c26033671c9`，
[run 40029732623](https://github.com/NoGod3524/EXReader/actions/runs/40029732623)
attempt 1 的 Windows/Linux 两作业均 success。两平台同次各通过公开 SDK 9 组、
原生 catalog 12 组、两处真实进程中断恢复；Linux 同次保留原 20 项 GTK UI 与新增 5 项。

Windows job `120674720408` 同次结果：

- 原 26 项原生自检通过。
- 54 项证据正反例通过，覆盖原有日志/来源规则及新增显式 static 来源约束；默认 shared 模式拒绝静态包。
- 原固定 158 项 UI 操作全过、失败 0、8 张具名截图齐备；原三个脚本未改。
- 实际产品目录 10 项通过：公开原件身份/字节/模式/本机 ID，取消和过期导入不落全局或本机记录，
  删除仅移除本机映射并保留全局 metadata，启动补映射及保留用户标题，
  注入目录写失败后原书仍能恢复阅读且待恢复提示可见，下一真实进程自动修复，
  同 profile 换 SDK 及同 SDK 换 profile 两种拒绝，不改设置或创建其他 SDK，原实例正常重启保留位置。

Windows 复用原任务线程；每次产品任务在同一线程内 `open → 操作 → close`，不跨任务持有 catalog。
attach 位于 UI 最终接受、所有取消补偿及 fallback title 更新之后。自动打开等 attach 完成；
删除先成功移除本机映射，再删除 SDK 原件，SDK 删除失败可由 repair 恢复映射。
已提交的删除不因晚到取消而伪报为未删除。元数据任务不清当前页和选区。
profile 与 SDK library 分别持有生命周期独占文件锁，两把锁均在加载或保存设置之前取得。
目录失败及任务启动失败显示待恢复；恢复提示不会被后继打开成功覆盖。

产品使用安装后的 **reading-library 静态 SDK**。`exr_core` 是接口目标；实际
`exr_version` 来源为 `exr_base/core.c.obj`，`exr_library_open` 来源为
`exr_library/library.c.obj`，逐项固定安装归档 SHA，实际 `dumpbin /DEPENDENTS`
拒绝兼容 SDK DLL 和浏览器 runtime。原 shared 验收默认仍要求其原 DLL，不接受静态包替代。
静态模式须显式给出 map，且默认模式、错误 linkage、错误 provider 都会被拒绝。
Windows 原 158 项中的删除驱动改为等待真实异步结果后仍验证书籍已消失，没有删除该断言。

| 平台 | 作业 | 工件 ID | 字节 | ZIP SHA-256 |
| --- | --- | --- | ---: | --- |
| Linux | 120674719912 | 12533019836 | 371503 | `01ffdddff7e0dc1bd63f22172c4d10dd242e6425c435386d4041b801c3f431be` |
| Windows | 120674720408 | 12534770764 | 36098338 | `9fd54c03ab543319235ee053e4070db2f4685b122a761ec2f0300c879c040627` |

两份工件的名称/ID/字节/digest/source 与原上传日志和 API 逐项一致，未过期，
有效期至 2027-01-21。Windows 工件含静态程序包、原始自检、54 拒绝记录、
158 操作/截图、独立产品恢复与双锁证据、map 与原构建日志。
原 158 操作封存目录不被产品检查修改；产品检查仅使用已关闭 profile 的副本。
归档字节不是单个可执行文件大小，也不是安装大小或内存峰值。

保留失败与中间证据：`f28e1763` /
[40028878816](https://github.com/NoGod3524/EXReader/actions/runs/40028878816)
编译和 26 自检成功，但新增校验把接口 `exr_core` 误当实体归档，严格拒绝，158 UI 未执行；
已按冻结 SDK 导出结构修为 `exr_base`。`571788c5` /
[40029299201](https://github.com/NoGod3524/EXReader/actions/runs/40029299201)
Windows 整套曾通过，之后审查收紧 owner 就绪观测，并补任务启动失败的 pending 提示；
最终只按上述 `5d97e5a0` 同次结果授予声明范围。

## 后续范围

[Draft PR10](https://github.com/NoGod3524/EXReader/pull/10) 尚未合并。
最终源码的默认必过门禁是独立 run `40029737987`，需另行等待其全部 17 作业和严格汇总，
不能用上述两作业产品验收替代。

Windows/GTK 的显示书架仍使用 SDK 全量 `books()` 数组，尚未接有界产品分页。
GTK 尚未接 PDF/CBZ 固定页界面；本轮实际 GTK UI 仅授 EPUB/TXT 原声明范围。
没有 WebDAV、真实设备或界面性能预算验收。后续推进桌面固定页及产品书架，
WebDAV 来源由独立包处理。用户原件仍由 SDK 保存，不复制运行中的 SDK 数据库。
