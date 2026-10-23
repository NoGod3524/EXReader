# R6：阅读SDK门禁与发布接线

起点`9bd2b2c3caf1f63dc4437e0af978247494e87145`；既有SDK冻结与四宿主结果保留在
[冻结记录](R5-SDK-FREEZE.md)。R6接线不改变公开API；集成分支同时纳入R2/R4已验证的核心修复，须重新冻结SDK。

## 候选封装

复用`reading-core.yml`两个Linux preset的构建与安装，在同一个stage执行现有严格许可检查，
并通过独立安装消费者核对SDK运行库版本/ABI与头文件；library额外使用公共API创建书库，
读取该库的实际application_id/schema7。消费者不链接源码树内部目标。

`tools/reading_release.py`核对profile/许可/九格式smoke的同源码结果、全部安装消费、
安装文件与组成清单的逐文件身份，输出带完整source/run/attempt、实际版本与逐文件SHA-256的
tar.gz和清单。归档包含隐含文件；拒绝symlink、越界、已有输出和安装后变更。
相同输入、身份和源码时间生成相同归档。候选不创建tag或发布：`published=false`、`quality_accepted=false`。

`.github/workflows/reading-release-candidate.yml`先执行封装正反例，再复用实际构建。
合成自验fixture只验证判定代码，不能替代真实安装消费。

## 后续接线

默认分支总门禁已在候选分支接入原生正确性/sanitizer、阅读profiles、平台组成检查及R2/R3固定语料/预算。
R2/R3报告必须绑定同source/run/attempt及冻结清单/测量契约/预算身份；诊断或缺证据不能变成发布通过。
原生七个检查不由Linux profile替代。R4改变核心后由集成人重新验证并冻结SDK。

GitHub默认分支当前`codex/framework`、rulesets仍未启用；About已更新为原生多格式/自有PDF/无WebView和MIT核心、可选依赖分别许可的说明，并云端读回。
本包会先固定实际产生的check名及可审阅规则，再启用门禁并读取云端配置确认。
发布动作与候选封装分开；最终产物只能使用已接受源码、固定版本及同次工件，回退指向原有不可变版本，
不覆盖旧tag、工件或失败。当前尚未授予R6整体完成。

## 当前云端接线与冻结影响

候选封装源码`65c968d65eaf274367bd645fd479a983f5a538a4`的run `39887578472`
三个作业全部成功，封装协议32项通过；两个实际安装SDK分别封装235/238个文件。
纯文档后继`99a7b3d7967c0b0888de2d4106e33cbdd3069027`的run `39887835489`也成功。
它们仍是`quality_accepted=false`的候选，不是产品或发布验收。

总门禁源码`76eb39d768559692825b1ee2ac1bab16abc3d10d`的run `39890734935`
实际启动17个作业：protocol 1、原生7、Linux profiles 2、Windows/macOS profiles 4、R2 1、R3 1、最终汇总1。
协议作业已确认封装32项及总门禁元数据37项通过。R3因尚无冻结预算按设计失败；
真实文档仍有开放缺陷，因此本轮不得授予总门禁通过。

`reading-required`始终执行，即使上游失败、跳过或取消；严格汇总拒绝这些状态，
核对八份报告工件的同source/run/attempt、有效digest、非空和未过期，再检查封装、许可、
平台拒绝回归、R2完整声明，以及R3冻结预算和原始证据。下载和重新审计均只发生在云端。
报告保留`published=false`、`complete_product=false`及零WP16信用。

后继门禁进一步核对当前attempt精确17个作业及十份必需native工件；不接受部分重跑沿用的旧native成功。
`fdf93b8`的run `39892685541`三作业成功，封装32项、门禁55项协议通过。
PR合并提交与GitHub运行元数据的分支头分别绑定，避免混淆实际受测源码。
run `39892833007`只读观察真实`reading-required`检查，确认发布者为GitHub Actions、integration ID 15368；
预备规则已绑定该发布者，仍为disabled，尚未修改仓库规则。
许可/平台拒绝报告新增同run/attempt与原报告散列绑定，R2聚合重核逐项原始附件，R3预算重核固定基线ZIP内的原报告。
这些后继接口仍需在最终共同源码完整验收，不因协议自验单独授予发布通过。

为复用原生七作业，`native.yml`仅增加`workflow_call`入口，原步骤不变。
该文件属于保护树，因此新SDK冻结必须纳入这一变化及后续核心修复；不能继续转授旧K的结果。
当前默认分支尚未安装本工作流，分支规则也尚未启用。
