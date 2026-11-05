# J17：macOS／iPhone／iPad 原生朗读适配

**可立即独立开工 · P2 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-tts-apple`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

独立可选 Apple 原生朗读组件，提供声音选择、速度、暂停/继续/停止和带请求身份的生命周期通知。

依赖只读：AVFoundation AVSpeechSynthesizer；调用者提供文本块。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

同时遵守[冻结TTS接口](tts-contract.md)，四个实现不互相等待或修改共同契约。

不读取书籍或持有 SDK；原生主线程/音频会话边界明确，后台策略由宿主决定。旧请求回调不能误归新页；禁止自动下载语音或接云端 TTS。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `extras/reader-tts-apple/**`
- `tests/reader_tts_apple/**`
- `.github/workflows/reader-tts-apple.yml`
- `docs/READER-TTS-APPLE.md`
- `docs/validation/reader-tts-apple.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

macOS 与 iPhone/iPad simulator 独立 probe；实际系统语音回调、可用时真实 PCM/WAV 输出、中文/emoji、取消/重入、队列替换、后台/销毁；没有实际声音的目标标pending，不能只以 API 调用成功授予。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不改 Host*.swift、签名、SDK/默认音频构建；物理设备与听感分别登记。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

