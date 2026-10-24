# J02：OPDS 浏览、搜索与获取适配

**可立即独立开工 · P1 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-opds-browser`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

在现有 OPDS 模块上提供可分页展示的目录/搜索/获取适配，复用其 feed、facet、OpenSearch、获取和宿主 transport 机制。

依赖只读：extras/opds/include/opds.h；extras/sideload/include/exr_sideload.h。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

快照复制所有展示字段；分页游标绑定 feed 身份；禁止把 buy/borrow/DRM 当免费获取。下载后的真实文件仅经公开侧载验证，网络和 SDK owner 分阶段。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `apps/reader/opds-browser/**`
- `tests/reader_opds_browser/**`
- `.github/workflows/reader-opds-browser.yml`
- `docs/READER-OPDS-BROWSER.md`
- `docs/validation/reader-opds-browser.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

Linux/Windows/macOS 安装后消费者；真实本地 HTTP/TLS transport，OPDS1/2、分页循环、facet、非 ASCII、跨源鉴权隔离、取消、伪扩展、损坏书、重复获取；已有限额不放宽。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不改 extras/opds，不自建 feed 解析器、商业支付或 DRM。传输缺能力必须明确 NEEDS_HOST，不能写空壳宣称完成。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

