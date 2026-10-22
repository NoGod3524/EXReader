# 原生阅读核心：首轮启动

基线是已联合验收的 S=`686ce2fe6c3463ef1b917569677ee9933e22faa9`。
本轮在 `codex/r1-reading-core` 追加配置、消费者与工具，不修改引擎、公开头、原默认构建或既有工作流。

## Linux 首轮验证通过

受测源码 `54d8c592ed4f48e2f5ddb7811de213c95e41243c`，
run [39853356309](https://github.com/NoGod3524/EXReader/actions/runs/39853356309)，attempt 1，2/2 作业成功。
已通过 GitHub 连接核对完整作业与工件元数据、完成日志；未下载工件或在本地执行测试。

| profile | job | 安装消费者 | 九格式 smoke | 库归档合计（字节） |
| --- | --- | ---: | ---: | ---: |
| reading-core | 120085073300 | 3/3 | 9/9 | 14513374 |
| reading-library | 120085072747 | 4/4 | 9/9 | 16377198 |

两作业均通过组件/依赖判定及 7 项拒绝自验、测量工具 26 项拒绝自验，
各完成三次独立进程的 1 MiB TXT/32 次翻页采样，采样汇总 accepted。
实际 check 名为 `reading (reading-core)`、`reading (reading-library)`；尚未设为默认分支必需检查。
库归档大小包括该配置安装的 SDK 与供应商静态库，不等于最终消费者可执行大小或整个安装包大小。

| 工件 | ID | 压缩字节 | SHA-256 |
| --- | --- | ---: | --- |
| reading-reading-core-39853356309-1 | 12458347102 | 6358103 | `0966d0e3fa791d7ff4108b27c5f38f9f6275adb291ef86c83e8d53633590c041` |
| reading-reading-library-39853356309-1 | 12458216936 | 7159580 | `d969e6629fbbb6301721510d5f3db314bda0ddf2917aa696141ca958bc7c81d7` |

两工件同 run/source、非空、未过期且 digest 有效。包含安装 SDK、逐文件身份/大小与组成、
消费者日志、逐格式结果、原始测量及汇总。验收范围仅为 Linux 两配置与合成初始采样；
PDF/随机跳页性能基线、真实 EPUB/PDF 故障、跨平台 profile、硬预算及发布保护仍待完成。

## 当前执行范围

- R1：新增 `reading-core`（多格式/PDF）与 `reading-library`（增加书库）两个静态 SDK preset。
  关闭音频、索引、PDF 编辑、旧共享总库、JNI 和 SDK 工具；保留 ICC、PDF 密码认证及全部现有图像开关。
  新增配置的安装后 C 消费者、C++ 头编译及九格式 smoke 在 GitHub Linux 执行。
- R2：冻结九格式原创 fixture 清单；它是小型回归，不计入真实文档 0/1710。
  见 [语料准备](READING-CORPUS.md)。后续实际 EPUB/PDF 失败仍须逐份登记并修复。
- R3：从安装 SDK 构建现有 benchmark，做 1 MiB TXT 首屏/32 次翻页、三次新进程采样。
  保留失败与原件，尚不授予 PDF/随机访问基线或任何硬性能预算，见 [测量口径](READING-PERFORMANCE.md)。
- R6：核对默认分支门槛并完成 [最小门禁映射](READING-CORE-GATE.md)；尚未启用仓库保护或自动发布。
- R5：并行梳理原生宿主接入，先冻结 SDK 书库来源与位置契约，再选择首个平台。
- R4：等待可复现的性能热点，不提前重写引擎。

## 云端命令

`.github/workflows/reading-core.yml` 对两个 preset 分别配置、构建、安装、运行消费者、smoke、
判定工具的拒绝自验与初始测量，并保存 source/run/attempt 命名工件。
首轮完成后登记实际 run、check 名和结果；未通过则保留失败并修复，不预先填通过状态。

首轮源码 `61aa183fb037df66e5c078a5c30111a240cd3b40`，run `39852907619`：
两个 profile 的构建、安装、消费者、组件判定与九格式 smoke 均成功，
测量工具自验因 mock 误拦截平台信息查询而失败，实际性能采样未执行。
后续修复仅收窄自验 mock 的命令匹配范围，未放宽失败判定；必须在新源码云端重验。

本地只读写源码/文档及操作 Git；不执行编译、测试、语料生成、benchmark 或工件解析。
新配置的结果只绑定其受测源码，不继承 S 的联合验收或旧源码长测额度。

## 后续分工

主线处理构建契约、性能采样判定、书库有界来源及进度/标注语义。
独立的 Windows/macOS 构建验证和文档同步另交 handoff；不同时修改同一工作树或核心源码。
两份可直接交出的任务见 [handoff 索引](handoffs/reading-simple-index.md)。
