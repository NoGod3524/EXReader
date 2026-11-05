# J19：Linux 原生 Speech Dispatcher 朗读适配

**可立即独立开工 · P2 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-tts-linux`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

新增独立可选 Linux 朗读适配，复用系统语音服务，提供列声音、说话、暂停/继续/停止及明确不可用状态。

依赖只读：系统 libspeechd/Speech Dispatcher；无 SDK 依赖。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

同时遵守[冻结TTS接口](tts-contract.md)，四个实现不互相等待或修改共同契约。

不自带新的 TTS引擎或服务器；严格 owner/回调生命周期，daemon消失可恢复，错误内容不泄漏原文。系统依赖与随包材料分开。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `extras/reader-tts-linux/**`
- `tests/reader_tts_linux/**`
- `.github/workflows/reader-tts-linux.yml`
- `docs/READER-TTS-LINUX.md`
- `docs/validation/reader-tts-linux.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

Ubuntu Actions 临时真实 Speech Dispatcher 与已有本机语音后端；实际发声/文件输出可观测则记录，daemon缺失/断开/取消/重开/Unicode/长文本/回调迟到；ASan/UBSan及许可材料。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不改 GTK 宿主或默认reading依赖；只证明连接/回调时不可宣称音频或听感通过。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

