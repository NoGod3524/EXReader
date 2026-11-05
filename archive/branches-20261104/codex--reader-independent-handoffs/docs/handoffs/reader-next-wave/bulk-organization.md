# J10：书架批量整理命令

**可立即独立开工 · P0 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-bulk-organization`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

提供多选书籍的收藏、加入/移出子书架/标签/系列等批量命令；调用者显式选择动作，包分批在产品 owner 上执行现有 typed commands。

依赖只读：reader_commands.h；reader_metadata.h；产品 catalog 公开查询。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

一项一事务，逐项报告 committed/created/conflict；不得宣称整批原子。每项保留完整 observed heads 和稳定重试 ID；取消不回滚已提交项。若需恢复日志，独立私有 sidecar 原子写入，不改 schema/wire。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `apps/reader/bulk-organization/**`
- `tests/reader_bulk_organization/**`
- `.github/workflows/reader-bulk-organization.yml`
- `docs/READER-BULK-ORGANIZATION.md`
- `docs/validation/reader-bulk-organization.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

三平台 2202 书、每批不超过100；中途冲突/删除依赖/重复重试、提交前后真实终止、取消、重开恢复、失败写日志；独立核对 metadata/history/outbox 和未选中书不变。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不修改 catalog/commands/revisions，不直接写产品 SQL、SDK 库或现有宿主批量选择 UI。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

