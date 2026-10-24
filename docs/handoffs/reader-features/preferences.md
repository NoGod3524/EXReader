# F3：阅读设置

先读[共同约束](README.md)，从固定起点创建`codex/reader-preferences`。
目标是统一可携带、可校验的阅读外观设置，供四套原生壳以后接入。

## 文件归属

仅新增`apps/reader/preferences/**`、`tests/reader_preferences/**`、
`.github/workflows/reader-preferences.yml`、`docs/READER-PREFERENCES.md`、
`docs/validation/reader-preferences.json`。

## 交付契约

- 可选安装包`EXReaderPreferences 0.1.0`，公开C ABI`reader_preferences.h`。
  字号、行距、段距、页边距、浅色/深色/跟随系统、阅读前景/背景、翻页方向/操作偏好。
  给出与现有SDK布局参数的对应表，区分重排可用项和固定页缩放；不直接重排或绘制UI。
- 默认值和合法区间从当前SDK/宿主约束整理，逐字段写入文档；不改任何宿主现有默认。
  拒绝NaN/Inf、越界、非法枚举、损坏文本、过大文件与不支持的格式版本。
- 设置为设备本地数据，不新增同步wire实体，不写产品schema或SDK表。
  使用调用者给出的app私有独立文件；不改现有宿主profile文件。
  提供宿主传入旧设置后显式导入的API，不能静默重置未知宿主配置。
- load/save/validate/defaults分清，输出所有权和错误状态明确。
  失败的load保留调用者已有设置；save用同目录临时文件+刷新+原子替换，
  错误/取消保留上次有效文件，真实重开可回读。未知版本保留原文件。
- 单调用者worker串行使用；不加后台watcher、远端配置、云服务、通用插件系统或新数据库。
  功能接口与平台主题通知分离，跟随系统由宿主传入当前状态。

## 云端出口

Windows/Linux/macOS安装后C/C++消费者，同源三平台实际文件往返。
覆盖默认值、每字段边界、Unicode路径、跨进程重开、损坏/截断/未知版本、
原子替换失败、取消、两个调用者的明确并发策略和真实终止后的旧值/新值完整性。
检查产品库、SDK库及既有宿主设置逐字未变。不能把配置模块通过写成主题UI或读屏验收。
