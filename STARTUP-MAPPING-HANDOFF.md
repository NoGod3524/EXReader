# Windows 首次映射调查

## 后续修复（2026-10-26）

独立分支 `codex/reader-startup-root-cause` 的产品候选经过源码 `e7a79ca79d5e89675e3ef3391abbfd95449a76bf` 验证。下方首次调查的“没有净修改”和拒绝 PERSIST 实验仍作为历史记录，不能代表本节的 WAL 候选。

PERSIST 原始失败已定位：原目录回归的外部 SQLite 连接执行 `CREATE TRIGGER injected_failure` 提交时，返回扩展错误 `SQLITE_IOERR_DELETE`（2570），底层 Windows 错误为 32（共享冲突），见 [40409565846](https://github.com/NoGod3524/EXReader/actions/runs/40409565846)。因此原 PERSIST 候选仍不可接入。

新候选只在 Windows 目录修复发现缺失映射时，且数据库最终路径能解析为本机固定磁盘、当前日志模式为默认 DELETE 时，尽力切换到 SQLite WAL；其他模式、远程或未知卷及切换失败时保留原行为。每本书仍独立提交，连接同步级别 `PRAGMA synchronous` 实测为 FULL（2），没有调低。WAL 模式会持续改变该数据库的日志格式，并可能产生 `-wal` 和 `-shm` 文件；依赖数据库文件复制、备份或外部工具的使用场景应采用 SQLite 一致性快照或同时处理有效日志。尚未在真实 SMB 或断电硬件上验证，现有证据包括进程强制终止而非突然断电。

同一 Windows runner 上六次交替对照，均使用 2202 个真实 SDK 原件和各自验证完整的产品映射：[40411216169](https://github.com/NoGod3524/EXReader/actions/runs/40411216169)。首次修复中位数基线 2639 ms、候选 929 ms；已映射修复中位数基线 35.7 ms、候选 8.7 ms。该计时是插桩的目录修复函数，不是首屏时间。工件 `12693986247`，SHA-256 `63e10c20127f77c8a80ba34f723eb29cc63947cc3251bb19d549830808966ae5`。

完整程序 [40411215984](https://github.com/NoGod3524/EXReader/actions/runs/40411215984)：12 次首次建映射首屏交互 p50/p95 为 1370/1408 ms，已映射启动为 144/167 ms，所有原性能流程通过；准备目录验证本地映射数、不同 SDK ID 数和连接到未删除书目的数均为 2202，完整性和外键检查通过。程序 SHA-256 `44846b16bac6bc2cf8f553ec3f2b6d02265537f93e579392cd4e9d5040e6908d`；工件 `12692238917`，SHA-256 `7594397d74fd83ebc73c7b84386604a9bbae6c7825b87df722787163f616580c`。旧版真实程序的对照见下方，因 runner 不同不作为严格因果比较；[40412067174](https://github.com/NoGod3524/EXReader/actions/runs/40412067174) 校验了两次原始工件摘要。

[40411215820](https://github.com/NoGod3524/EXReader/actions/runs/40411215820) 通过原目录、取消、SDK 写入后中断和目录事务中断恢复测试，新增测试也在已提交映射仍保存在非空 WAL 中时强制终止进程，重启后确认映射、原件和数据库完整性。工件 `12694026282`，SHA-256 `ddd1a857a6ec3320cb181af40641b46f616463f464dd0603eea18aca38fb135e`。[40411216177](https://github.com/NoGod3524/EXReader/actions/runs/40411216177) 通过完整 Windows wave-3 原回归，工件 `12693466902`，SHA-256 `0838eabde4204393919a11b9b7b7a62bdbf15219a51d9506338c5fc3e8da4b5b`。运行 `40410703817` 因同分支并发队列被取消，未作为验证结果。

可供选择性接入的产品差异仅涉及 `apps/reader/store/native/catalog.c`、`apps/reader/store/native/catalog.h` 和 `apps/reader/desktop/catalog_sdk.c`，不涉及 Windows 分组/书架界面。请以 `39625ec7c7de7731016199a460ba09c315dadebf` 对 `e7a79ca79d5e89675e3ef3391abbfd95449a76bf` 的这三个路径的差异为准；本分支其余文件为测量及测试。

## 首次调查（历史）

基准产品源码为 `39625ec7c7de7731016199a460ba09c315dadebf`。当前分支 `codex/reader-startup-mapping` 与该基准相比仅增加 Actions 测量和测试文件，产品代码没有净修改。不要接入实验分支 `codex/reader-startup-rejected-candidate` 的产品代码。

2202 个真实 SDK 原件、产品目录修复函数的分段采样显示，首次修复执行 2202 次独立提交；在一次运行中总修复约 4.0 秒，其中提交累计约 2.3–2.7 秒，全部 SQL 累计约 3.3–3.4 秒。已映射修复约 38–39 毫秒。SQLite 语句计时具有毫秒粒度，采样带有插桩开销。各次运行的机器性能不同，不宜将跨运行差值直接视为因果收益。

真实 Windows 产品的每组 12 次进程启动，首屏可交互时间如下，冷启动指每次使用已种入 SDK 原件但没有产品目录的配置，暖启动复用已准备的配置：

| 源码 | 首次建映射 p50 / p95 | 已映射启动 p50 / p95 | 结果 |
| --- | --- | --- | --- |
| `03918ef2ddcc6b214f9c8e18c44de457b494ec42`，产品代码与基准相同 | 4636 / 5005 ms | 173 / 189 ms | 原流程通过 |
| `cb430b9623069c9b9be46c2cdd069aa43eb793f4`，被拒绝的 PERSIST 实验 | 3685 / 3827 ms | 200 / 209 ms | 目录回归失败，不可接入 |

两个产品性能运行分别使用不同 GitHub runner，不能将其差值作为严格的同机因果对照。实验前在同一 runner 对目录修复代码的配对试验中，PERSIST 首次修复每组约缩短 0.6–0.8 秒，但对已映射目录也启用时重复修复变慢。候选在缺失映射时才切换模式，不改变逐本提交；原有 `desktop-public-sdk-catalog` 测试在外部连接写入时出现 `SQL: disk I/O error`，未能进入进程中断检查。撤回后，同一检查与 SDK 写入后和目录事务中两次强制终止、重启恢复检查均通过。错误出现在外部连接写入阶段，但具体失败 SQL 和底层 SQLite 扩展错误码尚未捕获，不能将更细的触发机制视为已证明。

性能流程校验了准备目录中 2202 个书名和原件大小，但其上传工件未包含准备目录数据库，无法从这两个实际 UI 运行的工件独立复核 2202 条本地映射及联接。独立分段测试对每次目录修复后检查了 2202 条映射、2202 个不同 SDK ID、2202 条指向未删除书目的联接，以及 `integrity_check`。后续如需声称真实 UI 运行的完整映射已被核对，应在同一 UI 运行中上传准备目录数据库或在运行中记录上述查询结果，并绑定程序和源码身份。

证据：

- 基准产品性能 [40406056620](https://github.com/NoGod3524/EXReader/actions/runs/40406056620)，工件 `12691432279`，SHA-256 `e5ce80f6af04634d86430ef0158975bed88d0f3c055cb671c1da3b39ec9b3a0a`，程序 SHA-256 `0afd438efd3ba4feeb718ab410ef4162afa4aa0e8e97bf0d25ca3d30a41d66d8`。
- 被拒绝产品性能 [40407618025](https://github.com/NoGod3524/EXReader/actions/runs/40407618025)，工件 `12692027012`，SHA-256 `037f0422fece7109cca07c7a1275ad85438a52d5f32ed7c72747ddf70e7ca211`，程序 SHA-256 `9d208d2b13f619a2230e2615920714a7cfbce1b9857fb35e1f36f19638f19067`。测试失败被保留，并在不删减测试的情况下继续采样，最终运行仍失败。
- [Actions 内工件校验和前后摘要 40408533687](https://github.com/NoGod3524/EXReader/actions/runs/40408533687)。
- [同机 PERSIST 对照 40406008118](https://github.com/NoGod3524/EXReader/actions/runs/40406008118)；[候选目录回归失败 40406810014](https://github.com/NoGod3524/EXReader/actions/runs/40406810014)，失败工件 `12691263429`，SHA-256 `7dc7f77f45897b8962fc3b95c8f6432e514f2fdc7f4a5811293af54665f3850a`。
- [撤回后原目录与中断恢复检查 40407343947](https://github.com/NoGod3524/EXReader/actions/runs/40407343947)，工件 `12692125170`，SHA-256 `bd8be2b1c3f3f45c1e8fc06ea03522ba9e3fae28bcd2e4115b25a167a8b2311a`；[撤回后完整 Windows wave-3 回归 40407343755](https://github.com/NoGod3524/EXReader/actions/runs/40407343755)。
- 初版采样失败 [40405067923](https://github.com/NoGod3524/EXReader/actions/runs/40405067923) 的 SQL 文件名筛选错误；[40405528976](https://github.com/NoGod3524/EXReader/actions/runs/40405528976) 的有效分段数据保留，但环境信息采集命令失败。不能把第一轮空 SQL 计数视为测量值。
