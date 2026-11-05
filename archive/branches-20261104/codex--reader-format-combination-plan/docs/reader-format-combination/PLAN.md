# RTF + CBZ 隔离组合候选与 F5 v2 验收方案

状态：**仅方案，待 root 审阅；未实现消费者适配、未建立新清单、未启动组合完整 CI。**

目标是在批准 SDK 的隔离副本同时应用两份已登记补丁，以新版本 F5 清单和 UTF-8 参数适配后的原消费者，对原 18 份真实文件做 Windows/Linux 同源验收。冻结 SDK、原 F5、原失败记录和旧 1710 目标不变。

## 1. 固定来源

| 对象 | 固定来源 | 字节/身份约束 |
| --- | --- | --- |
| 方案/未来候选包起点 | `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8` | 已含批准 SDK；不使用移动分支作为基线 |
| 批准 SDK | `edddc463c06ed5731195cdb8f06b2df6dff7699e`，3.41.0 / ABI 1 | 每轮另 checkout 到隔离目录；头、版本、ABI、原测试不改 |
| C04 RTF 补丁 | 封存 `4ba25590c71e9be2de29b72c64348d5dcbc0fba1` 的 `candidates/reader-next-c04/rtf-root-tail-padding.patch` | Git blob `c9fd516cb64b9c9a8855597fcac232b65830e2a6`；SHA-256 `2542b50eb2ae0d814b97670226ba704799fed44d347f60003d44982ef45a21fd` |
| C04 回归入口 | 完整受测 `bfc6447798d533c4d5d5fe7ca02e9a54fc928999` 的 `tests/reader_next_c04/` | `test_rtf_real_boundary.c` blob `a76d3ec1b1de1c0b16e09e36dd01ccbcb7eb8a78`；CMake blob `3bc0c7c89d8591187732a2bca1d8244853c3bf75`；run `40234424624/1` 双 OS 169 原回归和 100 边界过，但旧 F5 Crowley 查询失败保留 |
| S13 CBZ 补丁 | 封存 `15e652a998420f768dc5e580d8efd33553386376` 的 `candidates/reader-next-s13/s13-cbz-leading-slash.patch` | Git blob `a06005aeaeaf1c8ae0be200b22a9919667387f98`；SHA-256 `8320206c0efafe398cab0e63d2d59869e83292a32a56a33c53a894e5fa3ab78a` |
| S13 回归入口 | 受测 `313ebbb4f8e73ba42eb3bbe2b04b292f854886b4` 的 `tests/reader_next_s13/` | probe blob `6e4c90e5e4319f2efdf38ef1f8af732f05eaab97`；run.py blob `e1bf837affa4da55ebd66c71056184e4aac84f1a`；run `40236345116/1` 双 OS 各 baseline/candidate 169 + 103 具名观察全过 |
| C05 UTF-8 参数诊断 | 受测 `1659f83491985baa26b609f287a02a01744bc6b2`，封存 `61176eddd9af103a14e6b29325d5874c43322c63` | `candidates/reader-next-c05/probe.c` blob `7a92a6af40637d9a6f059ae24e086188a69f4a47`；CMake blob `b42c4aa1bb3a858640914e20a4ff97d45f751a2e`；run `40227530028/1` |
| 原 F5 | `278d63691a4c73e7aa932d71a40a5938c5427514` | 原 manifest/consumer/runner/许可全部固定取自该提交，不改原文件 |
| 原 manifest | `tests/reader_real_corpus/manifest.json` | Git blob `72841cbae68031c106125b489ec58d48e4232f02`；LF SHA-256 `be300d9a54329ab227ac7060bc39e0117de722ae3c60d6c0d998418eba994bf6`；旧 CRLF 记录 `2651b03dc9df0f8605b0da561518cc3138cd072ac61d113ea831d4f77c6d7c69` 作为历史形式保留 |
| 原完整 F5 消费者 | `tests/reader_real_corpus/consumer.c` | Git blob `0228e2f76aa56189285bc33706d376281f588e14`；LF SHA-256 `f2b5d06d1fb1450c74317b537164ca97b60d7826806175066b597335d342cf96` |
| 原消费者构建入口 | `tests/reader_real_corpus/CMakeLists.txt` | Git blob `b6a37a3e696c50846c85e8dd9124cdccb0ba5551`；LF SHA-256 `545147fa67c104ff6ccccb8a7419e17963c729639efdf759be777fbe11001288` |

所有新适配文件、组合 SDK tree、程序及最终 v2 manifest 的 SHA-256 都由未来 Actions 生成和认证，现在不预填不存在的结果。

## 2. 候选树合同

