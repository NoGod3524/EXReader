# 原生阅读核心：首轮启动

基线是已联合验收的 S=`686ce2fe6c3463ef1b917569677ee9933e22faa9`。
本轮在 `codex/r1-reading-core` 追加配置、消费者与工具，不修改引擎、公开头、原默认构建或既有工作流。

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

本地只读写源码/文档及操作 Git；不执行编译、测试、语料生成、benchmark 或工件解析。
新配置的结果只绑定其受测源码，不继承 S 的联合验收或旧源码长测额度。

## 后续分工

主线处理构建契约、性能采样判定、书库有界来源及进度/标注语义。
独立的 Windows/macOS 构建验证和文档同步另交 handoff；不同时修改同一工作树或核心源码。
