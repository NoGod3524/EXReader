# J06：书内外链与打开动作策略

**可立即独立开工 · P1 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-external-link-policy`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

实现小型独立策略包，把书内目标与需宿主处理的外部目标分开，返回显式动作与原始展示文本，绝不自动执行。

依赖只读：公开 SDK 的 resource/navigation 输出；无网络依赖。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

默认拒绝 javascript/data/可执行 shell、坏转义和控制字符；HTTPS/http/mailto 等由明确 allowlist 判定为 NEEDS_HOST。书内片段、CFI、容器路径继续交公开 SDK，不能自行猜章。策略句柄不使用全局可变状态。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `apps/reader/link-policy/**`
- `tests/reader_external_link_policy/**`
- `.github/workflows/reader-external-link-policy.yml`
- `docs/READER-EXTERNAL-LINK-POLICY.md`
- `docs/validation/reader-external-link-policy.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

C/C++ 安装消费者，Unicode、混合大小写 scheme、userinfo、协议相对路径、编码分隔符、重复转义、路径越界、超长输入、输出寿命与内存失败；证明没有网络/进程启动。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不修改 F2 导航模块，不新造 URL/书籍解析器，不新增插件框架或浏览器。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

