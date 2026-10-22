# H6 平台证据门禁独立核对

2026-10-22。通过 GitHub 连接读取 run、每页 100 项的 jobs/artifacts、完成日志和固定源码；未下载工件或执行本地测试。

## 已通过的固定候选

受测源码 `862be39869b047c71f178ce9e5b168ff5c03b7f9`，分支 `handoff/reading-h6-platform-gate`，
工作流 `.github/workflows/reading-platforms.yml`，run [39858465869](https://github.com/NoGod3524/EXReader/actions/runs/39858465869)，attempt 1，结论 success。
四作业全部同源码成功，完成日志确认如下：

| 平台 / profile | job ID | 安装消费者 | 合成 smoke | 实际程序执行 | 门禁与回归 |
| --- | --- | --- | --- | --- | --- |
| Windows / reading-core | 120102674407 | 3/3 | 9/9 | 必需 5 个全部 executed；benchmark exit 0 | accepted=true、problems=[]；回归 25/25 |
| Windows / reading-library | 120102674860 | 4/4 | 9/9 | 必需 6 个全部 executed；benchmark exit 0 | accepted=true、problems=[]；回归 26/26 |
| macOS / reading-core | 120102674728 | 3/3 | 9/9 | 必需 5 个全部 executed；benchmark exit 0 | accepted=true、problems=[]；回归 25/25 |
| macOS / reading-library | 120102674801 | 4/4 | 9/9 | 必需 6 个全部 executed；benchmark exit 0 | accepted=true、problems=[]；回归 26/26 |

回归数量包含正控和独立 Ninja 程序集合对照，不能全部称为负例数。安装文件合计分别为 Windows core 23,955,586 B、library 27,383,744 B，macOS core 13,781,718 B、library 15,547,919 B；这些数包含文档、头文件和示例，不是宿主运行体积。

四工件均同 run、同受测源码、非空、未过期，元数据 digest 为合法 SHA-256：

| 工件（统一后缀 `39858465869-1`） | ID | 压缩字节 | digest |
| --- | --- | ---: | --- |
| reading-platform-Windows-reading-core | 12459898857 | 8452023 | `sha256:f67e243d45d2b1ef9c14268044c0b698925db3441074b6bedabbb431c7fa119d` |
| reading-platform-Windows-reading-library | 12460273593 | 9666347 | `sha256:2595232f23258cc6f25a06b590aed417792a829ff8e1a8913fc1eec268b1ab4f` |
| reading-platform-macOS-reading-core | 12460398352 | 5734759 | `sha256:cb92666ba4af56266d7bc79751765973cc06b28acdf165b446c066600169948f` |
| reading-platform-macOS-reading-library | 12459699316 | 6540661 | `sha256:8051f42f853643710c8dd3478b8b4b5a350f75bf60666a708bc5e48f984fe89a` |

## 实现审查

审查 [固定工具源码](https://github.com/NoGod3524/EXReader/blob/862be39869b047c71f178ce9e5b168ff5c03b7f9/tools/reading_platform_evidence.py)、
[拒绝回归](https://github.com/NoGod3524/EXReader/blob/862be39869b047c71f178ce9e5b168ff5c03b7f9/tests/check_reading_platform_evidence.py) 与同源码 workflow：

- 必需集合固定为 document、benchmark、core/chapter/convert consumers，library profile 再加 library consumer。缺少、空集、重复、其他路径或未知程序均拒绝。程序须是 consumer Ninja 图中的原生可执行链接输出，并有仓库内编译源。
- snapshot 在执行前记录程序散列；CTest listing/JUnit、九格式 smoke、独立 run 记录共同覆盖全部必需程序。回归另外调用 `ninja -t targets all` 对照集合，避免仅由门禁自己的图解析器证明集合。
- benchmark 已实际调用 `table-fragments-12.epub`、固定字体、`--max-pages 1`；四份日志均 exit 0。这里只证明该程序被系统加载并运行，不授予性能预算或完整翻页结论。
- Windows `dumpbin /dependents` 明确只列 DLL 名称，不再将 `unresolved=[]` 冒充查找验证。加载器结论来自全部必需程序的成功执行；未执行程序不能借已有依赖名称通过。
- Windows 同时核对 SDK 与 consumer 的 MSVC x64、实际 CMake 选择的编译器/归档器/链接器路径在所选工具集内。修正后的 linker banner 要匹配工具集 major/minor 和选定 C/C++ 编译器 build，而不是要求工具集目录补丁号与工具二进制 build 完全相同。8.3/长路径归一化保留两种 CMake 拼写，没有移除路径与版本约束。
- macOS 要求 AppleClang、链接器版本输出，检查非系统依赖路径；两平台依赖工具失败、空输出和不可识别输出均有拒绝回归。

在本包声明的“平台构建、安装消费、程序集合与运行证据”范围内，`862be39` 已有同次云端正例及拒绝回归支持。该工作流仍只在交接分支 push 或 dispatch 运行，未启用默认分支必需检查。静态链接依赖和所有宿主架构仍按源码/构建及其各自验收处理，不由 DLL 名称扫描授予全项目无 WebView 结论。

## 新交付最终状态与实际执行来源

受测源码 `1c06a0e5ae99bf8213521494e4b283a9e93972ee`，run [39859122761](https://github.com/NoGod3524/EXReader/actions/runs/39859122761) 当前 `run_attempt=2, status=completed, conclusion=success`。完整读取 `/attempts/1/jobs?per_page=100`、`/attempts/2/jobs?per_page=100`、artifacts 及四份完成日志。

attempt 2 的 API 列表有四个 job ID，均为 `run_attempt=2`、同受测源码、success。但三个条目保留 attempt 1 的执行时间、日志与工件，只有 Windows library 重新执行。Windows core 的完成日志明确含 `GITHUB_RUN_ATTEMPT: 1`；其余三份原成功工件也均以 `-1` 结尾。API 列表标签不能证明四个作业都重新执行于 attempt 2。

| 平台 / profile | attempt 2 API job ID | 实际执行来源 | 安装消费者 | smoke | 必需程序 | 门禁 / 回归 |
| --- | --- | --- | --- | --- | --- | --- |
| Windows / reading-core | 120106678024 | attempt 1；21:40:19–21:43:20 UTC | 3/3 | 9/9 | 5/5 executed | accepted=true、problems=[]；25/25 |
| Windows / reading-library | 120106623146 | attempt 2；21:44:06–21:47:04 UTC | 4/4 | 9/9 | 6/6 executed | accepted=true、problems=[]；26/26 |
| macOS / reading-core | 120106625223 | attempt 1；21:40:18–21:41:56 UTC | 3/3 | 9/9 | 5/5 executed | accepted=true、problems=[]；25/25 |
| macOS / reading-library | 120106626259 | attempt 1；21:40:18–21:42:13 UTC | 4/4 | 9/9 | 6/6 executed | accepted=true、problems=[]；26/26 |

四份日志逐程序记录 program SHA-256、PE x64／Mach-O arm64 身份、源码路径与散列、实际执行方式及依赖工具输出；benchmark 均真实 exit 0。Windows 编译器 `19.44.35229` x64，macOS Apple clang `17.0.0`。安装总字节与前轮相同，仍不等于宿主运行体积。

成功工件为下列四份，同 run、同 `1c06a0e…`、非空且未过期，API digest 均合法；实际 attempt 按名称与上传日志保留：

| 完整工件名 | ID | 压缩字节 | digest |
| --- | --- | ---: | --- |
| reading-platform-Windows-reading-core-39859122761-1 | 12459809769 | 8451920 | `sha256:ef4a5f8b896408d2daa44e56a5533472b4603b1c5631f08a28da11c4bdbb7528` |
| reading-platform-Windows-reading-library-39859122761-2 | 12460394767 | 9666442 | `sha256:0e97e75432394296efc1d66ac219c178fa61fddab652dfb9563044f87e3cda62` |
| reading-platform-macOS-reading-core-39859122761-1 | 12460313103 | 5734782 | `sha256:e6aa249d42ecc4346f94126c190c96f53b2d8eb48f59bfb148fb09abd419f4e1` |
| reading-platform-macOS-reading-library-39859122761-1 | 12460043836 | 6540510 | `sha256:f835b076d78b8108cdcc95340fb9509d5f89a37087da5de5de9661ae67d9b917` |

run 共五份工件；额外一份 `reading-platform-Windows-reading-library-39859122761-1`，ID `12461530642`，9237 B，digest `sha256:8c5d474caaa68cc8046e5b0487047ab6a942a4b2c4bf1f68384cdabc1bb7d990`，属于失败配置尝试，不能计入成功四份。

最终交付 HEAD `27d95e9dc38d065dcd51a271aa1b019da2a0e9db` 与受测源码的 GitHub compare 只有 `docs/READING-PLATFORMS.md` 一项文档差异，提交带 `[skip ci]`。该文档也明确记录只重跑失败的 Windows library。

可确认 `1c06a0e…` 同源码同 run 的最终四平台/profile 验证通过，各证据的实际执行 attempt 如上。若集成出口要求四项在一个新 attempt 全部重执行，本 run 不满足该附加条件；不能将 API 新 job ID 或 `run_attempt=2` 标签写成“四项整轮复验”。旧 `862be39` / `39858465869` 仍是四项同 attempt 1 全部成功的独立记录。

## 保留失败

- 首轮 `86df54f244bcc5bd3c61e531455abc58b3862670` / run [39857949179](https://github.com/NoGod3524/EXReader/actions/runs/39857949179) 失败：macOS 拒绝回归误要求 benchmark 未执行时同时产生另一条缺记录错误；Windows 将合法的工具集目录版本 `14.44.35207` 与 linker build `14.44.35229.0` 按完整前缀比较。`862be39` 修正判定并整轮重跑通过，旧失败保留。
- 远端分支头随后为 `1c06a0e5ae99bf8213521494e4b283a9e93972ee`，增加 21 行逐程序/工具链日志输出，属于工具代码差异，不是纯文档。`39858465869` 的通过只绑定 `862be39`。
- 新头 run [39859122761](https://github.com/NoGod3524/EXReader/actions/runs/39859122761) attempt 1 的 Windows library，job `120104936355`，在 configure 下载 SQLite 时发生接收失败（curl status 56）；其余三作业成功。该失败保留为失败，不因后续 retry 改写。
- attempt 2 重新执行 Windows library 成功；其余三项复用同源码在 attempt 1 的成功执行，详细来源见上表。全程只读 GitHub，未下载工件或本地重跑。

合入时固定所选受测源码和上述实际 run/attempt 身份。后续合入新 SDK/schema 7 的共同源码还需重新验证，H6 结果不转移到活动中的 R5 实现。
