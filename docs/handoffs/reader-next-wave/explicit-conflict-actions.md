# J11：显式冲突选择与合并命令

**可立即独立开工 · P0 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-explicit-conflict-actions`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

把完整并发头集合做成独立有界快照，接受用户明确提供的 metadata 字段与操作，使用现有命令创建有全部 observed heads 的新修订。

依赖只读：reader_revisions.h；reader_commands.h；reader_metadata.h。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

不按时钟选胜者、不自动丢头；准备与提交间头集合变化必须冲突。书籍、分组、成员关系的墓碑/恢复分别处理；阅读锚点冲突仅展示/交宿主，不在本包自动 resolve 或导航。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `apps/reader/conflict-actions/**`
- `tests/reader_explicit_conflict_actions/**`
- `.github/workflows/reader-explicit-conflict-actions.yml`
- `docs/READER-EXPLICIT-CONFLICT-ACTIONS.md`
- `docs/validation/reader-explicit-conflict-actions.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

Windows/Linux/macOS 真正两端并发、缺父后补、墓碑后 put/显式 restore、头数上限、准备后外来修订、重试、取消与事务失败；核对原历史保留且无 SDK notes/原书改动。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不自写第二套 wire 解析器；展示保留的 validated wire/现有 typed 快照，缺少公共接口时交具体 gap，不越权改共享模块或静默缩范围。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

