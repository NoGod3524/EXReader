# J24：Unix 可重定位分发准备

**可立即独立开工 · P1 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-distribution-unix`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

在新候选分发流程里解决 Linux/macOS 构建路径、上游pkg-config绝对prefix和重复归档材料；源保护树完全不改。

依赖只读：固定SDK reading presets与已安装材料；tools/check_reading_licenses.py。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

通过外置构建参数/独立新stage处理，保持原Release优化和数值预算；只对新候选输出取证。不得改写R6已验六原包或冒用其散列、性能结果；不得删除许可/notice或改坏导出目标。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `tests/reader_distribution_unix/**`
- `.github/workflows/reader-distribution-unix.yml`
- `docs/READER-DISTRIBUTION-UNIX.md`
- `docs/validation/reader-distribution-unix.json`
- `tools/reader_distribution_unix/**`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

两平台从新安装前缀搬到另一目录后，公开C/C++消费者和全部原9格式smoke实际运行；归档/pc/config/文档字节扫描、库依赖/许可/相对路径核对，重复副本移除前后链接验证；不能解决的路径仍release_ready=false。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

新工具仅 tools/reader_distribution_unix/**，其余只本包 tests/workflow/docs；不触碰顶层CMake、vendor、SDK或现有发布流程，不创建tag/Release。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

