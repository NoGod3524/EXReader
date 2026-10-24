# J18：Android 系统 TextToSpeech 适配

**可立即独立开工 · P2 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-tts-android`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

独立 Android library 接入系统朗读，使用明确 request/utterance 身份提供声音选择、开始/停止/重试和生命周期。

依赖只读：Android TextToSpeech 与 UtteranceProgressListener；无 SDK 依赖。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

同时遵守[冻结TTS接口](tts-contract.md)，四个实现不互相等待或修改共同契约。

初始化/engine缺失/语言不支持明确上报；宿主提供文本，拒绝自动安装下载引擎；shutdown后拒绝新请求并抑制旧回调。回调不直接碰 SDK/UI owner。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `extras/reader-tts-android/**`
- `tests/reader_tts_android/**`
- `.github/workflows/reader-tts-android.yml`
- `docs/READER-TTS-ANDROID.md`
- `docs/validation/reader-tts-android.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

API26 编译、API34 emulator真实 engine 可用性与 synthesizeToFile；实际可用声音时验证音频文件与回调，缺 engine 路径也真实覆盖；旋转/关闭/终止、取消、长文本有界分块。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不改现有 Android 工程和 SDK 音频选项；模拟后端只能做负例，不授予真实朗读。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

