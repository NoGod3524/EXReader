# J12：同步、待处理与错误状态只读模型

**可立即独立开工 · P1 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-sync-status-view`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

为宿主低频同步面板提供拥有独立寿命的状态快照和有界待处理列表，复用真实 session/revision 状态。

依赖只读：reader_session.h；reader_revisions.h 的 outbox/heads 公开接口。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

分清操作次数与不同记录数、完整 sweep 与“全书库完成”；保留取消/关闭/需凭据/待 metadata/待原件/冲突状态。只输出固定安全原因，不带 URL、Authorization、服务端正文或原文引用。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `apps/reader/sync-status-view/**`
- `tests/reader_sync_status_view/**`
- `.github/workflows/reader-sync-status-view.yml`
- `docs/READER-SYNC-STATUS-VIEW.md`
- `docs/validation/reader-sync-status-view.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

三平台真实 TLS session 的所有状态转移、256分片、部分提交、离线/401/重试/取消/关闭，outbox分页与重入；秘密扫描、快照寿命、计数与原 report 独立核对，存储不变。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不新增线程、自动重试、同步后端、日志数据库或宿主面板。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

