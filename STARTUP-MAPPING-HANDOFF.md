# Windows 首次映射调查

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
