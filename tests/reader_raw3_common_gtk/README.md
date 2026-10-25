# 共同源码 GTK 完整原链投影

固定共同基线：`1a6d98ed613c61ffea4267f01f83e2c49b1c02f6`。
GTK 已封存叶子：`69c60ace09f7f995e92c55494b1bdf80e6474621`，其受测 source 为
`1cf5ab55b6a92c471af69a8e68b0e9d0c5e3fe6e`、完整 run 为 `40224308783/1`。
本包只新增当前目录的五个文件与一个工作流，既有文件逐 Git blob、类型、模式保护。
当前没有新云端运行，也没有新增运行验收；本地未执行语法、测试、构建或工件解析。

新工作流逐字还原已封存 `reader-gtk-raw3.yml`。允许的替换只有工作流名、分支、两处新 source guard、
三处 retained 入口、一处 raw strict 入口，以及移除一项新增云端语法/拒绝负例后即可完全还原。
原 35 实际 producer 步骤、31 authored OFF 步骤、原 compact45、raw45、actual owner/Mac 网络/NULL、
全部旧裁判、工件路径、原失败记录、预算和超时均保留，七作业拓扑不变。

`guard.py` 是新检查，既不调用被替代的旧 GTK source guard main，也不改写任何 Actions source 环境变量。
它检查真实 `HEAD == GITHUB_SHA`、固定基线祖先、全部旧 blob/mode、精确新增文件集合、工作区、
GTK69 的 Linux owner/CMake/codec/旧工作流/套件 pin、冻结 SDK 和八个已封存 raw 家族，
并逐字验证工作流投影。共同源码可包含基线已审查的其他平台与 WebDAV 修复，不能将这些树假装成 GTK 旧生产 pin。

原裁判依赖的两个输出文件名保留，但报告显式使用 `guard_kind=raw3-common-gtk-v1`、
`old_guard_executed=false`、真实 `composition_source` 和 `runtime_accepted=false`。
`accepted=true` 在这两份报告中仅表示新 source gate 通过。严格包装先验证新 kind、真实 Git/Actions 身份、
基线树与完整投影，再调用全部原导航和兼容性裁判；旧 host/SDK 固定哈希、真实进程/请求/像素负例断言不动。
导航裁判的生产 base 明确设置为真实共同基线。旧严格入口的实际 WORKFLOW 路径通过加载模块变量适配；
保留原已封存 loader 对更早 OFF 裁判的实际路径适配，没有生成虚假的旧 guard 成功文件。
两个原 strict 输出与最终 raw 输出均额外绑定新 guard kind；适配验证失败会改为 `accepted=false` 并失败退出。
Pillow 相关导航合同只在原 OFF 图片认证作业内加载。

合入共同源码前的源审查方案：

1. 核对相对固定基线只有上述六个新文件，原 SDK、owner、旧 guards、套件和预算没有差异。
2. 人工核对工作流 diff 仅含列明的入口/名称替换和新增 preflight step；云端再做逐字逆投影。
3. 核对新兼容报告明确标记新 kind，两个旧合同的全部断言仍完整调用，固定旧 host/SDK 常量没有覆盖。
4. 云端先做新 guard 负例：拒绝旧 kind、错误 Actions 身份、伪称旧 guard 已执行、运行授权、错误基线、
   blob/mode/新增文件变更、裁判缺失、缩短时间和隐藏工件丢失。
5. root 组合其他叶子时仍以真实固定共同基线保护全部旧树；由新的统一 adapter 精确加入已审查包装路径，
   本叶子不提前放宽任何额外路径。所有 source 与 strict 入口必须采用同一实际新允许集合。
6. root 选定单一最终 source 后才启动完整七作业：新 source gate、原完整链、原 OFF strict、
   原 compact strict、raw actual owners/网络/compact45，以及最终严格认证；历史诊断显式 skipped。

授予范围只可能是共同 source 的 GTK 叶子。完整产品、性能、真机、读屏和六平台互通仍不由本包授予。