1. 从批准 SDK 建 `sdk-base` 与 `sdk-combined` 两个隔离副本。只在后者先应用 C04、再应用 S13 补丁；原 `src/`、`include/`、旧冻结记录和原测试不改。
2. 补丁触及集合必须恰为 `src/rtf.c`、`src/cbz.c`，其他受保护路径全部与批准 SDK 相同。记录两补丁原字节和 SHA、pre/post 文件 SHA、SDK whole tree 与 `src` tree，不能混用 tree 名称。
3. RTF pre/post SHA 应分别为 `14a1537048e7e8bd412976c513d35b693672ed9a05afc09436773076f90c32d6` / `ea3fc050cc4ff2383fa97727e15568754cf9aa8ef12007e1e06311ed2ee56662`。
4. CBZ pre/post SHA 应分别为 `85f90ad69432a2a8d5979844694fa96715bdb2ef7186d276e374a684eb0d4d52` / `49ef7cb5f7160ceaa471fbfdeb194638a5cbbcca5fb9d44d3199e857f565c49d`。
5. 可在轻量云端协议检查中交换两补丁应用顺序，要求生成同一 tree；不在本机 apply/check 或运行验证。

RTF 保留值 listid 的接受仍明确属于只读兼容扩展；CBZ 只读去除一个前导 `/` 用于校验/分类，原页 ID 及所有路径拒绝、碰撞和限额仍保留。组合成功不表示这些补丁已成为批准 SDK。

## 3. 新版本 F5 清单

另建 `tests/reader_format_candidate/manifest-v2.json`，保持 `schema:1`，以新 `dataset_id:reader-real-corpus-v2` 登记版本。root guard 用原 F5 manifest 做完整深比较，只允许：

- 顶层 dataset_id 的版本登记。
- `rtf-crowley-policy.query` 从 `Policy and Procedure TTR` 改为 `EH123 Rhetoric and Composition I`。

18 个 id、path、格式、顺序、URL、字节、SHA-256、作者、出版信息、许可依据、pending、选择政策及每一项操作预期完全不变。功能性修正只有这一个 query；不存在改成 expected rejection、删除文件、替换输入或放宽操作预期。

新查询来自固定 Crowley 原件经公开 SDK 导出的真实连续正文首句，当前 UTF-8 范围 `[0,32)`。来源为 C04 诊断 `40235597650/1`：原件 63797 B，SHA `de6126e84aed9fa4204f4f7e84b1da6bedf4ef647479caa6a39befd40e9c5656`；完整正文 9215 B，SHA `3335a98106684c882c5f5737db2e6d8bd13e7bb8631ecf9cbbde9ac9c18dadef`；旧查询在精确、大小写/空白折叠后都不存在。诊断原 ZIP 已由 `40236000909` 在 Actions 认证。

新 query 的 find、anchor capture/resolve/reopen 必须在 v2 的新运行重新通过，不能把旧诊断或文本存在当作已经授予。v1 manifest 字节、旧失败与 `accepted:false` 继续保留；1710 仍为 `0/1710`，v2 只报告这 18 份独立真实语料。

原 `run_acceptance.py.validate_manifest` 硬钉 dataset_id=v1，不能直接宣称原 runner 已支持 v2。新增薄 v2 runner：先用未改旧校验验证原 manifest，再对 v2 做上述完整深比较；复用未改的下载、许可收集、`run_one` 和 `compare_expectations` 函数。新 summary 明确记录 dataset_id=v2 与实际 v2 SHA，不改旧校验函数，也不把 v2 伪装成 v1。

## 4. 消费者修正边界

C05 交付的是 FB2 专项 probe，不是已经通过全部九格式的 F5 替代消费者。新适配只复用它实际验证过的 Windows `CommandLineToArgvW` / `WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS)` 转换路径、来源和构建要求；必须给新 F5 适配另立身份和验收。

建议保留原 `consumer.c` 原字节，用很小的 C entry wrapper 将原 main 重命名后调用：Windows 从宽命令行转换参数为严格 UTF-8，保留空参数；POSIX 原 argv 直接传入。原 16 项 F5 操作、SDK 调用、查找、锚点、绘制和结果计算都不改。适配单独登记源代码/预处理来源和 SHA，安装后消费者只链接公开 `EXReader::exreader`；Windows 保留 `/utf-8` 并链接所需系统库。

Windows 要另测 ASCII、空 query、Cyrillic 两个真实 query、非 BMP、NFC/NFD、带空格参数及无效 UTF-16 的干净拒绝，记录进入原 F5 main 的 query UTF-8 hex 与清单字节精确相同。C05 原 raw ANSI 对照保留，不能将 `/utf-8` 编译开关当作 Windows argv 已是 UTF-8。所有文件/输出路径明确为绝对路径，避免 C04 发现的 corpus 路径二次拼接。

