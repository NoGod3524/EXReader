# RTF + CBZ 隔离组合候选与 F5 v2 结果

受测源码 **`8015c576822d5284dedfea17428ecf1a240befd0`**，分支 `codex/reader-format-combination`。完整第 2 轮 [40244430230/1](https://github.com/NoGod3524/EXReader/actions/runs/40244430230) 于 `2026-10-25T23:40:16Z` 完成，整体 success。完整轮预算 3 轮，已用 2 轮，第 3 轮未启动。

## 同一源码、同一轮结果

| 检查 | Windows | Linux |
| --- | --- | --- |
| 批准 baseline 原 native 全集 | 169/169 | 169/169 |
| 两补丁组合 candidate 原 native 全集 | 169/169 | 169/169 |
| C04 RTF 边界 | 100/100 | 100/100 |
| S13 CBZ 具名观察 | 103/103 | 103/103 |
| 严格 UTF-8 参数向量 | 8/8，另含 5 项 UTF-16 原生检查 | 8/8 |
| 原 v1 + 批准 SDK + 原消费者 | 12/18，真实失败保留 | 14/18，真实失败保留 |
| 原 v1 + 组合候选 + UTF-8 适配 | 17/18，Crowley 旧 query 仍失败 | 17/18，Crowley 旧 query 仍失败 |
| 独立 v2 + 组合候选 + UTF-8 适配 | **18/18** | **18/18** |

每端保留 11 条实际程序与库字节记录、完整原日志、原 JUnit、逐文件原 stdout/stderr/exit/readback，以及安装前缀。两份真实 CBZ 的原生观察在仅移除运行器绝对输入前缀后跨平台完全一致。

v2 仍是原 18 份真实文件，输入、许可和操作预期均未改；相对原 v1 只登记新 dataset_id，以及 Crowley 的真实连续正文 query `EH123 Rhetoric and Composition I`。Windows 两份 FB2 的 Cyrillic query 通过严格宽参数到 UTF-8 入口真实 find、capture、resolve、reopen。

## 严格汇总

strict job `121326920910` 在 Actions 下载并认证本轮 guard、corpus、Windows、Linux 四份原 ZIP 的 digest、字节、有效期及同源码/同 attempt 身份；从实际程序/库字节、原 JUnit、103 项具名记录和每文件原 F5 输出重算结论，不以 producer 的通过标志代替验证。它另外核对 Windows CBZ probe 部署的 DLL 与该端 SDK 安装字节一致。

| 作业 | ID | 终态 |
| --- | --- | --- |
| preflight | 121322898372 | success |
| corpus | 121322946182 | success |
| producer-windows | 121323122490 | success |
| producer-linux | 121323122348 | success |
| strict | 121326920910 | success |

| 工件 | ID | 原 ZIP 字节 | SHA-256 |
| --- | --- | ---: | --- |
| guard | 12618171932 | 3892 | `b084a2433316edb331d3a03c42209d04502881309ca7f0ee8ca672af50aa56d6` |
| corpus | 12617368263 | 8371026 | `375e5095115316c327e382f0bff01d619ada3a1908284148dcd5e2cccce32ab5` |
| windows | 12618916350 | 100077026 | `f361dd6c40397150d65377624f3e7c95214f54579278df8a3ba01d9de6dde93c` |
| linux | 12618691161 | 116239088 | `4f50f61c4694aac40abd24c6626914c1ba4fc64a98b4e26dca64bdd1ee12c3c0` |
| strict result | 12618846664 | 1247 | `4fe7a69354a4eedcfcfb635b1c14a7b9523ded23740f24897c7db5ceb3ba1310` |

Windows/Linux producer 工件分别到 `2026-11-24T23:39:45Z` / `2026-11-24T23:33:38Z`；guard/corpus/strict 到 `2027-01-23T23:21:58Z`。完整 API 身份和汇总原值见 [acceptance.json](acceptance.json)。strict 本身的输出 ZIP digest 由上传日志及只读 API 登记；strict 不会下载它尚未生成的自身输出。

## 候选身份

| 对象 | 身份 |
| --- | --- |
| 批准 SDK | `edddc463c06ed5731195cdb8f06b2df6dff7699e`，3.41.0 / ABI 1 |
| baseline SDK whole tree | `a2539bedd524520bc52727e777bae5d3f6a3cbe0` |
| candidate SDK whole tree | `dd5f4fa912bcaab483524a76988515c731f22702` |
| baseline src tree | `01753c0ada7a8c948a19173b965fbc0f42c1341b` |
| candidate src tree | `001bd8d0baa49ecde6fae82d799bafd0b007030f` |
| v2 manifest LF SHA-256 | `1da605400ab0718e70718e17edc4710ad5fe36c232e1eb705b6f7ede1ecc2b59` |

候选只在批准 SDK 隔离副本的 `src/rtf.c` / `src/cbz.c` 应用固定 C04/S13 补丁。受保护的 SDK、旧 F5、宿主与产品 schema 均未改。补丁来源和 pre/post 字节见 [PLAN.md](PLAN.md)。

## 第 1 轮失败与实际修复

完整第 1 轮 [40240804927/1](https://github.com/NoGod3524/EXReader/actions/runs/40240804927)，源码 `03530b6a4c97275432dffdcab80c39486475645a`，保留 failure。Linux 完整成功；Windows 的两套原 native169 和 RTF100 已过，但 CBZ probe 缺 `exreader.dll`，50 份 fixture 报告均为加载失败 `0xC0000135`，Windows 的 F5 面板尚未执行。

修复补齐与原 S13 工作流一致的安装 DLL 部署。轻量 [40244263135/1](https://github.com/NoGod3524/EXReader/actions/runs/40244263135) 通过：认证第 1 轮两个原 ZIP，另认证 S13 原成功 ZIP 中的同一 Windows probe；无 DLL 时真实 exit `3221225781`，部署原 SDK DLL 后同程序 exit `0`、页数 `4`。该诊断只证明部署根因，最终组合信用全部来自后续第 2 轮完整运行。122 项协议拒绝及双端 argv 检查也在轻量图通过。

## 授予范围与下一步

strict 的真实结果为 `candidate_package_accepted=true`、`f5_v2_accepted=true`、`original_f5_v1_accepted=false`。只授予隔离两补丁候选与独立 18 文件 v2 在 Windows/Linux 的声明范围。

`sdk_adopted=false`、`host_integration_accepted=false`、`complete_product=false`；旧 1710 仍为 `0/1710`。未发 tag/Release，未推批准 SDK 或宿主主线。交 root 审查后，才能另行处理 SDK 候选采用及宿主接入。所有构建、语法、夹具、原件/工件下载解压和校验均在 Actions；本机仅编辑、Git 与只读云端日志/API。
