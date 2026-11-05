# J23：应用模块公开边界故障与模糊回归

**可立即独立开工 · P1 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-app-boundary-fuzz`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

在独立消费者上对应用边界做有界 fuzz/分配故障回归，重点覆盖设置文件、reading wire、pending intent与公开字符串边界。

依赖只读：安装后的 preferences、reading-state、revisions、metadata 等现有公开API。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

不重写 SDK 已有 fuzz；基于真实合法种子变异，拒绝把任何非零退出都当通过。发现缺陷保留最小输入/完整调用栈，明确原模块 owner修复路径；测试包不偷偷修共享实现。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `tests/reader_app_boundary_fuzz/**`
- `.github/workflows/reader-app-boundary-fuzz.yml`
- `docs/READER-APP-BOUNDARY-FUZZ.md`
- `docs/validation/reader-app-boundary-fuzz.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

Linux Clang ASan/UBSan/LeakSanitizer，固定种子与限时；C ABI异常不逃逸、输出失败不污染、未知版本保持文件、跨进程重开；每个真实崩溃有确定性重放，原断言和预算不改。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

只写新测试/工作流/文档，构建/运行/生成种子都在Actions；不能只运行空目标或以吞崩溃获得绿。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