## 5. 一轮同源完整 Actions 图

`guard + corpus-pin -> Windows / Linux -> strict`。所有 job 使用同一具体 source SHA、run、attempt；两平台 fail-fast=false，失败和旧 attempt 全留。

### guard 与 corpus-pin

- 认证上表来源和完整原 F5 文件身份；只在独占候选/测试/文档/新 workflow 路径新增内容，禁止提交对冻结 SDK、宿主、产品 schema、旧 F5 或旧 workflows 的修改。
- 在 Actions 下载原 18 份文件及许可证据，按旧字节/散列全验，上传本轮 corpus 原 ZIP。两平台必须认证并消费该同源工件，不借旧 run 的语料工件授予新同源信用。
- 先做纯协议拒绝回归：清单多改一项预期/字节/许可/文件、漏文件、重复记录、补丁多触一处、伪 program hash、缺失/跨轮 artifact、坏 ZIP 原始成员路径，均必须拒绝。Windows 使用 S13 已验证的 `ZipInfo.orig_filename` 校验，防库提前规范化反斜杠掩盖坏路径。

### 每个平台

同一工具链和相同构建选项分别构建/安装 approved baseline 与 combined candidate，版本/ABI 不改，记录完整选项和依赖。每个平台只构建这两套 SDK，所有安装后消费者共享对应前缀。

1. **原 native 全集**：baseline 与 combined 各运行原 169 项，核所有名称集合、JUnit 与成功状态，不接受双边相同失败、少跑或过滤掉格式测试。
2. **既有边界**：C04 100 项候选边界和两真实 RTF 的公开状态对照；S13 原 103 项具名观察、真实 CBZ、路径/归一化碰撞/限额/取消与 ZIP 拒绝回归。复用固定 probe、夹具与检查函数；组合新 guard 允许恰好两处 patch，不改旧单补丁 guard 让它错误声称单文件不变。
3. **历史对照**：approved baseline + 原 v1/原消费者，保留这一轮真实失败；combined + UTF-8 消费者 + v1，保留 Crowley 原 query 的 miss 和连带锚点失败。对照使用原字节/查询/预期，不回写旧记录。
4. **v2 必需项**：combined + UTF-8 消费者 + v2，18/18 必须按原逐项操作预期通过，原件公开读回与输入 SHA 完全一致；两个 FB2 query 的 UTF-8 字节、find 与锚点必须真实通过，Crowley 使用新连续 query 重新完成 find/anchor/reopen。不能把不同字体下页数差异当作预设相等，也不能把 CBZ 无文本的原声明改成文字查找通过。

每项命令保留 timeout/exit/raw stdout/stderr，不能把无法打开文件当成格式拒绝。本包安装后 F5 消费者、RTF/CBZ probe、argv 适配测试程序和 SDK 库/DSO 的实际文件一并上传，附字节、SHA-256、加载/依赖输出、工具链、两个 SDK tree、两 patch、consumer、manifest 与 18 输入的身份；native 全集保留完整测试清单、原日志和 JUnit。

### strict

- 通过 GitHub API 检查本轮确切 attempt 的全部必需 job 名称/来源/终态；任一端或必需部分缺失就 pending/failed，不跨轮拼接。
- 实际下载本轮全部原 ZIP，核 source/run/attempt、字节、digest、expiry，再校验原始安全且唯一的 ZIP 成员、限额和实际程序/库字节，不能仅相信 summary 中的 hash 或 accepted 字段。
- 核两个平台的 source、base/combined SDK tree、补丁、v2 LF manifest 与 18 输入集合/散列完全一致；程序/库 hash 按平台认证，不要求 Windows 与 Linux 的二进制 hash 相同。
- 从原始 JUnit、完整具名记录与每文件 F5 原输出计算结论：两端 baseline/combined 原 169 全通过、C04/S13 必需检查全过、v2 18/18 且每项原预期精确满足。v1 结果分列保留，不继承或重写旧 F5。
- 报告 `candidate_package_accepted`、`f5_v2_accepted`、`sdk_adopted:false`、`host_integration_accepted:false`、`complete_product:false`、`legacy_1710_count:0`。不发 tag/Release，不直接推批准 SDK 或主线。

## 6. 审阅后执行顺序

root 审阅本方案后再建立独立组合功能分支和具体清单/适配/裁判；先跑轻量云端协议与参数拒绝回归，再显式 dispatch 完整 Windows/Linux 图。建议上限三轮完整组合 CI；修改源代码后整轮重执行，保留所有失败，不通过放宽预算、减少断言或跨 attempt 拼接解决失败。

所有构建、语法、夹具、测量、原件和工件下载/解压/处理只在 Actions。本轮只提交该方案文档。
